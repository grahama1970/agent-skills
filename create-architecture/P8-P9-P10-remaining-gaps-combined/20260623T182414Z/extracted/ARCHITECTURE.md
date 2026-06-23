# PersonaPlex P8-P9-P10 Remaining Gaps Combined Solution

## Purpose

This bundle extends the existing PersonaPlex P0-P8 adapter seam without replacing the deterministic architecture. It adds the three remaining live-service proof targets:

1. **P8 live Deepgram validation**: `deepgram_websocket_probe(...)` now auto-discovers the real speech fixture `assets/test/input_assistant.wav`, reads `DEEPGRAM_API_KEY` from the environment, streams raw linear16 PCM from the WAV file to Deepgram, and only sets `real_deepgram=true` after observing a `speech_final=true` event.
2. **P9 conversation compaction**: immutable turn ledger writes, immutable rolling summaries with source keys, CAS-style session-head generation checks, graph/vector lifecycle metadata, audio artifact path/hash registration, and optional derived `personaplex_turns` projection.
3. **P10 GPU PersonaPlex inference proof**: a bounded probe around `personaplex_golden_state_server.py` that accepts real proof only when a payload validates that `LMGen.step(...)` ran on a GPU and emitted bounded step output.

Every target keeps deterministic fallback behavior for offline sanity, but fallback receipts are explicitly not live proof. The authoritative fields are `real_deepgram`, `real_conversation_compaction`, and `real_gpu_personaplex`.

## Files

```text
skills/personaplex/scripts/personaplex_deepgram_live.py
skills/personaplex/scripts/personaplex_conversation_compaction.py
skills/personaplex/scripts/personaplex_gpu_inference_probe.py
skills/personaplex/scripts/personaplex_p3_p5_live_services.py
skills/personaplex/scripts/personaplex_p3_p5_combined_probe.py
skills/personaplex/scripts/personaplex_p8_live_deepgram_probe.py
skills/personaplex/scripts/personaplex_p9_compaction_probe.py
skills/personaplex/scripts/personaplex_p10_gpu_inference_probe.py
skills/personaplex/tests/test_p8_p9_p10_remaining_gaps.py
skills/personaplex/fixtures/p8_p9_p10/*
skills/personaplex/sanity_p8_live_deepgram_real_audio.sh
skills/personaplex/sanity_p9_conversation_compaction.sh
skills/personaplex/sanity_p10_gpu_personaplex_inference.sh
skills/personaplex/sanity_p8_p9_p10_combined.sh
```

## P8 Deepgram WebSocket

The Deepgram probe defaults to:

```text
wss://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate=16000&channels=1&interim_results=false&smart_format=false&endpointing=1000
```

Audio discovery order:

1. explicit `--audio-path`
2. `PERSONAPLEX_P8_AUDIO_PATH`
3. `DEEPGRAM_AUDIO_PATH`
4. `$PERSONAPLEX_ROOT/assets/test/input_assistant.wav`
5. `assets/test/input_assistant.wav` relative to the current checkout

For WAV files, the adapter strips the RIFF header and sends raw PCM frames because the Deepgram URL declares `encoding=linear16`. The receipt includes path/hash/sample-rate metadata only. It never includes raw audio bytes.

`real_deepgram=true` requires a live WebSocket and `speech_final=true`. Missing key, missing `websockets`, missing audio, WebSocket error, or no final speech event all produce deterministic fallback with `real_deepgram=false`.

## P9 Conversation Compaction

The compaction adapter writes the persistence model through the memory daemon `POST /upsert` endpoint:

| Collection | Purpose | Embedding |
|---|---|---|
| `conversation_history` | Canonical immutable per-turn ledger | `skip_embedding=false` |
| `conversation_history_summaries` | Immutable rolling summaries with `source_turn_keys` | `skip_embedding=false` |
| `personaplex_sessions` | Mutable session head with generation/CAS metadata | `skip_embedding=true` |
| `conversation_audio_artifacts` | Audio path/hash/format metadata only | `skip_embedding=true` |
| `personaplex_turns` | Optional derived projection, never canonical | `skip_embedding=true` |

The adapter performs a client-side CAS preflight before any memory mutation when a previous session head is supplied. If `previous_head.generation != expected_previous_generation`, it fails closed and records `cas_generation_mismatch`. Because the discovered daemon exposes only generic `/upsert`, the receipt records `cas_daemon_enforced=false`; this is honest and prevents claiming stronger server-side CAS than the endpoint proves.

All planned payloads are checked with `find_inline_vector_paths(...)` before mutation. Any explicit `vector`, `vectors`, `embedding`, `embeddings`, `dense_vector`, `sparse_vector`, `qdrant_vector`, or `semantic_vector` field fails closed before HTTP.

`real_conversation_compaction=true` requires 2xx memory daemon upserts for required collections: `conversation_history`, `conversation_history_summaries`, `personaplex_sessions`, and `conversation_audio_artifacts` when audio artifacts are present.

## P10 GPU PersonaPlex Inference Proof

The GPU probe uses three integration modes:

