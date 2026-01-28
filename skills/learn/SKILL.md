---
name: learn
description: >
  Learn from any content type. Auto-detects source (arXiv, YouTube, GitHub, PDF, URL)
  and routes to appropriate backend skill for extraction and storage.
allowed-tools: ["Bash", "Read"]
triggers:
  - learn
  - learn this
  - study
metadata:
  short-description: Learn from any content type
---

# Learn

**ONE command to learn from ANY content type.**

## Quick Start

```bash
# Learn from arXiv
./run.sh https://arxiv.org/abs/2302.02083 --scope horus_lore

# Learn from YouTube
./run.sh https://youtube.com/watch?v=xyz --scope project_kb

# Learn from PDF
./run.sh ./document.pdf --scope project_kb --context "technical docs"

# Learn from any URL
./run.sh https://example.com/article --scope research

# List learned content
./run.sh --list --scope horus_lore
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--scope` | `-s` | **Required.** Memory scope (e.g., `horus_lore`, `project_kb`) |
| `--context` | `-c` | Domain context for better extraction |
| `--force` | `-f` | Re-learn even if already learned |
| `--dry-run` | `-n` | Preview without learning |
| `--list` | `-l` | List learned content for scope |
| `--request` | `-r` | Request content if not available (saved to requests.json) |
| `--from-gaps` | `-g` | Reflect on past errors/questions to find knowledge gaps |

## Source Types

| Type | Detection | Backend |
|------|-----------|---------|
| arXiv | `arxiv.org` URL | `/arxiv` |
| YouTube | `youtube.com` | `/youtube-transcripts` + `/distill` |
| GitHub | `github.com` | `/fetcher` + `/distill` |
| PDF | `.pdf` extension | `/extractor` + `/distill` |
| Audiobook | `.aax`, `.m4b` | `/audiobook-ingest` + `/distill` |
| URL | any HTTP(S) | `/fetcher` + `/distill` |
| File | local path | `/distill` |

## Requesting Content

For content not yet available (e.g., audiobooks you want to purchase):

```bash
# Request an audiobook
./run.sh "Horus Rising by Dan Abnett" --scope horus_lore --request

# View pending requests
cat ~/.learn/<scope>/requests.json
```

## Reflection Mode (--from-gaps)

Query past conversations and logs to find knowledge gaps. This enables **curiosity-driven learning** by reflecting on:

- **Skill failures** - Skills like `/fixture-graph`, `/code-review`, `/anvil` that repeatedly failed
- **Learning failures** - Content that couldn't be learned
- **Errors** - Past errors from episodic memory
- **Questions** - Unanswered or recurring questions

```bash
# Find what I should learn based on past problems
./run.sh --from-gaps --scope horus_lore

# Output shows gaps like:
# | Type          | Content                        | Reason                         |
# |---------------|--------------------------------|--------------------------------|
# | skill_failure | fixture-graph failed to gen... | /fixture-graph failed - deeper |
# | skill_failure | code-review didn't solve bug   | /code-review failed - deeper   |
# | error         | Failed to parse PDF table...   | From episodic memory           |
```

**Sources checked:**
1. Skill execution logs (`~/workspace/.../logs/*.log`)
2. Learning history (`~/.learn/*/learned.json`)
3. Episodic memory (`agent_conversations` in ArangoDB)

This creates a **learning feedback loop**:
```
Past failures → Identify gaps → Generate curiosity → /dogpile → /learn → Better future responses
```

## Tracking

Learned content is tracked per-scope in `~/.learn/<scope>/learned.json`.

## Nightly Automation

Automated learning cycle that collects transcripts and learns from knowledge gaps.

### Commands

```bash
# Full nightly cycle (transcripts + learning)
./run.sh full --scope horus_lore --since 24

# Just collect transcripts from coding agents
./run.sh collect-transcripts --since 24

# Just learn from knowledge gaps
./run.sh nightly learn --scope horus_lore --max-gaps 5

# Dry run to see what would happen
./run.sh full --scope horus_lore --dry-run
```

### Transcript Collection

Collects and archives transcripts from:

| Agent | Location | Format |
|-------|----------|--------|
| Claude Code | `~/.claude/projects/` | JSONL |
| Codex | `~/.codex/sessions/` | JSONL |
| Pi | `~/.pi/sessions/` | JSON |
| KiloCode | `~/.kilocode/cli/` | JSON |

**Note:** Each agent has platform-specific transcript formats. Failed extractions are logged for manual review.

### Scheduler Integration

Register with `/scheduler` for automated nightly runs:

```bash
# Register nightly learning
.pi/skills/scheduler/run.sh register \
  --name "nightly-learn-horus" \
  --cron "0 2 * * *" \
  --command ".pi/skills/learn/run.sh full --scope horus_lore" \
  --workdir "/home/graham/workspace/experiments/pi-mono"

# Register transcript collection (more frequent)
.pi/skills/scheduler/run.sh register \
  --name "collect-transcripts" \
  --cron "0 */6 * * *" \
  --command ".pi/skills/learn/run.sh collect-transcripts --since 12"
```

### The Nightly Loop

```
Transcripts → Archive → Detect unresolved → Store gaps
                                    ↓
                           Knowledge gaps
                                    ↓
                           /dogpile research
                                    ↓
                           /distill → Memory
                                    ↓
                           Better future responses
```

## Composing with /taxonomy

For tagged storage with graph traversal support:

```bash
# Get taxonomy tags
tags=$(/path/to/taxonomy/run.sh --text "$content" --collection operational)

# Check if worth remembering
worth=$(echo "$tags" | jq -r '.worth_remembering')
```
