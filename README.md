# Agent Skills & Hooks

Shared skills and hooks for AI agents (Claude Code, Codex, Pi Agent, etc.).

## Repository Structure

```
agent-skills/
├── skills/           # Reusable agent skills
│   ├── perplexity/
│   ├── distill/
│   ├── memory/
│   └── ...
├── hooks/            # Agent lifecycle hooks
│   ├── quality-gate.sh
│   ├── memory-first.sh
│   ├── memory-prompt.sh
│   └── prompts/
│       └── quality-gate.md
├── deploy.sh         # Deploy to all agents
└── README.md
```

## Quick Start

```bash
# Deploy skills + hooks globally (one-time)
./deploy.sh

# Check what would be deployed
./deploy.sh --check

# Deploy only skills or hooks
./deploy.sh --skills
./deploy.sh --hooks
```

After deployment:
- **Skills** available at `~/.claude/skills/`, `~/.codex/skills/`, `~/.pi/agent/skills/`
- **Hooks** available at `~/.claude/hooks/`

## Skills

### Self-Contained Skills

| Skill | CLI | Purpose |
|-------|-----|---------|
| `scillm` | `batch.py`, `prove.py` | LLM completions + Lean4 proofs |
| `arxiv` | `arxiv_cli.py` | arXiv paper search |
| `youtube-transcripts` | `youtube_transcript.py` | YouTube transcript extraction |
| `perplexity` | `perplexity.py` | Paid web search with citations |
| `brave-search` | `brave_search.py` | Free web + local search |
| `context7` | `context7.py` | Library documentation lookup |
| `memory` | `run.sh` | Knowledge graph recall |
| `distill` | `run.sh`, `distill.py` | PDF/URL to Q&A pairs |
| `qra` | `run.sh`, `qra.py` | Text to Q&A pairs |
| `doc-to-qra` | `run.sh` | Happy path: document → Q&A |
| `inbox` | `/inbox` ↔ `emit_message` wrapper | Switchboard messaging + acknowledgements |
| `assess` | - | Project health assessment |
| `clarify` | `runner.py` | Interactive form gathering |

### Pointer Skills (Reference External Projects)

| Skill | External Project | Purpose |
|-------|------------------|---------|
| `fetcher` | fetcher project | Web crawling, PDF extraction |
| `runpod-ops` | runpod_ops project | GPU instance management |
| `surf` | surf-cli (npm) | Browser automation |
| `pdf-fixture` | extractor project | Test PDF generation |

## Hooks

Hooks run at agent lifecycle events to enforce quality and inject context.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `quality-gate.sh` | Stop (before exit) | Prevents exit with failing tests |
| `memory-first.sh` | PreToolUse (Grep/Task) | Check memory before codebase scan |
| `memory-prompt.sh` | UserPromptSubmit | Inject memory context |

### Hook Prompts

Hook prompts are **editable markdown files** in `hooks/prompts/`:

```
hooks/prompts/
└── quality-gate.md    # Template shown when tests fail
```

Template variables:
- `{{OUTPUT}}` - Test output / error message
- `{{ATTEMPT}}` - Current retry number
- `{{MAX_ATTEMPTS}}` - Max retries

## Usage Examples

```bash
# Skills (after deploy)
python ~/.claude/skills/perplexity/perplexity.py ask "What's new in Python 3.12?"
python ~/.claude/skills/context7/context7.py search arangodb "bm25"
~/.claude/skills/doc-to-qra/run.sh paper.pdf research

# Per-project (alternative to global)
ln -s /path/to/agent-skills/skills .agents/skills
ln -s ../.agents/skills .claude/skills
```

## Adding New Skills

**Small utility (API wrapper, ~100-300 lines)?**
→ Add to `skills/` with Python CLI

**Complex project (multiple classes, own venv, tests)?**
→ Keep as separate repo, add pointer skill in `skills/`

## Adding New Hooks

1. Create `hooks/your-hook.sh`
2. Optionally create `hooks/prompts/your-hook.md` for editable prompt
3. Configure in project's `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "~/.claude/hooks/your-hook.sh"}]
    }]
  }
}
```

## Agent Compatibility

| Agent | Skills | Hooks |
|-------|--------|-------|
| Claude Code | ✅ `~/.claude/skills/` | ✅ `~/.claude/hooks/` |
| Codex | ✅ `~/.codex/skills/` | ❓ Unknown |
| Pi Agent | ✅ `~/.pi/agent/skills/` | ❓ Unknown |
| Gemini | Via project docs | ❓ Unknown |

## See Also

- `skills/TRIGGERS.md` - All skill trigger phrases
- `skills/run-all-sanity.sh` - Run all skill sanity tests
