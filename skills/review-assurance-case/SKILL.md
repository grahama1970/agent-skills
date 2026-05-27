---
name: review-assurance-case
version: 1.0.0
description: >
  Multi-provider AI review of assurance cases (GSN/CAE).
  Checks structural integrity, logical soundness, evidence sufficiency,
  completeness, confidence calibration, contextual validity, and process compliance.
  47 checks across 7 categories grounded in ISO 15026, DO-178C, IEC 61508, ISO 26262, CMMC, and Assurance 2.0.
triggers:
  - review assurance case
  - review evidence case
  - assurance case review
  - check assurance case
  - audit evidence case
  - GSN review
  - CAE review
taxonomy:
  collection: operational
  tags: [review, assurance, GSN, CAE, ISO-15026, evidence, compliance]
composes:
  - memory
  - create-evidence-case
  - create-gsn-diagram
  - extract-entities
  - taxonomy
provides:
  - assurance-case-review-report
  - structural-integrity-check
  - evidence-sufficiency-audit
  - defeater-analysis
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /review-assurance-case

Multi-provider AI review of structured assurance cases using 47 checks across 7 categories.

## Architecture

Same pattern as `/review-code`, `/review-design`, `/review-paper`:
- Multi-provider (GitHub Copilot free, Claude, Codex, Gemini)
- 3-step pipeline: Structural Audit → Semantic Review → Final Verdict
- Session continuity with context bridging for stateless providers
- Memory integration (recall prior reviews, learn findings)

## Providers

| Provider | CLI | Cost | Session | Default Model |
|----------|-----|------|---------|---------------|
| github | copilot | FREE | yes | gpt-5 |
| anthropic | claude | paid | yes | sonnet |
| openai | codex | paid | no | gpt-5.2-codex |
| google | gemini | paid | no | gemini-2.5-flash |

## Commands

```bash
# Review an evidence case report (markdown)
run.sh review --file /tmp/evidence-case-reports/q01_report.md

# Review with specific provider
run.sh review --file report.md --provider anthropic --model opus

# Review JSON evidence case data directly
run.sh review --json /tmp/evidence-case-results/q01_result.json

# Full 3-step pipeline with intermediate saves
run.sh review-full --file report.md --rounds 2 --save-intermediate

# Check provider availability
run.sh check

# List available models
run.sh models
```

## 3-Step Pipeline

### Step 1: Structural Audit (Programmatic + LLM)
- S-01..S-10: Graph topology checks (every claim has argument, every argument terminates in evidence, no cycles, no dangling nodes, context nodes present)
- Quick pass/fail per check with evidence

### Step 2: Semantic Review (LLM)
- L-01..L-07: Logical soundness (valid inference, no fallacies, argument type matching)
- E-01..E-10: Evidence sufficiency (traceable artifacts, relevance, reliability, proportional to risk)
- C-01..C-10: Completeness (all threats covered, requirements traced, assumptions stated, defeaters addressed)
- CF-01..CF-06: Confidence calibration (explicit levels, no pseudo-precision, epistemic vs aleatoric)
- CX-01..CX-06: Contextual validity (operational context defined, evidence valid for context, adversarial threats addressed)

### Step 3: Final Verdict
- Aggregated findings with severity (critical/high/medium/low)
- Per-category scores (0-10)
- Overall verdict: ADEQUATE / NEEDS_WORK / INADEQUATE
- Specific recommendations for each failing check
- Comparison with prior reviews (if available)

## Review Categories (47 Checks)

| Category | IDs | Count | Type |
|----------|-----|-------|------|
| Structural Integrity | S-01..S-10 | 10 | Programmatic |
| Logical Soundness | L-01..L-07 | 7 | LLM |
| Evidence Sufficiency | E-01..E-10 | 10 | Mixed |
| Completeness | C-01..C-10 | 10 | Mixed |
| Confidence Calibration | CF-01..CF-06 | 6 | LLM |
| Contextual Validity | CX-01..CX-06 | 6 | LLM |
| Process Compliance | P-01..P-06 | 6 | Programmatic |

## Sources

- GSN Community Standard v3 (ISO 15026-2)
- CAE Framework (Adelard/NPSA) — Claims, Arguments, Evidence
- SACM v2.2 (OMG Structured Assurance Case Metamodel)
- Assurance 2.0 — Eliminative argumentation + defeater taxonomy
- DO-178C, IEC 61508, ISO 26262, CMMC Assessment Guide
- "Taxonomy of Real-World Defeaters in Safety Assurance Cases" (arXiv:2502.00238)
- "CoDefeater: Using LLMs to Find Defeaters" (arXiv:2407.13717)

## Memory Integration

- **Pre-hook**: Recall prior assurance case reviews for same project/domain
- **Post-hook**: Learn review findings with taxonomy bridge tags
- Graceful degradation if memory unavailable
