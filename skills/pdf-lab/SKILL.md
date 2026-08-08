---
name: pdf-lab
description: >
  Self-improving PDF extraction convergence loop. Diagnoses extraction failures
  by computing the delta between S00 estimates and actual extraction, reproduces
  issues on synthetic PDFs, discovers optimal parameters, and writes fixes back
  to the extractor pipeline code permanently.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
triggers:
  - pdf lab
  - tune pdf extraction
  - improve pdf extraction
  - converge extraction parameters
  - fix extraction delta
  - self improve extractor
  - write back pipeline fix
metadata:
  short-description: Self-improving PDF extraction with convergence + write-back
  version: "1.0.0"
runtime_self_improvement: substantial

provides:
  - pdf-extraction
composes:
  - memory
  - scillm
  - task-monitor
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
taxonomy:
  - precision
  - validation
  - resilience
disciplines:
  - extraction
  - evaluation-quality
---

# pdf-lab

`/pdf-lab` is a convergence loop that diagnoses PDF extraction failures,
reproduces them on synthetic PDFs, discovers optimal parameters, and
**writes those fixes back to the extractor pipeline code** permanently.

## Why This Exists

There is no absolute ground truth for real PDFs. The system works with
**deltas** between S00's estimate and actual extraction results. When S00
predicts 40 sections but extraction finds 15, something is wrong. `/pdf-lab`
figures out what, fixes it, and makes the fix permanent.

## Quick Start

```bash
cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/pdf-lab

# Main: diagnose, reproduce, converge, and write fix back
./run.sh tune /path/to/real.pdf \
  --review-json /path/to/review_result.json \
  --debug-json /path/to/debug_patterns.json \
  --converge --write-back --json

# Dry run: find the fix but don't write it
./run.sh tune /path/to/real.pdf \
  --review-json ... --debug-json ... \
  --converge --dry-run --json

# Quick diagnosis only (compute delta, no tuning)
./run.sh diagnose /path/to/real.pdf \
  --profile-json /path/to/profile.json \
  --structural-json /path/to/structural.json

# Generate synthetic reproduction PDF only
./run.sh synthetic \
  --patterns '["multi_column","split_tables"]' \
  --output /tmp/repro.pdf

# Show recent tuning results
./run.sh status

# List all pdf-lab code changes
./run.sh history

# Rollback a specific fix
./run.sh rollback --sha abc123

# Deterministic post-run verification for substantial-skill jobs
./run.sh verify --job-dir /tmp/pdf-lab-job

# Build a maintainer escalation packet when verify fails
./run.sh file-maintainer-ticket --job-dir /tmp/pdf-lab-job

# Standalone PDF Lab UX
cd ${HOME}/workspace/experiments/agent-skills/skills/pdf-lab/ui
npm install
npm run dev:all
```

If the workstation has exhausted file watchers, use the no-watch preview path:

```bash
npm run build
npm run preview:all
```

The standalone UI runs at `http://127.0.0.1:3012/#pdf-lab`. In `dev:all`, the
Vite app runs on port `3012` and the local API bridge runs on port `3013`. In
`preview:all`, the API bridge serves the built UI and API together on port
`3012`. The bridge serves real artifacts from
`PDF_LAB_PUBLIC_ROOT` and `PDF_LAB_ARTIFACTS_ROOT`; if an artifact or runtime
bridge is missing, endpoints fail closed with an explicit JSON error instead of
returning mock operational state.

## How Fixes Get Written Back

The pipeline has a tiered configuration system. `/pdf-lab` writes to the
appropriate tier:

| Tier | Target | Example |
|------|--------|---------|
| 1 | Env var defaults in step files | `CAMELOT_LINE_SCALE_DEFAULT` 15 -> 40 |
| 2 | Heuristic thresholds (code constants) | `LARGE_FONT_THRESHOLD` 11.0 -> 9.5 |
| 3 | Pattern rules (regex, filters) | New citation pattern in S04 |
| 4 | Preset YAML | `line_scale: 80` in arxiv twin_config.yml |
| 5 | Calibration records (ArangoDB) | Learned pattern in `learned_patterns` |
| 6 | /memory (runtime recall) | Winning params stored for instant recall |

## Persona Attribution

Every code change is traceable to the persona who flagged the issue via
git commit trailers (`Reviewed-By`, `Persona-Role`, `Issue-Codes`).

## Integration

Called by `inline_review_loop.py` when a persona review score is below
threshold. Falls back to heuristic adaptive params if convergence fails.

## Memory + Taxonomy Integration

The skill integrates with `/memory` through `memory/run.sh` subcommands in
`memory_integration.py`; it does not import ArangoDB clients or the memory
Python package directly.

- **Pre-hook (`recall_prior_convergence`)**: Before tuning, recalls prior convergence
  results for the same PDF type or URL. Enables the tuner to skip failed strategies
  and start from previously winning parameters.
- **Post-hook (`learn_convergence`)**: After tuning completes, stores the convergence
  outcome (strategy, iterations, final score, improvements, write-back results) to
  memory with taxonomy bridge tags for cross-skill recall.
- **Bridge keywords**: Precision, Resilience, Fragility, Corruption, Loyalty, Stealth
  (tuned to PDF extraction domain).
- **Tags**: `["pdf_lab", "convergence"] + bridges`

Gracefully degrades if `/memory` is unavailable.

## Runtime Verification

Post-run verification is mandatory for non-trivial pdf-lab jobs.

`pdf-lab` is a substantial runtime self-improvement skill. After any job that
creates extraction, convergence, or write-back artifacts, run:

```bash
./run.sh verify --job-dir <job-dir>
```

The verifier writes `<job-dir>/verify-receipt.json` and exits non-zero on
missing or inconsistent artifacts. When verification fails, create a maintainer
packet with:

```bash
./run.sh file-maintainer-ticket --job-dir <job-dir>
```

Runtime workers must not patch or commit `agent-skills` from inside a failed
pdf-lab job; maintainer escalation is documented in
`references/maintainer-escalation.md`.

## File Structure

```
pdf-lab/
  SKILL.md                   # This file
  run.sh                     # Shell entry point
  pdf_lab.py                 # Typer CLI entry point
  memory_integration.py      # Memory + Taxonomy hooks
  pyproject.toml             # Dependencies
  sanity.sh                  # Local behavioral sanity gate
  ui/                        # Standalone Vite PDF Lab UX and local API bridge
  scripts/                   # Runtime verification and compliance helpers
  references/                # Maintainer escalation and long-form contracts
  agents/pdf-lab/AGENTS.md   # Worker post-run rules
  lib/                       # Core libraries (delta, tuner, writer, etc.)
  docs/                      # Additional documentation
```

## Outputs

- Code changes written to `src/extractor/pipeline/steps/`
- `/memory` entries for future recall (synthetic creation, convergence, reverts)
- Git commits with persona attribution trailers
- JSON report of convergence results
- `verify-receipt.json` for deterministic runtime verification
- `maintainer-ticket.json` when a failed job needs skill-maintainer repair
