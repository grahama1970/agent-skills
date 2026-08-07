---
name: extractor-quality-check
description: Persona-driven datalake quality assessment with Margaret Chen (Pratt & Whitney) and Jennifer Cheung (NIWC Pacific). Dynamic annealing thresholds, batch review, and /ask consult integration.
triggers: extractor quality, datalake quality, margaret chen, jennifer cheung, extraction review

provides:
  - extractor-quality-check
composes:
  - create-figure
  - task-monitor
disciplines:
  - extraction
  - evaluation-quality
  - persona-simulation
---

# extractor-quality-check

**Persona-driven** datalake quality assessment for the extractor pipeline. Two named assessors co-preside over extraction quality using dynamic annealing thresholds.

## Prompt Iteration Rule (NON-NEGOTIABLE)

Margaret/Jennifer persona assessment prompts MUST be validated through `/prompt-lab` before deployment. NEVER hand-craft assessment system prompts in Python strings.

- Before deploying: `/prompt-lab eval` the assessment prompt against ground truth
- Comparing variants: `/prompt-lab compare` across models

## Assessors

| Name | Organization | Template | Domain |
|------|-------------|----------|--------|
| **Margaret Chen** | Pratt & Whitney | fictional | DO-178C, requirements engineering, ITAR, Lean4 |
| **Jennifer Cheung** | NIWC Pacific | expert | Naval systems, cybersecurity, MIL-STD, RMF |

## Architecture

Mirrors Brandon Bailey's role in `/sparta-review`:
- Watchdog triggers assessment at every supervisor checkpoint
- Margaret + Jennifer decide CONTINUE / STOP_AND_FIX / ESCALATE
- Auto-adjustments run before resuming extraction
- Dynamic annealing: lenient early, strict at certification

## Quick Start

```bash
cd ~/.claude/skills/extractor-quality-check

# Collect live datalake state
./run.sh state | python3 -m json.tool

# Run batch review
./run.sh review --run-id corpus_1770904449

# Show annealing thresholds
./run.sh thresholds

# Ask Margaret directly
# /ask Margaret Chen "what is the state of the datalake?"

# Ask Jennifer directly
# /ask Jennifer Cheung "what should we prioritize?"
```

## Annealing Schedule

| Phase | Coverage | Score | Fail Ratio | Margaret Says |
|-------|----------|-------|------------|---------------|
| Bootstrap | 0-20% | >= 0.70 | <= 10% | "Let's see what we're working with" |
| Early Growth | 20-50% | >= 0.78 | <= 5% | "Time to raise the bar" |
| Mid Growth | 50-75% | >= 0.85 | <= 3% | "No more excuses for sloppy extraction" |
| Late Growth | 75-90% | >= 0.88 | <= 2% | "Tightening the screws" |
| Refinement | 90-95% | >= 0.90 | <= 1% | "Every detail matters" |
| Certification | 95%+ | >= 0.95 | <= 0.5% | "This goes on the certification package" |

## Quality Framework

Uses the 7-dimension scoring framework:
- content_coverage (0.22)
- section_alignment (0.18)
- table_fidelity (0.16)
- equation_fidelity (0.14)
- ordering_yx (0.12)
- figure_fidelity (0.10)
- data_quality (0.08)

Grade thresholds: A+ >= 0.95, A >= 0.88, B >= 0.78, C >= 0.65, F < 0.65

**Never lower thresholds** -- fix the extraction, not the bar (SPARTA rule).

## Data Sources

The state collector reads (all local JSON, no network):
1. `supervisor_corpus.json` -- supervisor status, run metrics, failure buckets
2. `aggregate.json` (latest) -- verdict counts, dimension scores
3. `gap_plan.json` -- per-sector coverage
4. `supervisor_memory_events.jsonl` -- convergence signals
5. `report_*.json` -- latest daily corpus report

## Inline Review Mode (New)

