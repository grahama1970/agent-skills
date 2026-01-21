---
name: skills-sync
description: >
  Sync skills across all IDEs (Pi, Codex, Claude Code, Antigravity) using the
  canonical agent-skills repo. Use "sync skills", "broadcast skills", or "pull skills".
allowed-tools: Bash, Read
triggers:
  - sync skills
  - broadcast skills
  - push skills
  - pull skills
  - update shared skills
metadata:
  short-description: Sync skills across all IDEs via agent-skills repo
---

# Skills Sync Skill

Synchronize skills across **all IDEs and projects** using a central canonical repository.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CANONICAL REPO (Source of Truth)                │
│           ~/workspace/experiments/agent-skills/skills               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    skills-broadcast push
                                  │
       ┌──────────────────────────┼──────────────────────────┐
       ▼                          ▼                          ▼
┌─────────────┐          ┌─────────────┐          ┌─────────────┐
│   Pi Agent  │          │    Codex    │          │ Claude Code │
│ ~/.pi/agent │          │   ~/.codex  │          │  ~/.claude  │
│   /skills   │          │   /skills   │          │  /commands  │
└─────────────┘          └─────────────┘          └─────────────┘
       │                          │                          │
       ▼                          ▼                          ▼
┌─────────────┐          ┌─────────────┐          ┌─────────────┐
│ Antigravity │          │   pi-mono   │          │   memory    │
│  ~/.gemini  │          │ .pi/skills  │          │.agents/skill│
│   /skills   │          │             │          │             │
└─────────────┘          └─────────────┘          └─────────────┘
```

## Quick Start

```bash
# Add to PATH (one-time)
echo 'export PATH="$HOME/workspace/experiments/agent-skills:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Check current sync status
skills-broadcast status

# Edit skill anywhere, then broadcast to all IDEs
skills-broadcast push

# Pull latest skills into current project
skills-broadcast pull
```

## Commands

| Command                             | Description                          |
| ----------------------------------- | ------------------------------------ |
| `skills-broadcast push`             | Push local → canonical → all targets |
| `skills-broadcast push --from PATH` | Push from specific location          |
| `skills-broadcast pull`             | Pull canonical → current project     |
| `skills-broadcast status`           | Show all targets and sync state      |
| `skills-broadcast targets`          | List registered broadcast targets    |

## Supported IDEs

| IDE             | Skill Location       | Status      |
| --------------- | -------------------- | ----------- |
| **Pi**          | `~/.pi/agent/skills` | ✓ Supported |
| **Codex**       | `~/.codex/skills`    | ✓ Supported |
| **Claude Code** | `~/.claude/commands` | ✓ Supported |
| **Antigravity** | `~/.gemini/skills`   | ✓ Supported |

## Workflow: Edit Anywhere

1. **Edit** skill in any IDE or project
2. **Run** `skills-broadcast push` from that location
3. **Changes flow**: Local → agent-skills repo → All registered targets

```bash
# Example: Edit assess skill in pi-mono, broadcast to all
cd ~/workspace/experiments/pi-mono
vim .pi/skills/assess/SKILL.md
skills-broadcast push

# Or specify source explicitly
skills-broadcast push --from ~/.codex/skills
```

## Configuration

Override defaults via environment variables:

```bash
# Custom canonical repo location
export SKILLS_CANONICAL_REPO="$HOME/my-skills-repo"

# Custom broadcast targets (colon-separated)
export SKILLS_BROADCAST_TARGETS="$HOME/.pi/agent/skills:$HOME/.codex/skills"

# Auto-commit to canonical repo after push
# Auto-commit to canonical repo after push
export SKILLS_SYNC_AUTOCOMMIT=1
```

## Registering Projects

To include a new project in the broadcast list, add its absolute path to `~/.agent_skills_targets`:

```bash
echo "/home/user/workspace/my-new-project" >> ~/.agent_skills_targets
```

The tool will verify if the directory exists and automatically sync to any supported agent skill directory (`.pi/skills`, `.agent/skills`, etc.) found within it.

Alternatively, you can set `SKILLS_FANOUT_PROJECTS="/path/to/proj:/path/to/proj2"` in your environment.

## Legacy: skills-sync (Deprecated)

The old `skills-sync` script is still available but superseded by `skills-broadcast`:

```bash
# Old way (still works)
.agents/skills/skills-sync/skills-sync push --fanout

# New way (recommended)
skills-broadcast push
```

## Troubleshooting

**Target directory missing?**

- The script creates missing directories automatically
- Parent directory must exist

**Changes not appearing in IDE?**

- Some IDEs cache skills; restart the IDE
- Check `skills-broadcast status` to verify sync

**Conflicts between IDEs?**

- Always push from the most recently edited location
- Run `skills-broadcast push --from <newest>` explicitly
