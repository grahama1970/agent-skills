# Diarization Contract Inspection

Status before validation: pending.

Planned checks:

- JSON parse validation for both schemas and all fixtures.
- `pytest skills/watch/tests/test_watch_diarization_contracts.py`.
- Changed-path inspection.
- Documentation scan for `CONTRACT_DEFINED_NOT_IMPLEMENTED`.

## Results

```bash
find skills/watch/docs/architecture/schemas skills/watch/tests/fixtures/diarization skills/watch/docs/architecture/diarization_contract -name '*.json' -print0 | xargs -0 -n1 jq empty
```

Result: exit `0`.

```bash
PYTHONPATH=. pytest -q skills/watch/tests/test_watch_diarization_contracts.py
```

Result: `5 passed in 0.15s`.

```bash
rg -n "CONTRACT_DEFINED_NOT_IMPLEMENTED|not implemented|implemented yet|runtime support is not implemented|Do not claim pyannote support" skills/watch/SKILL.md skills/watch/README.md skills/watch/docs/PROJECT_KNOWLEDGE.md skills/watch/docs/architecture/watch_diarization_contract.md
```

Result: the non-implementation boundary is present in `SKILL.md`, `README.md`,
`PROJECT_KNOWLEDGE.md`, and `watch_diarization_contract.md`.

## Inspection Result

The contract artifact is accepted as a schema/documentation/test slice only. It
does not prove or implement pyannote runtime support.
