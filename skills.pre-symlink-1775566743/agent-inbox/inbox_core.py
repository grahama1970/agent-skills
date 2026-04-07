"""
Agent-Inbox Core - Registry, message CRUD, threading, and helpers.

Contains all core inbox operations: registry management, message send/read/ack,
status updates, threading, and project scanning.
"""

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Literal
import hashlib

from loguru import logger

# Lazy import for task-monitor client (avoid circular imports)
_task_monitor_client = None
_triage_module = None


def _get_task_monitor_client():
    """Lazy load task-monitor client."""
    global _task_monitor_client
    if _task_monitor_client is None:
        try:
            from . import task_monitor_client as tmc
            _task_monitor_client = tmc
        except ImportError:
            try:
                import task_monitor_client as tmc
                _task_monitor_client = tmc
            except ImportError:
                _task_monitor_client = False  # Mark as unavailable
    return _task_monitor_client if _task_monitor_client else None


def _get_triage_module():
    """Lazy load triage module."""
    global _triage_module
    if _triage_module is None:
        try:
            from . import triage
            _triage_module = triage
        except ImportError:
            try:
                import triage
                _triage_module = triage
            except ImportError:
                _triage_module = False  # Mark as unavailable
    return _triage_module if _triage_module else None

# Model types for dispatch (now dynamic)
ModelType = str

# Message status progression
MessageStatus = Literal["pending", "dispatched", "in_progress", "needs_verification", "done"]


@dataclass
class DispatchConfig:
    """Configuration for headless agent dispatch."""
    model: ModelType = "sonnet"
    auto_spawn: bool = True
    timeout_minutes: int = 30
    test_command: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "DispatchConfig":
        if not data:
            return cls()
        return cls(
            model=data.get("model", "sonnet"),
            auto_spawn=data.get("auto_spawn", True),
            timeout_minutes=data.get("timeout_minutes", 30),
            test_command=data.get("test_command"),
        )

INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
REGISTRY_FILE = INBOX_DIR / "projects.json"


def _ensure_dirs():
    """Ensure inbox directory structure exists."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    (INBOX_DIR / "pending").mkdir(exist_ok=True)
    (INBOX_DIR / "done").mkdir(exist_ok=True)


def _atomic_write(path: Path, data: str) -> bool:
    """Write atomically to a file to reduce race conditions."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data)
        tmp.replace(path)  # Atomic on POSIX systems
        return True
    except Exception as e:
        logger.error("Atomic write failed for %s: %s", path, e)
        return False


def _load_registry() -> Dict[str, str]:
    """Load project registry."""
    _ensure_dirs()
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text())
        except Exception as e:
            logger.debug("JSON parse failed: {}", e)
    return {}


def _save_registry(registry: Dict[str, str]):
    """Save project registry."""
    _ensure_dirs()
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, sort_keys=True))


def _detect_project(cwd: Optional[Path] = None) -> Optional[str]:
    """Detect current project from working directory."""
    cwd = cwd or Path.cwd()
    registry = _load_registry()

    # Check if cwd is inside any registered project
    for name, path in registry.items():
        try:
            project_path = Path(path).resolve()
            if cwd.resolve().is_relative_to(project_path):
                return name
        except Exception as e:
            logger.debug("resolution failed: {}", e)

    # Fallback: use directory name
    return cwd.name


_BLOCKED_PATH_SEGMENTS = {"node_modules", "site-packages", ".venv", "venv", "dist", "vendor"}


def register_project(name: str, path: str) -> bool:
    """Register a project path. Rejects node_modules and similar non-project paths."""
    project_path = Path(path).expanduser().resolve()
    if _BLOCKED_PATH_SEGMENTS & set(project_path.parts):
        print(f"Blocked: {name} -> {project_path} (contains {_BLOCKED_PATH_SEGMENTS & set(project_path.parts)})")
        return False
    registry = _load_registry()
    if not project_path.exists():
        print(f"Warning: Path does not exist: {project_path}")
    registry[name] = str(project_path)
    _save_registry(registry)
    print(f"Registered: {name} -> {project_path}")
    return True


