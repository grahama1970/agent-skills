# PersonaPlex P6-P7-P8 Real Services Combined Slice

## Purpose

This bundle extends the existing P0/P1/P2/P3-P5 PersonaPlex architecture by wiring the P3-P5 deterministic adapter seam to discovered live services:

- P6 memory upsert: `POST http://127.0.0.1:8601/upsert`
- P7 evidence case: `POST http://127.0.0.1:8601/create-evidence-case`
- P8 Deepgram WebSocket: `wss://api.deepgram.com/v1/listen` with `DEEPGRAM_API_KEY`

The adapters are fail-closed and receipt-first. A deterministic fallback receipt is useful for local sanity, but it is never real service proof. Only the relevant `real_*` boolean in the receipt is authoritative.

## Architecture Boundary Kept From P3-P5

The combined probe keeps the P3-P5 execution story:

1. A stale turn is fenced before mutation.
2. The active turn closes the release gate.
3. Evidence routing is attempted.
4. Conversation history is prepared for memory.
5. Receipts record real/fallback status for every service attempt.

The bundle does not add P9 compaction, browser microphone capture, or GPU PersonaPlex owner-loop proof. `real_gpu_personaplex` remains `false`.

## Adapter Modules

### `skills/personaplex/scripts/personaplex_p3_p5_live_services.py`

Provides P6 and P7 service adapters:

- `memory_upsert(...)`
- `create_evidence_case(...)`
- `build_conversation_document(...)`

Defaults are wired to the discovered daemon base URL `http://127.0.0.1:8601`. Environment overrides are supported:

- `PERSONAPLEX_MEMORY_URL` or `MEMORY_URL`
- `PERSONAPLEX_EVIDENCE_CASE_URL` or `EVIDENCE_CASE_URL`

Both adapters reject explicit inline vector fields before any network attempt. Conversation documents include `retrieval_text`. Audio is represented only as path/hash metadata.

### `skills/personaplex/scripts/personaplex_deepgram_live.py`

Provides P8 Deepgram probing:

- `deepgram_websocket_probe(...)`

The probe reads `DEEPGRAM_API_KEY`, optionally accepts `PERSONAPLEX_P8_AUDIO_PATH`, and attempts a live WebSocket using the optional Python `websockets` package. `real_deepgram=true` requires a live connection and at least one `speech_final=true` event. If the key, dependency, endpoint, or audio path is missing, it writes a deterministic transcript fixture with `real_deepgram=false`.

### `skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py`

Runs the combined P6-P7-P8 receipt and writes:

```text
/tmp/personaplex-p6-p7-p8-sanity/p6-p7-p8-final-receipt.json
```

The receipt preserves P3-P5 fields such as `active_turn_id`, `sealed_turn_keys`, `stale_rejection_count`, `queue_depth_at_release`, and per-target attempt receipts.

## Receipt Semantics

The following fields are authoritative:

- `real_memory_upsert=true`: memory daemon returned 2xx from `/upsert`.
- `real_create_evidence_case=true`: memory daemon returned 2xx from `/create-evidence-case`.
- `real_deepgram=true`: Deepgram WebSocket returned at least one `speech_final=true` event.
- `fallback_used=true`: deterministic fallback was used; do not claim live-service proof from this receipt.
- `no_inline_vectors=true`: payload inspection found no explicit inline vector/embedding fields.

`ok=true` means the probe completed and wrote a receipt; it does not mean the real service gate passed. The `real_*` flags decide that.

## Deterministic Fallbacks

Fallback fixtures live under:

```text
skills/personaplex/fixtures/p6_p7_p8/
```

They support deterministic offline sanity and local development:

- `deterministic_transcript_fixture.json`
- `evidence_case_clarify_fallback.json`
- `memory_upsert_document_fixture.json`

Fallbacks intentionally produce real flags set to `false`.

## Commands And Expected Exit Codes

Run from repo root after overlaying this bundle.

### Unit tests

```bash
python3 -m unittest discover -s skills/personaplex/tests -p 'test_p6_p7_p8_real_services.py'
```

Expected exit code: `0`.

### P6 memory upsert sanity

```bash
bash skills/personaplex/sanity_p6_real_memory_upsert.sh
```

Expected exit code: `0`. If the daemon is unavailable, receipt still exits `0` with `real_memory_upsert=false` and `fallback_used=true`.

Strict real gate:

```bash
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p6_real_memory_upsert.sh
```

Expected exit code: `0` only when the daemon returns 2xx from `/upsert`; otherwise `2`.

### P7 evidence-case sanity

```bash
bash skills/personaplex/sanity_p7_real_evidence_case.sh
```

Expected exit code: `0`. If the daemon is unavailable, receipt still exits `0` with `real_create_evidence_case=false` and `selected_route=/memory /clarify`.

Strict real gate:

```bash
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p7_real_evidence_case.sh
```

Expected exit code: `0` only when the daemon returns 2xx from `/create-evidence-case`; otherwise `2`.

### P8 Deepgram sanity

Offline/fallback mode:

```bash
bash skills/personaplex/sanity_p8_live_deepgram.sh
```

Expected exit code: `0`. If the API key, `websockets` dependency, or speech audio path is unavailable, receipt records `real_deepgram=false` and `deepgram_mode=deterministic_transcript_fixture`.

Strict real gate with a speech WAV/PCM path:

```bash
export PERSONAPLEX_P8_AUDIO_PATH=/path/to/16khz-mono-linear16-speech.wav
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p8_live_deepgram.sh
```

Expected exit code: `0` only when Deepgram returns a `speech_final=true` event; otherwise `2`.

### Combined P6-P7-P8 sanity

```bash
bash skills/personaplex/sanity_p6_p7_p8_combined.sh
```

Expected exit code: `0`. Receipts are written under `/tmp/personaplex-p6-p7-p8-sanity/`.

Strict combined real gate:

```bash
export PERSONAPLEX_P8_AUDIO_PATH=/path/to/16khz-mono-linear16-speech.wav
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p6_p7_p8_combined.sh
```

Expected exit code: `0` only when P6, P7, and P8 real flags are all `true`; otherwise `2`.

## Known Limitations

- Real P8 proof requires a valid Deepgram key, the optional `websockets` Python package, network access, and a speech audio file path. Without speech audio, the probe intentionally falls back.
- This bundle does not prove GPU PersonaPlex inference.
- This bundle does not implement P9 conversation compaction.
- The live memory daemon schema may reject documents for project-specific reasons; the receipt records status/body excerpts and falls back honestly.
