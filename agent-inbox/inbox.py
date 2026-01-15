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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict
import hashlib

INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
REGISTRY_FILE = INBOX_DIR / "projects.json"


def _ensure_dirs():
    """Ensure inbox directory structure exists."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    (INBOX_DIR / "pending").mkdir(exist_ok=True)
    (INBOX_DIR / "done").mkdir(exist_ok=True)


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


def send(to_project: str, message: str, msg_type: str = "info",
         priority: str = "normal", from_project: Optional[str] = None):
    """Send a message to another project's inbox."""
    _ensure_dirs()

    timestamp = datetime.now(timezone.utc).isoformat() + "Z"

    # Auto-detect from_project if not provided
    if not from_project:
        from_project = _detect_project() or "unknown"

    msg_id = _msg_id(to_project, timestamp, message)

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

    # Write to pending
    msg_file = INBOX_DIR / "pending" / f"{msg_id}.json"
    msg_file.write_text(json.dumps(msg, indent=2))

    print(f"Message sent: {msg_id}")
    print(f"  From: {from_project} -> To: {to_project}")
    print(f"  Type: {msg_type} ({priority})")
    return msg_id


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
            return json.loads(msg_file.read_text())

    return None


def ack_message(msg_id: str, note: Optional[str] = None, status: str = "done"):
    """Acknowledge/complete a message."""
    _ensure_dirs()

    # Find the message
    pending_file = INBOX_DIR / "pending" / f"{msg_id}.json"
    if not pending_file.exists():
        print(f"Message not found: {msg_id}")
        return False

    msg = json.loads(pending_file.read_text())
    msg["status"] = status
    msg["acked_at"] = datetime.now(timezone.utc).isoformat() + "Z"
    if note:
        msg["ack_note"] = note

    # Move to done
    done_file = INBOX_DIR / "done" / f"{msg_id}.json"
    done_file.write_text(json.dumps(msg, indent=2))
    pending_file.unlink()

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
        send(args.to, message, msg_type=args.type, priority=args.priority,
             from_project=args.from_project)

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


if __name__ == "__main__":
    main()
