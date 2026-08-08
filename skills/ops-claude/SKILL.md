---
name: ops-claude
description: >
  Claude Code maintenance, diagnostics, and usage analytics. Check inotify limits,
  clean caches, diagnose startup failures, manage skills directories, and track
  token usage, costs, and rate limit patterns across projects.
allowed-tools: Bash, Read
triggers:
  - claude won't start
  - claude crashes
  - claude out of memory
  - inotify limit
  - file watcher error
  - ENOSPC
  - clean claude cache
  - claude diagnostics
  - ops claude
  - claude usage
  - how much claude am I using
  - claude costs
  - claude savings
  - claude roi
  - token usage
  - claude report
  - claude spending
  - rate limit correlation
metadata:
  short-description: Claude Code maintenance, diagnostics, and usage analytics

provides:
  - ops-claude
composes:
  - debug-pdf
  - scillm
  - create-figure
  - analytics
  - rate-limit-recovery
  - memory
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - developer-tooling
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Ops-Claude Skill

Maintenance, diagnostics, and usage analytics for Claude Code installations.

## Supported IDEs/CLIs

| IDE | Skills Path | User-level |
|-----|-------------|------------|
| Claude Code | `.claude/skills` | `~/.claude/skills` |
| Pi Agent | `.pi/skills` | `~/.pi/skills` |
| Codex | `.codex/skills` | `~/.codex/skills` |
| KiloCode | `.kilocode/skills` | `~/.kilocode/skills` |
| GitHub Copilot | `.github/skills` | - |
| Antigravity/Gemini | `.gemini/skills` | `~/.gemini/skills` |
| Agent (generic) | `.agent/skills` | `~/.agent/skills` |

## Common Issues Addressed

| Error | Cause | Fix Command |
|-------|-------|-------------|
| `ENOSPC: System limit for number of file watchers` | inotify exhaustion | `./run.sh fix-inotify` |
| `JavaScript heap out of memory` | Too many files in skills | `./run.sh clean-skills` |
| `Allocation failed` | Node.js heap limit | `./run.sh fix-heap` |
| Claude hangs on startup | Corrupted cache | `./run.sh clean-cache` |

## Maintenance Commands

### diagnose
Run full diagnostics and report issues.
```bash
./run.sh diagnose          # Check everything
./run.sh diagnose --fix    # Check and fix automatically
```

### status
Show current resource usage and limits.
```bash
./run.sh status
```

### fix-inotify / fix-heap
Fix inotify limits or Node.js heap size.
```bash
./run.sh fix-inotify    # Requires sudo
./run.sh fix-heap
```

### clean-skills / clean-cache / clean-all
Clean .venv/__pycache__ from skills, or Claude Code caches.
```bash
./run.sh clean-skills
./run.sh clean-cache
./run.sh clean-all
```

### gitignore
Add/update .gitignore in all skills directories.
```bash
./run.sh gitignore
```

## Usage Analytics Commands

Requires `ccusage` CLI (already installed). Calculates API-equivalent costs for
Max plan usage — shows what you'd pay without the subscription.

### report
Usage dashboard with token volumes and API-equivalent costs.
```bash
./run.sh report --daily --days 7       # Daily view (default)
./run.sh report --monthly              # Monthly totals
./run.sh report --daily --days 7 --json  # JSON for /create-figure
```

### savings
Max plan ROI calculator.
```bash
./run.sh savings --monthly    # Current month breakdown
./run.sh savings --json       # JSON output
```

### correlate
Rate limit pattern analysis — cross-references usage with rate limit windows.
```bash
./run.sh correlate --days 14
```

### insights
Trend analysis, anomaly detection, and project breakdowns.
```bash
./run.sh insights --days 14
```

### top-projects
Per-project usage breakdown.
```bash
./run.sh top-projects --days 7 --limit 10
```

## JSON Output & Figure Integration

All analytics commands support `--json` for automation. JSON output includes
`figure_data` compatible with `/create-figure`:

```bash
# Generate line chart of daily costs
./run.sh report --daily --days 7 --json > /tmp/claude_usage.json
.pi/skills/create-figure/run.sh line /tmp/claude_usage.json --key figure_data.line
```

## Nightly Report

A scheduled job (`claude-usage-nightly`) runs at 6:00am daily:
- Generates yesterday's usage summary
- Compares against 7-day rolling average
- Detects anomalies (>2x average)
- Stores summaries to `~/.pi/memory/ops-claude/`

## Proactive Usage

Run `./run.sh diagnose` when:
- Claude Code fails to start
- Claude Code crashes with memory errors
- After syncing skills across projects
- System feels sluggish with many projects open

Run `./run.sh report` to:
- Track daily/monthly token consumption
- Justify Max plan ROI
- Identify high-usage projects
- Correlate rate limits with usage patterns

## Common Mistakes

### WRONG: Manually cleaning Claude Code caches without diagnostics
```bash
rm -rf ~/.claude/cache/  # may delete needed state
```

### RIGHT: Use the skill's clean commands
```bash
./run.sh clean-cache    # safe cleanup of Claude Code caches
./run.sh clean-skills   # removes .venv/__pycache__ from skills
```

### WRONG: Ignoring inotify limit errors (ENOSPC)
```
ENOSPC: System limit for number of file watchers reached
# Claude Code hangs or crashes
```

### RIGHT: Fix inotify limits immediately
```bash
./run.sh fix-inotify  # requires sudo, increases watcher limit
```

### WRONG: Not using --json for automation integration
```bash
./run.sh report --daily --days 7  # human-readable, not parseable
```

### RIGHT: Use --json for /create-figure integration
```bash
./run.sh report --daily --days 7 --json > /tmp/usage.json
.pi/skills/create-figure/run.sh line /tmp/usage.json --key figure_data.line
```
