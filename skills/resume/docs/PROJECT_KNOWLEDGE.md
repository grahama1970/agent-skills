# Resume Skill Project Knowledge

## Current State

The skill provides deterministic Markdown validation and claim-bound Markdown variant
compilation. It emits a `resume.variant.v1` manifest with source and variant SHA-256
digests, selected claim evidence references, and a producer-side seam receipt.

## Boundaries

- `RESUME.md` remains the repository-level canonical resume source.
- PDF generation remains owned by the repository workflow and converter.
- `/monitor-opportunities` owns opportunity discovery, ranking, report presentation,
  human outreach, and application authorization.
- This skill does not call an LLM, send messages, submit applications, or access
  ArangoDB directly.

## Composition

- `/monitor-opportunities` composes this skill (commit `5fec30084`, 2026-08-07):
  `resume_artifact.tailor_artifact` builds a tailoring request from its approved-claim
  snapshot, invokes `run.sh tailor`, verifies the seam receipt and claim ordering, and
  binds the `resume.variant.v1` manifest into its `tailored_resume_artifact` receipt.
  Covered by `skills/monitor-opportunities/tests/test_resume_artifact.py`.

## Evidence State

- Local deterministic smoke controls are defined in `sanity.sh`.
- The `/monitor-opportunities` composition seam is exercised by that skill's test
  gates (live subprocess, no network). PDF visual quality and a full live
  opportunity-to-artifact run remain unestablished.
