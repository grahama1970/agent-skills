"""Machine-local tab bindings under ~/.pi/*-projects/."""

from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger

from .config import project_root, surf_run_path

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class BindingState:
    name: str
    backend: str
    human_name: str = ""
    tab_id: str = ""
    view_id: str = ""
    conversation_url: str = ""
    kde_desktop_index: str = ""
    bound_manually: bool = False
    created_at: str = ""
    last_used_at: str = ""
    last_verified_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BindingError(RuntimeError):
    """Raised when a binding cannot be verified or safely changed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_url(url: str) -> str:
    raw = str(url).strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return raw
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _conversation_uuid(url: str) -> str:
    match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        url,
    )
    return match.group(0).lower() if match else ""


def _scan_live_tabs(surf_run: Path | None, timeout: float) -> list[dict[str, str]]:
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
        raise BindingError(f"surf tab.list failed with exit code {proc.returncode}")
    tabs: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tabs.append({"tab_id": parts[0], "title": parts[1], "url": parts[2]})
    return tabs


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
    human_name: str = "",
    tab_id: str = "",
    view_id: str = "",
    conversation_url: str = "",
    kde_desktop_index: str = "",
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
    if human_name:
        state.human_name = human_name.strip()
    state.tab_id = tab_id.strip() if tab_id else state.tab_id
    state.view_id = view_id.strip() if view_id else state.view_id
    if conversation_url:
        state.conversation_url = conversation_url.strip()
    if kde_desktop_index:
        state.kde_desktop_index = str(kde_desktop_index).strip()
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


def rebind_by_exact_url(
    name: str,
    backend: str,
    *,
    surf_run: Path | None = None,
    root: Path | None = None,
    timeout: float = 15.0,
    maintenance_authorized: bool = False,
) -> dict:
    """Atomically replace a stale tab_id with one live tab matching the stored URL."""
    state = load(name, backend, root=root)
    if state is None:
        raise BindingError(f"missing binding for {name!r} ({backend})")
    if backend == "cursor-browser":
        raise BindingError("rebind-by-exact-url is only supported for tab-id backends")
    if not state.conversation_url.strip():
        raise BindingError("stored project URL is required")
    if state.bound_manually and not maintenance_authorized:
        raise BindingError("manual binding requires maintenance authorization")

    previous = deepcopy(state)
    stored_url = _normalize_url(state.conversation_url)
    stored_uuid = _conversation_uuid(state.conversation_url)
    tabs = _scan_live_tabs(surf_run, timeout)
    matches = []
    for tab in tabs:
        url = tab["url"]
        if _normalize_url(url) == stored_url or (stored_uuid and _conversation_uuid(url) == stored_uuid):
            matches.append(tab)
    if not matches:
        raise BindingError("no live tab matches stored project URL")
    if len(matches) != 1:
        raise BindingError("ambiguous live tab matches stored project URL")

    match = matches[0]
    if match["tab_id"] == state.tab_id:
        raise BindingError("binding is not stale; live matching tab already has stored tab_id")

    now = _utc_now()
    state.tab_id = match["tab_id"].strip()
    state.conversation_url = match["url"].strip()
    state.last_used_at = now
    state.last_verified_at = now
    save(state, root=root)
    return {"binding": state.to_dict(), "previous_binding": previous.to_dict(), "matched_tab": match}


def unbind(name: str, backend: str, *, root: Path | None = None) -> bool:
    path = state_path(name, backend, root=root)
    if not path.exists():
        return False
    path.unlink()
    return True


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
        proc = subprocess.run(
            [str(surf), "tab.list"],
            cwd=surf.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        logger.error("surf tab.list failed: {}", exc)
        return state
    if proc.returncode != 0:
        return state
    seen = False
    matched_url = ""
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tid, _title, url = parts[0], parts[1], parts[2]
        if tid == state.tab_id:
            seen = True
            matched_url = url
            break
    if seen:
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
