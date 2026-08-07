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

## Evidence State

- Local deterministic smoke controls are defined in `sanity.sh`.
- PDF visual quality and live `/monitor-opportunities` integration are not established
  by this skill's smoke profile.
