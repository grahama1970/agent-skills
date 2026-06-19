"""Machine-local tab bindings under ~/.pi/*-projects/."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from .config import project_root, surf_run_path

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class BindingState:
    name: str
    backend: str
    tab_id: str = ""
    view_id: str = ""
    conversation_url: str = ""
    bound_manually: bool = False
    created_at: str = ""
    last_used_at: str = ""
    last_verified_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BindingError(RuntimeError):
    """Raised when a manually-bound tab is missing."""


class DuplicateConversationUrlError(BindingError):
    """Raised when a bound conversation URL is open in more than one tab."""


@dataclass
class LiveTab:
    id: str
    title: str = ""
    url: str = ""


@dataclass
class ReconcileRow:
    name: str
    backend: str
    state_path: str
    tab_id: str = ""
    view_id: str = ""
    conversation_url: str = ""
    bound_manually: bool = False
    live_found: bool = False
    live_title: str = ""
    live_url: str = ""
    duplicate_url_tab_ids: list[str] | None = None
    status: str = "unknown"
    issues: list[str] | None = None
    pruned: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["issues"] = data["issues"] or []
        data["duplicate_url_tab_ids"] = data["duplicate_url_tab_ids"] or []
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalise_url_for_identity(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc == "www.chatgpt.com":
        netloc = "chatgpt.com"
    path = re.sub(r"/+$", "", parsed.path or "/")
    return f"{scheme}://{netloc}{path}"


def parse_tab_list(text: str) -> dict[str, LiveTab]:
    """Parse ``surf tab.list`` TSV output into live tabs keyed by Chrome tab id."""
    tabs: dict[str, LiveTab] = {}
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        tab_id, title, url = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if tab_id:
            tabs[tab_id] = LiveTab(id=tab_id, title=title, url=url)
    return tabs


def _duplicate_url_tab_ids(tabs_by_id: dict[str, LiveTab], *, tab_id: str, url: str) -> list[str]:
    expected = _normalise_url_for_identity(url)
    if not expected:
        return []
    return sorted(
        tab.id
        for tab in tabs_by_id.values()
        if tab.id != tab_id and _normalise_url_for_identity(tab.url) == expected
    )


def live_tabs(*, surf_run: Path | None = None, timeout: float = 15.0) -> dict[str, LiveTab]:
    surf = surf_run or surf_run_path()
    if not surf.exists():
        raise BindingError(f"surf runtime not found at {surf}")
    try:
        proc = subprocess.run(
            [str(surf), "tab.list"],
            cwd=surf.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        raise BindingError(f"surf tab.list failed: {exc}") from exc
    if proc.returncode != 0:
        raise BindingError(f"surf tab.list failed with exit {proc.returncode}: {proc.stderr.strip()}")
    return parse_tab_list(proc.stdout)


def sanitize_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("-", str(name).strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    if not cleaned:
        raise ValueError(f"project name {name!r} sanitises to empty string")
    return cleaned[:128]


def state_path(name: str, backend: str, *, root: Path | None = None) -> Path:
    base = root or project_root(backend)
    return base / f"{sanitize_name(name)}.json"


def load(name: str, backend: str, *, root: Path | None = None) -> BindingState | None:
    path = state_path(name, backend, root=root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        logger.error("failed to read binding {}: {}", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    fields = BindingState.__dataclass_fields__
    payload = {k: data.get(k, "") for k in fields}
    if not str(payload.get("backend", "")).strip():
        payload["backend"] = backend
    if not str(payload.get("name", "")).strip():
        payload["name"] = sanitize_name(name)
    return BindingState(**payload)


def save(state: BindingState, *, root: Path | None = None) -> Path:
    base = root or project_root(state.backend)
    path = base / f"{sanitize_name(state.name)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
    tmp.replace(path)
    return path


def bind(
    name: str,
    backend: str,
    *,
    tab_id: str = "",
    view_id: str = "",
    conversation_url: str = "",
    manual: bool = False,
    root: Path | None = None,
) -> BindingState:
    if backend == "cursor-browser":
        if not view_id.strip():
            raise ValueError("view_id is required for cursor-browser bind")
        identity = view_id.strip()
    else:
        if not tab_id.strip():
            raise ValueError("tab_id is required for bind")
        identity = tab_id.strip()

    sanitised = sanitize_name(name)
    existing = load(sanitised, backend, root=root)
    now = _utc_now()
    state = existing or BindingState(name=sanitised, backend=backend, created_at=now)
    state.name = sanitised
    state.backend = backend
    state.tab_id = tab_id.strip() if tab_id else state.tab_id
    state.view_id = view_id.strip() if view_id else state.view_id
    if conversation_url:
        state.conversation_url = conversation_url.strip()
    if manual:
        state.bound_manually = True
    state.last_used_at = now
    state.last_verified_at = now
    if not state.created_at:
        state.created_at = now
    if not state.tab_id and backend != "cursor-browser":
        state.tab_id = identity
    save(state, root=root)
    return state


def unbind(name: str, backend: str, *, root: Path | None = None) -> bool:
    path = state_path(name, backend, root=root)
    if not path.exists():
        return False
    path.unlink()
    return True


def reconcile_bindings(
    backend: str | None = None,
    *,
    project: str = "",
    prune_missing: bool = False,
    surf_run: Path | None = None,
    root: Path | None = None,
) -> list[ReconcileRow]:
    """Compare stored bindings to live browser tabs and optionally prune dead ids."""
    states = list_bindings(backend, root=root)
    if project:
        wanted = sanitize_name(project)
        states = [state for state in states if sanitize_name(state.name) == wanted]

    tabs_by_id: dict[str, LiveTab] = {}
    scan_error = ""
    if any(state.backend != "cursor-browser" for state in states):
        try:
            tabs_by_id = live_tabs(surf_run=surf_run)
        except BindingError as exc:
            scan_error = str(exc)

    rows: list[ReconcileRow] = []
    for state in states:
        issues: list[str] = []
        live_found = False
        live_title = ""
        live_url = ""
        duplicates: list[str] = []
        status = "ready"

        if state.backend == "cursor-browser":
            status = "unsupported_live_scan"
            issues.append("cursor_browser_live_scan_unsupported")
        elif scan_error:
            status = "scan_failed"
            issues.append("surf_tab_list_failed")
        elif not state.tab_id:
            status = "missing_tab_id"
            issues.append("missing_tab_id")
        else:
            live = tabs_by_id.get(state.tab_id)
            if live is None:
                status = "missing_live_tab"
                issues.append("missing_live_tab")
            else:
                live_found = True
                live_title = live.title
                live_url = live.url
                if state.conversation_url and live.url and live.url != state.conversation_url:
                    status = "url_mismatch"
                    issues.append("url_mismatch")
                else:
                    duplicates = _duplicate_url_tab_ids(
                        tabs_by_id,
                        tab_id=state.tab_id,
                        url=state.conversation_url,
                    )
                    if duplicates:
                        status = "duplicate_conversation_url"
                        issues.append("duplicate_conversation_url")

        pruned = False
        if prune_missing and status == "missing_live_tab":
            pruned = unbind(state.name, state.backend, root=root)

        if scan_error:
            issues.append(scan_error)
        rows.append(
            ReconcileRow(
                name=state.name,
                backend=state.backend,
                state_path=str(state_path(state.name, state.backend, root=root)),
                tab_id=state.tab_id,
                view_id=state.view_id,
                conversation_url=state.conversation_url,
                bound_manually=state.bound_manually,
                live_found=live_found,
                live_title=live_title,
                live_url=live_url,
                duplicate_url_tab_ids=duplicates,
                status=status,
                issues=issues,
                pruned=pruned,
            )
        )
    return rows


def open_tab_and_bind(
    name: str,
    backend: str,
    *,
    url: str,
    manual: bool = True,
    surf_run: Path | None = None,
    root: Path | None = None,
    timeout: float = 15.0,
) -> BindingState:
    """Open a fresh browser tab through Surf and bind the returned tab id."""
    if backend == "cursor-browser":
        raise ValueError("open-bind is only supported for Chrome tab backends")
    target_url = url.strip()
    if not target_url:
        raise ValueError("url is required")
    surf = surf_run or surf_run_path()
    if not surf.exists():
        raise BindingError(f"surf runtime not found at {surf}")
    try:
        proc = subprocess.run(
            [str(surf), "tab.new", target_url],
            cwd=surf.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        raise BindingError(f"surf tab.new failed: {exc}") from exc
    if proc.returncode != 0:
        raise BindingError(f"surf tab.new failed with exit {proc.returncode}: {proc.stderr.strip()}")
    match = re.search(r"Created tab\s+([0-9]+):", proc.stdout)
    if not match:
        raise BindingError(f"could not parse tab id from surf tab.new output: {proc.stdout.strip()}")
    return bind(
        name,
        backend,
        tab_id=match.group(1),
        conversation_url=target_url,
        manual=manual,
        root=root,
    )


def list_bindings(backend: str | None = None, *, root: Path | None = None) -> list[BindingState]:
    from .config import SUPPORTED_BACKENDS

    out: list[BindingState] = []
    for b in (backend,) if backend else SUPPORTED_BACKENDS:
        base = root or project_root(b)
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            fields = BindingState.__dataclass_fields__
            payload = {k: data.get(k, "") for k in fields}
            payload["backend"] = b
            payload["name"] = payload.get("name") or path.stem
            out.append(BindingState(**payload))
    return out


def verify(
    name: str,
    backend: str,
    *,
    surf_run: Path | None = None,
    root: Path | None = None,
    timeout: float = 15.0,
) -> BindingState | None:
    state = load(name, backend, root=root)
    if not state:
        return None
    if backend == "cursor-browser":
        return state
    if not state.tab_id:
        return None
    surf = surf_run or surf_run_path()
    if not surf.exists():
        logger.error("surf runtime not found at {}", surf)
        return state
    try:
        tabs_by_id = live_tabs(surf_run=surf, timeout=timeout)
    except BindingError as exc:
        logger.error("surf tab.list failed: {}", exc)
        return state
    live = tabs_by_id.get(state.tab_id)
    if live is not None:
        matched_url = live.url
        if matched_url and state.conversation_url and matched_url != state.conversation_url:
            if state.bound_manually:
                raise BindingError(
                    f"Project {state.name!r} ({backend}) is manually bound to tab {state.tab_id}, "
                    "but that tab now points at a different URL.\n"
                    f"  bound_url: {state.conversation_url}\n"
                    f"  current_url: {matched_url}\n"
                    "Re-bind only after confirming the intended reviewer tab:\n"
                    f"  browser-oracle bind {state.name} --backend {backend} --tab-id <id> --url <url> --manual"
                )
            state.conversation_url = matched_url
        elif matched_url and matched_url != state.conversation_url:
            state.conversation_url = matched_url
        duplicate_tab_ids = _duplicate_url_tab_ids(
            tabs_by_id,
            tab_id=state.tab_id,
            url=state.conversation_url,
        )
        if duplicate_tab_ids:
            raise DuplicateConversationUrlError(
                f"Project {state.name!r} ({backend}) is bound to tab {state.tab_id}, "
                "but the same conversation URL is also open in other ChatGPT tabs.\n"
                f"  bound_url: {state.conversation_url}\n"
                f"  duplicate_tab_ids: {', '.join(sorted(duplicate_tab_ids))}\n"
                "Close duplicate conversation tabs or bind to a unique reviewer tab before submitting."
            )
        state.last_verified_at = _utc_now()
        save(state, root=root)
        return state
    if state.bound_manually:
        raise BindingError(
            f"Project {state.name!r} ({backend}) is manually bound to tab {state.tab_id}, "
            "but that tab is no longer open. Re-bind:\n"
            f"  browser-oracle bind {state.name} --backend {backend} --tab-id <id> --url <url> --manual"
        )
    return None
