#!/usr/bin/env python3
"""
Simple file-based inter-agent message inbox with project registry.

Usage:
    agent-inbox register PROJECT /path/to/project   # Register a project
    agent-inbox projects                            # List registered projects
    agent-inbox send --to PROJECT "message"         # Send (auto-detects --from)
    agent-inbox check                               # Check inbox (auto-detects project)
    agent-inbox list [--project PROJECT]
    agent-inbox read MSG_ID
    agent-inbox ack MSG_ID [--note "done"]
"""

import json
import os
import sys
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Literal
import hashlib

# Logging setup
logger = logging.getLogger("agent_inbox")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("AGENT_INBOX_LOG_LEVEL", "WARNING"))

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

# Model types for dispatch
ModelType = Literal["sonnet", "opus-4.5", "codex-5.2", "codex-5.2-high"]

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
        except Exception:
            pass
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
        except Exception:
            pass

    # Fallback: use directory name
    return cwd.name


def register_project(name: str, path: str) -> bool:
    """Register a project path."""
    registry = _load_registry()

    # Resolve and validate path
    project_path = Path(path).expanduser().resolve()
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
    # v2 dispatch options
    model: Optional[ModelType] = None,
    auto_spawn: bool = True,
    timeout_minutes: int = 30,
    test_command: Optional[str] = None,
    # v2 threading options
    reply_to: Optional[str] = None,
    thread_id: Optional[str] = None,
    # v2 control options
    dry_run: bool = False,
    # v2 context options
    context_files: Optional[List[str]] = None,
    # v2 triage options
    use_triage: bool = True,
    priority_override: bool = False,
) -> Optional[str]:
    """Send a message to another project's inbox.

    Args:
        to_project: Target project name
        message: Message content
        msg_type: Message type (bug, request, info, question)
        priority: Priority level (low, normal, high, critical)
        from_project: Source project (auto-detected if not provided)
        model: Model for headless dispatch (sonnet, opus-4.5, codex-5.2, codex-5.2-high)
        auto_spawn: Whether to auto-spawn agent for this message
        timeout_minutes: Timeout for headless agent
        test_command: Command to verify fix before auto-ack
        reply_to: Message ID this is replying to (for threading)
        context_files: List of file paths to include as context
        thread_id: Thread ID (auto-set from reply_to if not provided)
        dry_run: If True, print message JSON but don't write file
        use_triage: Whether to run AI triage for bug/request types (default: True)
        priority_override: If True, user's priority takes precedence over AI suggestion

    Returns:
        Message ID if sent, None if dry_run
    """
    _ensure_dirs()

    timestamp = datetime.now(timezone.utc).isoformat() + "Z"

    # Auto-detect from_project if not provided
    if not from_project:
        from_project = _detect_project() or "unknown"

    msg_id = _msg_id(to_project, timestamp, message)

    # Handle threading
    parent_id = None
    if reply_to:
        parent_msg = read_message(reply_to)
        if parent_msg:
            parent_id = reply_to
            # Inherit thread_id from parent, or use parent's id as thread root
            if not thread_id:
                thread_id = parent_msg.get("thread_id") or reply_to

    # Build dispatch config if model specified or for bug/request types
    dispatch = None
    if model or (msg_type in ("bug", "request") and auto_spawn):
        dispatch = DispatchConfig(
            model=model or "sonnet",
            auto_spawn=auto_spawn,
            timeout_minutes=timeout_minutes,
            test_command=test_command,
        )

    msg = {
        "id": msg_id,
        "to": to_project,
        "from": from_project,
        "type": msg_type,  # bug, request, info, question
        "priority": priority,  # low, normal, high, critical
        "status": "pending",
        "created_at": timestamp,
        "message": message,
    }

    # Add v2 fields if present
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
                    # Truncate very large files
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
                # Pass context data to triage
                ctx_for_triage = msg.get("context", []) if msg.get("context") else None
                triage_result = triage_mod.triage_message(message, ctx_for_triage, use_llm=True)

                # Apply AI-suggested priority if not overridden by user
                if triage_result and not priority_override:
                    suggested_priority = triage_result.get("suggested_priority")
                    if suggested_priority and suggested_priority != priority:
                        msg["priority"] = suggested_priority
                        msg["priority_source"] = "ai_triage"
                        print(f"  AI Triage: priority adjusted to '{suggested_priority}'")

                # Apply AI-suggested model if not explicitly set
                if triage_result and not model:
                    suggested_model = triage_result.get("suggested_model")
                    if suggested_model and dispatch:
                        dispatch.model = suggested_model
                        msg["dispatch"]["model"] = suggested_model
                        print(f"  AI Triage: model set to '{suggested_model}'")

                # Store triage classification in message
                if triage_result.get("classification"):
                    msg["triage"] = {
                        "severity": triage_result["classification"].get("severity"),
                        "reasoning": triage_result["classification"].get("reasoning"),
                        "complexity": triage_result["classification"].get("estimated_complexity"),
                        "affected_area": triage_result["classification"].get("affected_area"),
                    }

                # Note auto-routing suggestion (but don't override explicit --to)
                if triage_result.get("suggested_project"):
                    msg["triage_suggested_project"] = triage_result["suggested_project"]
                    if triage_result["suggested_project"] != to_project:
                        print(f"  AI Triage: suggested project '{triage_result['suggested_project']}' (using '{to_project}')")

            except Exception as e:
                print(f"  Warning: Triage failed: {e}")

    if dry_run:
        print(json.dumps(msg, indent=2))
        return None

    # Write to pending atomically
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
            except Exception:
                pass  # Triage logging is best-effort

    # Trigger webhooks for message_sent event
    if msg_type in ("bug", "request"):
        triage_mod = _get_triage_module()
        if triage_mod:
            try:
                triage_mod.trigger_webhooks("message_sent", msg)
            except Exception:
                pass  # Webhooks are fire-and-forget

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
    """Update the status of a message.

    Status progression: pending → dispatched → in_progress → needs_verification → done

    Args:
        msg_id: Message ID
        new_status: New status value
        note: Optional status note

    Returns:
        True if updated, False if message not found
    """
    _ensure_dirs()

    # Find the message in pending or done
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

            # If transitioning to done, move to done folder
            if new_status == "done" and status_dir == "pending":
                done_file = INBOX_DIR / "done" / f"{msg_id}.json"
                if not _atomic_write(done_file, json.dumps(msg, indent=2)):
                    logger.error("Failed to write done file for %s", msg_id)
                    return False
                try:
                    msg_file.unlink()
                except Exception as e:
                    logger.error("Failed to remove pending file %s: %s", msg_file, e)
                print(f"Message {msg_id}: {old_status} → {new_status} (moved to done)")
            else:
                if not _atomic_write(msg_file, json.dumps(msg, indent=2)):
                    logger.error("Failed to update message %s", msg_id)
                    return False
                print(f"Message {msg_id}: {old_status} → {new_status}")

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
                except Exception:
                    pass  # Webhooks are fire-and-forget

            return True

    print(f"Message not found: {msg_id}")
    return False