def unregister_project(name: str) -> bool:
    """Unregister a project."""
    registry = _load_registry()
    if name not in registry:
        print(f"Project not registered: {name}")
        return False
    del registry[name]
    _save_registry(registry)
    print(f"Unregistered: {name}")
    return True


def list_projects() -> Dict[str, str]:
    """List all registered projects."""
    return _load_registry()


def _msg_id(project: str, timestamp: str, content: str) -> str:
    """Generate short message ID."""
    h = hashlib.sha256(f"{project}{timestamp}{content}".encode()).hexdigest()[:8]
    return f"{project}_{h}"


def send(
    to_project: str,
    message: str,
    msg_type: str = "info",
    priority: str = "normal",
    from_project: Optional[str] = None,
    model: Optional[ModelType] = None,
    auto_spawn: bool = True,
    timeout_minutes: int = 30,
    test_command: Optional[str] = None,
    reply_to: Optional[str] = None,
    thread_id: Optional[str] = None,
    dry_run: bool = False,
    context_files: Optional[List[str]] = None,
    use_triage: bool = True,
    priority_override: bool = False,
) -> Optional[str]:
    """Send a message to another project's inbox."""
    _ensure_dirs()

    timestamp = datetime.now(timezone.utc).isoformat() + "Z"

    if not from_project:
        from_project = _detect_project() or "unknown"

    msg_id = _msg_id(to_project, timestamp, message)

    # Handle threading
    parent_id = None
    if reply_to:
        parent_msg = read_message(reply_to)
        if parent_msg:
            parent_id = reply_to
            if not thread_id:
                thread_id = parent_msg.get("thread_id") or reply_to

    # Build dispatch config if model specified or for bug/request types
    dispatch = None
    if auto_spawn and msg_type in ("bug", "request"):
        selected_model = model
        if not selected_model:
             defaults_file = INBOX_DIR / "project_defaults.json"
             if defaults_file.exists():
                 try:
                     defaults = json.loads(defaults_file.read_text())
                     selected_model = defaults.get(to_project)
                 except Exception as e:
                     logger.debug("value lookup failed: {}", e)
        if not selected_model:
            selected_model = "sonnet"

        dispatch = DispatchConfig(
            model=selected_model,
            auto_spawn=auto_spawn,
            timeout_minutes=timeout_minutes,
            test_command=test_command,
        )

    msg = {
        "id": msg_id,
        "to": to_project,
        "from": from_project,
        "type": msg_type,
        "priority": priority,
        "status": "pending",
        "created_at": timestamp,
        "message": message,
    }

    if dispatch:
        msg["dispatch"] = dispatch.to_dict()
    if thread_id:
        msg["thread_id"] = thread_id
    if parent_id:
        msg["parent_id"] = parent_id

    # Add context files if provided
    if context_files:
        context_data = []
        for file_path in context_files:
            try:
                path = Path(file_path).expanduser()
                if path.exists():
                    content = path.read_text()
                    if len(content) > 50000:
                        content = content[:50000] + "\n... (truncated)"
                    context_data.append({
                        "file": str(path.name),
                        "path": str(path),
                        "content": content,
                    })
                    print(f"  Context: {path.name} ({len(content)} chars)")
                else:
                    print(f"  Warning: Context file not found: {file_path}")
            except Exception as e:
                print(f"  Warning: Could not read {file_path}: {e}")
        if context_data:
            msg["context"] = context_data

    # Run AI triage for bug/request types
    triage_result = None
    if use_triage and msg_type in ("bug", "request"):
        triage_mod = _get_triage_module()
        if triage_mod:
            try:
                ctx_for_triage = msg.get("context", []) if msg.get("context") else None
                triage_result = triage_mod.triage_message(message, ctx_for_triage, use_llm=True)

                if triage_result and not priority_override:
                    suggested_priority = triage_result.get("suggested_priority")
                    if suggested_priority and suggested_priority != priority:
                        msg["priority"] = suggested_priority
                        msg["priority_source"] = "ai_triage"
                        print(f"  AI Triage: priority adjusted to '{suggested_priority}'")

                if triage_result and not model:
                    suggested_model = triage_result.get("suggested_model")
                    if suggested_model and dispatch:
                        dispatch.model = suggested_model
                        msg["dispatch"]["model"] = suggested_model
                        print(f"  AI Triage: model set to '{suggested_model}'")

                if triage_result.get("classification"):
                    msg["triage"] = {
                        "severity": triage_result["classification"].get("severity"),
                        "reasoning": triage_result["classification"].get("reasoning"),
                        "complexity": triage_result["classification"].get("estimated_complexity"),
                        "affected_area": triage_result["classification"].get("affected_area"),
                    }

                if triage_result.get("suggested_project"):
                    msg["triage_suggested_project"] = triage_result["suggested_project"]
                    if triage_result["suggested_project"] != to_project:
                        print(f"  AI Triage: suggested project '{triage_result['suggested_project']}' (using '{to_project}')")

            except Exception as e:
                print(f"  Warning: Triage failed: {e}")

    if dry_run:
        print(json.dumps(msg, indent=2))
        return None

    msg_file = INBOX_DIR / "pending" / f"{msg_id}.json"
    if not _atomic_write(msg_file, json.dumps(msg, indent=2)):
        logger.error("Failed to write message %s", msg_id)
        return None

    # Log triage decision for audit trail
    if triage_result and msg_type in ("bug", "request"):
        triage_mod = _get_triage_module()
        if triage_mod:
            try:
                triage_mod.log_triage(
                    msg_id,
                    triage_result.get("classification", {}),
                    routing=to_project,
                    manual_override=priority_override,
                )
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

    # Trigger webhooks for message_sent event
    if msg_type in ("bug", "request"):
        triage_mod = _get_triage_module()
        if triage_mod:
            try:
                triage_mod.trigger_webhooks("message_sent", msg)
            except Exception as e:
                logger.debug("triage_mod failed: {}", e)

    # Register with task-monitor for bug/request types with dispatch config
    task_name = None
    if dispatch and msg_type in ("bug", "request"):
        tmc = _get_task_monitor_client()
        if tmc:
            task_name = tmc.register_bug_fix_task(msg)

    print(f"Message sent: {msg_id}")
    print(f"  From: {from_project} -> To: {to_project}")
    print(f"  Type: {msg_type} ({priority})")
    if dispatch:
        print(f"  Model: {dispatch.model} (auto_spawn={dispatch.auto_spawn})")
    if task_name:
        print(f"  Task-monitor: {task_name}")
    if thread_id:
        print(f"  Thread: {thread_id}")

    return msg_id


