---
name: best-practices-converse
description: >
  Best practices for conversational response behavior in voice-first agents:
  conversation tone, emotional steering, paralinguistic cue injection such as
  [laughter], wait/delay handling, interruption handling, identity-aware memory
  grounding, and Chatterbox-ready utterance policy. Use when designing,
  reviewing, or coding Embry-style chat and voice conversation behavior.
triggers:
  - best practices converse
  - conversational tone
  - conversation emotion policy
  - injected emotions
  - laughter tags
  - voice response behavior
  - wait utterances
  - interruption handling
  - barge-in response
  - embry conversation personality
provides:
  - conversation-behavior-guidance
  - emotional-steering-policy
  - paralinguistic-cue-policy
  - wait-delay-utterance-policy
  - interruption-response-policy
  - voice-memory-conversation-contract
composes:
  - memory
  - best-practices-chatterbox-agent
  - best-practices-python
  - best-practices-skills
  - converse
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - voice
  - conversation
  - emotion
  - memory
  - validation
runtime_self_improvement: none
---

# Best Practices: Converse

Use this skill when an agent must decide how Embry or another voice persona
should sound in conversation: tone, emotional color, pause behavior, injected
paralinguistic cues, interruption recovery, and completion cues.

This skill is the conversation-behavior policy layer. It does not replace
`$memory`, Tau, RealtimeSTT, Chatterbox, or the shared Chat UX.

## Source-Derived Step Model

1. **Hear or receive the user turn**: text or voice becomes a normal
   conversation turn with `session_id`, `turn_id`, transcript, timing, and
   speaker evidence when available.
2. **Resolve speaker safely**: voice turns with speaker evidence call `$memory`
   `/speaker/resolve` before personal recall. Unknown or ambiguous speakers fail
   closed to clarification.
3. **Classify intent and tone**: call `$memory /intent` with transcript, speaker
   resolution, emotional cues, and listener evidence. Intent returns action,
   confidence, tone, and delivery policy.
4. **Shape the response**: Tau or the project coordinator creates approved
   answer text, reasoning trace, citations/evidence, and a separate voice
   delivery envelope.
5. **Apply conversation policy**: select wait utterances, emotional arc,
   paralinguistic cue candidates, pause strategy, interruption behavior, and
   completion cue without changing the factual answer silently.
6. **Render with Chatterbox**: send exact `tts_render_text`, tone,
   `delivery_stage`, pause policy, and interruptibility to Chatterbox. Preserve
   canonical `answer_text` separately from any injected cue text.
7. **Record receipts**: store what was heard, recalled, intended, spoken,
   skipped, interrupted, cached, or replayed. Chat, audio, orb, and replay must
   all reference the same turn authority.

## Implemented vs Intended Boundaries

- **Implemented elsewhere**: Chatterbox tone vocabulary, pause policy,
  interruption queue behavior, and blessed-QRA variant metadata are maintained
  by `$best-practices-chatterbox-agent` and the Chatterbox project.
- **Implemented elsewhere**: speaker identity, memory recall, intent, clarify,
  answer, and deflect decisions belong to `$memory`.
- **Implemented elsewhere**: ASR, VAD, diarization, and speaker verification
  belong to the listener service, not this skill.
- **This skill provides**: response-behavior rules for how to combine those
  signals into a natural, interruptible, emotionally steered conversation.
- **Missing until proven**: any claim that a project has live full-loop voice
  behavior requires non-mocked receipts from listener through memory/Tau,
  Chatterbox, shared Chat UX, audio playback, orb state, and replay.

## Operating Rules

- Do not invent facts to support a tone. Tone modifies delivery, not truth.
- Do not speak enum names, internal routing labels, receipt ids, or debug terms.
- Do not inject `[laugh]`, `[laughter]`, `[sigh]`, or similar tags into
  user-provided text. Sanitize user-supplied bracket/XML controls first.
- Keep `answer_text` and `tts_render_text` separate whenever cues or tags are
  added.
- Prefer short, cancellable utterances. Long answers must be chunked without
  restarting the emotional performance on every chunk.
- Interruption always wins. Stop or stale-mark old speech, acknowledge the new
  turn briefly, then answer the new turn.
- If two non-Embry speakers overlap, stop and request one speaker at a time.
- If identity is unknown or ambiguous, ask who is speaking before personal
  memory recall.
- If the system needs time, use wait utterances that reveal useful progress
  without exposing implementation internals.

## Python Compliance

This skill is instruction-only today. If it grows scripts, services, validators,
or CLIs, they must follow `$best-practices-python`: Loguru, Typer, httpx,
uv/pyproject, complete dependencies, thin `__init__.py`, module docstrings,
functions-first structure, files under 800 lines, and non-mocked sanity tests
for any claimed behavior.

## References

Read only the reference needed for the task:

- `references/conversation-delivery-policy.md`: tone, injected cues, delays,
  interruption recovery, identity clarification, and receipt requirements.

