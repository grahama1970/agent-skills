# /plan Is an Execution Manifest, Not a Strategy Generator

**Rule ID:** `plan-execution-manifest-not-strategy`  
**Severity:** CRITICAL for complex projects  
**Applies to:** `/plan`, `/review-plan`, `/orchestrate`, and project-agent task files.

## Core rule

For complex or ambiguous work, the project agent must not invent the strategy, status vocabulary, proof standard, prompt/schema contract, or meaning of success.

`/plan` should convert an already-reviewed contract into executable tasks. It should not be used as an autonomous reasoning engine.

```text
Human / reviewer defines: intent, contract, gates, stop conditions.
/plan encodes: tasks, runners, commands, dependencies, artifacts.
/orchestrate runs: code, tests, extraction, verification.
Deterministic gates decide: closure.
```

## What the project agent may do

Project agents may:

- find relevant files and functions,
- inspect code paths,
- draft YAML from an approved contract,
- implement narrow patches,
- run commands and tests,
- collect logs and artifacts,
- lightly debug failing commands,
- report exact evidence and unresolved blockers.

## What the project agent must not decide alone

Project agents must not independently decide:

- what `closed`, `verified`, `resolved`, or `done` means,
- status vocabulary,
- prompt/schema contracts,
- core-vs-preset ownership,
- whether a heuristic is a finding,
- whether a report/dashboard proves completion,
- whether to expand from canary to batch,
- whether an LLM/human review actually occurred,
- whether a core bug exists without a generic invariant or reproducer.

If a task requires those decisions, the plan must stop and request reviewer/human input.

## Bad plan patterns

```yaml
# BAD: asks project agent to reason about meaning and closure.
- id: "1"
  title: "Fix the second pass until it works"
  runner: code-runner

# BAD: asks agent to decide ownership.
- id: "2"
  title: "Determine whether this is a core bug or preset bug"
  runner: code-runner

# BAD: asks agent to prove with a report.
- id: "3"
  title: "Update dashboard until all blockers are green"
  runner: code-runner
```

## Good plan patterns

```yaml
# GOOD: evidence collection only; reviewer decides ownership.
- id: "1"
  title: "Collect bbox audit evidence for candidate actual:p19:table:0"
  runner: local
  command: "uv run python scripts/pdf_lab/audit_candidate_bbox.py actual:p19:table:0 --out /tmp/audit.json"
  definition_of_done:
    command: "test -s /tmp/audit.json && jq -e '.raw_bbox and .union_bbox and .max_drift_pt' /tmp/audit.json"
    assertion: "Audit JSON contains raw bbox, union bbox, and drift. No status mutation."

# GOOD: implements an already-approved rule.
- id: "2"
  title: "Implement paragraph_bbox_audit from raw.lines[].bbox"
  runner: code-runner
  allowlist:
    - scripts/pdf_lab/bbox_audit.py
    - tests/test_bbox_audit.py
  definition_of_done:
    command: "uv run pytest tests/test_bbox_audit.py -q"
    assertion: "Paragraph audit returns confirmed/disconfirmed/insufficient_evidence from line bboxes."
```

## Required for semantic/closure work

Before `/plan` writes tasks for status changes, model review, closure reports, extraction quality, or core-vs-preset routing, the input must include a reviewed contract with:

1. allowed input artifacts,
2. output schema,
3. status vocabulary,
4. forbidden shortcuts,
5. canary cases,
6. replay artifact requirements,
7. deterministic gates,
8. stop conditions.

If that contract is missing, `/plan` must write an interview/reviewer-request artifact instead of creating implementation tasks.

## Canary before batch

Any plan that introduces a new review loop, model prompt, classifier, extraction route, or verifier must run one or more canaries before a batch.

Batch expansion requires explicit reviewer approval after the canary evidence bundle is reviewed.

## Relationship to best-practices-agent

This rule composes with `agent-no-simulated-review`:

- heuristics may create hints, not findings;
- no review claim without replay artifacts;
- no closure claim without deterministic rerun and fixtures;
- project agents may propose, but deterministic gates close.