When `--inline-review` is passed (or `INLINE_REVIEW=true` env var), persona reviews run **inline after each PDF extraction** instead of via external supervisor polling. This is the recommended mode for new deployments.

### How it works

```
Extract PDF → Score (7 dimensions) → Margaret evaluates → Jennifer evaluates
    → Reconcile → Store in /memory (ArangoDB) → Remediate if WARN/FAIL
    → Re-extract → Loop until PASS (max 3 iterations)
```

### Key modules

| Module | Purpose |
|--------|---------|
| `inline_reviewer.py` | Per-PDF scoring + persona review + /memory storage |
| `inline_review_loop.py` | Self-improvement loop: extract → review → remediate → re-extract |
| `convergence_tracker.py` | Query /memory for score trajectories and trend detection |

### Inline reviewer (`review_pdf()`)

Takes a profile path, resolves all inputs, scores via `build_issues()` + `dimension_scores()` + `overall_from_dimensions()`, then runs `margaret_evaluates()` + `jennifer_evaluates()` + `reconcile()`. Searches /memory for related past reviews of the same PDF. Stores structured review via `record_assessment()`. For WARN/FAIL, also stores a lesson via `learn()` with remediation recommendation. All reviews include `/taxonomy` bridge tags for multi-hop graph traversal.

### Self-improvement loop (`review_loop()`)

Wraps `review_pdf()` with extraction + remediation. Each iteration stored in /memory with `supersedes` edges linking iterations. Max 3 iterations. PDFs that don't reach PASS are marked `hard_tail` for human review.

### Convergence tracker

Queries /memory `pdf_assessment` entries to compute linear regression over score trajectories. Classifies trends as `improving` (slope > 0.005), `degrading` (slope < -0.005), or `plateau`. Used by the supervisor to decide CONTINUE/SPOT_FIX/RESTART without running stratified samples.

### Activation

```bash
# Via CLI flag
./run.sh check /path/to/corpus --inline-review

# Via environment variable
export INLINE_REVIEW=true
./run.sh check /path/to/corpus
```

## Integration

### /ask consult
Both personas have `context_collector: datalake_state_collector.py` in their YAML.
When `/ask Margaret Chen ...` is invoked, consult.py runs the collector first,
injecting live metrics into the persona prompt.

### Supervisor Loop (Legacy mode)
`batch_review.run_batch_review()` is called by `supervise_learn_datalake.py`
after quality gate evaluation. The persona review can:
- Override a gate failure (CONTINUE) if personas judge quality acceptable
- Escalate beyond what the gate alone would do
- Attach specific adjustments (timeout tuning, sector prioritization, etc.)

### Supervisor Loop (Inline mode)
When `--inline-review` is active, the supervisor queries `/memory` for convergence
instead of running stratified samples. Reviews are already stored inline by the
child process, so the supervisor just reads score trajectories from ArangoDB.

## Files

| File | Purpose |
|------|---------|
| `margaret_chen_persona.yaml` | Margaret's persona definition |
| `jennifer_cheung_persona.yaml` | Jennifer's persona definition |
| `datalake_state_collector.py` | Live datalake state reader |
| `batch_review.py` | Batch review logic (legacy mode) |
| `inline_reviewer.py` | Per-PDF scoring + persona review + /memory storage |
| `inline_review_loop.py` | Self-improvement loop with remediation |
| `convergence_tracker.py` | /memory-based convergence tracking |
| `annealing.py` | Dynamic threshold schedule |
| `run.sh` | Skill runner |
| `SKILL.md` | This file |

## Related Skills

| Skill | Use For |
|-------|---------|
| `/ask` | Consult Margaret or Jennifer directly |
| `/create-persona` | Register personas in memory |
| `/train-voice` | Voice training for TTS |
| `/learn-datalake` | Supervised extraction loop |
| `/review-pdf` | 7-dimension quality assessment |
| `/reality-check-sparta` | Brandon Bailey's SPARTA review (pattern source) |
