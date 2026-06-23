# PersonaPlex E2E Live Voice UI Combined Solution

Bundle: `personaplex-e2e-live-voice-ui-combined-solution.zip`

This overlay preserves the P0-P10 adapter architecture and adds the final live-demo seam: one probe that executes the full turn path and writes a visual SPARTA Chat-style verification UI from the resulting receipt.

## Scope

Repo-relative files are under:

- `skills/personaplex/scripts/`
- `skills/personaplex/tests/`
- `skills/personaplex/fixtures/e2e_live_voice_ui/`
- `reviews/personaplex-deepgram/`

No production deployment, browser microphone capture, Orpheus TTS training, or persona authoring is included.

## Execution path

`personaplex_e2e_live_voice_session.py` runs the final turn in sequence:

1. **Deepgram ASR**
   - Uses `deepgram_websocket_probe(...)`.
   - Default audio path discovery includes `assets/test/input_assistant.wav` from the PersonaPlex checkout.
   - Reads `DEEPGRAM_API_KEY` from the environment.
   - Requires `speech_final=true` for `real_deepgram=true`.
   - Missing key/package/audio or missing `speech_final` produces a deterministic fallback receipt with `real_deepgram=false`.

2. **Turn gate**
   - Opens the next turn, increments `turn_id`/generation, records `queue_depth=0`, closes output before mutation, and records a stale-callback fence proof.
   - This is a deterministic adapter execution, not an external service. It sets `real_turn_gate=true` only because the real gate code ran, not because a fixture was used.

3. **Memory intent**
   - Classifies the active transcript into an intent route (`COMPLIANCE`, `PERSONA_MEMORY`, or `CLARIFY`) and returns tools + recall profile.
   - The default west-gateway audio/transcript routes to `COMPLIANCE (0.94)`.

4. **Recall / evidence**
   - Calls the memory daemon `POST /create-evidence-case` through the existing adapter.
   - Default daemon URL is `http://127.0.0.1:8601`.
   - `real_recall_evidence=true` only when the daemon returns 2xx.
   - Recall rows are extracted from common evidence-case response shapes (`items`, `matches`, `documents`, `evidence`, `citations`, etc.). If the daemon returns 2xx without explicit items, the UI shows a derived live evidence-case response row rather than inventing citations.

5. **PersonaPlex GPU inference**
   - Uses `run_gpu_personaplex_probe(...)` around `personaplex_golden_state_server.py` / `LMGen.step(...)`.
   - `real_gpu_personaplex=true` requires a validated payload proving GPU availability, `LMGen.step` execution, and bounded step output.
   - If the GPU proof payload includes text fields such as `embry_response`, `response_text`, or `generated_text`, the E2E receipt uses that as Embry's response. Otherwise, if GPU proof is real but no text field is exposed, the receipt records a bounded response tied to the validated LMGen step proof.

6. **Persistence upsert**
   - Writes the canonical turn record to `conversation_history` via memory daemon `POST /upsert`.
   - `real_persistence_upsert=true` only after a 2xx daemon response.
   - The payload includes no inline vectors. Audio is represented only as path/hash metadata.

7. **Session compaction**
   - Runs `run_conversation_compaction(...)` for rolling summary, projection, audio artifact metadata, and CAS session head lifecycle.
   - `real_session_compaction=true` only when the memory-daemon upsert path for compaction succeeds and the CAS/session-head conditions are satisfied.

8. **Verification UI**
   - Writes `/tmp/personaplex-e2e-live-voice-ui/personaplex-e2e-live-voice-ui.html` by default.
   - The UI renders chat messages, tool trace rows, intent/evidence summaries, recall cards, upsert status, and gate state.
   - Every tool row carries `data-real-flag-name` and `data-real-flag-value` attributes for deterministic tests.
   - The banner shows `ALL LIVE TOOL ROWS REAL=TRUE` only when every row has `real_flag_value=true` and the receipt is not a fixture.

## Files added

### Probe and UI renderer

- `skills/personaplex/scripts/personaplex_e2e_live_voice_session.py`
  - Final E2E orchestration script.
  - Writes `e2e-live-voice-receipt.json`, component receipts, events JSONL, and static UI HTML.
  - Supports `--require-real` to fail closed with exit code `2` unless every final `real_*` flag is true.

- `skills/personaplex/scripts/personaplex_e2e_ui_render.py`
  - Static HTML renderer for E2E receipts.
  - Can be used by the E2E probe, tests, or directly from CLI.

### UI surface

- `reviews/personaplex-deepgram/personaplex-e2e-live-voice-ui.html`
  - Standalone browser UI shell for receipt viewing when served through `python -m http.server`.
  - The E2E probe also writes a fully static rendered UI to its output directory, which can be opened directly from disk.

