# No Simulated Review / Evidence-Gated Decisions

**Rule ID:** `agent-no-simulated-review`  
**Severity:** CRITICAL  
**Applies to:** all project-agent workflows, review loops, closure reports, extraction pipelines, QA gates, prompt/model pipelines, dashboards, and status matrices.

## Core rule

Do not create authoritative-looking review, validation, correction, or closure results from heuristics, partial checks, stale artifacts, or report generation.

A heuristic may create a **hint**. It may not create a **confirmed finding**, **correction**, **core bug**, **human decision**, or **closure state**.

The required distinction is:

```text
hint/suspect        = weak signal; may route to an audit
confirmed finding   = audit-backed or reviewer-backed
review              = actual model/human/reviewer call with replay artifacts
fix                 = implemented code/preset/core/human decision
closure             = deterministic gates passed after rerun
```

## Banned patterns

```python
# BAD: Heuristic becomes a correction label.
if bbox_area > 0.45:
    risk_reasons.append("bbox_over_broad")

# BAD: Label copy masquerades as review.
if "bbox_over_broad" in risk_reasons:
    result["decision"] = "emit_correction"
    result["confidence"] = "high"

# BAD: Misleading process name when no model or human reviews anything.
python run_second_pass_reviews.py

# BAD: Closure label without deterministic proof.
status = "core_fixed"  # no core patch, no fixture, no rerun
```

## Required patterns

```python
# GOOD: Heuristic is only a hint.
if bbox_area > 0.45:
    risk_reasons.append("bbox_suspect_large_area")

# GOOD: Audit decides the strong label.
audit = bbox_audit_for_element(element)
if audit.status == "confirmed":
    risk_reasons.append("bbox_over_broad")
elif audit.status == "insufficient_evidence":
    risk_reasons.append("bbox_audit_insufficient")

# GOOD: Honest process identity.
result["adjudicator_kind"] = "deterministic_classifier"  # or llm / human / verifier
result["confidence"] = "deterministic"
```

## Required vocabulary discipline

Use status words precisely:

- `*_suspect_*` = weak heuristic hint
- `*_confirmed_*` = audit-backed finding
- `*_insufficient_evidence` = unresolved; never accepted by default
- `*_pending` = unresolved workflow state
- `reviewed` = a model, human, or named reviewer actually reviewed replayable evidence
- `verified` = deterministic verification passed
- `fixed` / `closed` = implementation or decision landed, rerun passed, fixtures/gates passed

Never use words such as `reviewed`, `verified`, `resolved`, `closed`, `core_fixed`, `agent_resolved`, `human_decision`, or `second_pass` unless the artifact proves the mechanism actually occurred.

## Replay artifact requirement

Every model, human, or deterministic review result must be replayable.

Required artifacts:

```text
system_prompt.txt              # if LLM
user_prompt.txt                # if LLM
input_payload.json
selected_config_or_preset.json
source_artifacts/              # images, crops, diffs, overlays, logs
model_response.json            # if LLM
deterministic_response.json    # if deterministic classifier
validated_decision.json
validation_result.json
```

No replay bundle means no accepted review result.

## Closure authority hierarchy

Project agents may propose.  
LLMs may adjudicate ambiguous cases.  
Humans may resolve product or semantic ambiguity.  
Only deterministic gates may close.

Closure requires:

1. source evidence attached or reproducible,
2. mechanism named honestly,
3. result replayable,
4. weak hints separated from confirmed findings,
5. deterministic validation passed,
6. unresolved cases remain explicitly pending.

## Canary before batch

Before running a new review/agent loop on many cases, prove the contract on canaries:

- one expected positive case,
- one expected negative case,
- one ambiguous or insufficient-evidence case,
- one expected failure case,
- one regression fixture.

Do not batch until the canaries pass.

## Required reviewer checkpoints

Reviewer signoff is required before:

- new status vocabulary,
- prompt/schema contract changes,
- any claim that a heuristic result is a finding,
- routing a defect to core code,
- expanding from canary to batch,
- declaring a report or dashboard to be proof of closure.

## Cross-project rule

No process may claim a capability unless the artifacts prove that capability actually ran.

Examples:

- No “LLM review” unless model input/output artifacts exist.
- No “visual review” unless page/crop images were attached.
- No “bbox_over_broad” unless a bbox audit confirms it.
- No “core bug” unless a generic invariant or reproducer exists.
- No “closed” unless deterministic rerun plus fixtures pass.
- No “human decision” unless a human decision record exists.
