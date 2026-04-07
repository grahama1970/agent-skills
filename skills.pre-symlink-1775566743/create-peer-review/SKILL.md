---
name: create-peer-review
description: >
  Automated peer review of research papers using Shadow-LEGO's self-improving cascade.
  Multiple fictional reviewer personas score papers against arxiv exemplars on standard
  rubrics (soundness, novelty, clarity, significance, presentation). The cascade learns
  from teacher reviews to produce increasingly accurate local reviews at zero marginal cost.
allowed-tools: Bash, Read
triggers:
  - peer review paper
  - review paper quality
  - score paper
  - compare to arxiv
  - reviewer feedback
metadata:
  short-description: Self-improving peer review via Shadow-LEGO cascade
provides:
  - create-peer-review
composes:
  - assistant
  - arxiv
  - create-classifier
  - create-gpt
  - create-persona
  - create-figure
  - analytics
  - scillm
  - memory
  - task-monitor
  - review-paper
  - dogpile
  - interview
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /create-peer-review

Automated peer review using Shadow-LEGO's 4-tier self-improving cascade.

## Overview

This skill generates multi-perspective peer reviews of research papers by:
1. Fetching exemplar papers from arxiv for structural comparison
2. Running 4 fictional reviewer personas with distinct expertise and biases
3. Scoring on 6 rubric dimensions (soundness, technical novelty, empirical novelty, significance, clarity, presentation)
4. Using Shadow-LEGO cascade: heuristic → classifier → local GPT → teacher
5. Self-improving: local reviewer GPTs learn from teacher reviews via shadow observation

## Architecture

### 4-Tier Review Cascade

| Tier | What | Tool | Cost | Latency |
|------|------|------|------|---------|
| 0 | Heuristic checks: word count, citation count, LaTeX errors, section balance, forbidden phrases | Rules in `review_heuristics.py` | Free | μs |
| 0.5 | Section quality classifier: pass/fail on structure, grounding, tone | DistilBERT via `/create-classifier` | Free | ~15ms |
| 1.5 | Reviewer persona GPT: detailed critique with rubric scores and rationale | QLoRA Qwen2.5-1.5B via `/create-gpt` | Free | ~300ms |
| 2 | Teacher review: full multi-aspect SWIF2T-style feedback | `/scillm batch.py` | Paid | 3-8s |

### Shadow Mode for Review Quality

Every local review runs in shadow mode alongside the teacher:
1. Tier 0.5 classifier predicts pass/fail per rubric dimension
2. Tier 1.5 GPT generates full review with scores and rationale
3. Teacher generates authoritative review (always runs in shadow)
4. Agreement logged to `shadow.jsonl` per reviewer persona
5. When reviewer GPT reaches **90% score agreement** with teacher → promotion

### Exemplar Comparison

Papers are compared against top-cited arxiv exemplars:
- Structural metrics: section word count ratios, citation density, figure-to-text ratio
- Quality signals: abstract information density, introduction flow, evaluation rigor
- Gap analysis: what the exemplars do that the candidate paper doesn't

### Reviewer Personas

4 fictional reviewers in `personas/reviewers.yaml`:
- **Alpha** (Dr. Yuki Tanaka): Soundness focus, skeptical, demands ablations
- **Beta** (Dr. Marcus Webb): Novelty focus, constructive, encyclopedic related work knowledge
- **Gamma** (Dr. Priya Krishnamurthy): Significance focus, pragmatic, production deployment lens
- **Delta** (Dr. Soren Lindqvist): Adversarial focus, terse, finds security holes

### Scoring System

Each reviewer scores on 6 dimensions (1-4 scale, NeurIPS/ICLR convention):
- **Soundness**: Are claims correct? Methods valid? (1=major flaws, 4=rigorous)
- **Technical Novelty**: Are the IDEAS new? (ICLR split)
- **Empirical Novelty**: Are the EXPERIMENTS/RESULTS new? (ICLR split)
- **Significance**: Does this matter? Who benefits?
- **Clarity**: Can it be understood and reproduced?
- **Presentation**: Figures, tables, formatting, code examples

Overall recommendation: **decoupled** 1-10 holistic judgment (ICLR convention).
The weighted signal from dimension scores is advisory — reviewers make holistic calls
(e.g., moderate novelty + immense significance = accept).

Accept/reject thresholds:
- **Strong Accept**: ≥8.0 (top 15%)
- **Accept**: ≥6.0 (marginally above threshold)
- **Borderline**: 5.0-6.0
- **Reject**: <5.0

## Built-in Eval: Arxiv Benchmark Corpus

The skill embeds an arxiv benchmark corpus (`data/arxiv_benchmarks.json`) that
provides empirical distributions for structural metrics. Every `review` command
automatically runs a benchmark eval and attaches it to the meta-review, so the
Tier 2 reviewer (project agent) has percentile rankings for scoring decisions.

### Benchmark Metrics

| Metric | Source | What it measures |
|--------|--------|------------------|
| `eq_per_pg` | Equation environments / pages | Mathematical rigor |
| `fig_per_pg` | Figure environments / pages | Visual communication |
| `ref_per_pg` | References / pages | Citation density |
| `footnotes` | `\footnote{}` count | Scholarly depth |
| `tables` | Table environments | Data presentation |

