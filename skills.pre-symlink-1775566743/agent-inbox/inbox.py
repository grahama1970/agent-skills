#!/usr/bin/env python3
"""
Simple file-based inter-agent message inbox with project registry.

Thin assembler: imports from inbox_core and inbox_cli, re-exports all public names.

Usage:
    agent-inbox register PROJECT /path/to/project
    agent-inbox projects
    agent-inbox send --to PROJECT "message"
    agent-inbox check
    agent-inbox list [--project PROJECT]
    agent-inbox read MSG_ID
    agent-inbox ack MSG_ID [--note "done"]
"""

# Re-export everything from sub-modules for backward compatibility
from inbox_core import (
    # Types and dataclasses
    ModelType,
    MessageStatus,
    DispatchConfig,
    # Constants
    INBOX_DIR,
    REGISTRY_FILE,
    # Internal helpers (used by dispatcher.py)
    _ensure_dirs,
    _atomic_write,
    _load_registry,
    _save_registry,
    _detect_project,
    _msg_id,
    _get_task_monitor_client,
    _get_triage_module,
    # Public API
    register_project,
    unregister_project,
    list_projects,
    send,
    update_status,
    save_message,
    list_thread,
    list_messages,
    read_message,
    ack_message,
    check_inbox,
    scan_projects,
)

from inbox_cli import main


if __name__ == "__main__":
    main()
