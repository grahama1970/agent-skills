# Speaker Attribution Algorithm Inspection

## Results

```bash
PYTHONPATH=. pytest -q skills/watch/tests/test_speaker_attribution.py skills/watch/tests/test_watch_diarization_contracts.py
```

Result: `12 passed in 0.16s`.

```bash
find skills/watch/docs/architecture/schemas skills/watch/tests/fixtures/diarization skills/watch/docs/architecture/diarization_contract -name '*.json' -print0 | xargs -0 -n1 jq empty
```

Result: exit `0`.

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: unavailable; `scripts/check_mock_evidence_claims.py` is missing on this
branch.

## Inspection Result

The algorithm slice is accepted as model-free attribution logic only. It does
not prove pyannote service availability, live diarization quality, report
rendering, memory persistence, or UI behavior.
