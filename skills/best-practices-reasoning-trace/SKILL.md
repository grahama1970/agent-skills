---
name: best-practices-reasoning-trace
description: >
  What separates successful from failed reasoning traces in real agent
  sessions, and the labeling contract that makes that claim checkable. Use
  when mining transcripts for training data, scoring a live run's reasoning
  quality, deciding whether a trace counts as a success or failure example,
  building verifier/critique datasets from agent transcripts, or when the
  human asks what makes reasoning succeed or fail across models. Encapsulates
  hand-written priors from operator lessons plus the outcome-grounding rules
  required to validate them against the local transcript corpus.
metadata:
  short-description: Success/failure discipline for reasoning traces
triggers:
  - reasoning trace
  - successful vs failed reasoning
  - mine reasoning traces
  - trace verifier
  - outcome label
  - landed vs failed
  - trace scoring
  - reasoning quality features
  - solver sft data
  - critique training data
  - what makes reasoning succeed
provides:
  - reasoning-trace-outcome-labeling-contract
  - reasoning-feature-taxonomy
  - trace-analysis-traps
  - live-trace-discipline-rules
composes:
  - mine-transcripts
  - memory
  - agentic-evals
complies:
  - best-practices-skills
taxonomy:
  - validation
  - resilience
  - evaluation
disciplines:
  - ml-training
  - evaluation-quality
  - agentic-orchestration
---

# best-practices-reasoning-trace

## Why this skill exists

The local corpus of real agent reasoning is large and already receipted:
thousands of Pi session transcripts, ~43 GB of Codex sessions, hundreds of
Claude CLI transcripts, and 2,600+ full web-model responses under the ask
output tree, all joinable to git history that records which work actually
landed. Separately, operator lessons (AGENTS.md) carry hand-written failure
patterns paid for by specific incidents. This skill is the bridge: the rules
for turning that corpus into labeled success/failure examples without
laundering false positives, and the behavioral taxonomy those examples are
expected to confirm or refute.

Every feature below is labeled `prior` until a feature-outcome table built
under this contract has validated it. Reciting a prior as validated is the
same defect this skill exists to prevent.

## Rule 1 — An outcome label comes from a receipt, never from the transcript

A trace's success is a fact about the world outside the transcript, so only a
world receipt can establish it.

Time proximity (the ±15-minute git join) generates attribution CANDIDATES; it
never qualifies them. Qualification requires content-level evidence that the
trace's contribution survived into the target repository state (patch-ID
equivalence as supporting evidence, then inspection of retained changes — patch
IDs ignore whitespace and are not byte-exact authorship proof). Attribution
carries a strength: `confirmed` | `ambiguous` | `unsupported`; competing
candidates are preserved, never resolved by picking the nearest timestamp.

Outcomes are dated EVENT CHAINS, not terminal verdicts:
`integrated -> evaluation_passed -> reverted`, each with its own evidence,
reason, scope, and `observed_through` horizon. "No observed revert" on a young
trace is censored data, not durable success; the nightly job revisits existing
affected outcomes, not just new transcripts. `rejected` is never read as
"wrong" — closed tickets are often duplicates, superseded, or out of scope.

| Event | The only acceptable receipt |
| --- | --- |
| `integrated` | content-attributed contribution in an identified repository state |
| `evaluation_passed` (renamed from "proven") | the exact tested tree, evaluator version, executed case IDs, assertions — a fixture *containing* a `real_world` case proves nothing about whether it ran |
| `rejected` | explicit human rejection/revert/closure naming the work and reason |
| `reverted` | dated revert commit; reason recorded (compatibility and product decisions are not correctness verdicts) |
| `unverified` | none of the above. The default. Never a supervised example |

**Coding-only selection bias:** research, review, clarification, safe refusal,
and permission-respecting stops succeed without commits. Add `task_kind` and
`outcome_evidence_kind`; use `not_applicable` for git attribution on
non-artifact work. Never teach "no commit means low quality."

Not outcome labels, each a documented false-positive source: a green transcript
ending; self-authored tests passing; the agent's self-report; a tool's
`success: true` about itself.

## Rule 1b — Labels are observations, never training permissions

Every outcome/feature classification is an observational record. Training
eligibility is a SEPARATE assertion (`eligible_for`, deny-by-default empty)
granted only through explicit gates (split lineage resolved, leakage checks,
provenance, permitted-use). "Landed" does not mean "usable for solver SFT" —
the highest-risk move in this domain is promoting artifact acceptance into
process-correctness supervision (ProcessBench: correct answers accompany
flawed processes).

## Rule 2 — The feature taxonomy (priors, pending validation)

Score each trace with typed observations carrying `present | absent | unknown |
not_applicable` — missing instrumentation must never masquerade as good or bad
behavior. Each observation records its definition version, evidence span, and
scorer run; absence claims require an inspected range and coverage status
(truncated/budget-exhausted inspection yields `unknown`, never `absent`).

The mechanically detected identical-args-repeat is named
`repeated_call_signature` — it is RAW DATA, not a failure feature: the same
read command before and after a write is exactly the desired read-back
behavior, and identical calls can be legitimate polling or flaky-test reruns.
Appropriateness is a separate contextual assessment.

Success-pattern features (expected to correlate with `integrated`):

- **read-receipt-first**: sufficiently current, relevant evidence consulted
  BEFORE the dependent decision (not "reading happened first" in every task)
- **verified-read-back**: effect read back against the correct artifact,
  version, and expected property — "read something afterward" is insufficient
