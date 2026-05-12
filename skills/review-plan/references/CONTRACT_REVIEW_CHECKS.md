# Contract Review Checks for /review-plan

**Rule ID:** `review-plan-contract-boundaries`  
**Severity:** CRITICAL for complex plans  
**Applies to:** `/review-plan` validation of task files before `/orchestrate`.

## Purpose

`/review-plan` must catch plans that ask project agents to invent strategy, semantics, proof standards, or closure while executing code.

A task file should encode an approved contract into commands and artifacts. It should not delegate architectural or semantic authority to a project agent.

## New FAIL checks

A plan should FAIL review when it contains any of the following without an explicit reviewed contract:

1. **Status vocabulary invention**
   - Examples: `decide status`, `mark closed`, `promote to verified`, `update matrix status`.
   - Required fix: cite the reviewed status vocabulary and the gate for each transition.

2. **Closure semantics delegated to agent**
   - Examples: `run until fixed`, `close all blockers`, `make report green`.
   - Required fix: replace with deterministic gates and stop conditions.

3. **Core-vs-preset ownership delegated to agent**
   - Examples: `determine if core bug or preset bug`.
   - Required fix: split into evidence collection task, then reviewer/human decision.

4. **Heuristic-to-finding promotion**
   - Examples: `if large area then bbox_over_broad`, `confidence high from branch`, `label as reviewed`.
   - Required fix: heuristic may emit only `*_suspect_*`; audit/reviewer produces confirmed labels.

5. **Fake review wording**
   - Examples: task named `review`, `second-pass`, `adjudicate`, or `human decision` without replay artifacts proving a model/human/reviewer is invoked.
   - Required fix: rename deterministic tasks honestly or wire the actual reviewer and replay bundle.

6. **Batch before canary**
   - Examples: `run on all candidates`, `process 100 pages`, `batch review all` for a new prompt/classifier/verifier.
   - Required fix: add canary task(s), reviewer checkpoint, and batch expansion gate.

7. **LLM output mutates source of truth directly**
   - Examples: model response directly updates preset, matrix, closure report, or core bug status.
   - Required fix: model response becomes evidence only; deterministic promotion/verifier task must follow.

8. **Report/dashboard used as proof**
   - Examples: `dashboard green`, `HTML report says resolved`, `coverage card shows 0 blockers` as final DoD.
   - Required fix: DoD must cite underlying deterministic artifacts, tests, diffs, projection/readback, or fixtures.

## Required sections for complex plans

Plans involving model review, extraction, closure, status transitions, or core-vs-preset routing must include:

```yaml
metadata:
  reviewed_contract:
    source: "<path or reviewer artifact>"
    status_vocabulary: "<path>"
    output_schema: "<path>"
    forbidden_shortcuts: "<path>"
    canary_required: true
    batch_expansion_requires_review: true
```

Each implementation task must state whether it is:

- evidence collection,
- implementation of an approved contract,
- deterministic verification,
- reviewer/human decision artifact generation.

## Good review response

When `/review-plan` finds one of these issues, it should not merely warn. It should return a precise correction:

```text
FAIL: Task 4 asks code-runner to decide whether this is a core bug.
Reason: core-vs-preset ownership is a semantic routing decision.
Fix: split into Task 4a collect evidence and Task 4b reviewer decision checkpoint.
```

## Relationship to other rules

This reference enforces:

- `skills/best-practices-agent/references/NO_SIMULATED_REVIEW.md`
- `skills/plan/references/EXECUTION_MANIFEST_NOT_STRATEGY.md`
- `skills/best-practices-plan/references/EXECUTION_CONTRACTS.md`

The boundary to preserve is:

```text
hint != finding
classifier != review
review != fix
fix != closure
report != proof
```
