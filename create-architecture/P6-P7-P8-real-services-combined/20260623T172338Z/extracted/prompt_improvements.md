# Prompt Improvements For The Next PersonaPlex Service-Wiring Round

## Recommended WebGPT / Project-Agent Prompt Additions

1. Require every service probe to distinguish `ok` from `real_*` proof.
   - `ok=true` may mean the probe completed with fallback.
   - `real_memory_upsert`, `real_create_evidence_case`, and `real_deepgram` must be the only proof flags.

2. Provide a speech audio fixture path when asking for live Deepgram proof.
   - Without an actual speech WAV/PCM file, a WebSocket can be opened but may not produce `speech_final=true`.
   - Add: `PERSONAPLEX_P8_AUDIO_PATH=/absolute/path/to/16khz-mono-linear16-speech.wav`.

3. Keep the memory payload contract explicit.
   - Include `retrieval_text`.
   - Do not include inline `vector`, `embedding`, `dense_vector`, or `sparse_vector` fields.
   - Represent audio only as `{path, sha256, size_bytes}` metadata.

4. Ask for strict and non-strict gates separately.
   - Non-strict sanity should exit `0` with honest fallback receipts.
   - Strict real proof should use `PERSONAPLEX_REQUIRE_REAL=1` and exit non-zero if live services do not respond.

5. Keep deferred rows out of the proof claim.
   - GPU PersonaPlex owner-loop proof and P9 compaction should remain separate acceptance rows.
   - Do not imply those are complete because P6-P8 adapter wiring works.

## Better Completion Contract

Use language like:

```text
Create an overlay zip. Include runnable tests that pass offline, sanity scripts that attempt live services, and strict real gates that exit 2 unless the corresponding real_* receipt flag is true. Do not describe fallback receipts as live proof.
```
