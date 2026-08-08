---
name: best-practices-chatterbox-agent
description: >
  Best practices for Chatterbox or Chatterbox-Turbo voice agents, especially
  interruptible Embry-style agents that run memory, search, LLM, or other
  long-running skills concurrently. Use when designing, reviewing, or coding a
  voice coordinator, async task batch, JSON event stream, cancellable TTS queue,
  Chatterbox emotion/tag policy, pause policy, barge-in behavior, or spoken
  progress/preamble strategy.
triggers:
  - chatterbox agent best practices
  - chatterbox voice agent
  - chatterbox turbo agent
  - interruptible voice agent
  - async voice coordinator
  - voice coordinator as_completed
  - json streaming voice agent
  - chatterbox emotions and pauses
  - embry chatterbox agent
  - chatterbox voice input
  - embry listener identity
provides:
  - chatterbox-agent-guidance
  - interruptible-voice-agent-patterns
  - async-voice-coordinator-contract
  - tts-emotion-pause-policy
  - voice-input-parity-contract
  - voice-agent-validation-checklist
composes:
  - memory
  - brave-search
  - best-practices-agent
  - best-practices-python
  - best-practices-skills
  - best-practices-subagent
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - voice
  - agents
  - async
  - validation
disciplines:
  - engineering-standards
  - voice-audio
---

# Best Practices: Chatterbox Agent

Use this skill to keep Chatterbox voice agents controllable, interruptible, and
evidence-grounded. Chatterbox is the speech renderer; the agent stack still owns
turn state, memory recall, long-running skill execution, cancellation, receipts,
and what is worth saying out loud.

## Core Pattern

Design the system as four separate loops:

```text
user audio / text turn
  -> turn manager
  -> skill orchestrator running asyncio task batches
  -> structured result queue
  -> voice coordinator
  -> cancellable Chatterbox TTS queue
```

The skill orchestrator may use `asyncio.as_completed()` to process memory,
search, ASR, LLM, and tool results as they finish. The voice coordinator must not
blindly speak every completed task. It scores, debounces, summarizes, and then
speaks only useful progress or final answer chunks.

## Voice Input Parity

Voice input is a first-class user turn source, not a secondary demo path. Any
Embry or Chatterbox project agent that supports text turns should define the
matching voice path with the same product expectations: identity, memory,
intent, recall, answer shaping, interruption, receipts, and safety gates.

The listener companion owns audio evidence:

```text
microphone frames
  -> VAD / noise filtering
  -> optional diarization or speaker verification
  -> ASR transcript events
  -> coordinator turn events
  -> memory speaker resolution
  -> intent / recall / answer
  -> cancellable Chatterbox speech
```

Use `$memory` `/speaker/resolve` before personal recall whenever a voice turn
has speaker evidence. The voice stack should pass listener evidence such as
speaker candidates, diarization labels, verification scores, transcript text,
and source names. `$memory` owns the safe identity decision:

```text
/speaker/resolve
  known     -> /intent with speaker_resolution -> speaker-scoped /recall
  unknown   -> ask identity clarification before personal recall
  ambiguous -> ask identity or disambiguating clarification before personal recall
```

Known voice turns should prefer the `speaker_conversation_memory` recall profile
when returned by `/speaker/resolve`. For Horus Lupercal, this means Embry should
recall Horus-scoped conversational facts, relationship context, preferences,
and prior conversations before speaking as though she knows the speaker.

Unknown or ambiguous voice turns must fail closed. Do not use another user's
QRA cache, emotional profile, relationship context, or memory facts until the
speaker is resolved. If Embry does not know who is speaking, she should ask in a
natural way and vary that question across turns.

Do not put raw audio processing inside Chatterbox. RealtimeSTT, pyannote,
SpeechBrain/ECAPA, WebRTC VAD, denoisers, or the listener service may provide
evidence. Chatterbox remains the renderer; the coordinator and `$memory` decide
who is speaking, what is known, what should be recalled, and what should be
said.

## Required Behavior

1. Create a fresh `turn_id` for every user turn.
2. Emit JSON events for task start, task result, progress speech, TTS submit,
   interruption, stale chunk skip, and final receipt.
3. Run independent slow work concurrently and consume results with
   `asyncio.as_completed()`.
