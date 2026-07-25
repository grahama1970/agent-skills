"""Kimi oracle backend.

Routes /ask oracle calls through `surf kimi.submit --no-activate`, which
controls an already-authenticated Kimi tab in the user's Chrome via the
surf-cli extension. The tab is never foregrounded; Kimi's conversation
state is preserved on the tab so iterative calls form a coherent dialogue.

Contract:
- A controlled Kimi tab id is required. If neither tab_id nor url is given,
  we try to auto-resolve by listing kimi.com tabs via `surf tab.list`;
  we refuse to proceed (with a clear instruction) if 0 or >1 candidates
  exist. We never silently pick.
- `surf kimi.submit --no-activate` enforces the sentinel proof contract:
  raw_contains_sentinel, clean_contains_sentinel=false, controlled_tab_id
  matches requested_tab_id, focus_changed=false.
- File paths embedded in the prompt are auto-attached so the human doesn't
  have to paste large bundles by hand.

Self-correction:
- The `BackendHealth` module tracks success/failure patterns per backend.
- If Kimi's DOM structure changes (e.g., textbox ref detection fails,
  sentinel stops appearing, stable polling never completes), health degrades.
- Degraded backends raise clear errors suggesting re-assessment.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env import load_dotenv_once
from .ask_config import SURF_RUN, KIMI_DEFAULT_TIMEOUT, KIMI_STABLE_POLLS
from .kimi_capacity import KimiCapacityBusyError, is_kimi_capacity_busy

load_dotenv_once()


@dataclass(frozen=True)
class KimiTabResolution:
    tab_id: str
    candidates: list[dict]
    source: str  # "explicit" | "auto" | "none" | "ambiguous"


class KimiTabError(RuntimeError):
    """Raised when no Kimi tab can be resolved unambiguously."""


class KimiBackendError(RuntimeError):
    """Raised when surf kimi.submit fails or the proof contract is broken."""


class KimiBackendDegradedError(KimiBackendError):
    """Raised when repeated failures suggest the provider DOM/bot detection
    has changed and the backend needs re-assessment."""


def _surf_run_path() -> Path:
    return Path(SURF_RUN)


def resolve_kimi_tab(
    explicit_tab_id: str | None,
    explicit_url: str | None,
    *,
    surf_run: Path | None = None,
) -> KimiTabResolution:
    """Find the controlled Kimi tab.

    Priority:
      1. explicit_tab_id (passed via --kimi-tab-id) — used as-is.
      2. explicit_url — resolved via surf tab.list matching.
      3. auto-resolve via `surf tab.list` filtered to kimi.com:
         - exactly 1 candidate → use it
         - 0 or >1 candidates → raise KimiTabError
    """
    surf = surf_run or _surf_run_path()
    if explicit_tab_id:
        return KimiTabResolution(
            tab_id=str(explicit_tab_id).strip(),
            candidates=[],
            source="explicit",
        )
    if explicit_url:
        return KimiTabResolution(
            tab_id="",
            candidates=[],
            source="explicit_url",
        )
    try:
        proc = subprocess.run(
            [str(surf), "tab.list"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=surf.parent,
        )
    except FileNotFoundError as exc:
        raise KimiTabError(
            f"surf runtime not found at {surf}. Set ASK_SURF_RUN or install the surf skill."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise KimiTabError(
            f"surf tab.list timed out. Is the surf-cli extension loaded in Chrome? ({exc})"
        ) from exc
    if proc.returncode != 0:
        raise KimiTabError(
            "surf tab.list failed; cannot auto-resolve a Kimi tab.\n"
            f"exit={proc.returncode} stderr={proc.stderr[-400:]}"
        )
    candidates: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tab_id, title, url = parts[0], parts[1], parts[2]
        if "kimi.com" not in url:
            continue
        if "/chat" not in url and "/agent" not in url:
            continue
        candidates.append({"id": tab_id, "title": title, "url": url})
    if len(candidates) == 1:
        return KimiTabResolution(
            tab_id=candidates[0]["id"],
            candidates=candidates,
            source="auto",
        )
    if not candidates:
        raise KimiTabError(
            "No open Kimi tab to control.\n"
            "Open exactly one kimi.com/chat tab in your Chrome (signed in), "
            "then either retry, or pass --kimi-tab-id with the id from the "
            "Tab ID Viewer extension."
        )
    listing = "\n".join(f"  {c['id']}\t{c['title']}\t{c['url']}" for c in candidates)
    raise KimiTabError(
        "Multiple Kimi tabs are open; refusing to guess.\n"
        "Pass --kimi-tab-id with the id you want to control, "
        "or close all but one kimi.com/chat tab and retry.\n"
        f"Candidates:\n{listing}"
    )


_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")


def extract_file_attachments(question: str, *, max_bytes: int = 2_000_000) -> list[dict[str, Any]]:
    """Find file paths referenced in the question and read them.

    Same attachment policy as browser_review_runtime.extract_file_attachments.
    """
    seen: set[Path] = set()
    out: list[dict[str, Any]] = []
    for match in _PATH_TOKEN_RE.finditer(question):
        token = match.group(1).rstrip(".,;:)>)")
        try:
            p = Path(token).expanduser()
        except Exception:
            continue
        if not p.is_absolute():
            try:
                p = p.resolve(strict=False)
            except Exception:
                continue
        if not p.exists() or not p.is_file():
            continue
        if p in seen:
            continue
        seen.add(p)
        try:
            data = p.read_bytes()
        except Exception as exc:
            out.append({
                "path": str(p),
                "error": f"read failed: {exc}",
                "bytes": 0,
                "truncated": False,
            })
            continue
        truncated = len(data) > max_bytes
        try:
            text = data[:max_bytes].decode("utf-8", errors="replace")
        except Exception:
            text = "<binary content omitted>"
            truncated = True
        out.append({
            "path": str(p),
            "bytes": len(data),
            "truncated": truncated,
            "text": text,
        })
    return out


def build_kimi_prompt(
    base_prompt: str,
    attachments: list[dict[str, Any]],
    *,
    system_preamble: str | None = None,
) -> str:
    """Compose the prompt to send to Kimi."""
    parts: list[str] = []
    if system_preamble:
        parts.append(system_preamble.strip())
        parts.append("")
    parts.append(base_prompt.strip())
    if attachments:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("## Attached files")
        parts.append("")
        for att in attachments:
            parts.append(f"### {att['path']}")
            if "error" in att:
                parts.append(f"_could not read: {att['error']}_")
                parts.append("")
                continue
            if att.get("truncated"):
                parts.append(
                    f"_truncated to {len(att['text']):,} chars (file was {att['bytes']:,} bytes)_"
                )
            parts.append("")
            parts.append("```")
            parts.append(att["text"])
            parts.append("```")
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


@dataclass
class KimiResult:
    response: str
    raw_response: str
    sentinel: str
    controlled_tab_id: str
    requested_tab_id: str
    requested_url: str
    raw_contains_sentinel: bool
    clean_contains_sentinel: bool
    no_activate: bool
    focus_changed: bool | None
    meta: dict[str, Any]
    artifact_dir: Path
    took_ms: int


def call_kimi(
    prompt: str,
    *,
    tab_id: str = "",
    url: str = "",
    timeout: float = KIMI_DEFAULT_TIMEOUT,
    stable_polls: int = KIMI_STABLE_POLLS,
    artifact_dir: Path | None = None,
    no_activate: bool = True,
    surf_run: Path | None = None,
    run_state: object | None = None,
    iteration: int | None = None,
    persona: str | None = None,
) -> KimiResult:
    """One Kimi round trip against the controlled Kimi tab.

    Multi-turn iteration: call this function repeatedly with the same tab_id.
    Kimi preserves conversation context per tab; each call appends a turn.
    """
    surf = surf_run or _surf_run_path()
    if not surf.exists():
        raise KimiBackendError(f"surf runtime not found: {surf}")

    resolution = resolve_kimi_tab(tab_id, url, surf_run=surf)
    resolved_tab_id = resolution.tab_id

    if artifact_dir is None:
        artifact_dir = Path(tempfile.mkdtemp(prefix="ask-kimi-"))
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "01_request.md"
    response_path = artifact_dir / "02_response.md"
    raw_path = artifact_dir / "02_response.raw.md"
    meta_path = artifact_dir / "02_response.meta.json"
    submitted_path = artifact_dir / "02_response.submitted.md"
    request_path.write_text(prompt)

    command = [
        str(surf), "kimi.submit",
        "--input", str(request_path),
        "--output", str(response_path),
        "--raw-output", str(raw_path),
        "--meta-output", str(meta_path),
        "--submitted-output", str(submitted_path),
        "--timeout", str(int(timeout)),
        "--stable-polls", str(int(stable_polls)),
        "--tab-id", resolved_tab_id,
    ]
    if no_activate:
        command.append("--no-activate")

    event_payload = {
        "backend": "webkimi",
        "tab_id": resolved_tab_id,
        "url": url or None,
        "no_activate": no_activate,
        "timeout_seconds": float(timeout),
        "artifact_dir": str(artifact_dir),
    }
    if iteration is not None:
        event_payload["iteration"] = iteration
    if persona:
        event_payload["persona"] = persona
    if run_state is not None and hasattr(run_state, "event"):
        run_state.event("oracle_kimi_call_started", **event_payload)

    start_t = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 90,
            cwd=surf.parent,
        )
    except subprocess.TimeoutExpired as exc:
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_kimi_call_failed",
                **event_payload,
                error="subprocess_timeout",
            )
        raise KimiBackendError(
            f"surf kimi.submit timed out after {timeout + 90:.0f}s"
        ) from exc

    took_ms = int((time.monotonic() - start_t) * 1000)
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}

    meta_status = str(meta.get("status") or "")
    if meta_status == "capacity_busy" or meta.get("failure") == "kimi_capacity_busy":
        excerpt = response_path.read_text() if response_path.exists() else ""
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_kimi_call_failed",
                **event_payload,
                error="kimi_capacity_busy",
                meta_status=meta_status,
            )
        raise KimiCapacityBusyError(response_excerpt=excerpt)

    if proc.returncode != 0 or meta_status not in ("completed", "done"):
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_kimi_call_failed",
                **event_payload,
                returncode=proc.returncode,
                meta_status=meta.get("status"),
                failure=meta.get("failure"),
                stderr_tail=(proc.stderr or "")[-2000:],
            )
        error_msg = (
            f"surf kimi.submit failed: returncode={proc.returncode} "
            f"meta_status={meta.get('status')} failure={meta.get('failure')}\n"
            f"stderr tail: {(proc.stderr or '')[-1000:]}"
        )
        # Detect degradation patterns suggesting DOM/bot-detection changes
        stderr_lower = (proc.stderr or "").lower()
        meta_status = meta.get("status", "")
        if (
            "could not find" in stderr_lower
            or "content script not loaded" in stderr_lower
            or meta_status == "timeout"
            or "sentinel" in str(meta.get("failure", "")).lower()
        ):
            raise KimiBackendDegradedError(
                error_msg + "\n\n"
                "This failure pattern suggests Kimi's site structure or "
                "bot detection may have changed. The kimi backend needs "
                "re-assessment. Consider:\n"
                "  1. Manually verify the Kimi tab is accessible via surf read/click/type\n"
                "  2. Run surf kimi.submit sanity test\n"
                "  3. Check if Kimi has deployed new UI or anti-automation measures\n"
                "  4. Report the failure pattern for backend health tracking"
            )
        raise KimiBackendError(error_msg)

    response_text = response_path.read_text() if response_path.exists() else ""
    raw_text = raw_path.read_text() if raw_path.exists() else ""

    if is_kimi_capacity_busy(response_text) or is_kimi_capacity_busy(raw_text):
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_kimi_call_failed",
                **event_payload,
                error="kimi_capacity_busy",
            )
        raise KimiCapacityBusyError(response_excerpt=response_text or raw_text)

    result = KimiResult(
        response=response_text,
        raw_response=raw_text,
        sentinel=str(meta.get("sentinel", "")),
        controlled_tab_id=str(meta.get("controlled_tab_id", "")),
        requested_tab_id=str(meta.get("requested_tab_id", "") or resolved_tab_id),
        requested_url=str(meta.get("requested_url", "") or url),
        raw_contains_sentinel=bool(meta.get("raw_contains_sentinel")),
        clean_contains_sentinel=bool(meta.get("clean_contains_sentinel")),
        no_activate=bool(meta.get("no_activate")),
        focus_changed=meta.get("focus_changed"),
        meta=meta,
        artifact_dir=artifact_dir,
        took_ms=took_ms,
    )

    if run_state is not None and hasattr(run_state, "event"):
        run_state.event(
            "oracle_kimi_call_finished",
            **event_payload,
            controlled_tab_id=result.controlled_tab_id,
            took_ms=took_ms,
            response_chars=len(response_text),
            raw_contains_sentinel=result.raw_contains_sentinel,
            clean_contains_sentinel=result.clean_contains_sentinel,
            focus_changed=result.focus_changed,
        )

    return result


def call_kimi_with_capacity_retry(
    prompt: str,
    *,
    max_retries: int | None = None,
    backoff_seconds: float | None = None,
    **kwargs: Any,
) -> KimiResult:
    """call_kimi with retries when Kimi reports system/capacity busy."""
    retries = max_retries
    if retries is None:
        retries = int(os.environ.get("ASK_KIMI_CAPACITY_RETRIES", "3"))
    backoff = backoff_seconds
    if backoff is None:
        backoff = float(os.environ.get("ASK_KIMI_CAPACITY_BACKOFF_SEC", "45"))
    last_exc: KimiCapacityBusyError | None = None
    for attempt in range(retries + 1):
        try:
            return call_kimi(prompt, **kwargs)
        except KimiCapacityBusyError as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            if kwargs.get("run_state") is not None and hasattr(kwargs["run_state"], "event"):
                kwargs["run_state"].event(
                    "oracle_kimi_capacity_retry",
                    attempt=attempt + 1,
                    max_retries=retries,
                    backoff_seconds=backoff * (attempt + 1),
                )
            time.sleep(backoff * (attempt + 1))
    assert last_exc is not None
    raise last_exc
