---
name: project-knowledge
description: >
  Shared project knowledge document that human and agent can both read and update.
  Aggregates state from /project-state, /checkpoint, /memory into a single
  PROJECT_KNOWLEDGE.md file. Coordinator skill — composes rather than reimplements.
triggers:
  - "project knowledge"
  - "what do we know"
  - "current understanding"
  - "update knowledge"
  - "sync knowledge"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
provides:
  - project-knowledge-file
  - shared-context
composes:
  - project-state
  - checkpoint
  - memory
taxonomy:
  - knowledge-management
  - coordination
  - documentation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /project-knowledge

Shared project knowledge document for human and agent collaboration.

## Why This Exists

The gap between individual lessons (/memory) and heavy documentation (/create-walkthrough):

| Skill | Retrieval | Update |
|-------|-----------|--------|
| `/memory` | Requires knowing what to query | Individual lessons |
| `/checkpoint` | Git log | Append-only commits |
| `/create-walkthrough` | File on disk | Heavy (interview + persona) |
| **`/project-knowledge`** | **Read file directly** | **Incremental section updates** |

This skill maintains a `PROJECT_KNOWLEDGE.md` file that:
1. Human can read/edit directly
2. Agent reads at session start
3. Both can update incrementally
4. Optionally syncs to /memory for cross-project recall

## Commands

```bash
# Read current knowledge (aggregates from sources)
./run.sh read

# Read with live refresh from /project-state
./run.sh read --refresh

# Update a specific section
./run.sh update "Current Understanding" "Lineage backfill works at 25K batches"

# Add a decision
./run.sh decide "Batch at 25K not 225K" "Daemon 502s at ~27K docs"

# Add an open question
./run.sh question "Cascade notification when lineage deps change?"

# Sync to /memory (for cross-project recall)
./run.sh sync

# Initialize PROJECT_KNOWLEDGE.md in current directory
./run.sh init

# Check drift between file and actual state
./run.sh diff
```

## File Structure

`PROJECT_KNOWLEDGE.md` lives in the project root:

```markdown
# Project Knowledge: {project-name}

**Last updated:** YYYY-MM-DD HH:MM by {human|agent}
**Status:** {Active development|Maintenance|Archived}

## Current Understanding

- Key insight 1
- Key insight 2

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| YYYY-MM-DD | What was decided | Rationale |

## Open Questions

- [ ] Question 1
- [ ] Question 2

## Key Files

| File | Purpose |
|------|---------|
| path/to/file.py | What it does |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
```

## Composition

`/project-knowledge` coordinates existing skills:

| Source | What It Provides | When Used |
|--------|------------------|-----------|
| `/project-state --quick` | Infrastructure health | `read --refresh`, `diff` |
| `/checkpoint --recent` | Last N commits + skill chains | `read --refresh` |
| `/memory recall "project:X"` | Prior learnings | `read --refresh`, `sync` |
| `git log --oneline -10` | Recent commit messages | `read --refresh` |

## Hook Integration

Recommended hooks to keep knowledge fresh:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": {"tool_name": "checkpoint"},
        "command": "~/.claude/skills/project-knowledge/run.sh update-from-checkpoint"
      }
    ]
  }
}
```

## Sync to Memory

`./run.sh sync` learns key sections to /memory:

```bash
# What gets synced:
# 1. "Current Understanding" → lesson with tag project:{name}
# 2. Each decision → individual lesson with tag decision:{name}
# 3. Key files table → lesson with tag architecture:{name}
```

This enables cross-project recall:
```bash
/memory recall "project:memory lineage backfill"
```

## Common Mistakes

```bash
# WRONG: Create new file each session
./run.sh init  # when file already exists
# RIGHT: Read and update existing file
./run.sh read
./run.sh update "Current Understanding" "new insight"

# WRONG: Full rewrite of section
./run.sh update "Current Understanding" "completely new content replacing everything"
# RIGHT: Append to section
./run.sh update "Current Understanding" --append "additional insight"

# WRONG: Skip sync, knowledge stays local
# RIGHT: Sync after significant updates
./run.sh sync
```

## Session Start Pattern

Agent should read PROJECT_KNOWLEDGE.md at session start:

```python
# In skill or hook
knowledge_file = Path.cwd() / "PROJECT_KNOWLEDGE.md"
if knowledge_file.exists():
    print(f"Reading project knowledge from {knowledge_file}")
    # Parse and inject into context
```

Or configure as a pre-hook that injects into context.
