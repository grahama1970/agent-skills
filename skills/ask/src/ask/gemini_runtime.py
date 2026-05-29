"""Gemini oracle backend.

Routes /ask oracle calls through `surf gemini.submit --no-activate`, which
controls an already-authenticated Gemini tab in the user's Chrome via the
surf-cli extension. The tab is never foregrounded; Gemini's conversation
state is preserved on the tab so iterative calls form a coherent dialogue.

Contract:
- A controlled Gemini tab id is required. If neither tab_id nor url is given,
  we try to auto-resolve by listing gemini.google.com tabs via `surf tab.list`;
  we refuse to proceed (with a clear instruction) if 0 or >1 candidates
  exist. We never silently pick.
- `surf gemini.submit --no-activate` enforces the sentinel proof contract:
  raw_contains_sentinel, clean_contains_sentinel=false, controlled_tab_id
  matches requested_tab_id, focus_changed=false.
- File paths embedded in the prompt are auto-attached so the human doesn't
  have to paste large bundles by hand.

Self-correction:
- The `BackendHealth` module tracks success/failure patterns per backend.
- If Gemini's DOM structure changes (e.g., textbox ref detection fails,
  sentinel stops appearing, stable polling never completes), health degrades.
- Degraded backends raise clear errors suggesting re-assessment.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ask_config import SURF_RUN, GEMINI_DEFAULT_TIMEOUT, GEMINI_STABLE_POLLS


@dataclass(frozen=True)
class GeminiTabResolution:
    tab_id: str
    candidates: list[dict]
    source: str  # "explicit" | "auto" | "none" | "ambiguous"


class GeminiTabError(RuntimeError):
    """Raised when no Gemini tab can be resolved unambiguously."""


class GeminiBackendError(RuntimeError):
    """Raised when surf gemini.submit fails or the proof contract is broken."""


class GeminiBackendDegradedError(GeminiBackendError):
    """Raised when repeated failures suggest the provider DOM/bot detection
    has changed and the backend needs re-assessment."""


def _surf_run_path() -> Path:
    return Path(SURF_RUN)


def resolve_gemini_tab(
    explicit_tab_id: str | None,
    explicit_url: str | None,
    *,
    surf_run: Path | None = None,
) -> GeminiTabResolution:
    """Find the controlled Gemini tab.

    Priority:
      1. explicit_tab_id (passed via --gemini-tab-id) — used as-is.
      2. explicit_url — resolved via surf tab.list matching.
      3. auto-resolve via `surf tab.list` filtered to gemini.google.com:
         - exactly 1 candidate → use it
         - 0 or >1 candidates → raise GeminiTabError
    """
    surf = surf_run or _surf_run_path()
    if explicit_tab_id:
        return GeminiTabResolution(
            tab_id=str(explicit_tab_id).strip(),
            candidates=[],
            source="explicit",
        )
    if explicit_url:
        return GeminiTabResolution(
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
        raise GeminiTabError(
            f"surf runtime not found at {surf}. Set ASK_SURF_RUN or install the surf skill."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GeminiTabError(
            f"surf tab.list timed out. Is the surf-cli extension loaded in Chrome? ({exc})"
        ) from exc
    if proc.returncode != 0:
        raise GeminiTabError(
            "surf tab.list failed; cannot auto-resolve a Gemini tab.\n"
            f"exit={proc.returncode} stderr={proc.stderr[-400:]}"
        )
    candidates: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tab_id, title, url = parts[0], parts[1], parts[2]
        if "gemini.google.com" not in url:
            continue
        candidates.append({"id": tab_id, "title": title, "url": url})
    if len(candidates) == 1:
        return GeminiTabResolution(
            tab_id=candidates[0]["id"],
            candidates=candidates,
            source="auto",
        )
    if not candidates:
        raise GeminiTabError(
            "No open Gemini tab to control.\n"
            "Open exactly one gemini.google.com tab in your Chrome (signed in), "
            "then either retry, or pass --gemini-tab-id with the id from the "
            "Tab ID Viewer extension."
        )
    listing = "\n".join(f"  {c['id']}\t{c['title']}\t{c['url']}" for c in candidates)
    raise GeminiTabError(
        "Multiple Gemini tabs are open; refusing to guess.\n"
        "Pass --gemini-tab-id with the id you want to control, "
        "or close all but one gemini.google.com tab and retry.\n"
        f"Candidates:\n{listing}"
    )


_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")


def extract_file_attachments(question: str, *, max_bytes: int = 2_000_000) -> list[dict[str, Any]]:
    """Find file paths referenced in the question and read them.

    Same implementation as webgpt_runtime.extract_file_attachments.
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


