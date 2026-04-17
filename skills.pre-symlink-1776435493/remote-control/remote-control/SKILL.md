---
name: remote-control
description: Start Claude Code remote-control sessions for iPad/mobile access to all registered projects
triggers:
  - remote control
  - iPad access
  - mobile access
  - start remote session
  - remote-control
  - connect from iPad
  - work from iPad
  - access projects remotely
  - embry-projects MCP
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

# Remote Control — iPad/Mobile Access to All Projects

Start a Claude Code remote-control session that provides access to all registered
projects via the `embry-projects` MCP server.

## Architecture

```
iPad Safari → claude.ai/code (remote-control URL)
    → workstation Claude Code session
        → embry-projects MCP server (stdio, user-scoped)
            → ~/.agent-inbox/projects.json (28+ projects)
                → bash in any project directory
```

## Quick Start

```bash
# Start remote-control from any directory
./run.sh start

# Start with a specific name
./run.sh start --name "evening-session"

# Check MCP server health
./run.sh health

# List registered projects
./run.sh projects
```

## What This Provides

Once `claude remote-control` is running and you connect from iPad:

- **`list_projects`** — all registered projects with git branches
- **`project_status(name)`** — branch, recent commits, changes
- **`run_in_project(name, command)`** — bash in any project's cwd
- **`read_project_file(name, path)`** — read files with traversal protection
- **`search_project(name, pattern)`** — ripgrep scoped to a project
- **`multi_project_status()`** — quick overview across projects

## Example iPad Prompts

- "List my projects"
- "Run tests in the extractor project"
- "Show me the status of sparta and memory"
- "Search for 'def recall' in the memory project"
- "Read CLAUDE.md from the embry-os project"

## Prerequisites

1. Claude Code v2.1.51+ (`claude --version`)
2. Pro/Max subscription (OAuth, not API keys)
3. `embry-projects` MCP server registered at user scope
4. `~/.agent-inbox/projects.json` populated (via `/agent-inbox register` or `scan`)

## MCP Server Location

- **Server**: `/home/graham/workspace/experiments/embry-os/services/mcp-daemon/server.py`
- **Venv**: `/home/graham/workspace/experiments/embry-os/services/mcp-daemon/.venv/`
- **Config**: `~/.claude.json` (user-scoped MCP entry `embry-projects`)

## Why Not Agent Teams?

Evaluated and rejected. Hard blockers: teammates can't have different cwds,
can't load different CLAUDE.md files, no declarative config, no session resumption.
