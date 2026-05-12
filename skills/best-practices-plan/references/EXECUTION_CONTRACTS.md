# Execution Contracts for Project-Agent Plans

**Rule ID:** `plan-reviewed-contract-first`  
**Severity:** CRITICAL for complex projects  
**Applies to:** `/plan`, `/best-practices-plan`, `/review-plan`, `/orchestrate`, and any task file that delegates work to a project agent.

## Core rule

A task plan is not a place for the project agent to invent strategy. It is a place to encode an already-reviewed contract into executable tasks.

For ambiguous or complex work, a valid plan must start from a contract that was defined by the human and/or reviewer. The project agent may translate that contract into YAML; it may not silently change the meaning of the work while implementing.

```text
Reviewer/human decides: intent, proof standard, status vocabulary, gates.
Plan encodes: commands, runners, allowlists, dependencies, artifacts.
Project agent executes: patches, tests, logs, evidence bundles.
Gates decide: closure.
```

## What must be in the contract

Plans involving extraction, review, model calls, status changes, closure, evidence cases, or core-vs-preset routing must include:

1. **Input artifacts** — exact files, JSON, images, fixtures, prompts, or service endpoints.
2. **Output schema** — allowed fields, allowed values, and validation command.
3. **Status vocabulary** — what each status means and what gate permits transition.
4. **Forbidden shortcuts** — e.g. no heuristic-to-finding, no fake review, no closure from reports.
5. **Canary cases** — at least one positive, negative, ambiguous, and expected-failure case when introducing a new loop.
6. **Replay artifacts** — prompt/payload/response/validation/log artifacts required for review results.
7. **Deterministic gates** — tests, diffs, fixtures, projection/readback, or other reproducible proof.
8. **Stop conditions** — when to stop and ask human/reviewer instead of continuing.

If those are missing, the plan must request clarification/review instead of creating implementation tasks.

## Banned task shapes

```yaml
# BAD: asks the project agent to define strategy.
- title: "Figure out the second-pass architecture and fix it"
  runner: code-runner

# BAD: asks the agent to decide proof semantics.
- title: "Determine if this is closed"
  runner: code-runner

# BAD: asks the agent to route ownership without a reviewed contract.
- title: "Decide if this is core or preset"
  runner: code-runner

# BAD: aggregate loop with no canary or stop condition.
- title: "Run the repair loop until all blockers are green"
  runner: code-runner
```

## Required task shapes

```yaml
# GOOD: collect evidence; reviewer decides.
- title: "Collect extraction evidence for candidate actual:p1:block:6"
  runner: local
  command: "uv run python scripts/pdf_lab/render_second_pass_prompt.py --candidate-id actual:p1:block:6 --out /tmp/case"
  definition_of_done:
    command: "test -s /tmp/case/input_payload.json && test -s /tmp/case/validation_result.json"
    assertion: "Replayable evidence bundle exists; no status mutation occurred."

# GOOD: implement an approved deterministic audit.
- title: "Implement paragraph_bbox_audit from raw.lines[].bbox"
  runner: code-runner
  allowlist:
    - scripts/pdf_lab/bbox_audit.py
    - tests/test_bbox_audit.py
  definition_of_done:
    command: "uv run pytest tests/test_bbox_audit.py -q"
    assertion: "Audit returns confirmed/disconfirmed/insufficient_evidence from line bboxes."
```

## Runner guidance

- Use `local` for deterministic commands and evidence gathering.
- Use `scillm` for one-shot edits that do not require architecture decisions.
- Use `code-runner` only for narrow implementation under an explicit contract and allowlist.
- Do not use `code-runner` for status vocabulary, closure semantics, prompt/schema design, or core-vs-preset routing decisions.

## Required stop-and-ask cases

Stop and request reviewer/human input when:

- the plan needs a new status or changes a status meaning,
- a heuristic would become a finding,
- a report/dashboard is being treated as proof,
- a model/LLM result would mutate a matrix or closure state,
- a defect might be routed to core code,
- batch expansion is proposed before canary review,
- evidence is insufficient but the plan wants to proceed anyway.

## Relationship to `agent-no-simulated-review`

This rule composes with `skills/best-practices-agent/references/NO_SIMULATED_REVIEW.md`.

A plan must preserve this boundary:

```text
hint != finding
classifier != review
review != fix
fix != closure
```

Any task file that blurs those boundaries should fail review before `/orchestrate` runs.
