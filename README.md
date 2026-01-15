# Agent Skills

Shared skills for AI agents (Claude Code, Codex, Gemini, etc.).

## Skill Types

Skills follow a **large vs small** rule:

### Self-Contained Skills (~100-300 lines)

Simple utilities that live entirely in this repo. Each has a Python CLI that outputs JSON.

| Skill | CLI | Purpose |
|-------|-----|---------|
| `scillm` | `batch.py`, `prove.py` | LLM completions + Lean4 proofs |
| `arxiv` | `arxiv_cli.py` | arXiv paper search |
| `youtube-transcripts` | `youtube_transcript.py` | YouTube transcript extraction |
| `perplexity` | `perplexity.py` | Paid web search with citations |
| `brave-search` | `brave_search.py` | Free web + local search |
| `context7` | `context7.py` | Library documentation lookup |
| `memory` | uses `memory-agent` | Knowledge graph recall |
| `distill` | `run.sh`, `distill.py` | PDF/URL to Q&A pairs |
| `qra` | `run.sh`, `qra.py` | Text to Q&A pairs |
| `doc-to-qra` | `run.sh` | Happy path: document → Q&A |
| `agent-inbox` | `inbox.py` | Inter-agent messaging |

**Knowledge Extraction Skills (choosing the right one):**
| Use Case | Skill | Why |
|----------|-------|-----|
| PDF/URL → memory | `doc-to-qra` | Simplest interface: `./run.sh paper.pdf research` |
| Need `--sections-only` | `distill` | More options when you need control |
| Plain text only | `qra` | Skips PDF extraction step |

**Why self-contained:** These are thin wrappers around APIs. No complex state, no heavy dependencies. Easy to debug, test, and maintain in place.

### Pointer Skills (Reference External Projects)

Complex projects that have their own repos, venvs, and test suites. The skill here is just documentation pointing to the real project.

| Skill | External Project | Purpose |
|-------|------------------|---------|
| `fetcher` | fetcher project | Web crawling, PDF extraction |
| `runpod-ops` | runpod_ops project | GPU instance management |
| `surf` | surf-cli (npm) | Browser automation |
| `pdf-fixture` | extractor project | Test PDF generation |

**Why pointers:** These projects have:
- Multiple interdependent classes
- Their own dependency trees
- Complex business logic
- Separate test suites
- Independent release cycles

Duplicating them here would create maintenance burden and version drift.

## Quick Start

```bash
# Self-contained skills - run directly
python .agents/skills/scillm/batch.py single "What is 2+2?" --json
python .agents/skills/scillm/prove.py "Prove n + 0 = n"
python .agents/skills/arxiv/arxiv_cli.py search --query "transformers"
python .agents/skills/youtube-transcripts/youtube_transcript.py get --video-id "VIDEO_ID"
python .agents/skills/perplexity/perplexity.py ask "What's new in Python 3.12?"
python .agents/skills/brave-search/brave_search.py web "brave search api"
python .agents/skills/context7/context7.py search arangodb "bm25"

# Knowledge extraction
.agents/skills/doc-to-qra/run.sh paper.pdf research        # Happy path
.agents/skills/distill/run.sh --file paper.pdf --scope research
.agents/skills/qra/run.sh --file notes.txt --scope project

# Inter-agent messaging
python .agents/skills/agent-inbox/inbox.py check
python .agents/skills/agent-inbox/inbox.py send --to other-project "Bug found"

# Pointer skills - use external CLIs
fetcher get https://example.com
surf go "https://example.com"
```

## Installation

Skills location: `.agents/skills/`

```bash
# For Claude Code auto-discovery, create symlink:
mkdir -p .claude
ln -s ../.agents/skills .claude/skills
```

## Skill Format

Each skill directory contains:
- `SKILL.md` - Documentation with YAML frontmatter
- CLI scripts (self-contained) or wrapper scripts (pointers)

```yaml
---
name: skill-name
description: >
  What this skill does. Use when user says "trigger phrase 1",
  "trigger phrase 2", or asks about X.
allowed-tools: Bash, Read
triggers:
  - trigger phrase 1
  - trigger phrase 2
  - asks about X
metadata:
  short-description: Brief description
---
```

**See [TRIGGERS.md](TRIGGERS.md) for all trigger phrases** - edit there to change when skills are invoked.

## Adding New Skills

**Small utility (API wrapper, ~100-300 lines)?**
→ Add as self-contained skill with Python CLI

**Complex project (multiple classes, own venv, tests)?**
→ Keep as separate repo, add pointer skill here

## Agent Discovery

| Agent | Discovery |
|-------|-----------|
| Claude Code | `.claude/skills/` symlink |
| Codex | `CLAUDE.md` or `AGENTS.md` reference |
| Gemini | Project documentation |