4. Put all speech through a voice coordinator and cancellable TTS queue.
5. Speak a short holding/preamble utterance when silence would feel broken.
6. Cancel or stale-mark old chunks immediately when the user interrupts.
7. Preserve receipts for what was actually retrieved, spoken, cancelled, or
   skipped.
8. Submit exact text to Chatterbox; record text hashes before TTS.
9. Do not allow three seconds of perceived dead air while work is pending. If
   no useful result is ready, speak a short low-buffer filler such as "Hmm. I
   need to think more about this." The user will interpret long silence as a
   crash.
10. Treat subagent/model-call latency as its own phase. After memory/search is
    ready, GPT-5.5 or Tau may still take several seconds to shape the answer;
    Embry must bridge that gap with a natural transition or optional idle hum.

## Memory Pipeline

For memory-grounded persona voice, use the complete memory route:

```text
memory.intent
  -> memory.recall
  -> memory.answer | memory.clarify | memory.deflect
```

Do not generate factual voice answers directly from Chatterbox, PersonaPlex, or a
TTS prompt. Chatterbox speaks the approved answer text; it does not own facts.

`$memory /intent` is also the authority for Embry's conversational tone and
injected emotion/tag policy. The voice coordinator must call `/intent` before
choosing `tone`, `delivery_stage`, `emotion_tags`, `chatterbox_tags`, or
`cue_policy` for generated answers, memory responses, clarification prompts,
deflections, one-at-a-time boundaries, and wait-presence utterances.

Tau or the voice coordinator may adapt wording and delivery only inside the
policy returned by `$memory /intent`. If `/intent` does not return an explicit
voice delivery policy, fail closed to a safe default such as
`memory_uncertain`, `clarify`, `emotion_tags=["careful"]`,
`chatterbox_tags=[]`, and `cue_policy="intent_missing_voice_delivery_policy"`,
then record that gap in the receipt. Do not silently guess an emotional arc from
local UI state, Chatterbox defaults, or prompt wording.

## Speech Policy

Speak in short, cancellable chunks. During long-running work, speak progress only
when it changes the user's understanding:

```text
"Give me five seconds to answer that. I'm checking memory first."
"Hmm. I need to think more about this."
"Hmm. Give me another second."
"I'm still here. I'm checking one more thing."
"Hold on. I have part of it."
"I found the account. I'm checking the billing history."
"One source is slow, but I have enough to continue."
"Stopping that answer. Give me a second to re-check the right thread."
```

The voice coordinator must track perceived silence, not only backend task time.
If playback will leave more than about 1.5-2.0 seconds of quiet while tasks are
pending, queue a short filler before the gap reaches 3 seconds. Keep fillers
non-factual and cancellable.

Recommended low-buffer fillers:

```text
"Hmm."
"Okay."
"Let me check."
"I'm looking now."
"One moment."
"Got it."
"I see."
"Checking that."
"Looking into it."
"I'm pulling that up."
"Almost there."
"I have part of it."
"That's coming in now."
"I'm still checking."
"Still with you."
"I found something."
"Let me verify that."
"One check is still running."
"I have enough to start."
"Here's what I'm seeing."
"Hmm. Give me another second."
"I'm still here. I'm checking one more thing."
"Hold on. I have part of it."
"Give me one more second."
```

Timing policy:

```text
0-700 ms: say nothing.
700 ms-2 s: use a soft filler like "Hmm." or "Let me check."
2-5 s: give a real progress update.
5-8 s: explain that the answer is still being shaped.
8+ s: optionally start low-volume cached wait entertainment, if available,
  and duck it as soon as speech resumes.
```

Subagent/model-call latency strategy:

```text
memory/search pending:
  speak fillers/progress tied to streamed results.

text reasoner or Tau subagent pending:
  say "I have enough to start. Give me a second to shape the answer."

particularly long wait:
  optionally start cached $hum/singing/idle playback on a separate idle channel.

answer ready:
  stop or duck hum, then say "Okay, here's the answer."
```

Wait entertainment is only an idle-presence signal for long waits. It must not
replace answer speech, must not mask user speech, and must stop or duck
immediately when Embry speaks or the human interrupts.

Embry may do more than hum during long waits. The point is to feel present,
endearing, and lightly entertaining for impatient humans while the real memory,
search, or subagent work continues. Allowed wait activities include:

```text
soft humming from a curated cache
low singing from a curated cache
quiet mouth beatbox / rhythm gesture
counting small prime numbers
short playful check-ins
brief curious observations about the search taking shape
```

