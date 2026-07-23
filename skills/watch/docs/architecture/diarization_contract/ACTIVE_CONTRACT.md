# Diarization Contract Slice

MODE: EXECUTE_ARTIFACT

## Artifact

Define Watch diarization and speaker-attribution contracts.

## Input

- Human-provided pyannote implementation plan.
- Current `skills/watch/SKILL.md`.
- Current `skills/watch/README.md`.
- Current `skills/watch/docs/PROJECT_KNOWLEDGE.md`.
- Current Watch schema/test layout.
- Verified external facts: pyannote.audio `4.0.7` and Community-1 exclusive
  speaker diarization support.

## Output Shape

- JSON schemas.
- JSON fixtures.
- Contract constants.
- Schema validation tests.
- Documentation boundary.

## Must Include

- Anonymous speaker labels.
- Regular and exclusive diarization tracks.
- Failure receipts and stable error codes.
- Focused-range source-timeline rule.
- Identity boundary: no speaker cluster promotion to character or person.

## Must Not Include

- Pyannote service implementation.
- CLI behavior changes.
- Report/memory/UI behavior changes.
- Live model claims.
- Hugging Face token handling.

## Runtime/Tooling

- `jq` JSON parse checks.
- `pytest` schema/contract tests.

## Inspection Method

- Validate JSON schema syntax.
- Validate all fixtures against schemas.
- Assert constants match schema vocabulary.
- Inspect changed paths.

## Failure Conditions

- Malformed JSON.
- Fixture schema validation failure.
- Missing identity boundary.
- Any claim that diarization is implemented in Watch.

## Allowed Writes

- `skills/watch/docs/architecture/**`
- `skills/watch/tests/fixtures/diarization/**`
- `skills/watch/tests/test_watch_diarization_contracts.py`
- `skills/watch/scripts/diarization_contract.py`
- `skills/watch/SKILL.md`
- `skills/watch/README.md`
- `skills/watch/docs/PROJECT_KNOWLEDGE.md`

## Forbidden Writes

- Service, Docker, CLI, pipeline, report, storage, and UI implementation files.

## Report Format

Report changed files, validation commands, commit SHA, push target, and next
legal artifact.
