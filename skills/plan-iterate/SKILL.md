---
name: plan-iterate
description: Evidence-gated phase iteration for implementation plans. Use when a task must proceed phase by phase with deterministic artifacts, validation logs, named external reviewer verdicts, default scillm GPT-5.5 high review, optional reviewer comparison, blocker tracking, and fail-closed acceptance before advancing; especially for security, correctness, deployment, or report-hardening work.
metadata:
  short-description: Evidence-gated implementation phase iteration
provides:
  - phase-iteration-control
  - evidence-review-packaging
  - fail-closed-phase-acceptance
composes:
  - plan
  - review-plan
  - scillm
  - ask
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-plan
disciplines:
  - agentic-orchestration
  - evaluation-quality
---

# Plan Iterate

Use this skill to control implementation phases:

```text
define phase -> implement -> validate locally -> package evidence -> external review -> patch blockers -> accept or stop
```

It does not replace `/plan`, `/review-plan`, `/orchestrate`, `$hack`, or `review-extraction`. It verifies whether an implemented phase satisfied its contract with evidence.

## Core Rules

- Do not mark a phase done from prose, status text, or absence of errors.
- Keep raw artifacts, validation logs, and reviewer responses in the phase directory.
- Treat scillm/WebGPT/external review as a bounded checkpoint, not an outsourced reasoning loop.
- Give `$scillm` bounded, replayable progress context on repeated reviews; do not rely on hidden CLI transcript state.
- Name the adjudicator for every review result: `webgpt`, `scillm`, `human`, or `deterministic_verifier`.
- A reviewer verdict is a receipt, not closure. Only deterministic validation can close a phase.
- Do not call heuristic classification, label copy, or report generation a review unless a named reviewer actually reviewed replayable evidence.
- Use reviewer comparison when the phase crosses a trust boundary or prior solo iteration produced a false green.
- Escalate before closure when raw evidence disagrees with report claims, a blocker repeats twice, or the human disproves a green claim.
- Run canaries before batching: one positive, one negative, one ambiguous/insufficient-evidence, one expected failure, and one regression fixture.
- For security-sensitive work, require raw proof artifacts, command logs, manifest hashes, and post-patch verification before accepting closure claims.

## Phase States

Use only these states:

```text
planned
implementing
local_validation_failed
ready_for_review
external_review_blocked
external_review_passed
accepted
superseded
abandoned
```

A phase is complete only when its status is `accepted`.

## CLI

Run commands from the repository root that owns the phase work:

```bash
skills/plan-iterate/run.sh init --phase phase-01-report-cleanup
skills/plan-iterate/run.sh record-skill-context --phase phase-01-report-cleanup --context /tmp/headless-skill-context.md
skills/plan-iterate/run.sh record-context --phase phase-01-report-cleanup --context /tmp/phase-context.md
skills/plan-iterate/run.sh package --phase phase-01-report-cleanup --output /tmp/phase-01-review.zip
skills/plan-iterate/run.sh record-review --phase phase-01-report-cleanup --verdict blocked --review scillm-gpt55-review.md
skills/plan-iterate/run.sh status
```

Use `--root DIR` when the phase state should live outside the current repository. The default root is `.plan-iterate`.

Run the medium-complexity local sanity before relying on the skill after edits:

```bash
skills/plan-iterate/sanity.sh
```

The sanity creates a temporary git repo, proves missing skill context fails
closed, records headless skill context, records progress context, packages a
review ZIP, records two distinct passing reviewer receipts against the same
bundle, and closes reviewer comparison.

## Phase Status Contract

Each phase owns:

```text
.plan-iterate/<phase-id>/
  PHASE_STATUS.json
  PHASE_REVIEW_REQUEST.md
  reviews/
```

`PHASE_STATUS.json` must use schema `plan_iterate.phase_status.v1` and include:

```json
{
  "schema": "plan_iterate.phase_status.v1",
  "phase_id": "phase-03-evolution-decision-log",
  "status": "ready_for_review",
  "implementation_summary": "...",
  "acceptance_contract": [],
  "changed_files": [],
  "validation_commands": [],
  "evidence_artifacts": [],
  "progress_context_artifacts": [],
  "skill_context_artifacts": [],
  "review_artifacts": [],
  "known_caveats": [],
  "claims": [],
  "blockers": [],
  "memory_context": {
    "collection": "plan_iterate_phase_context",
    "keys": []
  },
  "reviewer_policy": {
    "required": true,
    "comparison_required": false,
    "closure_rule": "deterministic_validation_and_external_review"
  },
  "review_results": [],
  "review_comparison": {
    "agreement": "pending",
    "closure_allowed": false,
    "reason": ""
  },
  "review_status": "pending"
}
```

