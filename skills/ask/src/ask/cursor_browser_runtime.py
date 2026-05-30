"""Cursor Browser oracle backend for /ask within Cursor IDE.

Routes oracle calls through `surf cursor-browser.submit`, which controls
ChatGPT (or other web oracles later) in Cursor's embedded Browser pane via
the cursor-browser-bridge HTTP extension.

Tab identity uses **viewId** (e.g. f53e74), NOT Chrome tab ids from surf tab.list.

Install once:
  git clone https://github.com/VectorlyApp/cursor-browser-bridge.git
  cd cursor-browser-bridge && ./install.sh
  Reload Cursor window; verify /tmp/cursor-browser-bridge-port exists.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ask_config import (
    CURSOR_BROWSER_DEFAULT_TIMEOUT,
    CURSOR_BROWSER_STABLE_POLLS,
    SURF_RUN,
)
from . import cursor_browser_project
from .webgpt_runtime import (
    WebgptBackendError,
    build_webgpt_prompt,
    extract_file_attachments,
    resolve_web_review_delivery,
)

# Reuse webgpt tab error naming for callers
CursorBrowserTabError = type("CursorBrowserTabError", (RuntimeError,), {})
CursorBrowserBackendError = WebgptBackendError


@dataclass(frozen=True)
class CursorBrowserTabResolution:
    view_id: str
    candidates: list[dict]
    source: str


@dataclass
class CursorBrowserResult:
    response: str
    raw_response: str
    sentinel: str
    controlled_view_id: str
    requested_view_id: str
    requested_url: str
    raw_contains_sentinel: bool
    clean_contains_sentinel: bool
    meta: dict[str, Any]
    artifact_dir: Path
    took_ms: int


def _surf_run_path() -> Path:
    return Path(SURF_RUN)


def _list_cursor_tabs(*, surf_run: Path) -> list[dict[str, str]]:
    import os

    env = os.environ.copy()
    scripts = str(surf_run.parent / "scripts")
    env["PYTHONPATH"] = scripts + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [str(surf_run), "cursor-browser.tab.list", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=surf_run.parent,
        env=env,
    )
    if proc.returncode != 0:
        raise CursorBrowserTabError(
            "surf cursor-browser.tab.list failed. Is cursor-browser-bridge installed?\n"
            f"stderr={proc.stderr[-500:]}"
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CursorBrowserTabError(
            f"Invalid tab list JSON from cursor-browser.tab.list: {proc.stdout[:300]}"
        ) from exc
    if not isinstance(data, list):
        return []
    return [
        {
            "viewId": str(item.get("viewId") or item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
        }
        for item in data
        if isinstance(item, dict)
    ]


def resolve_chatgpt_view(
    explicit_view_id: str | None,
    explicit_url: str | None,
    *,
    surf_run: Path | None = None,
) -> CursorBrowserTabResolution:
    surf = surf_run or _surf_run_path()
    if explicit_view_id:
        return CursorBrowserTabResolution(
            view_id=str(explicit_view_id).strip(),
            candidates=[],
            source="explicit",
        )
    tabs = _list_cursor_tabs(surf_run=surf)
    if explicit_url:
        matches = [
            t
            for t in tabs
            if t.get("url") == explicit_url
            or t.get("url", "").rstrip("/") == str(explicit_url).rstrip("/")
        ]
        if len(matches) == 1:
            return CursorBrowserTabResolution(
                view_id=matches[0]["viewId"],
                candidates=matches,
                source="explicit_url",
            )
        if not matches:
            raise CursorBrowserTabError(
                f"No Cursor Browser tab matched url: {explicit_url}"
            )
        listing = "\n".join(
            f"  {c['viewId']}\t{c.get('title','')}\t{c.get('url','')}" for c in matches
        )
        raise CursorBrowserTabError(
            "Multiple Cursor Browser tabs matched url; pass --cursor-browser-view-id.\n"
            f"Candidates:\n{listing}"
        )
    candidates = [t for t in tabs if "chatgpt.com" in t.get("url", "")]
    if len(candidates) == 1:
        return CursorBrowserTabResolution(
            view_id=candidates[0]["viewId"],
            candidates=candidates,
            source="auto",
        )
    if not candidates:
        raise CursorBrowserTabError(
            "No chatgpt.com tab in Cursor Browser.\n"
            "Open ChatGPT in Cursor Browser, or pass --cursor-browser-view-id from browser_tabs list."
        )
    listing = "\n".join(
        f"  {c['viewId']}\t{c.get('title','')}\t{c.get('url','')}" for c in candidates
    )
    raise CursorBrowserTabError(
        "Multiple chatgpt.com tabs in Cursor Browser; refusing to guess.\n"
        "Pass --cursor-browser-view-id or bind a project:\n"
        "  cursor-browser-project bind NAME --view-id VIEW_ID\n"
        f"Candidates:\n{listing}"
    )


def call_cursor_browser(
    prompt: str,
    *,
    view_id: str = "",
    url: str = "",
    project: str = "",
    attach_file: str = "",
    timeout: float = CURSOR_BROWSER_DEFAULT_TIMEOUT,
    stable_polls: int = CURSOR_BROWSER_STABLE_POLLS,
    artifact_dir: Path | None = None,
    surf_run: Path | None = None,
    run_state: object | None = None,
    iteration: int | None = None,
    persona: str | None = None,
) -> CursorBrowserResult:
    surf = surf_run or _surf_run_path()
    if not surf.exists():
        raise CursorBrowserBackendError(f"surf runtime not found: {surf}")

    project_state_loaded = False
    if project and not view_id and not url:
        try:
            existing = cursor_browser_project.verify(project, surf_run=surf)
        except cursor_browser_project.ProjectBindingError as exc:
            raise CursorBrowserBackendError(str(exc)) from exc
        if existing and existing.view_id:
            view_id = existing.view_id
            url = existing.conversation_url or ""
            project_state_loaded = True

    resolution = resolve_chatgpt_view(view_id or None, url or None, surf_run=surf)
    resolved_view_id = resolution.view_id

    if artifact_dir is None:
        artifact_dir = Path(tempfile.mkdtemp(prefix="ask-cursor-browser-"))
    artifact_dir = Path(artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = artifact_dir / "01_request.md"
    response_path = artifact_dir / "02_response.md"
    raw_path = artifact_dir / "02_response.raw.md"
    meta_path = artifact_dir / "02_response.meta.json"
    submitted_path = artifact_dir / "02_response.submitted.md"
    request_path.write_text(prompt)

    command = [
        str(surf),
        "cursor-browser.submit",
        "--input",
        str(request_path),
        "--output",
        str(response_path),
        "--raw-output",
        str(raw_path),
        "--meta-output",
        str(meta_path),
        "--submitted-output",
        str(submitted_path),
        "--view-id",
        resolved_view_id,
        "--timeout",
        str(int(timeout)),
        "--stable-polls",
        str(int(stable_polls)),
    ]
    if url:
        command.extend(["--url", url])

    event_payload = {
        "backend": "cursor-browser",
        "view_id": resolved_view_id,
        "url": url or None,
        "timeout_seconds": float(timeout),
        "artifact_dir": str(artifact_dir),
    }
    if iteration is not None:
        event_payload["iteration"] = iteration
    if persona:
        event_payload["persona"] = persona
    if run_state is not None and hasattr(run_state, "event"):
        run_state.event("oracle_cursor_browser_call_started", **event_payload)

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
                "oracle_cursor_browser_call_failed",
                **event_payload,
                error="subprocess_timeout",
            )
        raise CursorBrowserBackendError(
            f"surf cursor-browser.submit timed out after {timeout + 90:.0f}s"
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
                "oracle_cursor_browser_call_failed",
                **event_payload,
                returncode=proc.returncode,
                meta_status=meta.get("status"),
                failure=meta.get("failure"),
                stderr_tail=(proc.stderr or "")[-2000:],
            )
        raise CursorBrowserBackendError(
            f"surf cursor-browser.submit failed: returncode={proc.returncode} "
            f"meta_status={meta.get('status')} failure={meta.get('failure')}\n"
            f"stderr tail: {(proc.stderr or '')[-1000:]}"
        )

    response_text = response_path.read_text() if response_path.exists() else ""
    raw_text = raw_path.read_text() if raw_path.exists() else ""

    result = CursorBrowserResult(
        response=response_text,
        raw_response=raw_text,
        sentinel=str(meta.get("sentinel", "")),
        controlled_view_id=str(meta.get("controlled_view_id", resolved_view_id)),
        requested_view_id=str(meta.get("requested_view_id", "") or resolved_view_id),
        requested_url=str(meta.get("requested_url", "") or url),
        raw_contains_sentinel=bool(meta.get("raw_contains_sentinel")),
        clean_contains_sentinel=bool(meta.get("clean_contains_sentinel")),
        meta=meta,
        artifact_dir=artifact_dir,
        took_ms=took_ms,
    )

    if run_state is not None and hasattr(run_state, "event"):
        run_state.event(
            "oracle_cursor_browser_call_finished",
            **event_payload,
            controlled_view_id=result.controlled_view_id,
            took_ms=took_ms,
            response_chars=len(response_text),
            raw_contains_sentinel=result.raw_contains_sentinel,
            project=project or None,
            project_state_loaded=project_state_loaded if project else None,
        )

    if project and result.controlled_view_id:
        try:
            existing = cursor_browser_project.load(project)
            manual = bool(existing.bound_manually) if existing else False
            convo_url = (
                meta.get("conversation_url")
                or result.requested_url
                or (existing.conversation_url if existing else "")
            )
            cursor_browser_project.bind(
                project,
                result.controlled_view_id,
                conversation_url=convo_url or "",
                manual=manual,
            )
        except Exception:
            pass

    return result
