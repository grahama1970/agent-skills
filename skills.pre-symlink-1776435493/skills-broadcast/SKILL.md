---
name: skills-broadcast
description: >
  Sync skills across all IDEs (Pi, Codex, Claude Code, KiloCode) using symlinks
  to a single canonical directory. Use "sync skills", "broadcast skills", or "link skills".
internal: true
allowed-tools: Bash, Read
triggers:
  - skills-broadcast
  - skills-sync
  - sync skills
  - broadcast skills
  - push skills
  - pull skills
  - link skills
  - update shared skills
metadata:
  short-description: Symlink-based skill sharing across all IDEs
provides:
  - skill-broadcasting
composes:
  - memory
  - task-monitor

taxonomy:
  - distribution
  - synchronization
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Skills Broadcast Skill

Share skills across **all IDEs and projects** using symlinks to a single canonical directory.

## Architecture

```
┌─────────────────────────────────────────────────┐
│        CANONICAL (Source of Truth)               │
│   <project>/.pi/skills/                         │
│   (the one real copy — edit here)               │
└───────────────────────┬─────────────────────────┘
                        │
              symlinks (ln -sfn)
                        │
    ┌───────────┬───────┼───────┬───────────┐
    ▼           ▼       ▼       ▼           ▼
~/.codex/   ~/.claude/ ~/.pi/  ~/.kilocode/ project/
 skills      skills    agent/   skills      .agent/
                       skills               skills
```

**Every target is a symlink.** No copies, no rsync, no sync lag.

## Why Symlinks?

The old rsync approach:
- Duplicated **~300 GB** across 10+ targets
- Required 500+ lines of rsync exclusion lists
- Caused the **2026-02-11 deletion incident** (`rsync --delete` propagated a wiped dir)
- Changes required manual `push` to propagate

Symlinks:
- **0 bytes** duplicated
- **~200 lines** of code
- Changes are **instant** everywhere
- **Impossible** to accidentally delete skills via sync

## Quick Start

```bash
# See current state
./run.sh status

# Create symlinks at all targets (safe — backs up old dirs)
./run.sh link --dry-run    # preview first
./run.sh link              # do it

# Legacy commands still work
./run.sh push    # same as link
./run.sh pull    # same as link
```

## Commands

| Command                  | Description                              |
|--------------------------|------------------------------------------|
| `./run.sh link`          | Create symlinks at all targets           |
| `./run.sh status`        | Show all targets and their link state    |
| `./run.sh git-sync`      | Commit and push skills to agent-skills GitHub repo |
| `./run.sh cleanup`       | Delete .pre-symlink-* backups to reclaim disk |
| `./run.sh register PATH` | Add a project to target registry         |
| `./run.sh unregister PATH` | Remove a project from registry         |
| `./run.sh targets`       | List registered projects                 |
| `./run.sh push`          | Legacy alias for `link`                  |
| `./run.sh pull`          | Legacy alias for `link`                  |

## Status Output

```
=== Skills Broadcast Status ===

Canonical: /home/user/workspace/pi-mono/.pi/skills (146 skills)

Project: /home/user
  OK      .pi/agent/skills -> canonical
  OK      .codex/skills -> canonical
  OK      .claude/skills -> canonical
Project: /home/user/workspace/experiments/memory
  OK      .pi/skills -> canonical
```

## Safety

- Old directories are **backed up** (renamed with `.pre-symlink-<timestamp>`) before replacement
- Canonical must have **20+ skills** or the script refuses to run
- `--dry-run` previews all changes without modifying anything
- Backups can be deleted after verification: `rm -rf path.pre-symlink-*`

## Registering Projects

```bash
# Register a project for symlink targets
./run.sh register /path/to/project

# The registry is at ~/.agent_skills_targets
cat ~/.agent_skills_targets
```

## Supported IDEs

| IDE             | Skill Location       | Pattern           |
|-----------------|----------------------|-------------------|
| **Pi**          | `~/.pi/agent/skills` | `.pi/skills`      |
| **Codex**       | `~/.codex/skills`    | `.codex/skills`   |
| **Claude Code** | `~/.claude/skills`   | `.claude/skills`  |
| **KiloCode**    | `~/.kilocode/skills` | `.kilocode/skills` |
| **Generic**     | `.agent/skills`      | `.agent/skills`   |

## Git Sync to GitHub

The `git-sync` command pushes canonical skills to the `grahama1970/agent-skills` repo on GitHub.
This is a **manual** operation — run it when you want to checkpoint your current skill state.

```bash
./run.sh git-sync              # commit and push
./run.sh git-sync --dry-run    # preview what would change
```

How it works:
1. Temporarily replaces the `agent-skills/skills` symlink with a real copy
2. Prunes heavy artifacts (models, .venv, media files, >50MB dirs)
3. Commits with `sync: N skills from canonical (date)` and pushes
4. Restores the symlink (guaranteed via trap, even on failure)

## Heavy Artifact Policy

Heavy artifacts (**models, weights, checkpoints, datasets**) must live on `/mnt/storage12tb/` and be symlinked into skill dirs. The sanity check enforces this with a 100 MB threshold per subdirectory.