Validation command entries must include `command`, `exit_code`, and optional `log`.
Claims must cite evidence artifacts. Blockers with two or more occurrences must be marked `escalated: true`.
`review_results` must cite stored `review_artifacts` with response/request/bundle/receipt hashes, `phase_subject_sha256`, `skill_context_sha256`, invocation metadata, and `recorded_at`.
For repeated reviews, `review_results` after the first must include `progress_context_sha256`, and the phase must include `progress_context_artifacts` or Arango-backed `memory_context.keys`.
Implementation claims may cite only deterministic `evidence_artifacts`, not reviewer receipts.
`accepted` requires `review_comparison.closure_allowed=true`, no blocked/conditional review results, hashed changed file bytes, hashed deterministic evidence artifacts, hashed validation logs bound to the current phase subject, at least one claim covering the acceptance contract, and passing deterministic validation unless `reviewer_policy.required=false`.
`phase_subject_sha256` binds the acceptance contract, changed file paths and hashes, deterministic evidence, validation commands, claims, reviewer policy, known caveats, blockers, progress context references, skill context references, and memory context references.

## Review Bundle

`package` creates a ZIP containing:

```text
PHASE_STATUS.json
PHASE_REVIEW_REQUEST.md
changed-files.diff
manifest.json
validation-logs/
evidence-artifacts/
progress-context/
skill-context/
reviews/
```

The package fails closed when claims lack artifacts, evidence files are missing, progress context files are missing, skill context files are missing, validation commands lack exit codes, accepted validation logs lack current hashes, review results lack named adjudicators/provenance, review artifact hashes do not match current bytes, repeated reviews lack progress context, accepted phases have blocked or conditional reviews, repeated blockers are un-escalated, reviewer comparison does not allow closure, or accepted phases lack passing validation and deterministic evidence.

## External Reviewer Loop

Use external reviewers only at phase checkpoints, canaries, or escalation triggers:

```text
project agent implements phase
plan-iterate packages evidence
review-code bundles the phase completion for review
scillm/WebGPT/human reviews the review-code bundle and phase evidence
project agent records verdict
project agent patches exact blockers
repeat until pass or stop
```

Preserve reviewer outputs as `reviews/<timestamp>-<reviewer>-response.md` through `record-review`.

Each phase completion review should use a `$review-code bundle` as the reviewer-facing request, then send that bundle to the selected reviewer. The default reviewer path is `$review-code bundle` -> `$scillm` `gpt-5.5` high reasoning. The `$review-code` bundle should include the plan-iterate review ZIP hash, phase subject hash, skill context hash, acceptance contract, current diff, validation output, non-goals, known caveats, blockers, progress context, and headless skill context. The reviewer may critique the phase; the project agent still owns code changes and deterministic validation.

Default reviewer:

- `scillm:gpt-5.5-high`: default external reviewer for targeted phase/code/contract review. Use `$scillm` with `model: "gpt-5.5"` and top-level `reasoning_effort: "high"`, preferably streaming for long review bundles. It is replayable, scriptable, and exposes machine-readable reasoning proof.

Escalation and comparison reviewer use:

- `webgpt`: optional escalation for strategy, taxonomy decisions, report clarity, cross-project process review, or an independent human-facing judgment check using `$surf webgpt.submit`; do not make it the default when `$scillm` can review the same bundle.
- `scillm:gpt-5.5-high`: hard semantic or multimodal canaries; expensive, not for broad batches.
- `scillm:claude-sonnet-high`: adversarial plan, prompt, and implementation critique.
- `scillm:gemini-flash-high`: long-context PDF/report review when latency and cost matter.
- `scillm:oc-kimi`: bounded visual batches after canaries prove the prompt, schema, and image attachment contract.
- `scillm:opencode-deepseek`: text-only code or schema review; do not use for visual bbox decisions.
- `human`: policy, semantic, or residual ambiguity that the project agent and reviewers cannot resolve.

Record the default scillm GPT-5.5 high review:

Use a replayable request JSON that includes `model: "gpt-5.5"` and top-level
`reasoning_effort: "high"`. For long bundles, prefer SSE streaming and preserve
the request JSON, SSE/raw response, extracted review markdown, and final
`scillm_reasoning` proof. Do not set `max_tokens`; reasoning models can consume
internal reasoning tokens and low caps can produce empty output.