def update_status(msg_id: str, new_status: MessageStatus, note: Optional[str] = None) -> bool:
    """Update the status of a message."""
    _ensure_dirs()

    for status_dir in ["pending", "done"]:
        msg_file = INBOX_DIR / status_dir / f"{msg_id}.json"
        if msg_file.exists():
            try:
                msg = json.loads(msg_file.read_text())
            except Exception as e:
                logger.error("Failed to read message %s: %s", msg_id, e)
                continue
            old_status = msg.get("status")
            msg["status"] = new_status
            msg["status_updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"

            if note:
                if "status_notes" not in msg:
                    msg["status_notes"] = []
                msg["status_notes"].append({
                    "status": new_status,
                    "note": note,
                    "at": msg["status_updated_at"]
                })

            if new_status == "done" and status_dir == "pending":
                done_file = INBOX_DIR / "done" / f"{msg_id}.json"
                if not _atomic_write(done_file, json.dumps(msg, indent=2)):
                    logger.error("Failed to write done file for %s", msg_id)
                    return False
                try:
                    msg_file.unlink()
                except Exception as e:
                    logger.error("Failed to remove pending file %s: %s", msg_file, e)
                print(f"Message {msg_id}: {old_status} -> {new_status} (moved to done)")
            else:
                if not _atomic_write(msg_file, json.dumps(msg, indent=2)):
                    logger.error("Failed to update message %s", msg_id)
                    return False
                print(f"Message {msg_id}: {old_status} -> {new_status}")

            # Update task-monitor if this message has dispatch config
            if msg.get("dispatch"):
                task_name = f"bug-fix-{msg_id}"
                tmc = _get_task_monitor_client()
                if tmc:
                    details = {
                        "current_item": note or f"Status: {new_status}",
                        "stats": {
                            "from_project": msg.get("from"),
                            "to_project": msg.get("to"),
                            "model": msg.get("dispatch", {}).get("model", "sonnet"),
                        }
                    }
                    if new_status == "done":
                        tmc.complete_task(task_name, success=True, note=note or "")
                    else:
                        tmc.update_task_progress(task_name, new_status, details)

            # Trigger webhooks for status_changed event
            triage_mod = _get_triage_module()
            if triage_mod:
                try:
                    webhook_data = {
                        "msg_id": msg_id,
                        "old_status": old_status,
                        "new_status": new_status,
                        "to": msg.get("to"),
                        "from": msg.get("from"),
                        "type": msg.get("type"),
                        "note": note,
                    }
                    triage_mod.trigger_webhooks("status_changed", webhook_data)
                except Exception as e:
                    logger.debug("value lookup failed: {}", e)

            return True

    print(f"Message not found: {msg_id}")
    return False


def save_message(message: dict) -> bool:
    """Save/Update a message content directly (e.g. for retries)."""
    _ensure_dirs()
    msg_id = message.get("id")
    if not msg_id:
        logger.error("Cannot save message without ID")
        return False
    status = message.get("status", "pending")
    status_dir = "done" if status == "done" else "pending"
    msg_file = INBOX_DIR / status_dir / f"{msg_id}.json"
    if not _atomic_write(msg_file, json.dumps(message, indent=2)):
        logger.error("Failed to save message %s", msg_id)
        return False
    return True


def list_thread(thread_id: str) -> List[dict]:
    """List all messages in a thread, ordered by creation time."""
    _ensure_dirs()
    messages = []
    for status in ["pending", "done"]:
        status_dir = INBOX_DIR / status
        if not status_dir.exists():
            continue
        for f in status_dir.glob("*.json"):
            try:
                msg = json.loads(f.read_text())
                if msg.get("thread_id") == thread_id or msg.get("id") == thread_id:
                    messages.append(msg)
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
    messages.sort(key=lambda m: m.get("created_at", ""))
    return messages


def list_messages(project: Optional[str] = None, status: str = "pending"):
    """List messages, optionally filtered by project."""
    _ensure_dirs()
    status_dir = INBOX_DIR / status
    if not status_dir.exists():
        return []
    messages = []
    for f in sorted(status_dir.glob("*.json")):
        try:
            msg = json.loads(f.read_text())
            if project is None or msg.get("to") == project:
                messages.append(msg)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    return messages


def read_message(msg_id: str) -> Optional[dict]:
    """Read a specific message by ID."""
    _ensure_dirs()
    for status in ["pending", "done"]:
        msg_file = INBOX_DIR / status / f"{msg_id}.json"
        if msg_file.exists():
            try:
                return json.loads(msg_file.read_text())
            except json.JSONDecodeError as e:
                logger.error("Failed to parse message %s: %s", msg_id, e)
            except Exception as e:
                logger.error("Failed to read message %s: %s", msg_id, e)
    return None


def ack_message(msg_id: str, note: Optional[str] = None, status: str = "done"):
    """Acknowledge/complete a message."""
    _ensure_dirs()
    pending_file = INBOX_DIR / "pending" / f"{msg_id}.json"
    if not pending_file.exists():
        print(f"Message not found: {msg_id}")
        return False

    try:
        msg = json.loads(pending_file.read_text())
    except Exception as e:
        logger.error("Failed to read pending message %s: %s", msg_id, e)
        print(f"Error reading message: {msg_id}")
        return False

    msg["status"] = status
    msg["acked_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    if note:
        msg["ack_note"] = note

    done_file = INBOX_DIR / "done" / f"{msg_id}.json"
    if not _atomic_write(done_file, json.dumps(msg, indent=2)):
        logger.error("Failed to write done file for %s", msg_id)
        return False
    try:
        pending_file.unlink()
    except Exception as e:
        logger.error("Failed to remove pending file %s: %s", pending_file, e)

    # Trigger webhooks for message_acked event
    triage_mod = _get_triage_module()
    if triage_mod:
        try:
            webhook_data = {
                "msg_id": msg_id,
                "to": msg.get("to"),
                "from": msg.get("from"),
                "type": msg.get("type"),
                "ack_note": note,
            }
            triage_mod.trigger_webhooks("message_acked", webhook_data)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    print(f"Message acknowledged: {msg_id}")
    return True


def check_inbox(project: Optional[str] = None, quiet: bool = False, all_projects: bool = False) -> int:
    """Check for pending messages. Returns count. For use in hooks."""
    if all_projects:
        registry = _load_registry()
        total = 0
        for proj_name in sorted(registry.keys()):
            count = check_inbox(project=proj_name, quiet=quiet)
            total += count
        if total == 0 and not quiet:
            print("No pending messages across all projects.")
        return total

    if not project:
        project = _detect_project()

    messages = list_messages(project=project, status="pending")

    if not messages:
        if not quiet:
            if project:
                print(f"No pending messages for {project}.")
            else:
                print("No pending messages.")
        return 0

    critical = [m for m in messages if m.get("priority") == "critical"]
    high = [m for m in messages if m.get("priority") == "high"]
    normal = [m for m in messages if m.get("priority") in ("normal", None)]
    low = [m for m in messages if m.get("priority") == "low"]

    if not quiet:
        print(f"=== {len(messages)} pending message(s) for {project} ===")
        print()
        for priority_name, msgs in [("CRITICAL", critical), ("HIGH", high),
                                      ("NORMAL", normal), ("LOW", low)]:
            if msgs:
                print(f"[{priority_name}]")
                for m in msgs:
                    print(f"  {m['id']}: {m.get('type', 'info')} from {m.get('from', '?')}")
                    first_line = m.get("message", "").split("\n")[0][:60]
                    print(f"    {first_line}...")
                print()

    return len(messages)


def scan_projects(root_path: Path, max_depth: int = 2) -> List[str]:
    """Scan directory for projects and register them."""
    full_path = root_path.resolve()
    if not full_path.exists():
        print(f"Error: Path not found: {full_path}")
        return []

    registered = []
    print(f"Scanning {full_path} (max depth {max_depth})...")

    for i, path in enumerate(full_path.rglob("*")):
        try:
            rel = path.relative_to(full_path)
            if len(rel.parts) > max_depth:
                continue
        except ValueError:
            continue

        if not path.is_dir():
            continue

        if any(p in ("node_modules", "site-packages", "venv", ".venv", "dist", "build", "target", "vendor") for p in path.parts):
            continue

        is_project = (path / "package.json").exists() or \
                     (path / "pyproject.toml").exists() or \
                     (path / ".git").exists()

        if is_project:
            name = path.name
            if name.startswith(".") and name != ".":
                continue
            projects = list_projects()
            if name not in projects:
                register_project(name, str(path))
                registered.append(name)
                print(f"  [+] Registered: {name} -> {path}")

    return registered
