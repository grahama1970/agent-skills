---
name: doc2qra
description: >
  Convert any document (PDF, URL, text) into Question-Reasoning-Answer pairs
  with a document summary. Stores to memory for later recall.
allowed-tools: Bash, Read, WebFetch
triggers:
  - convert to QRA
  - document to QRA
  - pdf to QRA
  - extract QRA
  - extract Q&A
  - extract knowledge
  - create Q&A pairs
  - distill this
  - distill this pdf
  - distill this paper
  - remember this paper
  - store this research
  - learn from this document
  - ingest this pdf
  - turn this into Q&A
  - make Q&A from this
metadata:
  short-description: "Document → QRA pairs + summary (PDF, URL, text)"
provides:
  - document-ingestion
composes:
  - memory
  - scillm
  - taxonomy
  - task-monitor
taxonomy:
  - ingestion
  - knowledge
  - precision
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# doc2qra

**Convert any document into Question-Reasoning-Answer pairs with a summary.**

Input → Summary + QRA pairs → Memory

## Prompt Iteration Rule (NON-NEGOTIABLE)

QRA generation prompts MUST be validated through `/prompt-lab` before use. NEVER hand-craft QRA system prompts in Python strings.

- Before deploying: `/prompt-lab eval` the QRA extraction prompt against ground truth
- Improving quality: `/prompt-lab compare` across prompt variants and models

## Quick Start

```bash
# PDF → QRA with summary
./run.sh --file paper.pdf --scope research

# With domain focus (recommended for better relevance)
./run.sh --file paper.pdf --scope research --context "ML researcher"

# Preview before storing
./run.sh --file paper.pdf --dry-run

# URL → QRA
./run.sh --url https://example.com/article --scope web

# Text file → QRA
./run.sh --file notes.txt --scope project
```

## What It Does

1. **Extract** content from PDF/URL/text
2. **Summarize** the document (2-3 paragraph overview)
3. **Split** into logical sections
4. **Generate** Q&A pairs via LLM (parallel batch)
5. **Validate** answers are grounded in source
6. **Store** summary + QRAs to memory

## Pipeline Composition

doc2qra is a **self-contained composable skill**. It handles its own PDF extraction (pymupdf4llm), URL fetching (requests), and text parsing internally — no dependency on `/fetcher` or `/extractor` at runtime.

**Standalone usage** (agent calls doc2qra directly):
```
PDF/URL/Text → doc2qra → [taxonomy tagging] → memory
```

**Orchestrated usage** (via `/ingest-doc`):
```
PDF → /extractor → /cui-marker → /doc2qra (--from-extractor) → /taxonomy → /memory
```

When called with `--from-extractor`, doc2qra consumes pre-extracted structured JSON instead of doing its own extraction. This is the preferred path for compliance documents where `/extractor` presets matter.

**Internal integrations:**
- **taxonomy** (Python import): Extracts bridge tags from summary + per-QRA keywords. Stamps `taxonomy_tags` on ArangoDB docs for multi-hop graph traversal.
- **memory** (HTTP daemon): Stores QRAs via `/upsert`; indexing is handled server-side.
- **scillm** (HTTP proxy): LLM inference for summaries and QRA generation through `POST http://localhost:4001/v1/chat/completions`. Do not import `scillm` as a Python package; include `Authorization: Bearer sk-dev-proxy-123` and `X-Caller-Skill: doc2qra`.

## Parameters

| Flag | Description |
|------|-------------|
| `--file` | PDF, markdown, or text file |
| `--url` | URL to fetch and convert |
| `--scope` | Memory scope (default: research) |
| `--context` | Domain focus, e.g. "security expert" |
| `--dry-run` | Preview without storing |
| `--json` | JSON output (includes summary) |
| `--sections-only` | Extract sections only (no Q&A) |
| `--summary-only` | Generate only the summary |

## Output Format

When using `--json`, output includes:

```json
{
  "summary": "A 2-3 paragraph summary of the document...",
  "extracted": 15,
  "stored": 15,
  "sections": 8,
  "source": "paper.pdf",
  "scope": "research",
  "qra_pairs": [
    {"problem": "What is...", "solution": "The document explains..."},
    ...
  ]
}
```

## Examples

```bash
# Research paper with context
./run.sh --file arxiv_paper.pdf --scope research --context "ML researcher"

# Technical documentation
./run.sh --file api_docs.md --scope project --context "backend developer"

# Just get the summary
./run.sh --file paper.pdf --summary-only

# From extractor output (pipeline integration)
./run.sh --from-extractor /path/to/extractor/results --scope research
```

## Environment Variables (Optional Tuning)

