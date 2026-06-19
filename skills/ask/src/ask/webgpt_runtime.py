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

import os
import os
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
from .browser_oracle_client import apply_webgpt_browser_oracle


_WEBGPT_DONE_RE = re.compile(r"<<<WEBGPT_DONE:[^>]+>>>\s*")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _sanitize_clean_response(text: str, *, sentinel: str = "") -> str:
    """Strip sentinel tokens that surf may leave as trailing contamination."""
    cleaned = text or ""
    if sentinel:
        before, sep, _after = cleaned.partition(sentinel)
        if sep:
            cleaned = before
    marker = _WEBGPT_DONE_RE.search(cleaned)
    if marker:
        cleaned = cleaned[: marker.start()]
    return cleaned.strip()

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


def _run_webgpt_preflight_command(
    command: list[str],
    *,
    surf: Path,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=surf.parent,
        )
    except subprocess.TimeoutExpired as exc:
        raise WebgptBackendError("surf webgpt.preflight timed out") from exc

    try:
        preflight = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        preflight = {"status": "invalid_json", "stdout": (proc.stdout or "")[-1000:]}
    return proc, preflight


def _run_webgpt_preflight(
    *,
    surf: Path,
    resolved_tab_id: str,
    url: str,
    no_activate: bool,
) -> dict[str, Any]:
    """Run surf's fast WebGPT tab/focus preflight before a costly submit."""
    if os.environ.get("ASK_WEBGPT_SKIP_PREFLIGHT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return {"status": "skipped", "reason": "ASK_WEBGPT_SKIP_PREFLIGHT"}

    command = [str(surf), "webgpt.preflight", "--json"]
    if resolved_tab_id:
        command.extend(["--tab-id", resolved_tab_id])
        if url:
            command.extend(["--expect-url", url])
    elif url:
        command.extend(["--url", url])
    else:
        return {"status": "skipped", "reason": "no_explicit_tab_or_url"}

    if no_activate:
        command.append("--no-activate")
    foreground_allowed_by_env = _env_truthy("ASK_WEBGPT_ALLOW_FOREGROUND")
    if foreground_allowed_by_env:
        command.append("--allow-foreground-controlled")
    if _env_truthy("ASK_WEBGPT_ALLOW_UNVERIFIED_TAB_ID"):
        command.append("--allow-unverified-tab-id")

    proc, preflight = _run_webgpt_preflight_command(command, surf=surf)

    preflight_failed = proc.returncode != 0 or preflight.get("status") != "pass"
    if preflight_failed and resolved_tab_id and url:
        failures = set(preflight.get("failures") or [])
        identity_failures = {
            "tab_id_valid",
            "tab_open_chatgpt",
            "expected_url_matches_tab",
            "tab_identity",
            "url_resolve",
            "url_ambiguous",
        }
        if failures & identity_failures:
            retry_command = [str(surf), "webgpt.preflight", "--json", "--url", url]
            if no_activate:
                retry_command.append("--no-activate")
            if foreground_allowed_by_env:
                retry_command.append("--allow-foreground-controlled")
            retry_proc, retry_preflight = _run_webgpt_preflight_command(retry_command, surf=surf)
            if retry_proc.returncode == 0 and retry_preflight.get("status") == "pass":
                retry_preflight["url_recovery_from_tab_id_failure"] = True
                retry_preflight["initial_status"] = preflight.get("status")
                retry_preflight["initial_failures"] = preflight.get("failures") or []
                retry_preflight["initial_requested_tab_id"] = resolved_tab_id
                return retry_preflight
            preflight["url_recovery_attempted"] = True
            preflight["url_recovery_status"] = retry_preflight.get("status")
            preflight["url_recovery_failures"] = retry_preflight.get("failures") or []
            preflight["url_recovery_stdout_tail"] = (retry_proc.stdout or "")[-1000:]

    if (
        preflight_failed
        and "not_foreground_controlled" in (preflight.get("failures") or [])
        and not foreground_allowed_by_env
    ):
        retry_command = [*command, "--allow-foreground-controlled"]
        retry_proc, retry_preflight = _run_webgpt_preflight_command(retry_command, surf=surf)
        if retry_proc.returncode == 0 and retry_preflight.get("status") == "pass":
            retry_preflight["foreground_controlled_auto_allowed"] = True
            retry_preflight["initial_status"] = preflight.get("status")
            retry_preflight["initial_failures"] = preflight.get("failures") or []
            return retry_preflight
        raise WebgptBackendError(
            "surf webgpt.preflight failed before submit: "
            f"returncode={retry_proc.returncode} status={retry_preflight.get('status')} "
            f"failures={retry_preflight.get('failures')} "
            f"initial_failures={preflight.get('failures')}\n"
            f"stdout tail: {(retry_proc.stdout or '')[-1000:]}\n"
            f"stderr tail: {(retry_proc.stderr or '')[-1000:]}"
        )

    if proc.returncode != 0 or preflight.get("status") != "pass":
        raise WebgptBackendError(
            "surf webgpt.preflight failed before submit: "
            f"returncode={proc.returncode} status={preflight.get('status')} "
            f"failures={preflight.get('failures')}\n"
            f"stdout tail: {(proc.stdout or '')[-1000:]}\n"
            f"stderr tail: {(proc.stderr or '')[-1000:]}"
        )
    if foreground_allowed_by_env:
        preflight["foreground_controlled_env_allowed"] = True
    return preflight


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
_PATH_LIKE_PREFIXES = ("/", "~", "./", "../")


def extract_path_tokens(text: str) -> list[str]:
    """Return unique filesystem path tokens referenced in *text*."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _PATH_TOKEN_RE.finditer(text):
        token = match.group(1).rstrip(".,;:)>")
        if token.startswith("/") and "/" not in token[1:]:
            # Skill shorthand such as /ask, /scillm, or /code-runner is not a
            # local filesystem path for browser-review attachment validation.
            continue
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
    # Only validate paths named in the question. Paths inside inlined review
    # targets (READMEs, bundles) are document content, not missing attachments.
    referenced_set = set(question_refs)
    for att in attachments:
        if _attachment_has_text(att):
            for token in extract_path_tokens(str(att.get("text", ""))):
                referenced_set.add(token)
    referenced: list[str] = list(referenced_set)

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
        # Archives are delivered via surf --attach-file, not inlined into argv.
        if _is_archive_path(p):
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



WEBGPT_REVIEW_FILE_PREAMBLE = (
    "You are answering a /ask WebGPT review call. Treat the attached zip "
    "bundle or inlined review file as primary evidence. Do not assume unstated "
    "local filesystem paths. Do not run commands or edit repositories unless "
    "explicitly asked."
)

# surf webgpt.submit passes the full prompt on argv to the chatgpt helper;
# keep review rounds small when evidence is file-delivered (zip attach or one
# inlined concatenated bundle).
WEBGPT_ORACLE_PROMPT_MAX_BYTES = 256_000


def strip_path_tokens(text: str) -> str:
    """Remove filesystem path tokens from review questions."""
    cleaned = text
    for token in extract_path_tokens(text):
        cleaned = cleaned.replace(token, " ")
    return " ".join(cleaned.split())


def webgpt_review_uses_file_delivery(
    attach_file: str,
    attachments: list[dict[str, Any]],
) -> bool:
    """True when browser evidence is file-delivered instead of memory synthesis."""
    if attach_file:
        return True
    readable = [a for a in attachments if _attachment_has_text(a)]
    return len(readable) == 1


def build_webgpt_oracle_prompt(
    base_prompt: str,
    question: str,
    attachments: list[dict[str, Any]],
    *,
    attach_file: str = "",
    system_preamble: str | None = None,
) -> str:
    """Build a WebGPT oracle prompt sized for surf argv limits."""
    if webgpt_review_uses_file_delivery(attach_file, attachments):
        review_body = strip_path_tokens(question).strip() or question.strip()
        inline_attachments: list[dict[str, Any]] = []
        if not attach_file:
            inline_attachments = [
                a for a in attachments if _attachment_has_text(a)
            ]
        prompt = build_webgpt_prompt(
            review_body,
            inline_attachments,
            system_preamble=system_preamble or WEBGPT_REVIEW_FILE_PREAMBLE,
        )
    else:
        prompt = build_webgpt_prompt(
            base_prompt,
            attachments,
            system_preamble=system_preamble
            or (
                "You are answering a /ask oracle call. Treat retrieved memory "
                "context as supporting evidence; cite supported claims inline with "
                "source IDs like [MEMORY.1]. Distinguish supported facts from "
                "inference. Be concise and technically precise."
            ),
        )
    if len(prompt.encode("utf-8")) > WEBGPT_ORACLE_PROMPT_MAX_BYTES:
        raise WebgptBackendError(
            "WebGPT oracle prompt exceeds argv-safe size "
            f"({len(prompt.encode('utf-8')):,} bytes > "
            f"{WEBGPT_ORACLE_PROMPT_MAX_BYTES:,}). Use a zip attach bundle "
            "(one .zip path only) or a single concatenated review .md/.txt file."
        )
    return prompt

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
    browser_oracle_from: str = "",
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

    browser_oracle_meta: dict[str, Any] = {}
    if not tab_id and not url and not create_tab:
        from_path = (
            browser_oracle_from.strip()
            or os.environ.get("ASK_BROWSER_ORACLE_FROM", "").strip()
            or os.getcwd()
        )
        project, tab_id, url, browser_oracle_meta = apply_webgpt_browser_oracle(
            from_path=from_path,
            project=project,
            tab_id=tab_id,
            url=url,
            create_tab=create_tab,
        )
        if browser_oracle_meta.get("browser_oracle_applied") and run_state is not None and hasattr(
            run_state, "event"
        ):
            run_state.event(
                "browser_oracle_resolved",
                **{k: v for k, v in browser_oracle_meta.items() if v is not None},
            )
        if browser_oracle_meta.get("status") in {"needs_attention", "error"} and (
            project or browser_oracle_meta.get("project")
        ):
            reason = (
                browser_oracle_meta.get("reason")
                or browser_oracle_meta.get("error")
                or browser_oracle_meta.get("status")
            )
            resolved_project = project or str(browser_oracle_meta.get("project") or "")
            raise WebgptBackendError(
                f"browser-oracle project {resolved_project!r} is not ready: {reason}. "
                "Run browser-oracle doctor/reconcile, re-bind the project, pass "
                "--webgpt-tab-id/--webgpt-url, or use --webgpt-create-tab deliberately."
            )

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
    if project and not tab_id and not url and not create_tab:
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
        if url:
            command.extend(["--expect-url", url])
    elif url:
        command.extend(["--url", url])
    if create_tab and not resolved_tab_id:
        command.append("--create-tab")
    if no_activate:
        command.append("--no-activate")
    if _env_truthy("ASK_WEBGPT_ALLOW_FOREGROUND"):
        command.append("--allow-foreground-controlled")
    if _env_truthy("ASK_WEBGPT_ALLOW_UNVERIFIED_TAB_ID"):
        command.append("--allow-unverified-tab-id")
    if attach_file:
        command.extend(["--attach-file", str(attach_file)])

    preflight: dict[str, Any] = {}
    if not create_tab:
        preflight = _run_webgpt_preflight(
            surf=surf,
            resolved_tab_id=resolved_tab_id,
            url=url,
            no_activate=no_activate,
        )
        recovered_tab_id = str(preflight.get("requested_tab_id") or "").strip()
        if preflight.get("url_recovery_from_tab_id_failure") and recovered_tab_id:
            resolved_tab_id = recovered_tab_id
            if "--tab-id" in command:
                command[command.index("--tab-id") + 1] = resolved_tab_id
            elif "--url" in command:
                url_index = command.index("--url")
                del command[url_index : url_index + 2]
                command.extend(["--tab-id", resolved_tab_id])
                if url:
                    command.extend(["--expect-url", url])
        if (
            preflight.get("foreground_controlled_auto_allowed")
            and "--allow-foreground-controlled" not in command
        ):
            command.append("--allow-foreground-controlled")

    event_payload = {
        "backend": "webgpt",
        "tab_id": resolved_tab_id,
        "url": url or None,
        "no_activate": no_activate,
        "timeout_seconds": float(timeout),
        "artifact_dir": str(artifact_dir),
        "preflight_status": preflight.get("status") if preflight else None,
        "foreground_controlled_auto_allowed": bool(
            preflight.get("foreground_controlled_auto_allowed")
        ),
        "foreground_controlled_env_allowed": bool(
            preflight.get("foreground_controlled_env_allowed")
        ),
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
        raw_text = raw_path.read_text() if raw_path.exists() else ""
        expected_sentinel = str(meta.get("sentinel", "")).strip()
        if not expected_sentinel and submitted_path.exists():
            submitted_text = submitted_path.read_text(encoding="utf-8", errors="replace")
            submitted_match = _WEBGPT_DONE_RE.search(submitted_text)
            if submitted_match:
                expected_sentinel = submitted_match.group(0).strip()
        can_recover = bool(expected_sentinel and expected_sentinel in raw_text)
        if can_recover:
            response_text = _sanitize_clean_response(raw_text, sentinel=expected_sentinel)
            response_path.write_text(response_text + "\n", encoding="utf-8")
            meta = {
                **meta,
                "status": "completed",
                "recovered_after_submit_failure": True,
                "submit_returncode": proc.returncode,
                "submit_stderr_tail": (proc.stderr or "")[-2000:],
                "sentinel": expected_sentinel,
                "controlled_tab_id": resolved_tab_id,
                "requested_tab_id": resolved_tab_id,
                "requested_url": url,
                "raw_contains_sentinel": True,
                "clean_contains_sentinel": False,
                "no_activate": no_activate,
                "focus_changed": False if no_activate else None,
            }
            meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        else:
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

    if meta.get("recovered_after_submit_failure") and run_state is not None and hasattr(run_state, "event"):
        run_state.event(
            "oracle_webgpt_call_recovered",
            **event_payload,
            returncode=proc.returncode,
            stderr_tail=(proc.stderr or "")[-2000:],
        )

    response_text = response_path.read_text() if response_path.exists() else ""
    sentinel_value = str(meta.get("sentinel", ""))
    if response_text:
        response_text = _sanitize_clean_response(response_text, sentinel=sentinel_value)
        if response_path.exists() and sentinel_value and meta.get("clean_contains_sentinel"):
            response_path.write_text(response_text + "\n", encoding="utf-8")
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
