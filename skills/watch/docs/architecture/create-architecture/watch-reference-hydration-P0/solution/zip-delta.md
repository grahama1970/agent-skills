# Zip Delta: Watch Reference Hydration P0

**Timestamp:** 2026-06-27T23:01:22Z
**Solution zip:** `skills/watch/docs/architecture/create-architecture/watch-reference-hydration-P0/solution/watch-reference-hydration-P0-solution.zip`
**Checksum:** `fd25377aeebd40eca7e8af7119348669e3fcb348496c73cae822bce1b7115c7d`
**Manifest entries:** 26

## Port Classification

| Path | Status | Role |
| --- | --- | --- |
| `ARCHITECTURE.md` | `bundle_only` | `` |
| `COMMANDS.md` | `bundle_only` | `` |
| `KNOWN_GAPS.md` | `bundle_only` | `` |
| `README.md` | `bundle_only` | `` |
| `ROLLBACK_REBUILD.md` | `bundle_only` | `` |
| `prompt_improvements.md` | `bundle_only` | `` |
| `skills/watch/docs/architecture/patches/watch_reference_hydration_P0_docs.patch` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_identity_evidence.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_memory_trace_write.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_reference_hydration_plan.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_reference_package.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_source_reference_manifest.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/schemas/watch_track_observation.schema.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/state_machines/watch_reference_hydration_P0.state_machine.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/docs/architecture/watch_reference_hydration_P0.md` | `mechanically_ported_unchanged` | `` |
| `skills/watch/scripts/build_watch_memory_trace_plan.py` | `mechanically_ported_unchanged` | `` |
| `skills/watch/scripts/build_watch_reference_hydration_plan.py` | `mechanically_ported_unchanged` | `` |
| `skills/watch/scripts/validate_watch_reference_hydration_contract.py` | `mechanically_ported_unchanged` | `` |
| `skills/watch/scripts/watch_reference_hydration.py` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/asset_drone_stream.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/asset_movie_bad_santa.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/identity_evidence_inconclusive_domain_only.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/movie_reference_candidates_bad_santa.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/source_reference_manifest_drone_valid.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/fixtures/reference_hydration_P0/track_observations_bad_santa_0248.json` | `mechanically_ported_unchanged` | `` |
| `skills/watch/tests/test_watch_reference_hydration_P0.py` | `mechanically_ported_unchanged` | `` |

## Delta Summary

- `bundle_only`: 6
- `mechanically_ported_unchanged`: 20

## Unauthorized Semantic Delta

None detected in the WebGPT manifest paths. Repo-scoped files were copied mechanically from `solution/extracted/repo/` into the repo root, excluding `__pycache__` directories.

## Remaining Gaps

- Live Qdrant/Jina embedding writes are not implemented/proven.
- Arango metadata/Qdrant pointer writes are not implemented/proven.
- `$memory recall` of Watch traces is not implemented/proven.
- Automatic download/approval of actor reference images is not implemented/proven.
- Real-time UI overlay tracking is not proven by this slice.
