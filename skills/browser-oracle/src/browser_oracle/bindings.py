"""Machine-local tab bindings under ~/.pi/*-projects/."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
