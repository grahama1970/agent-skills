"""Per-project WebGPT tab binding.

A project (any short name like "code-runner-review", "sparta-architecture",
or "pr-1234") maps to one controlled ChatGPT tab so iterative oracle calls
form a coherent conversation thread per project.

State lives under ~/.pi/webgpt-projects/<sanitized-name>.json:

  {
    "name": "code-runner-review",
    "tab_id": "837343543",
    "conversation_url": "https://chatgpt.com/c/...",
    "bound_manually": true,
    "created_at": "2026-05-11T17:30:00Z",
    "last_used_at": "2026-05-11T19:45:12Z",
    "last_verified_at": "2026-05-11T19:45:12Z"
  }

Two workflows:

1. Manual bind (long-lived projects you want to babysit):
     webgpt-project bind code-runner-review --tab-id 837343543
   Sets bound_manually=true; the agent will never auto-replace this tab even
   if it appears closed (it raises a clear error so the human can re-bind).

2. Autonomous create (ephemeral tasks):
     $ask webgpt --webgpt-project pr-1234 …
   First call creates a background tab and records it; subsequent calls
   reuse it. If the tab is gone, the runtime auto-creates a new one and
   updates the binding.
"""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Default project-state root. Overridable via env for tests / alternate users.
DEFAULT_PROJECT_ROOT = Path(
    os.environ.get(
        "ASK_WEBGPT_PROJECT_ROOT",
        str(Path.home() / ".pi" / "webgpt-projects"),
    )
)

# Filename-safe project-name characters.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class ProjectState:
    name: str
    tab_id: str = ""
    conversation_url: str = ""
    bound_manually: bool = False
    created_at: str = ""
    last_used_at: str = ""
    last_verified_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectBindingError(RuntimeError):
    """Raised when a manually-bound tab is missing and must not be replaced."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitize_name(name: str) -> str:
    """Conservative filename sanitisation; no whitespace, no path separators."""
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
            # Don't crash listing on a single corrupt file.
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
    return ProjectState(
        **{k: data.get(k, "") for k in ProjectState.__dataclass_fields__}
    )


def save(state: ProjectState, *, root: Path | None = None) -> Path:
    path = project_state_path(state.name, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
    tmp.replace(path)
    return path


def bind(
    name: str,
    tab_id: str,
    *,
    conversation_url: str = "",
    manual: bool = False,
    root: Path | None = None,
) -> ProjectState:
    """Create or update a project's tab binding.

    `manual=True` marks this as human-curated; auto flows will refuse to
    replace it silently.
    """
    if not tab_id or not str(tab_id).strip():
        raise ValueError("tab_id is required to bind a project")
    sanitised = _sanitize_name(name)
    existing = load(sanitised, root=root)
    now = _utc_now()
    state = existing or ProjectState(name=sanitised, created_at=now)
    state.name = sanitised
    state.tab_id = str(tab_id).strip()
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


def update_last_used(name: str, *, root: Path | None = None) -> None:
    state = load(name, root=root)
    if not state:
        return
    state.last_used_at = _utc_now()
    save(state, root=root)


def verify(
    name: str,
    surf_run: Path,
    *,
    root: Path | None = None,
    timeout: float = 15.0,
) -> ProjectState | None:
    """Return the project state iff its tab is still open in Chrome.

    Returns None when the project is unknown OR the tab has been closed.
    Callers should treat None as "(re)create a tab on the next call."

    For manually-bound projects whose tab has been closed, raises
    ProjectBindingError so the human is asked to re-bind rather than letting
    the agent silently start a new conversation.
    """
    state = load(name, root=root)
    if not state or not state.tab_id:
        return None
    try:
        proc = subprocess.run(
            [str(surf_run), "tab.list"],
            cwd=Path(surf_run).parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        # Don't invalidate state on transient surf failures.
        return state
    if proc.returncode != 0:
        return state
    seen = False
    matched_url = ""
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        tab_id, _title, url = parts[0], parts[1], parts[2]
        if tab_id == state.tab_id:
            seen = True
            matched_url = url
            break
    if seen:
        # Refresh conversation_url if ChatGPT moved from "/" to "/c/<id>".
        if matched_url and matched_url != state.conversation_url:
            state.conversation_url = matched_url
        state.last_verified_at = _utc_now()
        save(state, root=root)
        return state
    if state.bound_manually:
        raise ProjectBindingError(
            f"Project '{state.name}' is manually bound to tab {state.tab_id}, "
            "but that tab is no longer open in Chrome. Re-bind explicitly:\n"
            f"  webgpt-project bind {state.name} --tab-id <new-id>\n"
            "Or pass --webgpt-create-tab once to acquire a fresh background "
            "tab (which will overwrite the manual binding)."
        )
    return None


def gc_stale(*, days: int = 30, root: Path | None = None) -> list[str]:
    """Remove auto-bound projects whose last_used_at is older than `days`.

    Manually-bound projects are never garbage-collected.
    """
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
