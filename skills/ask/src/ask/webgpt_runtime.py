"""WebGPT oracle backend.

Routes /ask oracle calls through `surf webgpt.submit --no-activate`, which
controls an already-authenticated ChatGPT tab in the user's Chrome via the
surf-cli extension. The tab is never foregrounded; ChatGPT's conversation
state is preserved on the tab so iterative calls form a coherent dialogue.

Contract:
- A controlled ChatGPT tab id is required. If neither tab_id nor url is given,
  we try to auto-resolve by listing chatgpt.com tabs via `surf tab.list`;
  we refuse to proceed (with a clear instruction) if 0 or >1 candidates
  exist. We never silently pick.
- `surf webgpt.submit --no-activate` enforces the sentinel proof contract:
  raw_contains_sentinel, clean_contains_sentinel=false, controlled_tab_id
  matches requested_tab_id, focus_changed=false.
- File paths embedded in the prompt are auto-attached so the human doesn't
  have to paste large bundles by hand.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ask_config import SURF_RUN, WEBGPT_DEFAULT_TIMEOUT, WEBGPT_STABLE_POLLS
from . import webgpt_project
from .webgpt_rate_limit import WebgptRateLimitError, check_and_record


@dataclass(frozen=True)
class WebgptTabResolution:
    tab_id: str
    candidates: list[dict]
    source: str  # "explicit" | "auto" | "none" | "ambiguous"


class WebgptTabError(RuntimeError):
    """Raised when no ChatGPT tab can be resolved unambiguously.

    The message tells the project agent exactly how to recover: ask the human
    to open one ChatGPT tab (the Tab ID Viewer extension shows the id) or to
    pass --webgpt-tab-id explicitly.
    """


class WebgptBackendError(RuntimeError):
    """Raised when surf webgpt.submit fails or the proof contract is broken."""


def _surf_run_path() -> Path:
    return Path(SURF_RUN)


def resolve_chatgpt_tab(
    explicit_tab_id: str | None,
    explicit_url: str | None,
    *,
    surf_run: Path | None = None,
) -> WebgptTabResolution:
    """Find the controlled ChatGPT tab.

    Priority:
      1. explicit_tab_id (passed via --webgpt-tab-id) — used as-is.
      2. explicit_url — `surf webgpt.submit` resolves it; we just record it.
      3. auto-resolve via `surf tab.list` filtered to chatgpt.com:
         - exactly 1 candidate → use it
         - 0 or >1 candidates → raise WebgptTabError
    """
    surf = surf_run or _surf_run_path()
    if explicit_tab_id:
        return WebgptTabResolution(
            tab_id=str(explicit_tab_id).strip(),
            candidates=[],
            source="explicit",
        )
    if explicit_url:
        return WebgptTabResolution(
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
        raise WebgptTabError(
            f"surf runtime not found at {surf}. Set ASK_SURF_RUN or install the surf skill."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise WebgptTabError(
            f"surf tab.list timed out. Is the surf-cli extension loaded in Chrome? ({exc})"
        ) from exc
    if proc.returncode != 0:
        raise WebgptTabError(
            "surf tab.list failed; cannot auto-resolve a ChatGPT tab.\n"
            f"exit={proc.returncode} stderr={proc.stderr[-400:]}"
        )
    candidates: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tab_id, title, url = parts[0], parts[1], parts[2]
        if "chatgpt.com" not in url:
            continue
        candidates.append({"id": tab_id, "title": title, "url": url})
    if len(candidates) == 1:
        return WebgptTabResolution(
            tab_id=candidates[0]["id"],
            candidates=candidates,
            source="auto",
        )
    if not candidates:
        raise WebgptTabError(
            "No open ChatGPT tab to control.\n"
            "Open exactly one chatgpt.com tab in your Chrome (signed in), "
            "then either retry, or pass --webgpt-tab-id with the id from the "
            "Tab ID Viewer extension."
        )
    listing = "\n".join(f"  {c['id']}\t{c['title']}\t{c['url']}" for c in candidates)
    raise WebgptTabError(
        "Multiple ChatGPT tabs are open; refusing to guess.\n"
        "Pass --webgpt-tab-id with the id you want to control, "
        "or close all but one chatgpt.com tab and retry.\n"
        f"Candidates:\n{listing}"
    )


_PATH_TOKEN_RE = re.compile(r"(?:(?:^|\s)|`)((?:~|/|\./|\.\./)[^\s`]+)")

_ARCHIVE_EXTENSIONS = (
    ".zip",
    ".tar",
    ".tgz",
    ".tar.gz",
    ".tar.bz2",
    ".7z",
)


def extract_path_tokens(text: str) -> list[str]:
    """Return unique filesystem path tokens referenced in *text*."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".,;:)>")
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _resolve_path_token(token: str) -> Path | None:
    try:
        path = Path(token).expanduser()
    except Exception:
        return None
    if not path.is_absolute():
        try:
            path = path.resolve(strict=False)
        except Exception:
            return None
    return path