For headless reviewers and subprocess agents, record a compact skill context
artifact before packaging review evidence. Treat headless calls as skill-blind
unless the request explicitly includes the relevant skill names, absolute
`SKILL.md` paths, runtime entrypoints, artifact protocol, and role boundaries.
The skill context should state which component is orchestrator, reviewer,
implementer, memory store, and human escalation path.

Record headless skill context:

```bash
skills/plan-iterate/run.sh record-skill-context \
  --phase phase-01-report-cleanup \
  --context /tmp/headless-skill-context.md
```

For the default phase-review loop, the context should mention at minimum
`$plan-iterate`, `$review-code`, `$scillm`, `$memory`, and `$interview`. Add
`$code-runner` or `$subagent-runner` only when that phase actually uses them.

For repeated reviews, include a bounded progress context artifact and store the
same compact context in ArangoDB through `$memory` using the
`plan_iterate_phase_context` collection. ArangoDB `$memory` is the default source
of progress history; local `progress-context/` files are hashable mirrors for
bundle replay, not the primary history store. The context should be source-derived:
prior reviewer findings, blocker ledger, decision log, current delta, and
artifact hashes. Store only compact progress context in ArangoDB; keep large
raw artifacts on disk and reference them by path/hash.

Record progress context before a non-first review:

```bash
skills/plan-iterate/run.sh record-context \
  --phase phase-01-report-cleanup \
  --context /tmp/phase-01-progress-context.md \
  --memory-key phase-01-review-002
```

`record-context` copies the context into `progress-context/`, records its
SHA-256 in `progress_context_artifacts`, and adds the ArangoDB key to
`memory_context.keys`. By default it writes the compact context to `$memory`
via `/upsert`. Use `--skip-memory-upsert` only for isolated tests or when memory
is operationally unavailable; report that gap because repeated reviews should
not depend only on hidden CLI state or local fallback files.

```bash
skills/plan-iterate/run.sh record-review \
  --phase phase-01-report-cleanup \
  --reviewer scillm-gpt55-high \
  --adjudicator-kind scillm \
  --verdict needs_changes \
  --review /tmp/scillm-gpt55-review.md \
  --review-request /tmp/scillm-request.json \
  --review-bundle /tmp/phase-review.zip \
  --invocation-command "curl /v1/chat/completions model=gpt-5.5 reasoning_effort=high" \
  --invocation-receipt /tmp/scillm-http-response.json \
  --model gpt-5.5
```

Record an optional WebGPT escalation review:

```bash
skills/plan-iterate/run.sh record-review \
  --phase phase-01-report-cleanup \
  --reviewer webgpt \
  --adjudicator-kind webgpt \
  --verdict passed \
  --review /tmp/webgpt-response.md \
  --review-request /tmp/webgpt-request.md \
  --review-bundle /tmp/phase-review.zip \
  --invocation-command "surf webgpt.submit --input /tmp/webgpt-request.md" \
  --invocation-receipt /tmp/webgpt-response.meta.json
```

When `reviewer_policy.comparison_required=true`, `record-review --verdict passed` stores each reviewer receipt without marking the phase externally passed. After all required distinct reviewers are recorded, set the comparison explicitly:

```bash
skills/plan-iterate/run.sh record-comparison \
  --phase phase-01-report-cleanup \
  --agreement agree \
  --closure-allowed \
  --reason "scillm GPT-5.5 high and comparison reviewer both passed the same bundle."
```

## Reviewer Comparison

Set `reviewer_policy.comparison_required=true` when:

- the phase changes correctness, extraction, security, compliance, deployment, memory, or user-facing verification;
- the human disproved an earlier green claim;
- a blocker survived two implementation attempts;
- the phase combines code, prompt, schema, data, and UI/report judgment.

Comparison is explicit state, not an implied mood:

```json
{
  "review_comparison": {
    "agreement": "agree",
    "closure_allowed": true,
    "reason": "scillm GPT-5.5 high and comparison reviewer agree; deterministic validation passed."
  }
}
```

Use only these agreement values:

```text
pending
agree
partial
disagree
insufficient
```

If reviewers disagree, duplicate the same reviewer, return `conditional_pass`, return `partial`, or evidence is insufficient, set `status=external_review_blocked`, keep `closure_allowed=false`, patch the blocker, and rerun the relevant validation/review. Do not batch or accept the phase from a split review.
`review_comparison.closure_allowed=true` is valid only when `agreement=agree`.
Comparison-required phases require all passing reviewers to reference the same `review_bundle_sha256`, and every review result must match the current `phase_subject_sha256` computed from the acceptance contract, changed file paths and hashes, deterministic evidence, validation commands, and claims.