### Tests and fixtures

- `skills/personaplex/tests/test_e2e_live_voice_ui.py`
  - Proves renderer output includes chat messages, tool rows, real flag attributes, intent/evidence/upsert strings, recall cards, and fallback warnings.
  - Runs the E2E fallback path and checks that unavailable dependencies are not claimed as real.

- `skills/personaplex/fixtures/e2e_live_voice_ui/real_tool_data_render_fixture.json`
  - UI rendering fixture shaped like a successful live receipt.
  - Marked `fixture_only=true`; it is not live proof.

- `skills/personaplex/fixtures/e2e_live_voice_ui/fallback_render_fixture.json`
  - UI fallback rendering fixture.

### Sanity scripts

- `skills/personaplex/sanity_e2e_live_voice_ui.sh`
  - Live final probe. Exits `0` only when all real services prove true because it passes `--require-real`.

- `skills/personaplex/sanity_e2e_live_voice_fallback.sh`
  - Deterministic safety-net probe with Deepgram/GPU skipped and memory URL pointed at an unavailable port. Exits `0` while proving the receipt is honest (`all_real_true=false`).

## Receipt contract

Final receipt schema: `personaplex.e2e_live_voice_ui.final_receipt.v1`.

Important fields:

- `real_flags.real_deepgram`
- `real_flags.real_turn_gate`
- `real_flags.real_memory_intent`
- `real_flags.real_recall_evidence`
- `real_flags.real_gpu_personaplex`
- `real_flags.real_persistence_upsert`
- `real_flags.real_session_compaction`
- `all_real_true`
- `fallback_used`
- `tool_trace[]`
- `conversation[]`
- `recall_items[]`
- `evidence_summary`
- `component_receipts`
- `ui_path`

`all_real_true=true` is the only final live-demo success condition. Fixture receipts and fallback receipts are not acceptable live proof.

## Commands

Run all PersonaPlex tests after applying this overlay:

```bash
cd <repo>
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 -m unittest discover -s skills/personaplex/tests -v
```

Expected exit code: `0`.

Run deterministic fallback sanity:

```bash
cd <repo>
./skills/personaplex/sanity_e2e_live_voice_fallback.sh
```

Expected exit code: `0`. Expected result: receipt exists, UI exists, and `all_real_true=false`.

Run final live E2E proof:

```bash
cd <repo>
export DEEPGRAM_API_KEY='<real key>'
export PERSONAPLEX_ROOT='<path to PersonaPlex checkout>'
export PERSONAPLEX_MEMORY_URL='http://127.0.0.1:8601'
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 skills/personaplex/scripts/personaplex_e2e_live_voice_session.py \
    --out-dir /tmp/personaplex-e2e-live-voice-ui \
    --memory-url http://127.0.0.1:8601 \
    --evidence-case-url http://127.0.0.1:8601 \
    --deepgram-audio-path "$PERSONAPLEX_ROOT/assets/test/input_assistant.wav" \
    --require-real
```

Expected exit code: `0` only when Deepgram, memory daemon, GPU proof, persistence, and compaction all return real proof. Expected exit code: `2` if any final `real_*` flag is false. Other nonzero exit codes indicate coding/runtime errors.

View the generated UI:

```bash
xdg-open /tmp/personaplex-e2e-live-voice-ui/personaplex-e2e-live-voice-ui.html
```

or:

```bash
python3 -m http.server 8765 --directory /tmp/personaplex-e2e-live-voice-ui
# then open http://127.0.0.1:8765/personaplex-e2e-live-voice-ui.html
```

## Rollback

Remove these overlay files:

```bash
rm -f skills/personaplex/scripts/personaplex_e2e_live_voice_session.py
rm -f skills/personaplex/scripts/personaplex_e2e_ui_render.py
rm -f skills/personaplex/tests/test_e2e_live_voice_ui.py
rm -rf skills/personaplex/fixtures/e2e_live_voice_ui
rm -f skills/personaplex/sanity_e2e_live_voice_ui.sh
rm -f skills/personaplex/sanity_e2e_live_voice_fallback.sh
rm -f reviews/personaplex-deepgram/personaplex-e2e-live-voice-ui.html
```

No migration or destructive cleanup is required. The live probe writes generated outputs under `/tmp/personaplex-e2e-live-voice-ui` by default.

## Known limitations

- The bundle cannot prove live Deepgram/GPU/memory service behavior inside this offline creation environment. It provides the code, tests, and commands that prove the path in the target checkout.
- If the GPU proof hook returns only bounded token/hash output and no decoded text, the E2E receipt records a bounded Embry response tied to the validated LMGen step proof rather than inventing a full natural-language completion.
- The standalone review HTML fetches JSON only when served by HTTP. The generated probe UI is fully static and can be opened directly from disk.
