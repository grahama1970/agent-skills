---
name: agent-inbox
description: >
  File-based inter-agent messaging. Check inbox, send bugs/requests to other projects,
  acknowledge resolved issues. Use for cross-project agent communication.
allowed-tools: Bash, Read
triggers:
  - check your inbox
  - check inbox
  - check messages
  - any messages
  - any pending messages
  - check for messages
  - agent sent you
  - sent you an issue
  - sent you a bug
  - address the bug
  - fix the issue from
  - message from agent
  - inter-agent message
  - send message to
  - send bug to
  - notify the agent
  - tell the other agent
  - cross-project message
  - pending issues
  - pending bugs
metadata:
  short-description: Inter-agent messaging for cross-project communication
---

# Agent Inbox Skill

Simple file-based inter-agent message system. Allows agents working on different projects to communicate bugs, requests, and information without manual copy/paste.

## When to Use

- Agent A finds a bug in project B's code
- Agent needs to request help from another project's agent
- Passing information between project workspaces
- Any cross-project agent communication

## Installation

The `agent-inbox` wrapper script is at `.agents/skills/agent-inbox/agent-inbox`.

```bash
# Option 1: Add to PATH (recommended)
export PATH="$PATH:/path/to/project/.agents/skills/agent-inbox"

# Option 2: Create alias
alias agent-inbox='python /path/to/project/.agents/skills/agent-inbox/inbox.py'

# Option 3: Direct invocation
python .agents/skills/agent-inbox/inbox.py <command> [args]
```

## Setup (One-Time)

Register your projects so agent-inbox knows where they are:

```bash
# Register projects (use direct path if agent-inbox not on PATH)
agent-inbox register memory /home/user/workspace/memory
agent-inbox register scillm /home/user/workspace/litellm

# List registered projects
agent-inbox projects

# Check which project current directory maps to
agent-inbox whoami

# Unregister if needed
agent-inbox unregister old-project
```

## Quick Start

```bash
# Send a bug report to the scillm project
agent-inbox send --to scillm --type bug --priority high "
File: scillm/extras/providers.py:328
Error: UnboundLocalError on 'options'
Fix: Rename local variable to avoid shadowing
"

# Check for pending messages (anytime)
agent-inbox check

# List all pending messages
agent-inbox list

# Read a specific message
agent-inbox read scillm_abc123

# Acknowledge when fixed
agent-inbox ack scillm_abc123 --note "Fixed: renamed to merged_options"
```

## CLI Commands

### `register` - Register a project (one-time setup)

```bash
agent-inbox register <name> <path>

# Examples:
agent-inbox register memory /home/user/workspace/memory
agent-inbox register scillm /home/user/workspace/litellm
```

### `unregister` - Remove a project

```bash
agent-inbox unregister <name>
```

### `projects` - List registered projects

```bash
agent-inbox projects
agent-inbox projects --json
```

### `whoami` - Show detected project for current directory

```bash
agent-inbox whoami
```

### `send` - Send a message to another project

```bash
agent-inbox send --to PROJECT --type TYPE --priority PRIORITY "message"

# Types: bug, request, info, question
# Priority: low, normal, high, critical

# Examples:
agent-inbox send --to memory --type request "Please add 'proved_only' parameter to search()"
agent-inbox send --to scillm --type bug --priority critical "Server crashes on startup"

# Read message from stdin (useful for multi-line)
cat error.log | agent-inbox send --to scillm --type bug
```

### `list` - List messages

```bash
agent-inbox list                      # All pending
agent-inbox list --project scillm     # For specific project
agent-inbox list --status done        # Completed messages
agent-inbox list --json               # JSON output
```

### `read` - Read a specific message

```bash
agent-inbox read MSG_ID
agent-inbox read MSG_ID --json
```

### `ack` - Acknowledge/complete a message

```bash
agent-inbox ack MSG_ID
agent-inbox ack MSG_ID --note "Fixed in commit abc123"
```

### `check` - Check inbox (for hooks)

```bash
agent-inbox check                     # Check all
agent-inbox check --project scillm    # Check specific project
agent-inbox check --quiet             # Just return count (exit code 1 if messages)
```

## Integration with Claude Code Hooks

Add to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "on_session_start": [
      "agent-inbox check --project $(basename $PWD) || true"
    ]
  }
}
```

Or add to your shell profile to check on every new terminal:

```bash
# ~/.bashrc or ~/.zshrc
alias claude-start='agent-inbox check --project $(basename $PWD); claude'
```

## Message Format

Messages are stored as JSON in `~/.agent-inbox/`:

```
~/.agent-inbox/
├── pending/
│   └── scillm_abc123.json
└── done/
    └── memory_def456.json
```

Each message:

```json
{
  "id": "scillm_abc123",
  "to": "scillm",
  "from": "extractor",
  "type": "bug",
  "priority": "high",
  "status": "pending",
  "created_at": "2026-01-11T20:30:00Z",
  "message": "File: providers.py:328\nError: UnboundLocalError..."
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_INBOX_DIR` | Inbox directory location | `~/.agent-inbox` |
| `CLAUDE_PROJECT` | Current project name (for `from` field) | `unknown` |

## Workflow Example

**Agent A (extractor project) finds bug:**
```bash
agent-inbox send --to scillm --type bug --priority high "
Bug in scillm/extras/providers.py:328

Error: UnboundLocalError: cannot access local variable 'options'

The _worker function references 'options' on line 328 before it's
assigned on line 345. This is because the assignment makes Python
treat it as a local variable throughout the function.

Suggested fix: Rename line 345 'options = dict(options or {})' to
'merged_options = dict(options or {})' and update subsequent references.
"
```

**User switches to scillm project:**
```bash
cd /path/to/scillm
claude  # Or agent-inbox check runs automatically via hook
```

**Agent B (scillm project) sees message:**
```
=== 1 pending message(s) ===
Project: scillm

[HIGH]
  scillm_a1b2c3d4: bug from extractor
    Bug in scillm/extras/providers.py:328...
```

**Agent B fixes and acknowledges:**
```bash
agent-inbox ack scillm_a1b2c3d4 --note "Fixed: renamed to merged_options in commit abc123"
```

## Python API

```python
from inbox import (
    register_project, unregister_project, list_projects,
    send, list_messages, read_message, ack_message, check_inbox
)

# Setup (one-time)
register_project("memory", "/home/user/workspace/memory")
register_project("scillm", "/home/user/workspace/litellm")
list_projects()  # {"memory": "/home/...", "scillm": "/home/..."}

# Send
send("scillm", "Bug report...", msg_type="bug", priority="high")

# List
messages = list_messages(project="scillm")

# Read
msg = read_message("scillm_abc123")

# Ack
ack_message("scillm_abc123", note="Fixed")

# Check (returns count)
count = check_inbox(project="scillm", quiet=True)
```
