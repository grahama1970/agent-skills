# Review Skill Iteration Contract

All `review-*` skills use the same bounded iteration vocabulary.

## Standard Options

Every `review-*` skill that accepts a review target should support, or explicitly
fail closed when it cannot support, these options:

- `--max-rounds N`: bounded review/remediation rounds. `N > 1` activates
  controller mode.
- `--output-dir PATH`: directory for machine-readable review artifacts.
- `--ask-gate`: run real `$ask --deep-review` as an external final/readiness
  gate when the local deterministic review has no blockers.
- `--ask-model MODEL`: default `gpt-5.5`.
- `--ask-reasoning LEVEL`: default `high`.
- `--ask-timeout SECONDS`: default should be long enough for queued `$scillm`
  reviewer calls.
- `--ask-focus LABELS`: comma-separated deep-review focus labels.

Domain-specific names such as `--rounds`, `--cycles`, or `--loop` may remain as
aliases, but `--max-rounds` is the canonical parameter.

## Gate Artifact

Controller mode writes:

```text
<output-dir>/review_result.json
```

Canonical schema:

```json
{
  "schema": "review_skill.gate.v1",
  "skill": "review-plan",
  "target": "path-or-target-id",
  "verdict": "PASS|NEEDS_CHANGES|BLOCKED|INSUFFICIENT_EVIDENCE",
  "reason": "short_machine_reason",
  "iterations": 1,
  "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "warn": 0, "fail": 0},
  "findings": [],
  "next_iteration_plan": [],
  "ask_artifacts": {
    "request_json": null,
    "status_json": null,
    "events_jsonl": null,
    "review_md": null,
    "review_json": null
  }
}
```

## Pass Rule

The gate must not return `PASS` when any of these are present:

- critical, high, or medium findings
- unresolved blockers
- missing required review artifacts
- failed deterministic validators
- insufficient evidence
- stale screenshots, stale diffs, stale fixtures, or stale endpoint proof
- malformed or missing `$ask` artifacts when `--ask-gate` is requested

Review text alone is not proof. The gate must be based on stored artifacts.

## Remediation Boundary

Review skills may produce suggestions and next-iteration plans. They must not
silently mutate production code or source artifacts unless that skill documents
an explicit remediation command and writes before/after artifacts.

If a skill cannot remediate directly, `--max-rounds > 1` still has meaning: the
skill runs as a fail-closed controller and writes `review_result.json` so the
project agent, `$plan-iterate`, or `/orchestrate` can perform the next
remediation pass.

## `$ask` Gate

When `--ask-gate` is set:

1. Use the real `$ask` runtime.
2. Use `--deep-review` with readable target files, not archives or opaque
   directories.
3. Preserve `request.json`, `status.json`, `events.jsonl`, `review.md`, and
   `review.json` paths in `review_result.json`.
4. Account for `$scillm` queue/concurrency and hard timeouts. A timeout or
   stream failure is `INSUFFICIENT_EVIDENCE` unless an inspectable review
   artifact was produced.