Papers are scored by percentile rank against the corpus: **weak** (<p25), **ok** (p25-p75), **strong** (>p75).

### Growing the Corpus

```bash
# Add a paper from local .tex file
bash run.sh ingest-benchmark 2305.05176 --tex /path/to/paper.tex

# Score your paper against the corpus
bash run.sh benchmark paper_output/sensai_cascade/draft.tex

# The corpus auto-grows as /dogpile discovers new arxiv papers
```

## Commands

```bash
# Full peer review of a paper
bash run.sh review artifacts/neophyte_paper_v5/

# Benchmark eval: score paper against arxiv corpus
bash run.sh benchmark paper_output/draft.tex

# Add paper to benchmark corpus
bash run.sh ingest-benchmark 2305.05176 --tex path/to/paper.tex

# Compare against arxiv exemplars
bash run.sh compare-exemplars artifacts/neophyte_paper_v5/ --papers 2305.05176,2411.05844

# Score a single section
bash run.sh score-section artifacts/neophyte_paper_v5/sections/eval.tex --reviewer alpha

# Train reviewer GPTs from shadow data
bash run.sh train --reviewer alpha --data ~/.pi/assistant/shadow.jsonl

# Shadow agreement report
bash run.sh shadow-report

# Generate visual review summary (via /create-figure + /analytics)
bash run.sh visualize artifacts/neophyte_paper_v5/ --output review_dashboard.png
```

## Output

Reviews are written to `{paper_dir}/reviews/`:
```
reviews/
├── alpha_review.json      # Per-reviewer structured review
├── beta_review.json
├── gamma_review.json
├── delta_review.json
├── meta_review.json       # Aggregated scores + decision
                           # Also includes benchmark_eval percentiles and pen_name_violations
├── exemplar_comparison.json
├── shadow.jsonl           # Shadow observation log
└── figures/
    ├── rubric_radar.png   # Radar chart of scores per reviewer
    ├── exemplar_gap.png   # Gap analysis vs exemplars
    └── score_history.png  # Score convergence across drafts
```

## Self-Improvement Loop

```
Draft N → 4 reviewer personas score (shadow mode)
        → Teacher confirms/overrides
        → Disagreements logged to shadow.jsonl
        → When agreement ≥90%: reviewer GPT promoted
        → Next draft: reviewer GPT scores autonomously (free, on-device)
        → /create-figure generates visual diff between drafts
```

## Pen Name Enforcement (Non-Negotiable)

Papers reviewed by `/create-peer-review` MUST use pen names for all persona references. Real people never appear in papers.

| Real Persona | Pen Name | Role in Papers |
|-------------|----------|----------------|
| Brandon Bailey | (use pen name from personas.yaml) | Security/SPARTA analysis |
| Margaret Chen | (use pen name from personas.yaml) | Compliance/extraction |
| Jennifer Cheung | (use pen name from personas.yaml) | RMF/DISA validation |
| Embry Lawson | (use pen name from personas.yaml) | System architecture |
| Graham Anderson | Graham Anderson | Human architect (real person, OK as author) |

The reviewer personas (Alpha/Tanaka, Beta/Webb, Gamma/Krishnamurthy, Delta/Lindqvist) are already fictional and need no mapping.

### Enforcement
- `/create-peer-review` flags any real persona name found in paper text as a HIGH severity finding
- The check runs before structural scoring — pen name violations block the review

## Integration with /create-paper

The `/create-paper` skill can invoke `/create-peer-review` as a quality gate:
```python
# In create-paper's multi-draft loop:
for draft_num in range(max_drafts):
    generate_draft(section)
    review = peer_review(section, reviewers=["alpha", "beta", "gamma", "delta"])
    if review.decision == "accept":
        break
    revision_notes = review.aggregate_feedback()
    # Feed revision notes back into next draft
```

## /paper-lab Integration

`/create-peer-review` serves as the **final quality gate** in the `/paper-lab` convergence loop:

```
/paper-lab Phase 2 (headless):
  Round N: /review-paper → fixes → /review-paper (converge on 8.5+)

/paper-lab Phase 3 (final gate):
  /create-peer-review → 4 persona reviews + benchmark eval
  Target: 8+/10 average across all 4 reviewers
```

### Score Interpretation for /paper-lab
- **8+/10**: Paper passes — ready for submission
- **6-8/10**: Needs another /paper-lab round focused on reviewer feedback
- **<6/10**: Fundamental issues — return to Phase 1 (/interview with author)

### What /create-peer-review Adds Beyond /review-paper
- Arxiv benchmark comparison (structural percentiles)
- Cross-reviewer consensus analysis
- Author-as-reviewer qualitative feedback (senior corpus authors)
- Publication venue readiness assessment

## Integration

| Skill | Integration |
|-------|------------|
| `/review-paper` | Internal quality signal — /create-peer-review is the external simulation |
| `/dogpile` | Future: search author's other papers for deeper reviewer profiles |
| `/interview` | Phase 3: author resolves reviewer questions (never during automated review) |
| `/paper-lab` | Orchestrator — calls /create-peer-review as final quality gate |
