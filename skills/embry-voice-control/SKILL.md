---
name: embry-voice-control
description: >
  Agent-readable Embry voice control-plane contract for speaking, listening,
  cancelling, replaying, and inspecting live voice/chat turns. Use when a
  project agent needs to control Embry Chatterbox voice, RealtimeSTT listener
  state, shared Chat UX synchronization, memory/Tau routing, orb state, or
  session replay through explicit endpoints instead of ad hoc browser scripts.
triggers:
  - embry voice control
  - make embry speak
  - make embry listen
  - control embry voice
  - embry chatterbox endpoint
  - voice chat control plane
  - embry listen start
  - embry speak endpoint
  - replay embry conversation
  - embry orb sync
provides:
  - embry-voice-control-plane
  - voice-chat-turn-endpoints
  - chatterbox-speech-control
  - listener-control-contract
  - voice-session-replay-contract
  - chat-audio-orb-authority-contract
composes:
  - memory
  - tau
  - best-practices-chatterbox-agent
  - best-practices-converse
  - best-practices-python
  - best-practices-skills
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - voice
  - conversation
  - endpoints
  - memory
  - validation
runtime_self_improvement: basic
---

# Embry Voice Control

Use this skill when an agent needs to operate Embry voice as a controllable
system. This is the endpoint/control-plane contract. It is not the conversation
style guide and it is not the Chatterbox renderer itself.

Think of `embry-voice-control` as the voice front-end to Tau: it receives voice
or text turns, gathers listener and memory evidence, asks Tau to shape the
agentic response when needed, and then sends approved render text to Chatterbox.
It must not become a second reasoner beside Tau.

## Boundary

- `$memory` owns speaker identity, intent, recall, answer, clarify, and deflect.
- Tau owns agentic reasoning and project/tool coordination; this skill fronts
  Tau with voice/chat control.
- Chatterbox owns speech rendering from approved `tts_render_text`.
- RealtimeSTT/listener owns VAD, ASR, diarization, and speaker evidence.
- Shared Chat UX owns visible transcript, reasoning trace, audio controls, orb
  state, and replay presentation.
- `embry-voice-control` owns the agent-readable endpoint contract connecting
  those systems for one turn/session.

## Required Endpoint Surface

Implementations should expose JSON endpoints with stable request/response
schemas:

```text
GET  /health
GET  /state
GET  /readiness

POST /listen/start
POST /listen/stop

POST /turn
POST /speak
POST /turn/cancel
POST /replay

GET  /sessions
GET  /sessions/{session_id}
GET  /turns/{turn_id}
GET  /receipts/{turn_id}
```

The endpoint names are the control contract. A current project may temporarily
adapt them to local URLs such as `/api/projects/embry-voice/live-turn`, but
agents should treat this skill as the stable target shape.

## Turn Flow

```text
voice/text turn
  -> /turn
  -> listener evidence when voice is enabled
  -> $memory /speaker/resolve when speaker evidence exists
  -> $memory /intent, including voice delivery policy
  -> $memory /recall and /answer | /clarify | /deflect as routed
  -> Tau response shaping when needed
  -> Chatterbox /tau/voice-render or /synthesize-batch-stream
  -> shared Chat UX transcript + audio + orb + replay receipt
```

Every response must preserve a single turn authority:

```text
turn_id == chat receipt turn_id == audio artifact authority == orb source
```

## Speaking

`POST /speak` is for direct approved speech. It must not invent factual answers.

Required request fields:

- `turn_id`
- `session_id`
- `tts_render_text`
- `answer_text`, when different from rendered text
- `tone`
- `delivery_stage`
- `pause_strategy`
- `interrupt_policy`
- `interruptible`
- `play_local`, when speaker playback is requested

Required response fields:

- `mocked`
- `live`
- `turn_id`
- `conversation_tone` or `tone`
- `delivery_stage`
- `emotion_tags`
- `chatterbox_tags`
- `cue_policy`
- `intent_policy_source`
- `pause_strategy`
- `interrupt_policy`
- `audio_artifact_id`
- `audio_url` or `audio_path`
- `audio_authority`
- `voice_envelope`, when orb sync is supported
- `receipt_path`

