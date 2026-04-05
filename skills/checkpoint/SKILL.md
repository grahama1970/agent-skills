---
name: checkpoint
description: >
  Session grading and cataloging for the learning flywheel. Stores checkpoints
  in ArangoDB via httpx to memory daemon — findable by BM25, semantic search,
  and multi-hop graph traversal. Grades sessions with a 5-level rubric, stores
  proven/failed skill chains for /recommend-skill-chain, links to episodic
  archives, and cross-references ~/.claude/ memory. Git commits both project
  AND skills on every save. NON-NEGOTIABLE.

triggers:
  - checkpoint
  - save checkpoint
  - /checkpoint
  - save where we left off
  - remember where we are
  - grade this session

allowed-tools: [Bash, Read, Write, Glob, Grep]

metadata:
  short-description: "Session grading and cataloging via /memory"
  author: "Horus"
  version: "3.0.0"

provides:
  - session-checkpoint
  - context-preservation
  - conversation-continuity
  - skill-chain-training-data

composes:
  - memory
  - taxonomy
  - recommend-skill-chain
  - episodic-archiver
  - mine-transcripts

taxonomy:
  - checkpoint
  - state-management
  - session-continuity
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /checkpoint

Session grading and cataloging engine. Every session gets analyzed, graded, and
stored so `/memory recall` can surface proven solutions and `/recommend-skill-chain`
can recommend what worked (and warn about what failed).

## Quick Start

```bash
# Save with explicit skill chain and grade
./run.sh save \
  --topic "SPARTA convergence pipeline" \
  --summary "Fixed grounding threshold bug, PASS rate now 78%" \
  --outcome success \
  --skills assess --skills dogpile --skills plan \
  --grade clean

# Auto-grade from session signals
./run.sh save \
  --topic "Fix auth bug" \
  --summary "Resolved login timeout" \
  --outcome success \
  --auto-grade

# Recall the latest checkpoint
./run.sh last

# Search by topic
./run.sh recall --topic "SPARTA grounding"

# List recent
./run.sh list --limit 10
```

## How It Works: The Learning Flywheel

```
Session ends
    ↓
/checkpoint save --skills A B C --grade clean
    ↓
1. git commit with Skills: trailer (machine-readable in commit message)
    ↓
2. httpx POST /store → checkpoints collection (BM25 searchable)
    ↓
3. learn_chain() → skill_chains collection (self-contained document):
   - problem + solution (BM25 searchable)
   - skills, grade, commit, files_changed, tags, scope
   - mind tags (tactical, from /taxonomy/extract)
   - code tags (workflow type, from classify_task)
   - embedding (for semantic search)
    ↓
4. store_skill_chain() → lessons_v2 (legacy, backward compat)
    ↓
5. git push + tag → project AND skills repos
    ↓
Findable via: recall --brief → items + skill_chain
    ↓
Next similar problem → agent gets proven chain + grade
```

### What gets stored where

| Collection | What | Searchable via |
|------------|------|----------------|
| `checkpoints` | Session snapshot (topic, resume, grade, git state) | BM25, tags |
| `skill_chains` | **Self-contained**: problem, solution, skills, grade, mind, code, embedding | BM25 + semantic + graph traversal |
| `lessons_v2` | Legacy skill-chain lesson (backward compat) | BM25 |
| git commit | `Skills:` and `Grade:` trailers in commit message | `git log --grep="Skills:"` |

### Taxonomy axes on skill_chains

Only the axes that make sense for code:
- **mind**: tactical (Detect/Harden/Model/...) — from /taxonomy/extract
- **code**: workflow type (extraction/review/training/...) — from keyword classifier
- **NO heart**: emotional tags are for persona content, not code
- **NO intent**: interaction tags are for UI commands, not code

## Save Options

| Option | Required | Description |
|--------|----------|-------------|
| `--topic` / `-t` | Yes | Current conversation topic |
| `--summary` / `-s` | Yes | Brief summary of where we left off |
| `--outcome` / `-o` | No | success, partial, failed, research, blocked (default: partial) |
| `--skills` | No | Skills used (repeatable). First-class — not regex-scraped |
| `--grade` | No | unresolved, workaround, solved, clean, reusable |
| `--auto-grade` | No | Auto-grade from session signals via RUBRIC.md decision tree |
| `--session-id` | No | Link to conversation session |
| `--episode-key` | No | Link to episodic archive document in ArangoDB |
| `--ingest-claude-memory` | No | Cross-reference ~/.claude/ project memory files |
| `--mine-session` | No | Extract skill chains from transcript via /mine-transcripts |
| `--files` / `-f` | No | Key file paths (repeatable) |
| `--decisions` | No | Key decisions made (repeatable) |
| `--next-steps` | No | What should happen next (repeatable) |
| `--blockers` | No | What blocked progress (repeatable) |
| `--evidence` / `-e` | No | Verifiable evidence (repeatable) |
| `--scope` | No | Memory scope (default: git project name) |
| `--json` | No | Output as JSON |

