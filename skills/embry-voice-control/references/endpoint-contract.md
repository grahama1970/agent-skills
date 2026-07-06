# Embry Voice Control Endpoint Contract

This reference defines the minimum endpoint behavior for an Embry voice control
service.

## Health And Readiness

`GET /health` returns process liveness.

Required fields:

- `status`
- `version`
- `memory`
- `tau`
- `chatterbox`
- `listener`
- `chat_ux`

`GET /readiness` returns operational readiness, not optimism.

Allowed readiness values:

- `READY`
- `USABLE_WITH_GAPS`
- `NOT_READY`
- `NOT_ESTABLISHED`

Readiness must list missing live proof for listener, speaker identity,
memory/Tau, Chatterbox, Chat UX, orb, and replay separately.

## POST /turn

Purpose: run one user turn through the full voice/chat control path.

Required request fields:

- `session_id`
- `turn_id`
- `input_mode`: `text` or `voice`
- `text`, when available
- `speaker_evidence`, when voice identity evidence exists
- `voice_enabled`
- `chat_enabled`
- `replay_enabled`

Required response fields:

- `schema`
- `mocked`
- `live`
- `session_id`
- `turn_id`
- `speaker_resolution`
- `memory_intent`
- `memory_answer` or `memory_clarify` or `memory_deflect`
- `tau_result`
- `tts_render_request`
- `audio_authority`
- `chat_receipt`
- `orb_state`
- `receipt_path`
- `unverified`

## POST /speak

Purpose: render approved text through Chatterbox and optionally play it.

Misuse cases that must fail closed:

- missing `turn_id`
- missing `tts_render_text`
- untrusted user-supplied Chatterbox tags
- request asks Chatterbox to answer facts without memory/Tau approval
- stale turn has already been cancelled
- Chatterbox service unavailable

## POST /listen/start

Purpose: start listener capture for a session.

Required response fields:

- `listener_state`
- `capture_source`
- `vad_enabled`
- `asr_engine`
- `diarization_enabled`
- `receipt_path`

The service must state whether browser/WebRTC capture, local file/loopback, or
physical microphone input is being used.

## POST /turn/cancel

Purpose: cancel or stale-mark the active turn.

Required response fields:

- `cancelled_turn_id`
- `newer_turn_id`, when known
- `stale_chunks_marked`
- `audio_bytes_after_cancel`
- `receipt_path`

## POST /replay

Purpose: rebuild a conversation session in the shared Chat UX timeline with
audio and orb state synchronized.

Required response fields:

- `session_id`
- `turn_count`
- `audio_artifact_count`
- `timeline_offsets_ms`
- `replay_started`
- `receipt_path`

Replay must include both human/project-agent turns and Embry turns.

