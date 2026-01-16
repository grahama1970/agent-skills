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

## Running the Skill (No Global Install Needed)

The repo already includes a wrapper script (`.agents/skills/agent-inbox/agent-inbox`). Run it directly or invoke the Python entrypoint—no global install or PATH hacks required.

```bash
# Preferred: run the bundled wrapper
.agents/skills/agent-inbox/agent-inbox check

# Alternate: call Python explicitly
python .agents/skills/agent-inbox/inbox.py check
```

If you want convenience aliases, you can add the skill folder to `PATH`, but it’s optional and not assumed anywhere in this doc.

## Setup (One-Time)

Register your projects so agent-inbox knows where they are:

```bash
# Register projects (use direct path if agent-inbox not on PATH)
.agents/skills/agent-inbox/agent-inbox register memory /home/user/workspace/memory
.agents/skills/agent-inbox/agent-inbox register scillm /home/user/workspace/litellm

# List registered projects
.agents/skills/agent-inbox/agent-inbox projects

# Check which project current directory maps to
.agents/skills/agent-inbox/agent-inbox whoami

# Unregister if needed
.agents/skills/agent-inbox/agent-inbox unregister old-project
```

## Quick Start

```bash
# Send a bug report to the scillm project
.agents/skills/agent-inbox/agent-inbox send --to scillm --type bug --priority high "
File: scillm/extras/providers.py:328
Error: UnboundLocalError on 'options'
Fix: Rename local variable to avoid shadowing
"

# Check for pending messages (anytime)
.agents/skills/agent-inbox/agent-inbox check

# List all pending messages
.agents/skills/agent-inbox/agent-inbox list

# Read a specific message
.agents/skills/agent-inbox/agent-inbox read scillm_abc123

# Acknowledge when fixed
.agents/skills/agent-inbox/agent-inbox ack scillm_abc123 --note "Fixed: renamed to merged_options"
```

## CLI Commands (Wrapper ≙ `python inbox.py`)

### `register` - Register a project (one-time setup)

```bash
.agents/skills/agent-inbox/agent-inbox register <name> <path>

# Examples:
.agents/skills/agent-inbox/agent-inbox register memory /home/user/workspace/memory
.agents/skills/agent-inbox/agent-inbox register scillm /home/user/workspace/litellm
```

### `unregister` - Remove a project

```bash
.agents/skills/agent-inbox/agent-inbox unregister <name>
```

### `projects` - List registered projects

```bash
.agents/skills/agent-inbox/agent-inbox projects
.agents/skills/agent-inbox/agent-inbox projects --json
```

### `whoami` - Show detected project for current directory

```bash
.agents/skills/agent-inbox/agent-inbox whoami
```

### `send` - Send a message to another project

```bash
.agents/skills/agent-inbox/agent-inbox send --to PROJECT --type TYPE --priority PRIORITY "message"

# Types: bug, request, info, question
# Priority: low, normal, high, critical

# Examples:
.agents/skills/agent-inbox/agent-inbox send --to memory --type request "Please add 'proved_only' parameter to search()"
.agents/skills/agent-inbox/agent-inbox send --to scillm --type bug --priority critical "Server crashes on startup"

# Read message from stdin (useful for multi-line)
cat error.log | .agents/skills/agent-inbox/agent-inbox send --to scillm --type bug
```

### `list` - List messages

```bash
.agents/skills/agent-inbox/agent-inbox list                      # All pending
.agents/skills/agent-inbox/agent-inbox list --project scillm     # For specific project
.agents/skills/agent-inbox/agent-inbox list --status done        # Completed messages
.agents/skills/agent-inbox/agent-inbox list --json               # JSON output
```

### `read` - Read a specific message

```bash
.agents/skills/agent-inbox/agent-inbox read MSG_ID
.agents/skills/agent-inbox/agent-inbox read MSG_ID --json
```

### `ack` - Acknowledge/complete a message

```bash
.agents/skills/agent-inbox/agent-inbox ack MSG_ID
.agents/skills/agent-inbox/agent-inbox ack MSG_ID --note "Fixed in commit abc123"
```

### `check` - Check inbox (for hooks)

```bash
.agents/skills/agent-inbox/agent-inbox check                     # Check all
.agents/skills/agent-inbox/agent-inbox check --project scillm    # Check specific project
.agents/skills/agent-inbox/agent-inbox check --quiet             # Just return count (exit code 1 if messages)
```

## Integration with Claude Code Hooks

Add to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "on_session_start": [
      ".agents/skills/agent-inbox/agent-inbox check --project $(basename $PWD) || true"
    ]
  }
}
```

Or add to your shell profile to check on every new terminal:

```bash
# ~/.bashrc or ~/.zshrc
alias claude-start='.agents/skills/agent-inbox/agent-inbox check --project $(basename $PWD); claude'
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
.agents/skills/agent-inbox/agent-inbox send --to scillm --type bug --priority high "
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
claude  # Or .agents/skills/agent-inbox/agent-inbox check runs automatically via hook
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
.agents/skills/agent-inbox/agent-inbox ack scillm_a1b2c3d4 --note "Fixed: renamed to merged_options in commit abc123"
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
