"""Per-project Cursor Browser viewId bindings for /ask cursor-browser.

State: ~/.pi/cursor-browser-projects/<name>.json
  {
    "name": "sparta-cursor",
    "view_id": "f53e74",
    "conversation_url": "https://chatgpt.com/c/...",
    "bound_manually": true,
    ...
  }

viewId is NOT a Chrome tab id. Get it from Cursor browser_tabs list or
`surf cursor-browser.tab.list`.
"""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROJECT_ROOT = Path(
    os.environ.get(
        "ASK_CURSOR_BROWSER_PROJECT_ROOT",
        str(Path.home() / ".pi" / "cursor-browser-projects"),
    )
)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class ProjectState:
    name: str
    view_id: str = ""
    conversation_url: str = ""
    bound_manually: bool = False
    created_at: str = ""
    last_used_at: str = ""
    last_verified_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectBindingError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitize_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("-", str(name).strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    if not cleaned:
        raise ValueError(f"Project name {name!r} sanitises to empty string")
    return cleaned[:128]


def project_state_path(name: str, *, root: Path | None = None) -> Path:
    root = root or DEFAULT_PROJECT_ROOT
    return Path(root) / f"{_sanitize_name(name)}.json"


def list_projects(*, root: Path | None = None) -> list[ProjectState]:
    root = root or DEFAULT_PROJECT_ROOT
    if not root.exists():
        return []
    out: list[ProjectState] = []
    for p in sorted(root.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            out.append(ProjectState(**{k: data.get(k, "") for k in ProjectState.__dataclass_fields__}))
        except Exception:
            continue
    return out


def load(name: str, *, root: Path | None = None) -> ProjectState | None:
    path = project_state_path(name, root=root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return ProjectState(**{k: data.get(k, "") for k in ProjectState.__dataclass_fields__})


def save(state: ProjectState, *, root: Path | None = None) -> Path:
    path = project_state_path(state.name, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
    tmp.replace(path)
    return path


def bind(
    name: str,
    view_id: str,
    *,
    conversation_url: str = "",
    manual: bool = False,
    root: Path | None = None,
) -> ProjectState:
    if not view_id or not str(view_id).strip():
        raise ValueError("view_id is required to bind a project")
    sanitised = _sanitize_name(name)
    existing = load(sanitised, root=root)
    now = _utc_now()
    state = existing or ProjectState(name=sanitised, created_at=now)
    state.name = sanitised
    state.view_id = str(view_id).strip()
    if conversation_url:
        state.conversation_url = conversation_url
    if manual:
        state.bound_manually = True
    state.last_used_at = now
    state.last_verified_at = now
    if not state.created_at:
        state.created_at = now
    save(state, root=root)
    return state


def unbind(name: str, *, root: Path | None = None) -> bool:
    path = project_state_path(name, root=root)
    if not path.exists():
        return False
    path.unlink()
    return True


def verify(name: str, surf_run: Path | None = None, *, root: Path | None = None, timeout: float = 15.0) -> ProjectState | None:
    """Return project state iff view_id still appears in Cursor browser tab list."""
    from .ask_config import SURF_RUN

    state = load(name, root=root)
    if not state or not state.view_id:
        return None
    surf = surf_run or Path(SURF_RUN)
    try:
        import json
        import subprocess

        proc = subprocess.run(
            [str(surf), "cursor-browser.tab.list", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=surf.parent,
        )
        if proc.returncode != 0:
            return state
        tabs = json.loads(proc.stdout)
        if not isinstance(tabs, list):
            return state
    except Exception:
        return state
    seen = False
    matched_url = ""
    for tab in tabs:
        if tab.get("viewId") == state.view_id:
            seen = True
            matched_url = tab.get("url", "")
            break
    if seen:
        if matched_url and matched_url != state.conversation_url:
            state.conversation_url = matched_url
        state.last_verified_at = _utc_now()
        save(state, root=root)
        return state
    if state.bound_manually:
        raise ProjectBindingError(
            f"Project '{state.name}' is manually bound to viewId {state.view_id}, "
            "but that tab is no longer open in Cursor Browser. Re-bind:\n"
            f"  cursor-browser-project bind {state.name} --view-id <new-view-id>"
        )
    return None


def gc_stale(*, days: int = 30, root: Path | None = None) -> list[str]:
    if days <= 0:
        return []
    cutoff = time.time() - days * 86400
    removed: list[str] = []
    for state in list_projects(root=root):
        if state.bound_manually:
            continue
        try:
            last = state.last_used_at.replace("Z", "+00:00")
            ts = datetime.fromisoformat(last).timestamp() if last else 0.0
        except Exception:
            ts = 0.0
        if ts and ts < cutoff:
            unbind(state.name, root=root)
            removed.append(state.name)
    return removed
