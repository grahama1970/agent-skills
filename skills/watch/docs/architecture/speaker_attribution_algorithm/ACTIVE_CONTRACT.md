# Speaker Attribution Algorithm Slice

MODE: EXECUTE_ARTIFACT

## Artifact

Implement model-free transcript-to-speaker attribution over normalized Watch
diarization dictionaries.

## Input

- `skills/watch/docs/architecture/watch_diarization_contract.md`
- `skills/watch/docs/architecture/schemas/watch_speaker_attribution.schema.json`
- `skills/watch/scripts/diarization_contract.py`
- Human-provided speaker attribution algorithm requirements.

## Output Shape

- Pure Python module with no pyannote imports.
- Unit tests for dominant, mixed, unassigned, overlap, zero-duration, and
  unavailable cases.
- Inspection/status record.

## Must Include

- Exclusive-turn reconciliation.
- Regular-turn overlapping-speech flag.
- Text immutability.
- Anonymous speaker identity boundary.

## Must Not Include

- Pyannote service calls.
- HTTP client behavior.
- CLI flags.
- Report, storage, memory, or UI integration.

## Runtime/Tooling

- `pytest`
- `jq`

## Inspection Method

- Run `PYTHONPATH=. pytest -q skills/watch/tests/test_speaker_attribution.py skills/watch/tests/test_watch_diarization_contracts.py`.
- Parse existing diarization contract JSON files with `jq`.
- Inspect changed paths.

## Failure Conditions

- Any pyannote import.
- Transcript text mutation.
- Auto-promotion from speaker cluster to character or identity.
- Missing tests for mixed and zero-duration cases.
