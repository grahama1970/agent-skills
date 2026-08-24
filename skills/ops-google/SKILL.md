---
name: ops-google
description: >
  Manage Google Gemini API resources, tracking usage budget and model availability.
  Prevents surprise Google billing by enforcing cross-process call limits.
triggers:
  - google status
  - gemini status
  - google billing
  - gemini usage
  - ops-google
  - gemini budget
  - is gemini safe
  - gemini rate limits
  - check google spend
metadata:
  short-description: Google Gemini API management and budget safety
provides:
  - ops-google
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - model-ops
---

# Ops Google Skill

Manage Google Gemini API resources and prevent surprise billing.

Google Pro account (`grahama1970@gmail.com`) auto-bills with no hard spending cap.
This skill makes Gemini usage visible and controllable via local budget tracking.

## Triggers

- "Check gemini status" -> `status`
- "How much gemini budget left?" -> `usage`
- "Is gemini safe to use?" -> `billing-check`

## Commands

```bash
# Full status: model health + rate limits + budget remaining
./run.sh status

# List available Gemini models with specs
./run.sh models

# Show call count from shared budget file (cross-process)
./run.sh usage [--json]

# RPM/TPM limits for current tier (Google Pro)
./run.sh rate-limits [--model <model>]

# Quick API connectivity test
./run.sh sanity [model]

# Check if billing is safe (warns if no budget cap)
./run.sh billing-check

# Update max daily calls in shared state file
./run.sh set-budget <max_calls>
```

## Environment Variables

| Variable           | Description                                      |
| ------------------ | ------------------------------------------------ |
| `GEMINI_API_KEY`   | Google AI Studio API key                         |
| `GEMINI_MAX_CALLS` | Max calls per process (default: 5000)            |

## Budget Safety

Google auto-bills with **no hard spending cap**. The skill enforces:

1. **Per-process limit**: `GEMINI_MAX_CALLS` in `chutes_error_hook.py` (default 5000)
2. **Cross-process limit**: Shared counter at `~/.pi/ops-google/usage.json`
3. **Daily reset**: Counter resets when the date changes

The shared counter is updated atomically by `chutes_error_hook.py` on every
Gemini fallback call. `/ops-google usage` reads it.

## Rate Limits (Google Pro Tier)

| Model              | RPM   | TPM       |
| ------------------ | ----- | --------- |
| gemini-2.5-flash   | 2000  | 4,000,000 |
| gemini-2.5-pro     | 150   | 2,000,000 |
| gemini-2.0-flash   | 2000  | 4,000,000 |

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed
with `/context7` (library docs) or `/fetcher` (any URL/PDF) rather than
caching stale copies. Verified reachable (HTTP 200) 2026-08-24.

- Google Gemini API docs: <https://ai.google.dev/gemini-api/docs>
- llms.txt (LLM-friendly doc index): <https://ai.google.dev/gemini-api/docs/llms.txt>

```bash
skills/context7/run.sh "google gemini api models"
skills/fetcher/run.sh "https://ai.google.dev/gemini-api/docs"
```
