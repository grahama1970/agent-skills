# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create one combined solution zip for the remaining PersonaPlex gaps after P6-P7-P8. The creation bundle is attached as a zip. Read all files before creating.

**Required zip name:** `personaplex-p8-p9-p10-remaining-gaps-combined-solution.zip`

Three targets:

1. **P8: Live Deepgram WebSocket validation** — wire existing `deepgram_websocket_probe` with real speech audio (`assets/test/input_assistant.wav` from PersonaPlex checkout). Source `DEEPGRAM_API_KEY` from env. Capture `speech_final=true`. Deterministic fallback when key absent.

2. **P9: Conversation compaction** — rolling summaries, CAS session-head updates, audio artifact metadata, graph/vector lifecycle. Defined in GOAL.md persistence model. Memory daemon at `http://127.0.0.1:8601`.

3. **P10: GPU PersonaPlex inference proof** — probe that runs `LMGen.step(...)` on available GPU via `personaplex_golden_state_server.py`. Records `real_gpu_personaplex=true|false`.

If any material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return the solution zip.

## Key Facts

- Memory daemon: `http://127.0.0.1:8601` (POST /upsert and /create-evidence-case proven live)
- Deepgram default URL: `wss://api.deepgram.com/v1/listen?...`
- Speech audio: PersonaPlex project has `assets/test/input_assistant.wav` at the checkout path
- GPU inference: `personaplex_golden_state_server.py` auto-detects PersonaPlex python
- All 34 PersonaPlex tests pass currently
- Keep existing architecture; extend adapter seam

## Constraints

- Keep existing P0-P8 architecture; extend adapter seam.
- Receipts must honestly record real_* flags.
- No inline vectors in memory payloads.
- Deterministic fallback when live services unavailable.