def _is_archive_path(path: Path) -> bool:
    lower = path.name.lower()
    return any(lower.endswith(ext) for ext in _ARCHIVE_EXTENSIONS)


def _attachment_has_text(att: dict[str, Any]) -> bool:
    return bool(att.get("text")) and not att.get("error")



class WebReviewBundleError(WebgptBackendError):
    """Browser reviewer cannot consume path-only evidence bundles."""

    FRIENDLY = (
        "I'm a web-based agent and I can't read local file paths. "
        "Please provide either a zip review bundle of no more than 5 files, "
        "or give me a concatenated text file."
    )

    def __init__(self, *, backend: str = "webgpt", detail: str = "") -> None:
        message = self.FRIENDLY
        if detail:
            message = f"{message}\n\nDetected issue: {detail}"
        super().__init__(message)
        self.backend = backend
        self.detail = detail


def _zip_member_count(path: Path, *, max_files: int = 5) -> tuple[int, str | None]:
    try:
        with zipfile.ZipFile(path) as zf:
            members = [info for info in zf.infolist() if not info.is_dir()]
    except Exception as exc:
        return 0, f"could not read zip archive: {exc}"
    if not members:
        return 0, "zip archive is empty"
    if len(members) > max_files:
        return len(members), f"zip contains {len(members)} files (maximum {max_files})"
    return len(members), None


def resolve_web_review_delivery(
    question: str,
    attachments: list[dict[str, Any]],
    *,
    backend: str = "webgpt",
) -> str:
    """Validate review evidence and return a zip path for --attach-file when used.

    Returns an empty string when evidence is delivered as inlined concatenated text.
    Raises WebReviewBundleError with a project-agent-friendly message when the
    bundle only lists local paths the browser tab cannot read.
    """
    question_refs = extract_path_tokens(question)
    zip_refs = [
        token
        for token in question_refs
        if (p := _resolve_path_token(token)) is not None and _is_archive_path(p)
    ]

    if len(question_refs) == 1 and len(zip_refs) == 1:
        archive = _resolve_path_token(zip_refs[0])
        assert archive is not None
        if not archive.is_file():
            raise WebReviewBundleError(
                backend=backend,
                detail=f"zip path does not exist: {zip_refs[0]}",
            )
        _, zip_err = _zip_member_count(archive)
        if zip_err:
            raise WebReviewBundleError(backend=backend, detail=zip_err)
        if backend != "webgpt":
            raise WebReviewBundleError(
                backend=backend,
                detail=(
                    "zip attach is supported for $ask webgpt only; "
                    "use a concatenated text/markdown file for other web backends"
                ),
            )
        return str(archive)

    _validate_inlined_web_review_evidence(question, attachments, backend=backend)
    return ""


def _validate_inlined_web_review_evidence(
    question: str,
    attachments: list[dict[str, Any]],
    *,
    backend: str = "webgpt",
) -> None:
    """Require concatenated inlined text when not using a zip attach bundle."""
    question_refs = extract_path_tokens(question)
    referenced: list[str] = []
    seen: set[str] = set()
    for source in [question, *(a.get("text", "") for a in attachments if a.get("text"))]:
        for token in extract_path_tokens(source):
            if token not in seen:
                seen.add(token)
                referenced.append(token)

    if not referenced:
        return

    inlined_paths: set[str] = set()
    for att in attachments:
        if not _attachment_has_text(att):
            continue
        raw_path = str(att.get("path", ""))
        inlined_paths.add(raw_path)
        resolved = _resolve_path_token(raw_path)
        if resolved is not None:
            inlined_paths.add(str(resolved))

    details: list[str] = []
    directories: list[str] = []
    missing: list[str] = []
    path_only: list[str] = []
    archives: list[str] = []

    for token in referenced:
        path = _resolve_path_token(token)
        if path is None:
            missing.append(token)
            continue
        if _is_archive_path(path):
            archives.append(token)
            continue
        if path.is_dir():
            directories.append(token)
            continue
        if not path.is_file():
            missing.append(token)
            continue
        if token not in inlined_paths and str(path) not in inlined_paths:
            path_only.append(token)

    if directories:
        details.append(
            "directory paths were referenced (" + ", ".join(directories) + ")"
        )
    if missing:
        details.append(
            "some referenced paths do not exist (" + ", ".join(missing) + ")"
        )
    if path_only:
        details.append(
            "these files were referenced by path only, without inlined content: "
            + ", ".join(path_only)
        )
    if archives:
        details.append(
            "archive paths were referenced alongside other paths ("
            + ", ".join(archives)
            + "); pass only the zip path, or use one concatenated text file"
        )
    if question_refs and not any(_attachment_has_text(a) for a in attachments):
        details.append(
            "the prompt references filesystem paths but no readable text was inlined"
        )
    failed_reads = [a["path"] for a in attachments if a.get("error")]
    if failed_reads:
        details.append("attachment read failed: " + ", ".join(failed_reads))

    if details:
        raise WebReviewBundleError(backend=backend, detail="; ".join(details))


