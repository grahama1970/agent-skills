# P6-P7-P8 Gap Report

**Engagement type:** WebGPT solution zip (single combined round)
**Slice ID:** p6-p7-p8-real-services-combined
**Solution zip:** `personaplex-p6-p7-p8-real-services-combined-solution.zip`
**SHA-256:** `28005 bytes` (from controlled tab `837355270` download)

## Implemented In This Slice

1. WebGPT solution zip downloaded from controlled tab `837355270` via file attachment button.
2. `MANIFEST.json.bundle_filename` matched `personaplex-p6-p7-p8-real-services-combined-solution.zip`.
3. 17 source/doc/fixture files ported; 3 adapter modules updated with real URL wiring.
4. New probe scripts: `p6_real_memory_upsert_probe.py`, `p7_real_evidence_case_probe.py`, `p8_live_deepgram_probe.py`.
5. New test file: `test_p6_p7_p8_real_services.py` — 8 tests, all pass.
6. New sanity scripts per target plus combined.
7. Backward-compat aliases added to fix P3-P5 test regressions (WebGPT renamed `P3P5CombinedProbe` class to `run_combined_probe` function).
8. Combined PersonaPlex tests: **Ran 34 tests, OK** (5 P0 + 5 P1 + 7 P2 + 6 P3-P5 + 8 P6-P7-P8 + 3 P1 wrapper control-plane).

## Port Delta vs Zip

1. WebGPT's adapter rewrite broke the old `P3P5CombinedProbe` class API and renamed all utility functions in `personaplex_p3_p5_live_services.py`. Added backward-compat aliases to preserve old test behavior. (Committed separately.)
2. The old `attempt_evidence_case` backward-compat needed a `fail_closed` field injected when returning the new `create_evidence_case` response — the new API doesn't include it. (Fixed inline.)
3. Backup files (`*.p6p7p8bak`) removed after port verification.

## Remaining Gaps

### P6: Real Memory Upsert

**Status: PARTIAL → LIVE (when daemon is running)**

The adapter now defaults to `http://127.0.0.1:8601` and successfully POSTs. Receipt records `real_memory_upsert=true` when the daemon responds. Still requires explicit `DEEPGRAM_API_KEY` and `MEMORY_URL` env for non-local deployment.

### P7: Real Evidence Case

**Status: PARTIAL → LIVE (when daemon is running)**

The adapter defaults to `http://127.0.0.1:8601` and successfully POSTs. Receipt records `real_create_evidence_case=true` when the daemon responds.

### P8: Live Deepgram WebSocket

**Status: PARTIAL**

Probe stub exists (`personaplex_p8_live_deepgram_probe.py`) and `deepgram_websocket_probe` is wired. Default path is `skipped_by_cli` or uses `DEEPGRAM_API_KEY`. The test `test_deepgram_missing_key_uses_deterministic_fixture_not_real` passes. Live proof requires an actual speech audio path + valid Deepgram API key.

### P9: Conversation Compaction

**Status: MISSING** (not in scope for this slice)

### GPU PersonaPlex Inference

**Status: MISSING** (not in scope; `real_gpu_personaplex` remains `false`)

## Next Slice

Recommended: **P9-conversation-compaction** (rolling summaries, immutable source turn retention, graph/vector lifecycle, CAS session-head updates). Or **P8-live-deepgram-validation** with a real speech WAV fixture and valid `DEEPGRAM_API_KEY`.

## Proof

```bash
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 -m unittest discover -s skills/personaplex/tests -v
# Ran 34 tests, OK
```
