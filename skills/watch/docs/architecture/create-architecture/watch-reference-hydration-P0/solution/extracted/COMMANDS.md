# Watch Reference Hydration P0 Commands

Copy the `repo/` directory contents into the repository root, then run:

```bash
python3 -m py_compile \
  skills/watch/scripts/watch_reference_hydration.py \
  skills/watch/scripts/build_watch_reference_hydration_plan.py \
  skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  skills/watch/scripts/build_watch_memory_trace_plan.py
```

Movie reference-candidate plan:

```bash
python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_movie_bad_santa.json \
  --reference-candidates skills/watch/tests/fixtures/reference_hydration_P0/movie_reference_candidates_bad_santa.json \
  --out /tmp/watch_movie_reference_hydration_plan.json

python3 skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  --plan /tmp/watch_movie_reference_hydration_plan.json
```

Expected meaning: movie ingest/tracking may continue with candidate refs, but identity promotion remains disabled.

Non-movie missing-manifest fail-closed proof:

```bash
python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_drone_stream.json \
  --out /tmp/watch_drone_missing_manifest_plan.json

python3 skills/watch/scripts/validate_watch_reference_hydration_contract.py \
  --plan /tmp/watch_drone_missing_manifest_plan.json \
  --expect-fail-closed
```

Source-manifest-backed stream plan:

```bash
python3 skills/watch/scripts/build_watch_reference_hydration_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_drone_stream.json \
  --source-manifest skills/watch/tests/fixtures/reference_hydration_P0/source_reference_manifest_drone_valid.json \
  --out /tmp/watch_drone_reference_hydration_plan.json
```

Planned memory trace payload:

```bash
python3 skills/watch/scripts/build_watch_memory_trace_plan.py \
  --asset skills/watch/tests/fixtures/reference_hydration_P0/asset_movie_bad_santa.json \
  --observations skills/watch/tests/fixtures/reference_hydration_P0/track_observations_bad_santa_0248.json \
  --identity-evidence skills/watch/tests/fixtures/reference_hydration_P0/identity_evidence_inconclusive_domain_only.json \
  --out /tmp/watch_memory_trace_plan.json
```

Tests:

```bash
pytest -q skills/watch/tests/test_watch_reference_hydration_P0.py
```

Do not claim Qdrant, Arango, memory, identity, or recall progress from these commands. They prove only deterministic P0 contracts and fail-closed behavior.