def list_thread(thread_id: str) -> List[dict]:
    """List all messages in a thread, ordered by creation time.

    Args:
        thread_id: Thread ID (usually the first message ID)

    Returns:
        List of messages in thread order
    """
    _ensure_dirs()

    messages = []

    # Search in both pending and done
    for status in ["pending", "done"]:
        status_dir = INBOX_DIR / status
        if not status_dir.exists():
            continue

        for f in status_dir.glob("*.json"):
            try:
                msg = json.loads(f.read_text())
                # Include if thread_id matches OR this is the thread root
                if msg.get("thread_id") == thread_id or msg.get("id") == thread_id:
                    messages.append(msg)
            except Exception:
                pass

    # Sort by creation time
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
        except Exception:
            pass

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

    # Find the message
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

    # Move to done atomically
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
        except Exception:
            pass  # Webhooks are fire-and-forget

    print(f"Message acknowledged: {msg_id}")
    return True


def check_inbox(project: Optional[str] = None, quiet: bool = False, all_projects: bool = False) -> int:
    """Check for pending messages. Returns count. For use in hooks."""

    # Check all registered projects
    if all_projects:
        registry = _load_registry()
        total = 0
        for proj_name in sorted(registry.keys()):
            count = check_inbox(project=proj_name, quiet=quiet)
            total += count
        if total == 0 and not quiet:
            print("No pending messages across all projects.")
        return total

    # Auto-detect project if not provided
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

    # Group by priority
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
                    # Show first line of message
                    first_line = m.get("message", "").split("\n")[0][:60]
                    print(f"    {first_line}...")
                print()

    return len(messages)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Inter-agent message inbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register projects (one-time setup)
  agent-inbox register scillm /home/user/workspace/litellm
  agent-inbox register memory /home/user/workspace/memory

  # Send a bug report (auto-detects current project as sender)
  agent-inbox send --to scillm --type bug "Bug in providers.py line 328"

  # Check inbox (auto-detects current project)
  agent-inbox check

  # Acknowledge a message
  agent-inbox ack scillm_abc123 --note "Fixed in commit xyz"