These activities are never factual answer substitutes. They must be cancellable,
duckable, and selected from structured metadata based on `$memory intent`,
conversation tone, user mood, expected wait, and safety context. Serious grief,
medical/legal/security, angry-user, or high-stakes contexts should prefer quiet,
calm, low-energy presence or plain progress phrases. Casual, playful, creative,
or explicitly entertainment-friendly contexts may use more charming behavior
such as beatbox, low singing, or prime-counting.

Do not overuse a single trick. Rotate wait activities across a session and
record the selected `wait_activity`, `activity_text` or `audio_track_id`,
`mood_tags`, `tone_tags`, `expected_wait_ms`, and interruption behavior in JSON
events.

Avoid raw implementation status:

```text
"Task 4 completed."
"Awaiting remaining futures."
"Tool returned JSON."
"For this turn..."
"I will drop stale chunks."
```

Keep internal mechanics out of spoken Embry responses. Terms like `turn_id`,
`JSON stream`, `receipt`, `gate`, `memory row`, `stale chunk`, and `voice
coordinator` belong in logs and receipts. Embry's audible response should only
contain pause communication and the answer itself unless the human explicitly
asks about the system mechanics.

## Tonal Delivery Vocabulary

Use this controlled vocabulary for voice coordinator events, QRA response
overlays, blessed-QRA audio variants, Chatterbox receipts, and future
style-capable TTS adapters. These values are operational metadata. Do not speak
the enum names aloud.

Do not invent new delivery values casually. If a project needs a new value,
update this skill or record `custom_tone_reason` in the receipt so reviewers can
see why the standard set was not enough.

Canonical `tone` values:

| tone | Use when |
| --- | --- |
| `neutral_warm` | Default concise Embry delivery for ordinary helpful answers. |
| `calm_precise` | Factual, technical, security, compliance, or source-grounded answers. |
| `careful_concerned` | Risk, uncertainty, safety-sensitive, or emotionally delicate turns. |
| `serious_low_energy` | High-stakes, angry-user, legal, medical, security, or grief-adjacent contexts. |
| `memory_confident` | Speaker-scoped memory or exact QRA hit has strong evidence. |
| `memory_uncertain` | Memory is weak, missing, conflicting, or needs clarification. |
| `curious_searching` | Memory/search/tool work is pending and a non-factual bridge is needed. |
| `playful_light` | Casual, low-risk, explicitly playful, or entertainment-friendly turns. |
| `relieved` | A confusion, error, or tense thread has resolved. |
| `firm_boundary` | Stop, cancel, refusal, safety, or turn-taking boundary. |
| `identity_clarification` | Speaker is unknown or ambiguous and personal recall must fail closed. |
| `one_at_a_time_interrupt` | Multiple non-Embry speakers overlap and the agent should stop and ask for one speaker. |
| `deflect_calm` | Off-topic, unsafe, unsupported, or no-match response without escalation. |
| `grief_safe` | Grief, trauma, sadness, or highly vulnerable user state. |
| `wait_presence` | Low-content presence while live work continues. |

Canonical `delivery_stage` values:

```text
setup
slightly_concerned
neutral
positive
satisfied
clarify
boundary
interrupted
deflect
wait
```

Canonical `pace` values:

```text
brief
measured
slow_careful
quick_light
firm_short
```

Canonical `pause_strategy` values:

```text
short_answer_no_filler
chunk_pause_150_350ms
careful_setup_pause
clarify_direct_no_completion
boundary_stop_then_prompt
wait_filler_then_progress
hum_duck_on_speech
```

Canonical `wait_activity` values:

```text
none
soft_hum
low_singing
quiet_rhythm
prime_counting
playful_check_in
curious_observation
```

Canonical `chatterbox_tags` values, only when the active Chatterbox model or API
documents support them:

```text
[chuckle]
[sigh]
[gasp]
[whispering]
[laugh]
```

## Required Speech Delivery Envelope

Every time Embry speaks, the coordinator must choose and record a delivery
envelope. This applies to final answers, holding utterances, wait presence,
interruption acknowledgements, identity clarification, one-at-a-time boundaries,
completion cues, blessed QRA playback, replay, and direct sanity speech.

