---
name: best-practices-qra
description: >
  Canonical rules for QRA pair generation, reasoning provenance, model-training
  datasets, human-authored submission boundaries, critique-only assistants,
  reward/verifier design, and 2026 reasoning-model research gates. Use when
  designing, reviewing, training, evaluating, or deslopping QRA question,
  reasoning, answer, critique, or reward-model pipelines.
triggers:
  - best practices qra
  - QRA training
  - QRA pair generation
  - QRA reasoning
  - reasoning pair model training
  - human-authored reasoning
  - critique-only QRA model
  - QRA reward model
  - QRA verifier
  - humanize reasoning
provides:
  - qra-training-rules
  - reasoning-provenance-boundary
  - qra-eval-rubric
  - critique-only-model-contract
composes:
  - acceptance-contract
  - best-practices-prompt
  - best-practices-python
  - best-practices-report
  - best-practices-security
  - best-practices-self-improvement-loop
  - best-practices-subagent
  - deslop
  - ponytail
  - dogpile
  - arxiv
  - agentic-evals
  - battle
  - create-report
  - memory
taxonomy:
  - qra
  - reasoning
  - model-training
  - provenance
  - evaluation
disciplines:
  - model-ops
  - evaluation-quality
  - engineering-standards
  - research-retrieval
---

# QRA Best Practices

Use this skill before creating or reviewing any QRA pair, QRA grading pipeline,
QRA training corpus, QRA reward model, QRA verifier, or assistant that touches
submitted reasoning.

This skill is research-gated. Its rules must stay grounded in retained arXiv /
Dogpile / Brave research receipts plus the applicable `best-practices-*` skills.
If a rule is not source-backed yet, label it as a design default, not a 2026
best-practice claim.

## Required skill composition

Every QRA grading run must declare which relevant skills were applied and report
violations as structured findings. Do not hide best-practice failures inside
free-form reviewer prose.

Minimum composition matrix:

| Skill | Checks | Violation category |
|-------|--------|--------------------|
| `best-practices-qra` | QRA schema, provenance, pool-to-advice DAG, output boundary | `qra_contract_violation` |
| `best-practices-prompt` | grader prompts, critic prompts, reward/verifier prompts | `prompt_contract_violation` |
| `best-practices-python` | implementation shape for Python pipeline code | `python_practice_violation` |
| `best-practices-security` | provider/data handling, source trust, injection and leakage risks | `security_violation` |
| `best-practices-subagent` | lane roles, tool authority, receipt shape, retry budget | `subagent_violation` |
| `best-practices-self-improvement-loop` | coded training/eval loops, no agent-directed self-improvement theater | `self_improvement_violation` |
| `best-practices-report` | advice packet, release report, non-claims | `report_violation` |
| `best-practices-project` | setup/readiness, proof gates, retained artifacts | `project_readiness_violation` |
| `deslop` | slop in prompts, code, reports, schemas, generic AI rationale | `slop_violation` |
| `ponytail` | unnecessary abstraction, speculative platform work, non-minimal pipeline | `overengineering_violation` |

Violation finding shape:

```json
{
  "schema": "qra_best_practice_violation.v1",
  "skill": "best-practices-qra",
  "category": "qra_contract_violation",
  "severity": "blocker | high | medium | low",
  "location": "file/path or QRA field",
  "evidence": "exact quote, field path, or receipt reference",
  "why_it_matters": "concrete risk",
  "smallest_fix": "minimal action"
}
```

The final `qra_grade_advice.v1` packet must include a `best_practice_violations[]`
array, even when empty.

## Source hierarchy

Apply guidance in this order:

1. The current project brief / acceptance contract.
2. `best-practices-qra` rules in this file.
3. Applicable `best-practices-*` skills: prompt, Python, security, report,
   self-improvement-loop, subagent, project, delivery-proof, README.
4. Latest retained `$arxiv` / `$dogpile` / `$brave-search` research receipts.
5. `$deslop` cleanup findings.
6. `$ponytail` simplification: keep the smallest pipeline that satisfies the
   contract and evals.

## Core boundary

Live campaign submissions and evaluator deliverables require **human-authored
reasoning** unless the campaign contract explicitly allows AI-generated
reasoning.

Do not build this workflow:

```text
patch/source -> model writes verdict/reasoning -> human rewrites -> submit
```

Rewriting model-originated analysis does not make the reasoning human-authored.
The safe default is:

```text
source material + deterministic evidence -> human verdict -> human reasoning -> validation/export
```

## Allowed lanes

| Lane | Allowed | Not allowed |
|------|---------|-------------|
| QRA grading pipeline | model and subagent grading, source-fidelity findings, code-smell findings, security findings, adversarial findings, research findings, rewrite advice | hiding model provenance or presenting advisory output as Graham-authored without review |
| Live submission | deterministic observations, line checks, schema validation, Graham-reviewed rationale | unlabeled model output or unreviewed paste-ready prose |
| Critique assistant | missing evidence, unsupported claim, category mismatch, invalid citation, rewrite checklist | secret replacement of Graham's authorship decision |
| Graham-style draft | optional draft text trained/few-shot grounded on Graham-approved examples, labeled `model_generated_graham_style_draft` | claiming the draft is human-authored before Graham explicitly accepts it |
| Offline training | synthetic QRA pairs, reasoning traces, critique labels, verifier/reward labels, humanization experiments | relabeling training output as human-authored campaign work |
| Research | `$dogpile`, `$brave-search`, `$arxiv`, paper extraction, benchmark/eval design | claiming best-2026 technique without source receipts |

