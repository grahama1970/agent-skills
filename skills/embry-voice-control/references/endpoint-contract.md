# Embry Voice Control Endpoint Contract

This reference defines the minimum endpoint behavior for an Embry voice control
service.

Embry voice control is the voice front-end to Tau. The endpoint layer should
collect voice/chat evidence, call memory and Tau, and render Tau-approved speech
through Chatterbox. It should not invent a parallel reasoning path.

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
- `conversation_tone` or `tone`
- `delivery_stage`
- `emotion_tags`
- `chatterbox_tags`
- `cue_policy`
- `intent_policy_source`
- `pause_strategy`
- `interrupt_policy`
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
- missing selected tone
- missing `emotion_tags`, `chatterbox_tags`, `cue_policy`, `pause_strategy`,
  `interrupt_policy`, or `intent_policy_source`
- untrusted user-supplied Chatterbox tags
- request asks Chatterbox to answer facts without memory/Tau approval
- stale turn has already been cancelled
- Chatterbox service unavailable

For normal generated speech, `intent_policy_source` must be `memory.intent`.
Direct sanity speech may use `direct_sanity_explicit_policy`, but that receipt
only proves Chatterbox render/control wiring, not memory-driven tone steering.

## POST /listen/start

Purpose: start listener capture for a session.

The default implementation must start or attach to the Unix/PipeWire
RealtimeSTT listener service. Browser microphone capture may be exposed as a
diagnostic client source, but it must not be required for the main listener to
work.

Required response fields:

- `listener_state`
- `capture_source`
- `vad_enabled`
- `asr_engine`
- `diarization_enabled`
- `receipt_path`

The service must state whether PipeWire physical microphone, PipeWire loopback,
local file injection, or browser/WebRTC diagnostic input is being used. If the
source is browser/WebRTC, the response must label the proof as diagnostic and
must not mark listener readiness as release-ready.

Preferred listener event transport:

```text
Unix socket or localhost SSE/WebSocket
```

Current workstation transport is localhost HTTP with SQLite WAL persistence:

```text
POST /v1/listener/events
GET  /v1/sessions
GET  /v1/sessions/{session_id}/events
GET  /v1/sessions/{session_id}/journal
POST /v1/turns/{turn_id}/cancel
```

Each `embry.voice_event.v1` requires `event_id`, `session_id`, `turn_id`, a
monotonic positive `sequence`, `type`, `created_at`, and `payload`. Producers
must continue sequence numbers across turns in a session. Exact event replay is
idempotent; conflicting event IDs or duplicate session sequence numbers fail.

Required event types:

- `listener.state`
- `listener.wake_detected`
- `listener.partial_transcript`
- `listener.final_transcript`
- `listener.error`
- `listener.receipt_written`

## Wake Word Event

The wake word is exactly `Embry`. Do not require `Hey Embry`.

The listener service owns wake detection. React only renders state from the
event stream. Chatterbox does not detect wake words.

Accepted wake event shape:

```json
{
  "schema": "embry_voice_control.wake_detected.v1",
  "type": "voice.wake_detected",
  "wake_phrase": "embry",
  "session_id": "...",
  "source": "embry-voice-control",
  "confidence": 0.91,
  "state_transition": ["idle", "wake_detected", "listening"],
  "ui_feedback": {
    "standby_instruction": "SAY \"EMBRY\"",
    "instruction_opacity": 0.2,
    "subtitle": "LISTENING...",
    "orb_state": "listening"
  }
}
```

Wake attempts must fail closed when confidence is below threshold, the speaker is
not the resolved primary speaker, the wake cooldown is active, or Embry is
currently speaking and self-audio suppression is active.

## Controlled Wake-To-Turn Runner

When the UI/control plane exists but live hot-mic wake is not established, use a
controlled wake event to exercise the real turn endpoint:

```bash
./run.sh wake-capital-france-live --base-url http://127.0.0.1:3001/api/projects/embry-voice
```

The runner must include the wake event in the `/turn` or local adapter
`/live-turn` request. It must write a receipt and fail when the control plane
does not return live non-mocked turn authority, audio authority, voice policy,
pause policy, interrupt policy, and an answer mentioning Paris for:

```text
What is the capital of France?
```

This is not a substitute for `/listen/start`; the receipt must state
`hot_mic_wake_proven=false` until a RealtimeSTT or browser microphone wake event
produces the same request.

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
