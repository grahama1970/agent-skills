# Phase Review Request: phase-04-docs-workflow-update

## Requested Verdict

Return one verdict:

```text
PASS
NEEDS_CHANGES
BLOCKED
```

## Review Focus

- Does `PHASE_STATUS.json` make claims only when evidence artifacts exist?
- Does every external verdict name the adjudicator kind (`webgpt`, `scillm`, `human`, or `deterministic_verifier`)?
- Does every review result cite stored response/request/bundle/receipt artifacts with current SHA-256 hashes and invocation metadata?
- Does the bundle include a `skill_context_artifacts` entry explaining the headless skill contract, including skill paths, runtime entrypoints, role boundaries, and reviewer limits?
- For repeated reviews, does the bundle include bounded progress context (`progress_context_artifacts` and/or `memory_context.keys`) covering prior findings, blockers, decisions, and current delta?
- If the reviewer is `$scillm`, does the request use `model: "gpt-5.5"` with top-level `reasoning_effort: "high"` and no `max_tokens` field?
- Do validation commands include exit codes and logs where applicable?
- Do changed files match the implementation summary?
- Are caveats explicit rather than hidden by green language?
- Are heuristic hints separated from confirmed findings and reviewer receipts separated from deterministic evidence?
- If this phase touches security, correctness, deployment, or reports, is the proof deterministic enough to advance?

## Reviewer Instructions

Check the bundle artifacts before trusting prose. List exact blockers and the minimal patch required to resolve each blocker.

Do not mark closure from reviewer prose alone. A reviewer verdict is a receipt; deterministic validation gates close the phase.

For phase completion, the reviewer-facing prompt should be produced by `$review-code bundle` and then submitted to `$scillm` `gpt-5.5` with top-level `reasoning_effort: "high"`. Do not include `max_tokens` in the `$scillm` request. Treat headless reviewers as skill-blind unless this bundle provides the relevant `SKILL.md` paths and compact operational contracts.
