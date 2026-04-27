# ask Deep Review Contract

Deep review is the `/ask` lane for comprehensive, read-only, Web-GPT-style
architecture and implementation-risk review. It exists to avoid manual browser
copy-paste while preserving auditability.

## Contract

- Deep review defaults to oracle execution with `gpt-5.5` and `xhigh` reasoning when available.
- Deep review uses `subagent-runner` by default because it is a focused agent call, not a batch LLM lane.
- Deep review is read-only at runtime. It may write only review artifacts and telemetry.
- Memory recall is context, not evidence. Repo claims must be grounded in inspected files, diffs, tests, artifacts, or command output.
- The output must include both human-readable markdown and machine-checkable JSON.

## Required Inputs

A review must have a target:

```text
--deep-review-target src/ask/ask.py
--deep-review-target "current branch vs main"
--deep-review-target docs/IMPLEMENTATION_PLAN.md
```

If the human says only `safe to proceed?`, the route must fail closed or request
a target. Broad review without a target creates false confidence.

## Required Artifacts

```text
.ask_artifacts/deep-review/<timestamp>/review.md
.ask_artifacts/deep-review/<timestamp>/review.json
```

`review.md` is for human reading. `review.json` is for deterministic gating,
telemetry, and future automation.

## Required Verdicts

The final verdict must be exactly one of:

```text
SAFE
SAFE_WITH_CONDITIONS
NOT_SAFE
INSUFFICIENT_EVIDENCE
```

## Required Sections

`review.json` must include:

- `target_reconstruction`
- `architecture_boundaries`
- `fail_closed_behavior`
- `production_failure_modes`
- `evidence_auditability`
- `deterministic_checks`
- `test_proof`
- `complexity_removal`
- `security_data_risk`

Each section must distinguish `verified`, `issues_found`, `none_found`, and
`not_assessed`. `none_found` requires evidence. `not_assessed` fails the verifier
for required sections.

## Verifier Gates

The deterministic verifier rejects:

- invalid verdicts
- missing targets
- `SAFE` or `SAFE_WITH_CONDITIONS` without inspected evidence
- missing sections
- `not_assessed` required sections
- shallow summaries
- findings without evidence, impact, fix, or verification
- unexpected non-artifact file changes

Consensus is not a failure. Unsupported, non-independent, shallow review is a
failure.

## Non-Goals

- Deep review is not a code-runner and is not `/code-runner`.
- Deep review does not patch source files.
- JSON is not proof of reasoning depth.
- Memory recall is not evidence by itself.
- Local Codex/scillm execution does not guarantee exact ChatGPT Web Pro parity.
