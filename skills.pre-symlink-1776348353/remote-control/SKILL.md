---
name: remote-control
description: Open Claude Code remote-control sessions in any registered project from iPad
triggers:
  - remote control
  - iPad access
  - mobile access
  - start remote session
  - remote-control
  - connect from iPad
  - work from iPad
  - open project
  - open sparta
  - open extractor
  - switch project
tools:
  - Bash
  - Read
composes:
  - agent-inbox
provides:
  - remote-project-access
tags:
  - ops
  - remote
  - iPad
  - mcp
---

# Remote Control — Open Any Project from iPad

From iPad, say "open sparta" and get a URL to a full Claude Code session
running in that project on your workstation. Each project gets its own
session with its own CLAUDE.md, skills, and MCP servers.

## How It Works

The `embry-projects` MCP server (user-scoped, auto-loaded in every session)
manages tmux sessions running `claude remote-control` per project.

```
iPad Claude Code session
  → "open sparta"
  → MCP tool open_project("sparta")
  → tmux new-session in /workspace/experiments/sparta
  → claude remote-control starts
  → URL returned to iPad
  → open URL in new Safari tab = full session in sparta
```

## MCP Tools

### Session Management (the key ones)
- **`open_project(name)`** — Launch remote-control in a project, return URL for iPad
- **`close_project(name)`** — Stop a project's remote-control session
- **`active_sessions()`** — List all running sessions with URLs

### Cross-Project Utilities
- **`list_projects()`** — All registered projects with branches
- **`project_status(name)`** — Git status for a project
- **`run_in_project(name, command)`** — Run bash in any project
- **`read_project_file(name, path)`** — Read a file from any project
- **`search_project(name, pattern)`** — Ripgrep in a project
- **`multi_project_status()`** — Overview across projects

## iPad Workflow

1. Start ONE hub session: `claude remote-control --name hub` (on workstation, once)
2. Connect from iPad via the hub URL
3. From iPad say: "open sparta" → get URL → open in new Safari tab
4. Say: "open memory" → another URL → another tab
5. Say: "active sessions" → see all running sessions
6. Say: "close sparta" → tear down when done

## Setup

```bash
# First-time: install MCP server and register with Claude Code
./run.sh install

# Health check
./run.sh health
```

## Prerequisites

1. Claude Code v2.1.51+ with Pro/Max subscription
2. `tmux` installed
3. `embry-projects` MCP registered (`./run.sh install`)
4. Projects registered via `/agent-inbox`