For normal generated turns, this envelope must be derived from `$memory /intent`.
The receipt must identify the intent policy source, for example
`intent_policy_source="memory.intent"` and the relevant `intent_id`,
`route_key`, or `recall_profile` when available. Direct local sanity speech may
use an explicit `direct_sanity_explicit_policy`, but it must say so and must not
be treated as proof that memory-driven emotional steering works.

Required fields for every spoken item:

```text
conversation_tone or tone
delivery_stage
pace
pause_strategy
interrupt_policy
emotion_tags
chatterbox_tags
cue_policy
intent_policy_source
answer_text
tts_render_text
answer_text_hash
tts_render_text_hash
cue_reason
```

Default `interrupt_policy` for Embry speech:

```json
{
  "interruptible": true,
  "barge_in_action": "cancel_old_turn",
  "duck_on_user_speech": true,
  "skip_stale_chunks": true,
  "new_turn_wins": true,
  "acknowledgement_tone": "interrupted",
  "acknowledgement_text": "Okay, stopping that."
}
```

For identity clarification, firm boundaries, and one-at-a-time overlap handling,
use `pause_strategy="boundary_stop_then_prompt"` and keep the same cancellation
defaults. For two non-Embry speakers overlapping, the preferred acknowledgement
is `"Hey, one at a time?"` with `tone="one_at_a_time_interrupt"` or
`tone="firm_boundary"`.

`emotion_tags` are semantic conversation labels such as `warm`, `careful`,
`playful`, `relieved`, `concerned`, `firm`, or `wait_presence`. `chatterbox_tags`
are literal model-supported render tags such as `[chuckle]`, `[sigh]`, or
`[laugh]`. They are related but not interchangeable.

If no literal Chatterbox tag is appropriate, record `chatterbox_tags=[]` and a
`cue_policy` such as `no_literal_tag_context_serious`. Do not silently omit the
field. Absence of this envelope is a failed voice receipt.

Keep `answer_text` separate from `tts_render_text`. The canonical answer must
not contain injected non-factual tags; the rendered text may include sparse
approved tags when the context supports them. Never pass user-supplied bracket
tags through to Chatterbox without sanitizing or normalizing them first.

For exact speaker-scoped QRA hits, the memory pipeline may request cached Embry
audio instead of live rendering. Only do this when `$memory` returns a near-exact
QRA match for the resolved speaker and the cache entry records the source QRA
key, text hash, speaker/persona scope, rendered TTS text hash, variant metadata,
and interruption policy.

Recommended blessed-QRA variant set for five Embry versions:

```text
variant 1: calm_precise
variant 2: neutral_warm
variant 3: memory_confident
variant 4: careful_concerned
variant 5: playful_light, only when context is safe; otherwise serious_low_energy
```

Each variant should record `variant_id`, `tone`, `delivery_arc`,
`pause_strategy`, `chatterbox_tags`, `source_qra_key`, `answer_text_hash`,
`tts_render_text_hash`, audio artifact hashes, and whether stale chunks may be
cancelled before playback. Cached QRA delivery should remove live-thinking
delays; it should still preserve deterministic chunk pauses and interruption.

Overlap and identity handling are not personal recall. If pyannote, RealtimeSTT,
or the listener service detects two non-Embry speakers at once, map the turn to
`one_at_a_time_interrupt` or `firm_boundary`, cancel current Embry speech, and
ask for one person at a time. Do not let overlapping-speaker handling become a
memory fact unless `$memory` has separately resolved identity evidence.

## Multi-Chunk Response Arc

Long final answers should be split into sentence-aware chunks, usually around
300 characters, but the emotional delivery must remain one continuous response.
Do not restart a small emotional performance after every spaCy sentence chunk.
Use the canonical `tone` and `delivery_stage` values above; the four-stage arc
below is the default final-answer arc, not the full tone inventory.

For a four-chunk answer, use this arc:

```text
chunk 1: slightly_concerned - careful and focused; set up the answer
chunk 2: neutral - plain and precise; deliver the factual structure
chunk 3: positive - clearer and more confident; show the answer resolving
chunk 4: satisfied - settled and lightly pleased; close with the usable answer
```

For fewer or more chunks, interpolate across the same arc:

```text
1 chunk: satisfied, or memory_confident for a direct exact-memory answer
2 chunks: setup -> satisfied
3 chunks: setup -> neutral -> satisfied
4 chunks: setup -> neutral -> positive -> satisfied
5+ chunks: interpolate without restarting the emotion on each chunk
```