def validate_web_review_evidence(
    question: str,
    attachments: list[dict[str, Any]],
    *,
    backend: str = "webgpt",
) -> None:
    """Backward-compatible wrapper around resolve_web_review_delivery."""
    resolve_web_review_delivery(question, attachments, backend=backend)


def extract_file_attachments(question: str, *, max_bytes: int = 2_000_000) -> list[dict[str, Any]]:
    """Find file paths referenced in the question and read them.

    Conservative: only pulls in paths that:
      - start with /, ~, ./, or ../
      - resolve to a real file the user can read
      - are <= max_bytes after read (truncated and flagged otherwise)
    """
    seen: set[Path] = set()
    out: list[dict[str, Any]] = []
    for match in _PATH_TOKEN_RE.finditer(question):
        token = match.group(1).rstrip(".,;:)>")
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


def build_webgpt_prompt(
    base_prompt: str,
    attachments: list[dict[str, Any]],
    *,
    system_preamble: str | None = None,
) -> str:
    """Compose the prompt to send to ChatGPT.

    File attachments are inlined under a clearly-labelled section so the
    human reading the ChatGPT tab can see what the agent sent.
    """
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
class WebgptResult:
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


def call_webgpt(
    prompt: str,
    *,
    tab_id: str = "",
    url: str = "",
    create_tab: bool = False,
    project: str = "",
    attach_file: str = "",
    timeout: float = WEBGPT_DEFAULT_TIMEOUT,
    stable_polls: int = WEBGPT_STABLE_POLLS,
    artifact_dir: Path | None = None,
    no_activate: bool = True,
    surf_run: Path | None = None,
    run_state: object | None = None,
    iteration: int | None = None,
    persona: str | None = None,
) -> WebgptResult:
    """One WebGPT round trip against the controlled ChatGPT tab.

    Tab acquisition priority:
      1. explicit `tab_id`
      2. explicit `url`
      3. `create_tab=True` — surf's CHATGPT_NEW_TAB path creates a fresh
         chatgpt.com tab; with no_activate=True the tab is created in the
         background (`active: false`) and never foregrounds. The new tab's id
         is returned in `controlled_tab_id` so the caller can reuse it for
         follow-up rounds.
      4. auto-resolve a single open chatgpt.com tab via `surf tab.list`.

    Multi-turn iteration: call this function repeatedly with the same tab_id.
    ChatGPT preserves conversation context per tab; each call appends a turn.
    """
    surf = surf_run or _surf_run_path()
    if not surf.exists():
        raise WebgptBackendError(f"surf runtime not found: {surf}")

    # Soft rate-limit guard: stop a runaway loop from burning the
    # ChatGPT account's per-3-hour cap. Configurable via
    # ASK_WEBGPT_MAX_ROUNDS_PER_HOUR; bypassable for tests via
    # ASK_WEBGPT_RATE_LIMIT_DISABLE=1.
    try:
        check_and_record()
    except WebgptRateLimitError as exc:
        raise WebgptBackendError(str(exc)) from exc

    # Project binding takes precedence after explicit tab_id/url but before
    # create_tab/auto-resolve. A bound, still-open tab gets reused; a stale
    # auto-binding silently re-creates; a stale manual binding raises so the
    # human re-binds explicitly — UNLESS create_tab=True, in which case the
    # caller has explicitly opted in to overwriting the manual binding and we
    # must NOT raise (bug ASK-WEBGPT-002 flagged by ChatGPT: the documented
    # recovery path "pass --webgpt-create-tab" was unreachable because verify
    # raised before the create_tab branch even got a chance to run).
    project_state_loaded = False
    if project and not tab_id and not url:
        try:
            existing = webgpt_project.verify(project, surf_run=surf)
        except webgpt_project.ProjectBindingError as exc:
            if create_tab:
                # Caller explicitly asked to (re)acquire a tab; overwrite
                # the stale manual binding silently on success.
                existing = None
            else:
                raise WebgptBackendError(str(exc)) from exc
        if existing and existing.tab_id:
            tab_id = existing.tab_id
            url = existing.conversation_url or ""
            project_state_loaded = True

    if create_tab and not tab_id and not url:
        # Skip resolution entirely; surf webgpt.submit will fall through to
        # CHATGPT_NEW_TAB which creates a fresh tab. With --no-activate, the
        # new tab is created with active=false so it stays in the background.
        resolution = WebgptTabResolution(tab_id="", candidates=[], source="create")
        resolved_tab_id = ""
    elif project and not tab_id and not url:
        # Project specified but no binding exists yet — implicitly create one.
        resolution = WebgptTabResolution(tab_id="", candidates=[], source="project_create")
        resolved_tab_id = ""
    else:
        resolution = resolve_chatgpt_tab(tab_id, url, surf_run=surf)
        resolved_tab_id = resolution.tab_id

    if artifact_dir is None:
        artifact_dir = Path(tempfile.mkdtemp(prefix="ask-webgpt-"))
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "01_request.md"
    response_path = artifact_dir / "02_response.md"
    raw_path = artifact_dir / "02_response.raw.md"
    meta_path = artifact_dir / "02_response.meta.json"
    submitted_path = artifact_dir / "02_response.submitted.md"
    request_path.write_text(prompt)

    command = [
        str(surf), "webgpt.submit",
        "--input", str(request_path),
        "--output", str(response_path),
        "--raw-output", str(raw_path),
        "--meta-output", str(meta_path),
        "--submitted-output", str(submitted_path),
        "--timeout", str(int(timeout)),
        "--stable-polls", str(int(stable_polls)),
    ]
    if resolved_tab_id:
        command.extend(["--tab-id", resolved_tab_id])
    elif url:
        command.extend(["--url", url])
    if no_activate:
        command.append("--no-activate")
    if attach_file:
        command.extend(["--attach-file", str(attach_file)])

    event_payload = {
        "backend": "webgpt",
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
        run_state.event("oracle_webgpt_call_started", **event_payload)

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
                "oracle_webgpt_call_failed",
                **event_payload,
                error="subprocess_timeout",
            )
        raise WebgptBackendError(
            f"surf webgpt.submit timed out after {timeout + 90:.0f}s"
        ) from exc

    took_ms = int((time.monotonic() - start_t) * 1000)
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {}

    if proc.returncode != 0 or meta.get("status") != "completed":
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_webgpt_call_failed",
                **event_payload,
                returncode=proc.returncode,
                meta_status=meta.get("status"),
                failure=meta.get("failure"),
                stderr_tail=(proc.stderr or "")[-2000:],
            )
        raise WebgptBackendError(
            f"surf webgpt.submit failed: returncode={proc.returncode} "
            f"meta_status={meta.get('status')} failure={meta.get('failure')}\n"
            f"stderr tail: {(proc.stderr or '')[-1000:]}"
        )

    response_text = response_path.read_text() if response_path.exists() else ""
    raw_text = raw_path.read_text() if raw_path.exists() else ""

    result = WebgptResult(
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
            "oracle_webgpt_call_finished",
            **event_payload,
            controlled_tab_id=result.controlled_tab_id,
            took_ms=took_ms,
            response_chars=len(response_text),
            raw_contains_sentinel=result.raw_contains_sentinel,
            clean_contains_sentinel=result.clean_contains_sentinel,
            focus_changed=result.focus_changed,
            project=project or None,
            project_state_loaded=project_state_loaded if project else None,
        )

    # Persist the project binding (auto-bind on first use; refresh
    # last_used_at / conversation_url on every successful call).
    if project and result.controlled_tab_id:
        try:
            existing = webgpt_project.load(project)
            manual = bool(existing.bound_manually) if existing else False
            convo_url = (
                meta.get("conversation_url")
                or result.requested_url
                or (existing.conversation_url if existing else "")
            )
            webgpt_project.bind(
                project,
                result.controlled_tab_id,
                conversation_url=convo_url or "",
                manual=manual,
            )
        except Exception:
            # Persistence is best-effort; never fail the oracle call.
            pass

    return result
