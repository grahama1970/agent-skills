# Plan to Code-Runner Pipeline Infographic Design Brief

## Purpose

Update the project-agent visual contract for the `/plan -> /review-plan -> /orchestrate -> /code-runner` pipeline after the reliability adoption tranche.

## Target Reader

Future project agents adopting the pipeline in another repository.

## Core Message

The pipeline is usable only when front gates, bounded code-runner execution, complete-task commit/revert semantics, readiness gates, and artifact-first escalation all remain in place.

## Source Map

| Source | Visual Claim |
|---|---|
| `skills/orchestrate/docs/PLAN_TO_CODE_RUNNER_READINESS.md` | supported task shape, readiness commands, complete-task rules |
| `skills/orchestrate/docs/OTHER_PROJECT_ADOPTION.md` | adoption gate, external smoke proof, AGENTS snippet |
| `skills/orchestrate/pipeline_readiness.py` | quick/gates profiles, adoption smoke, code-runner non-soak gate |
| `skills/orchestrate/tests/run_external_project_adoption_smoke.sh` | external temporary repo smoke reuses full composed E2E |
| `.github/workflows/skills-ci.yml` | scheduled/manual adoption smoke and soak jobs |
| `skills/plan/plan.py` and `skills/review-plan/review_plan.py` | opaque DoD metadata and live/browser fail-closed validation |

## Truth Labels

Implemented:
- `/plan` validates structured task shape.
- `/review-plan` preserves raw fields and blocks contract violations.
- `/orchestrate` owns retrieval, retry, blind/review gates, source commit revert, and artifact-first escalation.
- `/code-runner` owns bounded worktree execution, allowlist patching, source apply, source DoD, source commit, artifacts, and cleanup.
- `pipeline_readiness.py` exposes quick/gates/adoption/code-runner checks.
- External adoption smoke runs against a temporary external git repo.

Intended:
- Other projects copy the AGENTS snippet and run readiness before use.
- Nightly/manual jobs accumulate soak evidence.

Remaining risk:
- Opaque DoD commands can still be misleading unless the local-only metadata is truthful and reviewed.
- Live browser/server workflows must remain outside `code-runner`.

## Required Panels

1. Adoption entry gate.
2. Front-door plan/review validation.
3. Orchestrate policy and generated spec.
4. Code-runner bounded worker.
5. Complete-task commit/revert path.
6. Readiness/CI evidence.
7. Failure escalation and human decision path.

## Readability Constraints

- Use color bands matching the accepted project diagram: blue validation, orange policy, purple code-runner, green success, red failure.
- Show exact command/file names where possible.
- Keep arrows mostly left-to-right with a clear failure lane.
- Do not imply live browser/server checks are allowed in code-runner.

## Render Plan

Editable source:

`skills/orchestrate/docs/PLAN_CODE_RUNNER_PIPELINE_INFOGRAPHIC.html`

Browser-rendered PNG:

`skills/orchestrate/docs/PLAN_CODE_RUNNER_PIPELINE_INFOGRAPHIC.png`

Target screenshot size: `1800x3000`.

## Rejection Criteria

Reject the visual if it:
- omits the adoption readiness gate
- shows browser/live checks inside code-runner
- fails to show commit/revert behavior
- omits failure bundle/interview request artifacts
- omits the remaining opaque DoD risk
- cannot be rendered locally in a browser

