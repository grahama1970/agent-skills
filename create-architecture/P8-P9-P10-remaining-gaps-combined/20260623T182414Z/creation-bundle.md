# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create one combined solution zip for the remaining PersonaPlex gaps after P6-P7-P8:

1. **P8: Live Deepgram WebSocket validation** — wire the existing `deepgram_websocket_probe` with a real speech audio WAV fixture. The probe already exists; it needs a working end-to-end test that sources `DEEPGRAM_API_KEY` from env, connects to Deepgram, sends real audio, and captures at least one `speech_final=true` event. Provide a deterministic fallback when the key is absent.

2. **P9: Conversation compaction** — implement the missing persistence layer: rolling summaries with immutable source keys, CAS (compare-and-swap) session-head updates for `personaplex_sessions`, graph/vector lifecycle metadata, audio artifact registration. These are defined in the GOAL.md persistence ownership model but not yet wired into the live path.

3. **P10: GPU PersonaPlex inference proof** — create a probe that runs the actual PersonaPlex `LMGen.step(...)` path on available GPU hardware. The golden-state server exists at `personaplex_golden_state_server.py` and can run PersonaPlex inference when the A5000/GPU is available. Create a focused probe that runs a bounded inference step and records `real_gpu_personaplex=true|false` honestly.

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return one downloadable solution zip:

```
personaplex-p8-p9-p10-remaining-gaps-combined-solution.zip
```

`MANIFEST.json.bundle_filename` must match.

## Required Output

- `MANIFEST.json` with `bundle_filename`
- `ARCHITECTURE.md` for P8+P9+P10
- `prompt_improvements.md`
- Finished repo-relative files under `skills/personaplex/...`
- Tests and sanity scripts per target
- Deterministic fallback fixtures
- Exact commands

## Key Context

### P8: Deepgram WebSocket
- Probe exists: `personaplex_deepgram_live.py` → `deepgram_websocket_probe()`
- Default URL: `wss://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate=16000&channels=1&interim_results=false&smart_format=false&endpointing=1000`
- Audio fixture: the upstream PersonaPlex project has `assets/test/input_assistant.wav` (16kHz mono linear16). This can be used as the speech audio source.
- API key: `DEEPGRAM_API_KEY` in env or `~/.zshrc`

### P9: Conversation Compaction
- Flow defined in GOAL.md persistence model:
  - `conversation_history` is canonical immutable turn ledger
  - `conversation_history_summaries` are immutable rolling summaries with source keys
  - `personaplex_sessions` is a mutable session head with CAS/generation semantics
  - `conversation_audio_artifacts` stores audio metadata by hash/path
  - `personaplex_turns` is an optional derived projection (never canonical)
- Memory daemon at `http://127.0.0.1:8601` supports upsert with `skip_embedding` flag
- Current live path writes per-turn documents but does NOT update summaries, session head, or audio artifact records

### P10: GPU PersonaPlex Inference
- Server at `personaplex_golden_state_server.py` with PersonaPlex integration
- GPU inference requires actual `LMGen.step(...)` calls on available hardware
- The golden-state server uses `PERSONAPLEX_ROOT` env var to find the PersonaPlex checkout
- Probe should attempt inference and record `real_gpu_personaplex=true|false`

## Constraints

- Keep existing P0-P8 architecture; extend from current adapter seam.
- Do not claim real service proof from deterministic fixture receipts.
- Receipts must honestly record real_* flags.
- P9 persistence changes must preserve backward compatibility with existing receipt schemas.
- Only the GPU inference probe needs PersonaPlex runtime; compaction and Deepgram are HTTP/stdlib.

## Non-Goals

- Do not rewrite P0-P8 architecture.
- Do not add browser microphone capture.
- Do not replace deterministic fallback paths.
- GPU inference may be deferred to a later round if hardware is unavailable.

## Current Local Evidence

All 34 PersonaPlex tests pass:
```bash
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 -m unittest discover -s skills/personaplex/tests -v
# Ran 34 tests, OK
```

P6 memory upsert: LIVE (`http://127.0.0.1:8601/upsert` returns 2xx)
P7 evidence case: LIVE (`http://127.0.0.1:8601/create-evidence-case` returns 2xx)
P8 Deepgram: PARTIAL (probe stub with `real_deepgram=false` fallback)
P9 compaction: MISSING
P10 GPU inference: MISSING

Existing probe integration point — `run_combined_probe()` in `personaplex_p3_p5_combined_probe.py` accepts `deepgram_audio_path`, `memory_url`, `evidence_case_url`, `deepgram_url`, and `skip_deepgram` parameters. Extend this function to accept compaction parameters.

## Files Likely In Scope

- `skills/personaplex/scripts/personaplex_deepgram_live.py` — P8: valid WebSocket test with real audio
- `skills/personaplex/scripts/personaplex_p3_p5_live_services.py` — P9: add compaction functions
- `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py` — P9: wire compaction into probe
- `skills/personaplex/scripts/personaplex_golden_state_server.py` — P10: GPU inference probe path
- `skills/personaplex/scripts/` — new P9/P10 probe modules
- `skills/personaplex/tests/` — new test files
- `skills/personaplex/sanity_*.sh` — new sanity scripts
- `skills/personaplex/fixtures/` — new fixtures