## Grading Rubric (RUBRIC.md)

Five levels. See `docs/RUBRIC.md` for the full decision tree with Mermaid flowchart.

| Grade | Label | When |
|-------|-------|------|
| 1 | `unresolved` | Problem not solved. Blockers remain. |
| 2 | `workaround` | Hack or temporary fix. Will break again. |
| 3 | `solved` | Solved with corrections or multiple attempts. |
| 4 | `clean` | First try. No rework. Tests pass. |
| 5 | `reusable` | Generalizable — new skill/pattern created. |

All grades feed `/recommend-skill-chain`: clean/reusable → proven-success, unresolved/workaround → proven-failure.

## Recall Options

| Option | Description |
|--------|-------------|
| `--topic` / `-t` | Topic to search for (default: all checkpoints) |
| `--scope` | Memory scope filter (default: current workspace, falls back to all) |
| `--limit` / `-k` | Max results (default: 3) |
| `--json` | Output as JSON |

## What Gets Stored (v3 schema)

**Problem field** (BM25-searchable):
```
CHECKPOINT: 2026-03-26 [pi-mono] SPARTA threshold fix
Outcome: success
Branch: main

Fixed false negative rate from 0.85 threshold in QRA validation pipeline.
```

**Tags** (faceted filtering):
`checkpoint`, `session-state`, `outcome:success`, `project:pi-mono`, `date:2026-03-26`, `branch:main`, `grade:clean`, `has-claude-memory`, `has-episode`

**Solution doc** (structured JSON):
- `checkpoint_version: 3`, `timestamp`, `topic`, `summary`, `outcome`
- `grade`, `rubric_version` — 5-level rubric grading
- `skills_used`, `skills_confidence`, `skills_source` — explicit or regex-extracted
- `commit_hash`, `diff_stat` — git provenance (run `git show {hash}` for full diff)
- `session_id`, `episode_key` — episodic archiver linkage
- `claude_memory_refs` — cross-references to ~/.claude/ project memory files
- `git` — branch, commit, recent commits, modified files
- `files`, `decisions`, `next_steps`, `blockers`, `evidence`

## Common Mistakes

```bash
# WRONG: Save without --skills, rely on regex extraction
./run.sh save -t "Fixed bug" -s "Done" --outcome success
# → skills_used will be empty or regex-guessed at 0.8 confidence

# RIGHT: Explicitly declare what skills were used
./run.sh save -t "Fixed bug" -s "Done" --outcome success \
  --skills assess --skills review-code

# WRONG: Always grade "clean" without thinking
# → Grade inflation makes /recommend-skill-chain useless

# RIGHT: Follow the RUBRIC.md decision tree honestly
# Did the human correct you? → grade:solved, not grade:clean

# WRONG: Skip --episode-key when archiver has already run
# → No graph edge, /trace can't reach the full transcript

# RIGHT: Pass episode key when available
./run.sh save -t "..." -s "..." --episode-key "ep_abc123"
```

## How Agents Use Proven Chains

```bash
# Agent hits a problem → recall finds the solution AND the proven chain
.agents/skills/memory/run.sh recall --q "PDF extraction drops tables" --brief

# Response includes:
# {
#   "items": [{"problem": "...", "solution": "..."}],
#   "skill_chain": {
#     "skills": ["extractor", "review-pdf", "memory"],
#     "code": ["extraction"],
#     "mind": ["Detect", "Harden"],
#     "success_rate": 1.0
#   }
# }

# Agent follows the proven chain instead of guessing
```

## Integration

| Skill | Role |
|-------|------|
| `/memory` | Storage backend. `skill_chains` is a supplemental recall source. |
| `/taxonomy` | Assigns mind tags (tactical) + code tags (workflow) at write time |
| `/recommend-skill-chain` | Queries skill_chains for proven chains. Nightly prune + verify. |
| `/episodic-archiver` | Full transcript archive, linked via graph edge |
| `/mine-transcripts` | Nightly transcript extraction → commit-anchored chains |

## Data Flow: 2,300+ Skill Chains

```
Sources:
  /checkpoint --skills (production)     → highest confidence
  git commit Skills: trailers           → machine-readable
  Commit-transcript correlation         → ±15min timestamp window
  mine-transcripts nightly              → regex-mined (lower confidence)

Storage:
  skill_chains collection               → self-contained documents
  skill_chains_search view              → BM25 on problem/solution
  mind/code taxonomy                    → multi-hop graph traversal

Consumption:
  recall --brief                        → returns skill_chain field
  chain-recall "query"                  → direct semantic search
  /recommend-skill-chain                → ranked recommendations
```