"""
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # register
    p_register = subparsers.add_parser("register", help="Register a project")
    p_register.add_argument("name", help="Project name")
    p_register.add_argument("path", help="Project path")

    # unregister
    p_unregister = subparsers.add_parser("unregister", help="Unregister a project")
    p_unregister.add_argument("name", help="Project name")

    # projects
    p_projects = subparsers.add_parser("projects", help="List registered projects")
    p_projects.add_argument("--json", action="store_true", help="Output JSON")

    # send
    p_send = subparsers.add_parser("send", help="Send a message")
    p_send.add_argument("--to", required=True, help="Target project")
    p_send.add_argument("--type", default="info", choices=["bug", "request", "info", "question"])
    p_send.add_argument("--priority", default="normal", choices=["low", "normal", "high", "critical"])
    p_send.add_argument("--from", dest="from_project", help="Source project (auto-detected)")
    # v2 dispatch options
    p_send.add_argument("--model", choices=["sonnet", "opus-4.5", "codex-5.2", "codex-5.2-high"],
                        help="Model for headless agent dispatch")
    p_send.add_argument("--timeout", type=int, default=30,
                        help="Timeout in minutes for headless agent (default: 30)")
    p_send.add_argument("--test", dest="test_command",
                        help="Command to verify fix before auto-ack")
    p_send.add_argument("--no-dispatch", action="store_true",
                        help="Disable auto-spawn for this message")
    # v2 threading options
    p_send.add_argument("--reply-to", dest="reply_to",
                        help="Message ID to reply to (for threading)")
    # Control options
    p_send.add_argument("--dry-run", action="store_true",
                        help="Print message JSON without writing file")
    p_send.add_argument("--register-path", dest="register_path",
                        help="Auto-register target project with this path before sending")
    # Context options
    p_send.add_argument("--context-file", dest="context_files", action="append",
                        help="File to include as context (can be used multiple times)")
    # Triage options
    p_send.add_argument("--no-triage", action="store_true",
                        help="Skip AI triage for this message")
    p_send.add_argument("--priority-override", action="store_true",
                        help="Keep user's priority even if AI suggests different")
    p_send.add_argument("message", nargs="?", help="Message (or read from stdin)")

    # list
    p_list = subparsers.add_parser("list", help="List messages")
    p_list.add_argument("--project", help="Filter by project (auto-detected if omitted)")
    p_list.add_argument("--all", action="store_true", help="Show all projects")
    p_list.add_argument("--status", default="pending", choices=["pending", "done"])
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    # read
    p_read = subparsers.add_parser("read", help="Read a message")
    p_read.add_argument("msg_id", help="Message ID")
    p_read.add_argument("--json", action="store_true", help="Output JSON")

    # ack
    p_ack = subparsers.add_parser("ack", help="Acknowledge a message")
    p_ack.add_argument("msg_id", help="Message ID")
    p_ack.add_argument("--note", help="Acknowledgment note")

    # check (for hooks)
    p_check = subparsers.add_parser("check", help="Check for pending messages (auto-detects project)")
    p_check.add_argument("--project", help="Project name (auto-detected if omitted)")
    p_check.add_argument("--all", action="store_true", help="Check all registered projects")
    p_check.add_argument("--quiet", "-q", action="store_true", help="Only return count")

    # whoami
    p_whoami = subparsers.add_parser("whoami", help="Show detected project for current directory")

    # v2: update-status
    p_update = subparsers.add_parser("update-status", help="Update message status")
    p_update.add_argument("msg_id", help="Message ID")
    p_update.add_argument("status", choices=["pending", "dispatched", "in_progress", "needs_verification", "done"])
    p_update.add_argument("--note", help="Status note")

    # v2: reply
    p_reply = subparsers.add_parser("reply", help="Reply to a message (creates threaded response)")
    p_reply.add_argument("msg_id", help="Message ID to reply to")
    p_reply.add_argument("message", nargs="?", help="Reply message (or read from stdin)")
    p_reply.add_argument("--type", default="info", choices=["bug", "request", "info", "question"])
    p_reply.add_argument("--priority", default="normal", choices=["low", "normal", "high", "critical"])
    p_reply.add_argument("--model", choices=["sonnet", "opus-4.5", "codex-5.2", "codex-5.2-high"])

    # v2: thread
    p_thread = subparsers.add_parser("thread", help="List messages in a thread")
    p_thread.add_argument("thread_id", help="Thread ID (usually first message ID)")
    p_thread.add_argument("--json", action="store_true", help="Output JSON")

    # v2: triage
    p_triage = subparsers.add_parser("triage", help="Manual triage operations")
    p_triage.add_argument("action", choices=["classify", "route", "webhook-add", "webhook-remove", "webhook-list", "log"])
    p_triage.add_argument("--message", help="Message to triage")
    p_triage.add_argument("--msg-id", help="Message ID for log retrieval")
    p_triage.add_argument("--url", help="Webhook URL")
    p_triage.add_argument("--events", help="Comma-separated webhook events")
    p_triage.add_argument("--project", help="Project filter for webhook")
    p_triage.add_argument("--no-llm", action="store_true", help="Use heuristics only")
    p_triage.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if args.command == "register":
        register_project(args.name, args.path)

    elif args.command == "unregister":
        unregister_project(args.name)

    elif args.command == "projects":
        projects = list_projects()
        if getattr(args, 'json', False):
            print(json.dumps(projects, indent=2))
        else:
            if not projects:
                print("No projects registered.")
                print("Use: agent-inbox register <name> <path>")
            else:
                print("Registered projects:")
                for name, path in sorted(projects.items()):
                    print(f"  {name}: {path}")

    elif args.command == "send":
        message = args.message
        if not message:
            message = sys.stdin.read().strip()
        if not message:
            print("Error: No message provided")
            sys.exit(1)

        # Auto-register project if --register-path provided
        if getattr(args, 'register_path', None):
            register_project(args.to, args.register_path)

        send(
            args.to,
            message,
            msg_type=args.type,
            priority=args.priority,
            from_project=args.from_project,
            model=args.model,
            auto_spawn=not getattr(args, 'no_dispatch', False),
            timeout_minutes=args.timeout,
            test_command=args.test_command,
            reply_to=args.reply_to,
            dry_run=getattr(args, 'dry_run', False),
            context_files=getattr(args, 'context_files', None),
            use_triage=not getattr(args, 'no_triage', False),
            priority_override=getattr(args, 'priority_override', False),
        )

    elif args.command == "list":
        project = None if getattr(args, 'all', False) else (args.project or _detect_project())
        messages = list_messages(project=project, status=args.status)
        if getattr(args, 'json', False):
            print(json.dumps(messages, indent=2))
        else:
            if not messages:
                print(f"No {args.status} messages." + (f" (project: {project})" if project else ""))
            else:
                for m in messages:
                    status_icon = "📬" if m.get("status") == "pending" else "✅"
                    priority_icon = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "⚪"}.get(m.get("priority", "normal"), "🟡")
                    print(f"{status_icon} {priority_icon} [{m['id']}] {m.get('type', 'info')}: {m.get('from', '?')} → {m.get('to', '?')}")
                    first_line = m.get("message", "").split("\n")[0][:50]
                    print(f"      {first_line}...")

    elif args.command == "read":
        msg = read_message(args.msg_id)
        if not msg:
            print(f"Message not found: {args.msg_id}")
            sys.exit(1)
        if getattr(args, 'json', False):
            print(json.dumps(msg, indent=2))
        else:
            print(f"ID: {msg['id']}")
            print(f"From: {msg.get('from', '?')} → To: {msg.get('to', '?')}")
            print(f"Type: {msg.get('type', 'info')} | Priority: {msg.get('priority', 'normal')}")
            print(f"Status: {msg.get('status', '?')}")
            print(f"Created: {msg.get('created_at', '?')}")
            if msg.get("acked_at"):
                print(f"Acked: {msg.get('acked_at')}")
            if msg.get("ack_note"):
                print(f"Note: {msg.get('ack_note')}")
            print()
            print("--- Message ---")
            print(msg.get("message", ""))

    elif args.command == "ack":
        ack_message(args.msg_id, note=args.note)

    elif args.command == "check":
        count = check_inbox(project=args.project, quiet=args.quiet, all_projects=getattr(args, 'all', False))
        if args.quiet:
            print(count)
        sys.exit(0 if count == 0 else 1)

    elif args.command == "whoami":
        project = _detect_project()
        registry = _load_registry()
        if project in registry:
            print(f"Project: {project}")
            print(f"Path: {registry[project]}")
        else:
            print(f"Project: {project} (not registered)")
            print(f"Current dir: {Path.cwd()}")
            print()
            print("To register: agent-inbox register {project} {Path.cwd()}")

    elif args.command == "update-status":
        update_status(args.msg_id, args.status, note=args.note)

    elif args.command == "reply":
        # Get the parent message to find target project
        parent = read_message(args.msg_id)
        if not parent:
            print(f"Parent message not found: {args.msg_id}")
            sys.exit(1)

        message = args.message
        if not message:
            message = sys.stdin.read().strip()
        if not message:
            print("Error: No message provided")
            sys.exit(1)

        # Reply goes TO the original sender (swap to/from)
        send(
            parent.get("from", parent.get("to")),
            message,
            msg_type=args.type,
            priority=args.priority,
            model=args.model,
            reply_to=args.msg_id,
        )

    elif args.command == "thread":
        messages = list_thread(args.thread_id)
        if getattr(args, 'json', False):
            print(json.dumps(messages, indent=2))
        else:
            if not messages:
                print(f"No messages found in thread: {args.thread_id}")
            else:
                print(f"=== Thread: {args.thread_id} ({len(messages)} messages) ===")
                print()
                for i, m in enumerate(messages):
                    indent = "  " if m.get("parent_id") else ""
                    arrow = "↳ " if m.get("parent_id") else ""
                    print(f"{indent}{arrow}[{m['id']}] {m.get('from', '?')} → {m.get('to', '?')}")
                    print(f"{indent}  {m.get('type', 'info')} | {m.get('priority', 'normal')} | {m.get('status', '?')}")
                    print(f"{indent}  {m.get('created_at', '?')}")
                    first_line = m.get("message", "").split("\n")[0][:60]
                    print(f"{indent}  {first_line}...")
                    print()

    elif args.command == "triage":
        triage_mod = _get_triage_module()
        if not triage_mod:
            print("Error: Triage module not available")
            sys.exit(1)

        if args.action == "classify":
            if not args.message:
                print("Error: --message required for classify")
                sys.exit(1)
            result = triage_mod.triage_message(args.message, use_llm=not args.no_llm)
            if getattr(args, 'json', False):
                print(json.dumps(result, indent=2))
            else:
                cls = result.get("classification", {})
                print(f"Severity: {cls.get('severity', 'unknown')}")
                print(f"Priority: {result.get('suggested_priority', 'normal')}")
                print(f"Model: {result.get('suggested_model', 'sonnet')}")
                print(f"Reasoning: {cls.get('reasoning', 'N/A')}")
                if result.get("suggested_project"):
                    print(f"Suggested Project: {result['suggested_project']}")

        elif args.action == "route":
            if not args.message:
                print("Error: --message required for route")
                sys.exit(1)
            project = triage_mod.auto_route(args.message)
            if project:
                print(f"Suggested project: {project}")
            else:
                print("Could not auto-detect project from message")

        elif args.action == "webhook-add":
            if not args.url:
                print("Error: --url required")
                sys.exit(1)
            events = args.events.split(",") if args.events else None
            triage_mod.register_webhook(args.url, events, args.project)
            print(f"Webhook registered: {args.url}")

        elif args.action == "webhook-remove":
            if not args.url:
                print("Error: --url required")
                sys.exit(1)
            if triage_mod.unregister_webhook(args.url):
                print(f"Webhook removed: {args.url}")
            else:
                print("Webhook not found")

        elif args.action == "webhook-list":
            webhooks = triage_mod._load_webhooks()
            if webhooks:
                for wh in webhooks:
                    print(f"  {wh['url']}")
                    print(f"    Events: {wh.get('events', ['all'])}")
                    if wh.get('project'):
                        print(f"    Project: {wh['project']}")
            else:
                print("No webhooks registered")

        elif args.action == "log":
            if not args.msg_id:
                print("Error: --msg-id required for log")
                sys.exit(1)
            log = triage_mod.get_triage_log(args.msg_id)
            if log:
                if getattr(args, 'json', False):
                    print(json.dumps(log, indent=2))
                else:
                    print(f"Message ID: {log.get('msg_id')}")
                    print(f"Timestamp: {log.get('timestamp')}")
                    cls = log.get("classification", {})
                    print(f"Severity: {cls.get('severity')}")
                    print(f"Reasoning: {cls.get('reasoning')}")
                    routing = log.get("routing", {})
                    print(f"Routed to: {routing.get('target_project')} ({routing.get('method')})")
            else:
                print(f"No triage log found for: {args.msg_id}")


if __name__ == "__main__":
    main()