def build_gemini_prompt(
    base_prompt: str,
    attachments: list[dict[str, Any]],
    *,
    system_preamble: str | None = None,
) -> str:
    """Compose the prompt to send to Gemini."""
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
class GeminiResult:
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


def call_gemini(
    prompt: str,
    *,
    tab_id: str = "",
    url: str = "",
    timeout: float = GEMINI_DEFAULT_TIMEOUT,
    stable_polls: int = GEMINI_STABLE_POLLS,
    artifact_dir: Path | None = None,
    no_activate: bool = True,
    surf_run: Path | None = None,
    run_state: object | None = None,
    iteration: int | None = None,
    persona: str | None = None,
) -> GeminiResult:
    """One Gemini round trip against the controlled Gemini tab.

    Multi-turn iteration: call this function repeatedly with the same tab_id.
    Gemini preserves conversation context per tab; each call appends a turn.
    """
    surf = surf_run or _surf_run_path()
    if not surf.exists():
        raise GeminiBackendError(f"surf runtime not found: {surf}")

    resolution = resolve_gemini_tab(tab_id, url, surf_run=surf)
    resolved_tab_id = resolution.tab_id

    if artifact_dir is None:
        artifact_dir = Path(tempfile.mkdtemp(prefix="ask-gemini-"))
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "01_request.md"
    response_path = artifact_dir / "02_response.md"
    raw_path = artifact_dir / "02_response.raw.md"
    meta_path = artifact_dir / "02_response.meta.json"
    submitted_path = artifact_dir / "02_response.submitted.md"
    request_path.write_text(prompt)

    command = [
        str(surf), "gemini.submit",
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
        "backend": "webgemini",
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
        run_state.event("oracle_gemini_call_started", **event_payload)

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
                "oracle_gemini_call_failed",
                **event_payload,
                error="subprocess_timeout",
            )
        raise GeminiBackendError(
            f"surf gemini.submit timed out after {timeout + 90:.0f}s"
        ) from exc

    took_ms = int((time.monotonic() - start_t) * 1000)
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}

    if proc.returncode != 0 or meta.get("status") not in ("completed", "done"):
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_gemini_call_failed",
                **event_payload,
                returncode=proc.returncode,
                meta_status=meta.get("status"),
                failure=meta.get("failure"),
                stderr_tail=(proc.stderr or "")[-2000:],
            )
        error_msg = (
            f"surf gemini.submit failed: returncode={proc.returncode} "
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
            raise GeminiBackendDegradedError(
                error_msg + "\n\n"
                "This failure pattern suggests Gemini's site structure or "
                "bot detection may have changed. The gemini backend needs "
                "re-assessment. Consider:\n"
                "  1. Manually verify the Gemini tab is accessible via surf read/click/type\n"
                "  2. Run surf gemini.submit sanity test\n"
                "  3. Check if Gemini has deployed new UI or anti-automation measures\n"
                "  4. Report the failure pattern for backend health tracking"
            )
        raise GeminiBackendError(error_msg)

    response_text = response_path.read_text() if response_path.exists() else ""
    raw_text = raw_path.read_text() if raw_path.exists() else ""

    result = GeminiResult(
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
            "oracle_gemini_call_finished",
            **event_payload,
            controlled_tab_id=result.controlled_tab_id,
            took_ms=took_ms,
            response_chars=len(response_text),
            raw_contains_sentinel=result.raw_contains_sentinel,
            clean_contains_sentinel=result.clean_contains_sentinel,
            focus_changed=result.focus_changed,
        )

    return result