Store the chosen `delivery_stage`, `tone`, `delivery_role`, `pace`,
`pause_strategy`, and `arc_position` in JSON events and receipts. The stage
metadata is operational guidance for the voice coordinator and future
style-capable TTS adapters; it should not be spoken as debug text.

Between final-answer chunks, use short deterministic playback-layer pauses
rather than repeated filler phrases. Fillers like "Hmm" or "Give me another
second" are for waiting on retrieval, tools, or model calls, not for every
completed sentence chunk of an already-ready answer.

Sparse personality cues are allowed when they improve perceived continuity, but
they must not make the answer feel like it is restarting between chunks:

```text
Good:
- 150-350 ms playback-layer pause between normal final chunks.
- One soft "Hmm." before a careful answer when the first chunk needs a cautious
  setup.
- One documented Turbo tag such as `[sigh]` only when the context calls for a
  concerned or relieved breath.
- A light `[chuckle]` only in casual/user-positive contexts.

Bad:
- Saying "give me another second" after the final answer is already ready.
- Repeating "Hmm" before every 300-character chunk.
- Using `[sigh]` in support/security answers where it could sound annoyed.
- Adding cue words that change the factual answer text or break exact-text
  receipts without recording the rendered TTS text separately.
```

If the cue is not part of the factual answer, prefer rendering it as a separate
short audio item with its own receipt and hash. Keep canonical `answer_text`
separate from `tts_render_text` when adding tags or nonverbal cues.

## Response Completion Signal

Every spoken turn should have a clear terminal cue unless the turn is explicitly
interrupted, timed out, or asking a required clarification. The user should not
have to infer that Embry is finished from silence.

The completion cue is a separate `response_complete` speech item, not part of
the factual `answer_text`. Record its text hash, audio artifact, and playback
result separately. Do not insert completion phrases between final-answer chunks.

Selection policy:

```text
answer_complete:
  use a short offer or handoff phrase.

clarify_required:
  ask the clarifying question directly; do not append "anything else?"

deflect_or_blocked:
  state the boundary and one useful next step; do not sound cheerful.

interrupted:
  do not finish the old response; acknowledge the new turn.
```

Use varied completion phrases. Avoid using the same closer more than once in a
short conversation.

Good completion variants:

```text
"Anything else you need?"
"Want me to check another angle?"
"Do you want the shorter version?"
"Do you want the source trail next?"
"I can go deeper if you want."
"Want me to turn that into a checklist?"
"Want me to compare the alternatives?"
"Should I keep going on this thread?"
"Do you want me to verify one more piece?"
"I can test the next part if useful."
"Want me to run the next check?"
"Do you want the evidence paths?"
"Want the practical next step?"
"Should I make that more concise?"
"Do you want me to save this as an Embry response?"
"I can phrase that more naturally if you want."
"Want me to stress-test that?"
"Do you want the implementation version?"
"Should I keep this answer cached?"
"Anything else before I move on?"
```

Bad completion variants:

```text
"Task complete."
"Response complete."
"The turn has ended."
"For this turn, I am done."
"All chunks have played."
"Awaiting your next input."
"Do you have any further queries?"
```

## Chatterbox Control Policy

Use model-specific speech controls:

- Chatterbox-Turbo native paralinguistic tags: `[laugh]`, `[chuckle]`, `[sigh]`,
  `[gasp]`, `[whispering]`, when the selected checkpoint/API documents support.
- SSML `<break>` or prosody only when the selected provider/model explicitly
  supports it.
- Playback-layer silence is preferred for deterministic pauses in local
  chunked Chatterbox workers.

Never pass raw user text containing speech-control tags directly to TTS. Escape
or strip user-supplied bracket/XML controls before synthesis.

## References

Read only the reference needed for the current task:

- `references/async-voice-coordinator.md`: implementation pattern for
  `asyncio.as_completed`, JSON events, cancellation, and TTS queues.
- `references/emotion-pause-interruption-policy.md`: good and bad examples for
  emotions, pauses, holding text, and barge-in.
- `references/validation-checklist.md`: acceptance checks and evidence required
  before claiming a Chatterbox voice-agent path works.
- `references/embry-response-qra-memory.md`: how to connect existing QRA
  records to Embry-specific spoken answers, emotions, pauses, and dynamic
  latency behavior without polluting canonical QRA facts.