## Listening

`POST /listen/start` and `POST /listen/stop` control listener state only. They
do not directly answer the user.

The required wake word is exactly:

```text
Embry
```

The visible standby affordance should say `SAY "EMBRY"`. When the local listener
detects the wake word, it must emit a wake event and transition:

```text
idle -> wake_detected -> listening
```

The UI should dim the `SAY "EMBRY"` instruction and show `LISTENING...` as soon
as the wake event is accepted. The listener should reject low-confidence,
non-primary-speaker, cooldown, and while-Embry-is-speaking wake attempts.

Listener output must become structured turn evidence:

- `audio_turn_started`
- `partial_transcript`
- `final_transcript`
- `speaker_candidates`
- `diarization_segments`
- `overlap_detected`
- `interruption_detected`
- `barge_in_detected`

Speaker evidence must be passed to `$memory /speaker/resolve`; the voice
control layer must not choose identity by label assumption.

## Replay

`POST /replay` should replay the conversation through the same Chat UX timeline,
including user turns, Embry responses, Chatterbox audio, reasoning trace, and orb
state. Replay is not only audio playback; it is a reconstruction of the turn
sequence with timing offsets.

## Required Behavior

- Voice input is as first-class as text input.
- `$memory /intent` is the authority for Embry's conversational tone and
  injected emotion/tag policy on normal generated turns. The voice control layer
  must not guess tone or Chatterbox tags locally when memory intent is available.
- Every Embry speech item must include a selected conversational tone and an
  injected-emotion/tag policy. If no literal Chatterbox tag is appropriate, the
  receipt must explicitly record `chatterbox_tags=[]` and explain the
  `cue_policy`; omission is a failed receipt. Receipts must also record
  `intent_policy_source`, normally `memory.intent`; direct local sanity speech
  may use `direct_sanity_explicit_policy`.
- Every Embry speech item must include the default pause and interrupt strategy.
  `pause_strategy` and `interrupt_policy` are required receipt fields, not UI
  hints. Missing pause or interrupt policy is a failed voice receipt.
- Unknown or ambiguous speakers fail closed to identity clarification.
- Multiple non-Embry speakers overlapping map to a one-at-a-time boundary.
- Barge-in cancels old speech and stale chunks before the new turn wins.
- Chat text, audio, orb, and receipts must share turn authority.
- Any cached QRA audio path must be gated by `$memory` near-exact approved QRA
  recall for the resolved speaker.
- All claims of working behavior require non-mocked receipts that state
  `mocked`, `live`, what was exercised, and what remains unverified.

## Implementation Standards

If this skill grows scripts or a service, follow `$best-practices-python`:
Loguru, Typer, httpx, uv/pyproject, module docstrings, thin `__init__.py`,
complete dependencies, functions first, files under 800 lines, and non-mocked
sanity tests.

## Live Sanity

Run the deterministic wake-word contract sanity before live listener work:

```bash
./run.sh wake-sanity
```

This writes a receipt under
`/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/wake-word/`. It proves
only the local wake-word state contract and does not prove hot mic capture,
RealtimeSTT wake detection, Chatterbox, Chat UX, or orb sync.

Run the opt-in live harness before claiming the voice front-end works:

```bash
./run.sh verify --profile controlled-live
```

The harness calls real configured endpoints and writes receipts under
`/mnt/storage12tb/skills/embry-voice-control/outputs/e2e/<run-id>/`. Missing
services, missing fields, stale turn authority, absent Tau evidence, or absent
audio/orb authority must produce `NOT_ESTABLISHED` or `NOT_READY`, not a mocked
pass.

## References

- `references/endpoint-contract.md`: request/response shapes and misuse cases.
- `references/e2e-sanity-checks.md`: live non-mocked sanity matrix.