- **re-ran-previously-working-path**: regression-check coverage where applicable
- **supported_failure_mechanism** (replaces "root-cause-not-symptom" as a
  cheap binary): fix rests on an evidenced mechanism, alternatives considered,
  attribution unresolved where evidence is incomplete
- **escalated_appropriately** (no fixed threshold): escalation judged under the
  actual budget, permissions, and policy, not a hard "after two failures" rule

Failure-pattern features (expected to correlate with non-landing):

- **repeated_call_signature**: raw mechanical signal (see above); failure only
  via contextual assessment as unproductive retry
- **stopped-mid-goal-for-status**: VOLUNTARY premature termination only — a
  requested update, handoff, context limit, timeout, or permission boundary is
  not this feature
- **routed-around-blocker**: split authorized-equivalent-fallback (resilience,
  not this feature) from bypassing a required constraint
- **insufficient_evidence_change**: whether the evidence actually supported the
  change — not where diagnosis began (some error strings fully specify the fix)
- **claimed-unverified**: claim-evidence relation, distinguishing missing
  visible support, invalid evidence, and actually contradicted claims

Missing measurement family (the real gap versus 2026 practice — PRMBench,
ToolPRMBench): **step-local semantic validity** — tool suitability, argument
prerequisites, target identity, whether subsequent claims follow from
observations, state/constraint preservation, error propagation and VERIFIED
recovery (post-error steps are not automatically wrong — reflective-PRM work
models error cessation), and diagnostic value of probes. Workflow habits are
audit hypotheses; step validity is the supervision target.

## Rule 3 — Three traps that decide whether the result is real

1. **Confounders.** Hard tasks both require more tool calls and fail more.
   A raw "more verification predicts success" correlation can invert under
   conditioning. Analyze paired comparisons — same repo, same blocker type,
   similar task size — not whole-corpus aggregates. Report the pairing, not
   just the pooled number.
2. **Survivorship.** `rejected` ≠ wrong. Correct-but-abandoned work exists;
   the label records the world's decision, not the reasoning's quality.
   Never convert outcome labels into correctness labels for training without
   a human adjudication pass on a sample.
3. **Label leakage into features.** Features must be computable from the
   trace alone, without knowing the outcome. A feature that encodes "the
   human replied angrily" is outcome-adjacent, not reasoning quality.

## Rule 4 — Provenance of mined traces

All mined traces are model-origin. That is fine for their legitimate uses and
forbidden for others:

| Use | Allowed? |
| --- | --- |
| Solver SFT on `integrated` traces | only via explicit `eligible_for` gates; a landed artifact may support final-answer SFT without validating the intermediate steps — training on a whole successful transcript also teaches its abandoned errors |
| Critique data (`integrated` + `rejected` pairs on the same blocker) | yes, labeled `model_origin`, with split groups by repo/task family |
| Verifier/reward feature development | yes, on receipt-grounded event chains |
| Any human-authored rationale path | no — mined model text never becomes `human_composed` content |
| Full trace text embedded into `$memory` | no — store pointer records (trace id, digest, label, artifact path); artifacts remain the provenance spine |

Filter client-sensitive content and secrets before ANY external scoring, not
only before memory writes — quotes, summaries, and vectors inherit the
restriction.

**Correction-derived preference pairs are NOT default DPO pairs.** Most user
corrections are instructions or partial diagnoses, not interchangeable
assistant completions; training "you edited the wrong repo" as a chosen
completion teaches role mismatch. Pair construction requires: target
resolution (which answer was corrected), comparable output objects for the
same decision, context accounting (new information vs. fair same-context
comparison), an independent preference basis, and preserved derivation. When
feedback supplies missing information, build a feedback-conditioned repair
example instead — and never mark the original answer wrong for lacking
information it could not have had. `corrected_by` stays observational until a
separate pair-construction gate passes.

## Rule 5 — Scoring and audit mechanics

Literal quote verification is DETERMINISTIC code, never a model call. An exact
quote does not establish that it supports the assigned feature ("I found the
root cause" is a quote, not root-cause evidence) — contextual support is the
stronger model's job. Scorer children get redacted, read-only, OUTCOME-BLIND
source views; exhausted budgets and unread context are processing failures,
never reasoning-quality labels.

Audit honesty: a 10% sample of 200 traces is 20 decisions; even ZERO errors in
20 implies only a 13.9% one-sided 95% upper bound on the error rate
(1 − 0.05^(1/20)). Model-on-model agreement proves less. Report per-feature
precision/recall against blinded HUMAN reference labels, with disagreement and
abstention separated.

## Rule 6 — Live application (agent discipline)

When this skill activates during a live run, the taxonomy doubles as
self-discipline:

- before naming a cause: read the owning receipt (Rule 1 of the trace is
  Rule 1 of the live run)
- after each claimed effect: read it back
- after two focused failures on one blocker: escalate, do not attempt three
- never end a turn on a status report while an obvious repair remains
- label every state claim in your own final report with the command that
  proved it, or mark it unverified

A live trace that follows these rules is an `integrated`-candidate in the
making; one that violates them is generating tomorrow's negative examples.

## Non-claims

- No feature here is corpus-validated yet; the first feature-outcome table
  reports exploratory ASSOCIATIONS with clustered uncertainty, not confirmation
  of priors, and 200 records cannot produce a corpus-wide success rate.
- Outcome labels are world decisions, not reasoning-quality judgments.
- Observable transcript content is not verified access to the model's internal
  reasoning; causal claims from prose alone are out of scope.
- Nothing in this skill certifies a reasoning model; it labels data.
- Full design review with sources: `references-webgpt-design-review-20260915.md`.