## QRA pair schema rules

A QRA training record must separate source, answer, reasoning, provenance, and
usage rights.

Minimum fields:

```json
{
  "question": "...",
  "reasoning": {
    "text": "...",
    "provenance": "human_authored | model_generated | synthetic | distilled | critique_only",
    "author_id": "...",
    "allowed_use": "training | eval | live_submission | critique_only"
  },
  "answer": "...",
  "evidence": [
    {"source_id": "...", "quote": "...", "locator": "..."}
  ],
  "labels": {
    "domain": "...",
    "difficulty": "...",
    "failure_modes": []
  }
}
```

Rules:

1. Never collapse `reasoning.text` and `reasoning.provenance` into a plain string.
2. Never let a model emit `human_authored` provenance.
3. Never export records for live submission when provenance is not
   `human_authored`.
4. Keep evidence quotes source-bound; no citation-free QRA training records.
5. Store model critique as flags or scores, not replacement reasoning.

## Pool-to-advice DAG

A production QRA grader should run as a pool-driven DAG. Keep it boring: do not
build a training platform, dashboard, or custom orchestration layer until the
pool lease, fanout, synthesis, and receipt loop work.

Optimize for speed first. Run fast local/API lanes by default. Browser models,
especially WebGPT with typical 25min+ latency, are escalation or calibration
lanes unless retained measurements prove they materially improve grades or
Graham rewrite advice.

Ponytail minimum viable pipeline:

```text
lease QRA -> validate -> pi-subagents fanout -> synthesize -> qra_grade_advice.v1 -> release lease
```

A production QRA grader should run as a pool-driven DAG:

1. Lease one available `qra_pool.item.v1`.
2. Run deterministic preflight: schema, sources, rubric vocabulary, duplicate check.
3. Fan out with `pi-subagents` lanes: source fidelity, code smell, security, QRA research, adversarial challenge, humanization, optional Graham-style draft.
4. Synthesize into `qra_grade_advice.v1` with grade, confidence, evidence, objections, rewrite checklist, and provenance-labeled optional draft.
5. Store lane receipts and release/update the pool item.

The output is everything Graham needs to write or approve the rationale: not just a score.

Browser advisor lanes must record latency and marginal value: new blocker/high
findings, grade changes, rewrite-advice changes, and whether the handler should
remain default, escalation-only, or disabled.

## Model-training lane

Research-backed techniques to evaluate before choosing a training recipe:

- supervised fine-tuning on source-bound QRA pairs;
- preference optimization such as DPO/IPO/ORPO when pairwise human preferences exist;
- RL-style methods such as PPO/GRPO only when reward signals are stable and auditable;
- process supervision / process reward models for step-level reasoning quality;
- verifier-guided sampling for evidence support and citation validity;
- critique-only models that flag unsupported reasoning without generating prose;
- synthetic-data distillation only behind provenance labels and retained evals.

Default order:

1. Build a deterministic schema and validator.
2. Collect small human-authored gold records.
3. Train/evaluate a verifier or critique model before a generation model.
4. Add SFT only when records are source-bound and provenance-labeled.
5. Add preference/RL methods only after reward hacking tests exist.

## Humanization rule

Humanization is allowed only for offline model-output quality experiments or
clearly model-generated artifacts. It is not a laundering step for live campaign
reasoning.

A humanization pipeline must preserve:

- original model output hash;
- transformed output hash;
- transform method;
- human review status;
- final provenance.

If the final text began as model-generated reasoning, it remains
`model_generated` or `model_assisted`, not `human_authored`.

## Evaluation gates

Before claiming a QRA model or workbench is ready, run retained evals for:

- evidence quote fidelity;
- answer support by cited source;
- reasoning support by cited source;
- provenance boundary enforcement;
- no generated reasoning in live-export path;
- critique model cannot emit replacement prose;
- reward/verifier model rejects fabricated citations;
- deslop pass rejects generic AI phrasing and unsupported abstractions;
- regression fixtures for reward hacking and synthetic-data leakage.

## Research gate

Do not claim this skill contains “best 2026 techniques” until a source-backed
research bundle exists. Current seed sources live in the qra-training project,
including `docs/research/reasoning-model-training-seed.md`; those are enough to
shape the design, not enough to freeze the final rulebook.

Required research chain:

1. Write `/tmp/arxiv_context.md` for the current QRA training goal.
2. Run `$dogpile` with arXiv, Brave, and GitHub lanes for reasoning training,
   verifier/reward models, process supervision, and preference optimization.
3. Use `$arxiv` HTML-first extraction for selected papers.
4. Store findings through `$memory` or a retained report.
5. Update this skill with exact paper-backed rules and citations.

## Deslop and Ponytail checklist

Run `$deslop` on QRA prompts, schemas, reports, and code. Use `$ponytail` to cut
anything not needed for the current proof gate.

Remove:

- vague “high quality reasoning” instructions without measurable criteria;
- generic chain-of-thought encouragement;
- unverifiable humanization claims;
- wrappers around simple schema validation;
- duplicated provenance enums;
- replacement-reasoning fields in critique schemas;
- broad “AI reviewer” language where the allowed role is critique-only;
- custom orchestration when `pi-subagents` workflowScript is enough;
- hand-rolled queues before a file/DB-backed lease proves insufficient;
- model-training machinery before a retained grading/advice eval exists;
- dashboards before receipts and JSON artifacts exist.
