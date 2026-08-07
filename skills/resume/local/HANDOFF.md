# Handoff Report: Resume Skill

**Timestamp**: 2026-08-07T14:19:12Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python
- **Core Purpose**: Validate the canonical Markdown resume and compile claim-bound,
  evidence-referenced Markdown variants for `/monitor-opportunities`.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**: `validate` checks canonical Markdown; `tailor` emits a
  variant and `resume-variant.json` seam manifest.
- **Implemented Reality**: Both commands are implemented in `scripts/resume.py` and
  exercised by `sanity.sh`.
- **Drift/Misalignments**: PDF visual quality and live `/monitor-opportunities`
  integration are not established by the local smoke profile.

## 3. What is Working Well

- Positive validation accepts the canonical fixture.
- Positive tailoring emits a variant and `seam_validation.status=PASS`.
- Negative tailoring rejects an unapproved claim and emits no variant.
- `uv` isolation is used for the skill CLI and sanity gate.

## 4. What is Currently Broken

- **Failed Tests**: None in the focused resume smoke gate.
- **Known Issues**: The repository's `best-practices-skills` package cannot be built
  by `uv run --project` because its existing project metadata has no package target;
  its validator was instead run in an isolated environment with Loguru, PyYAML, and
  Typer supplied explicitly.
- **Recent Regressions**: None observed for this new skill.

## 5. Next Steps

1. Integrate the task-only files into `agent-skills@main`.
2. Have `/monitor-opportunities` consume `resume-variant.json` as its authoritative
   per-opportunity resume artifact.
3. Add a live integration case only when the opportunity-monitoring contract is ready.

## 6. Project Context for Success

- **Key Files**: `SKILL.md`, `run.sh`, `sanity.sh`, `scripts/resume.py`, and
  `docs/PROJECT_KNOWLEDGE.md`.
- **Recent Changes**: New deterministic resume skill scaffold, registered resume
  capabilities, and generated this handoff report.

## Evidence State

- `mocked: no`
- `live: no`
- Exercised: local file validation, claim-bound variant compilation, JSON manifest
  seam receipt, and negative-control rejection.
- Unverified: PDF rendering quality, ATS behavior, remote services, and live
  `/monitor-opportunities` composition.