1. `PERSONAPLEX_P10_COMMAND` or `--command` returning JSON.
2. Import `personaplex_golden_state_server.py` and call one of:
   - `probe_lmgen_step`
   - `run_lmgen_step_probe`
   - `run_gpu_personaplex_probe`
   - `p10_lmgen_step_probe`
3. Best-effort CLI call:
   - `python personaplex_golden_state_server.py --probe-lmgen-step --json`

A returned payload is accepted as real proof only if all validation checks pass:

```text
real_gpu_personaplex == true
lmgen_step_called == true
GPU/CUDA device evidence is present
bounded step output is present, such as output_token_id, logits_shape, or step_output_sha256
```

Otherwise the probe writes a fallback receipt with `real_gpu_personaplex=false`.

## Combined Probe

`personaplex_p3_p5_combined_probe.py` runs the remaining-gap sequence:

1. P8 Deepgram WebSocket, or deterministic transcript fallback.
2. P7 context/evidence routing remains available for continuity.
3. P6 canonical turn memory upsert remains available for continuity.
4. P9 compaction over the sealed turn, including session head and audio metadata.
5. P10 GPU inference proof, or deterministic fallback.
6. Final receipt at `/tmp/personaplex-p8-p9-p10-sanity/p8-p9-p10-final-receipt.json`.

The strict real targets are:

```json
{
  "p8_real_deepgram": true,
  "p9_real_conversation_compaction": true,
  "p10_real_gpu_personaplex": true
}
```

## Commands And Expected Exit Codes

Run from repository root after overlaying this bundle.

### Unit tests

```bash
PYTHONPATH="$PWD/skills/personaplex/scripts:${PYTHONPATH:-}" \
  python3 -m unittest discover -s skills/personaplex/tests -p 'test_p8_p9_p10_remaining_gaps.py' -v
```

Expected exit code: `0`.

### P8 Deepgram non-strict sanity

```bash
bash skills/personaplex/sanity_p8_live_deepgram_real_audio.sh
```

Expected exit code: `0`. If `DEEPGRAM_API_KEY`, the `websockets` dependency, network, or speech audio is unavailable, the receipt records `real_deepgram=false` and fallback mode.

### P8 Deepgram strict live proof

```bash
export DEEPGRAM_API_KEY='<key>'
export PERSONAPLEX_P8_AUDIO_PATH="$PWD/assets/test/input_assistant.wav"
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p8_live_deepgram_real_audio.sh
```

Expected exit code: `0` only when Deepgram returns `speech_final=true`; otherwise `2`.

### P9 compaction non-strict sanity

```bash
bash skills/personaplex/sanity_p9_conversation_compaction.sh
```

Expected exit code: `0`. If `http://127.0.0.1:8601/upsert` is unavailable, fallback files are written and `real_conversation_compaction=false`.

### P9 compaction strict live proof

```bash
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p9_conversation_compaction.sh
```

Expected exit code: `0` only when required memory-daemon upserts return 2xx; otherwise `2`.

### P10 GPU PersonaPlex non-strict sanity

```bash
bash skills/personaplex/sanity_p10_gpu_personaplex_inference.sh
```

Expected exit code: `0`. If the golden-state server, GPU runtime, or LMGen hook is unavailable, fallback records `real_gpu_personaplex=false`.

### P10 GPU PersonaPlex strict proof

```bash
export PERSONAPLEX_ROOT=/path/to/PersonaPlex
export PERSONAPLEX_GOLDEN_STATE_SERVER=/path/to/personaplex_golden_state_server.py
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p10_gpu_personaplex_inference.sh
```

Expected exit code: `0` only when a validated `LMGen.step(...)` GPU proof is returned; otherwise `2`.

An explicit command hook is also supported:

```bash
export PERSONAPLEX_P10_COMMAND='python /path/to/personaplex_golden_state_server.py --probe-lmgen-step --json'
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p10_gpu_personaplex_inference.sh
```

### Combined non-strict sanity

```bash
bash skills/personaplex/sanity_p8_p9_p10_combined.sh
```

Expected exit code: `0`; individual real flags may be false if services are unavailable.

### Combined strict remaining-gaps gate

```bash
export DEEPGRAM_API_KEY='<key>'
export PERSONAPLEX_P8_AUDIO_PATH="$PWD/assets/test/input_assistant.wav"
export PERSONAPLEX_ROOT=/path/to/PersonaPlex
export PERSONAPLEX_GOLDEN_STATE_SERVER=/path/to/personaplex_golden_state_server.py
PERSONAPLEX_REQUIRE_REAL=1 bash skills/personaplex/sanity_p8_p9_p10_combined.sh
```

Expected exit code: `0` only when P8, P9, and P10 target flags are all true; otherwise `2`.

## Known Limitations

- Real P8 proof requires a valid Deepgram key, the optional `websockets` package, network access, and speech audio.
- The generic memory daemon `/upsert` endpoint does not prove server-side CAS. The adapter performs a client-side generation check and records `cas_daemon_enforced=false` unless a stronger daemon endpoint is later added.
- Real P10 proof requires the PersonaPlex checkout, GPU runtime, and a golden-state server hook or command that returns validated LMGen-step proof.
- Deterministic fallback receipts are useful for offline sanity but must never be cited as live-service proof.
