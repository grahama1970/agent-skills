# Agent-Inbox Usage Guide

The **Agent-Inbox** skill (formerly `pi-messenger`) is a persistent communication bus and orchestration engine for AI agents.

## 1. Getting Started (For Humans)

### A. Start the Service

Ensure the dispatcher is running in the background:

```bash
systemctl --user start agent-inbox
systemctl --user status agent-inbox
```

### B. Interactive TUI

Manage your inbox visually:

```bash
agent-inbox tui
```

- **Browse**: Use arrow keys to navigate messages.
- **Read**: Press `Enter` to view full thread history.
- **Reply**: Type in the box to intervene or guide an agent ("Steering").

### C. CLI Commands

- **Send**: `agent-inbox send --to <project> "Message content"`
- **List**: `agent-inbox list --status pending`
- **Reply**: `agent-inbox reply <MSG_ID> "Response"`

### D. Configuration

Define your agents and defaults in `~/.agent-inbox/`.

**1. `models.json` (Define Agents)**
Map model aliases to executable commands.

```json
{
  "sonnet": ["claude", "--model", "sonnet"],
  "kimi-researcher": ["kimi", "run", "--model", "k2"],
  "ollama-coder": ["ollama", "run", "deepseek-coder"]
}
```

**2. `project_defaults.json` (Assign Agents)**
Set default agents for specific projects.

```json
{
  "pi-mono": "sonnet",
  "my-local-project": "ollama-coder"
}
```

## 2. Orchestration (For Project Agents)

You can use `agent-inbox` as a powerful backend for `/orchestrate`.

### A. Create Plan

Write a `0N_TASKS.md` file with per-task agents:

```markdown
- [ ] **Task 1**: Research implementation
  - Agent: kimi-researcher <-- Uses definition from models.json

- [ ] **Task 2**: Write code
  - Agent: ollama-coder
```

### B. Execute

Run orchestration with the `agent-inbox` backend:

```bash
ORCHESTRATE_BACKEND=agent-inbox /orchestrate 01_TASKS.md
```

The system will dispatch tasks sequentially to the specified agents.

## 3. Core Concepts

### Supervisor Loop

When an agent completes a task, the dispatcher verifies it (if `test_command` is set).

- **Pass**: Task marked done.
- **Fail**: Agent is re-spawned with error logs to fix it (max 3 retries).

### Steering

You can intervene in running tasks by replying to the active message thread via TUI or CLI. The agent will see your new message in its next prompt context.
