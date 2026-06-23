# P6-P7-P8 Sanity Report

## Bundle Verification

| Check | Status | Detail |
|-------|--------|--------|
| Zip download | PASS | Downloaded from controlled tab 837355270 |
| Zip SHA-256 | RECORDED | See `solution.sha256` |
| Manifest `bundle_filename` | PASS | Matches `personaplex-p6-p7-p8-real-services-combined-solution.zip` |
| File count | 17 | Listed in manifest |
| Extract | PASS | 24 entries extracted (including empty dirs) |
| py_compile (3 probe scripts) | PASS | exit 0 |
| Focused tests (isolated) | PASS | Ran 8 tests, OK |

## Files in Bundle

- `ARCHITECTURE.md` — P6-P7-P8 wiring contract
- `prompt_improvements.md` — next-round improvements
- `MANIFEST.json` — file manifest with checksums
- `skills/personaplex/scripts/personaplex_p3_p5_live_services.py` — updated adapter with real URL wiring
- `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py` — updated combined probe
- `skills/personaplex/scripts/personaplex_deepgram_live.py` — updated for env-var wiring
- `skills/personaplex/scripts/personaplex_p6_real_memory_upsert_probe.py` — new P6 probe
- `skills/personaplex/scripts/personaplex_p7_real_evidence_case_probe.py` — new P7 probe
- `skills/personaplex/scripts/personaplex_p8_live_deepgram_probe.py` — new P8 probe stub
- `skills/personaplex/tests/test_p6_p7_p8_real_services.py` — new focused test (8 tests)
- `skills/personaplex/fixtures/p6_p7_p8/*` — deterministic fallback fixtures
- `skills/personaplex/sanity_p6_real_memory_upsert.sh` — new sanity
- `skills/personaplex/sanity_p7_real_evidence_case.sh` — new sanity
- `skills/personaplex/sanity_p8_live_deepgram.sh` — new sanity
- `skills/personaplex/sanity_p6_p7_p8_combined.sh` — new combined sanity