| Variable | Default | Description |
|----------|---------|-------------|
| `DOC2QRA_PDF_MODE` | fast | PDF mode: fast, accurate, auto |
| `DOC2QRA_CONCURRENCY` | 6 | Parallel LLM requests |
| `DOC2QRA_GROUNDING_THRESH` | 0.6 | Grounding similarity threshold |
| `DOC2QRA_NO_GROUNDING` | - | Set to 1 to skip validation |
| `DOC2QRA_NO_LLM` | - | Set to 1 to force heuristic summary and QRA extraction |

Legacy `DISTILL_*` names are still accepted as fallbacks for compatibility, but new callers should use `DOC2QRA_*`.

## Migration from distill/qra/doc-to-qra

This skill consolidates the functionality of:
- `distill` → Use `doc2qra` instead
- `qra` → Use `doc2qra` instead
- `doc-to-qra` → Use `doc2qra` instead

All three legacy skills now redirect to `doc2qra` with deprecation warnings.

## Where Data Lands

QRAs are stored in **ArangoDB database `memory`**, collection **`lessons`**, with a `scope` field matching `--scope`.

**NOT** in `sparta_qra` — that collection is for validated SPARTA-specific content only.

Quick AQL queries to check your data:

```aql
// Count QRAs per scope
FOR doc IN lessons
  COLLECT scope = doc.scope WITH COUNT INTO cnt
  SORT cnt DESC
  RETURN { scope, count: cnt }

// Count QRAs for a specific scope
RETURN LENGTH(FOR doc IN lessons FILTER doc.scope == "hasard_lee" RETURN 1)

// Sample recent QRAs
FOR doc IN lessons
  FILTER doc.scope == "hasard_lee"
  SORT doc.created_at DESC
  LIMIT 5
  RETURN { problem: LEFT(doc.problem, 80), created: doc.created_at }
```

## Concurrency Warning

**Chutes API allows 5-6 concurrent connections per token across ALL processes.**

Each doc2qra process runs its own `asyncio.Semaphore(6)` — but this limit is **per-process** with no cross-process coordination. Two doc2qra processes = 12 concurrent requests against a 5-6 connection limit = self-DoS.

**Safe rule: run 1 doc2qra process at a time.**

Check before launching:

```bash
# Count running doc2qra processes
ps aux | grep -c '[d]oc2qra'

# See what's running with arguments
ps aux | grep '[d]oc2qra'
```

The `run.sh` startup check will warn you if another instance is already running. Suppress with `CHUTES_SKIP_LOCK=1` if you know what you're doing.

## Token Freshness

`.env` is loaded **once at startup**. Token rotation does NOT propagate to running processes.

Three locations checked (first found wins):
1. `$PROJECT_ROOT/.env` (pi-mono root)
2. `~/.env`
3. `./.env` (current directory)

**After rotating your Chutes token:**

```bash
# Kill all running doc2qra processes
pkill -f doc2qra

# Then restart — new .env will be loaded
./run.sh --file paper.pdf --scope research
```

## Common Mistakes

### WRONG: Running multiple doc2qra processes in parallel
```bash
for scope in hasard_lee kim_campbell; do
  ./run.sh --file "${scope}.md" --scope "$scope" &  # BAD: self-DoS on Chutes
done
```

### RIGHT: Run one process at a time (sequential loop)
```bash
for scope in hasard_lee kim_campbell; do
  ./run.sh --file "${scope}.md" --scope "$scope"  # sequential, respects concurrency limit
done
```

### WRONG: Hand-crafting QRA extraction prompts in Python
```python
PROMPT = "Generate Q&A pairs from this text..."  # hand-written, untested
```

### RIGHT: Validate prompts through /prompt-lab first
```bash
.pi/skills/prompt-lab/run.sh eval --prompt qra_grounded_v1 --model deepseek
```

### WRONG: Storing QRAs in sparta_qra collection directly
```bash
./run.sh --file paper.pdf --scope sparta_qra  # wrong! sparta_qra is for validated content
```

### RIGHT: Store in lessons collection with appropriate scope
```bash
./run.sh --file paper.pdf --scope research  # goes to lessons collection
```

## Batch Usage

**Correct: sequential loop (one process at a time)**

```bash
for scope in hasard_lee kim_campbell dan_hampton christian_brose; do
  echo "=== Processing $scope ==="
  ./run.sh --file "/path/to/${scope}_transcript.md" --scope "$scope"
done
```

Inside a single `doc2qra` process, section-level LLM calls use bounded async requests and consume results as they complete. Do not replace this with unbounded `asyncio.gather`; current `/scillm` guidance requires `asyncio.create_task` plus `asyncio.as_completed` or the server-side batch pool for large QRA workloads.

**WRONG: backgrounded parallel (self-DoS)**

```bash
# DO NOT DO THIS — launches N processes, each with 6 async connections
for scope in hasard_lee kim_campbell dan_hampton christian_brose; do
  ./run.sh --file "/path/to/${scope}_transcript.md" --scope "$scope" &  # BAD
done
wait  # All processes hammering Chutes simultaneously
```
