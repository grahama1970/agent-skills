# Emotion, Pause, and Interruption Policy

Use this reference when writing voice prompts, TTS chunks, or agent instructions
for Chatterbox or Chatterbox-Turbo.

## Default Voice

Default to calm, warm, and concise. Do not overperform emotion. The safest
production voice style is:

```text
neutral-warm
brief
low-to-moderate expressiveness
easy to interrupt
```

## Holding Utterances

Use holding text only while real work is pending. It must not imply the answer is
already known.

Good:

```text
"Give me five seconds to answer that. I'm checking memory first."
"Hmm. I need to think more about this."
"Hmm. I have part of it, but I want one more result."
"Hmm. Give me another second."
"I'm still here. I'm checking one more thing."
"Hold on. I have part of it."
"Give me one more second."
"Still with you."
"That's coming in now."
"I have enough to start."
"Here's what I'm seeing."
"Hold on. I need to look at the memory trail before I answer."
"One second. I'm checking the stored context and then I'll respond."
"I'm going to pause for a second while the search finishes."
"Still checking. I won't guess; I'll answer when the evidence is back."
```

Bad:

```text
"I found it."                 # if recall/search is still pending
"The answer is Kai."          # unsupported before memory grounding
"Please wait while I process."# robotic and unhelpful
"Executing skill batch four." # implementation leakage
```

Use "hmm" only as a low-buffer filler while real tasks are still pending. It
should be short, non-factual, and cancellable. Do not repeat it enough to sound
stuck.

Do not allow three seconds of perceived dead air while work is pending. The
human will read that as a crash, stalled model, or broken audio path. If the next
real progress chunk is not ready, say one short filler and keep listening for
interruptions.

Use a rotating filler list rather than repeating the same phrase. The filler
should reassure the human that Embry is still present, not expose the internal
lookup or tool state.

Runtime timing:

```text
0-700 ms: silence is acceptable.
700 ms-2 s: speak a soft filler.
2-5 s: speak a useful progress phrase.
5-8 s: say that the answer is still being shaped.
8+ s: optionally start cached hum/idle audio and duck it when speech resumes.
```

Subagent calls add latency after evidence arrives. Treat that as a separate
phase:

```text
"I have enough to start. Give me a second to shape the answer."
"Okay, I have it now."
"Here's the answer."
```

For particularly long waits, `$hum` may run as low-volume background idle audio.
It must be a separate mixer channel, must duck under speech, and must stop on
barge-in. Do not hum over the final answer.

## Progress Updates

Good:

```text
"I have the pricing. Still checking exclusions."
"I found the memory thread. I'm checking one current source."
"One source is slow, but I have enough to continue."
"That check failed, so I'm using the backup path."
```

Bad:

```text
"Task 1 finished."
"Tool returned JSON."
"Awaiting futures."
"The LLM call timed out."
"For this turn, I will drop stale chunks."
"I found memory row embry_123."
"The voice coordinator has sufficient results."
```

The voice coordinator may log technical detail in JSON events, but spoken output
should translate it into user-relevant progress.
Embry's spoken response should not include route names, memory IDs, JSON stream
details, receipt terminology, stale-chunk language, or other implementation
internals. The receipt can contain those details; the voice should communicate
pauses and answer the question.

## Emotion Tags

For Chatterbox-Turbo, use native bracketed paralinguistic tags only when the
selected model/API documents support them:

```text
"That calendar is packed [chuckle], but I found two open slots."
"I see the issue. The card expired, so the renewal failed."
"Okay [sigh], I can see why that was confusing."
```

Use `[chuckle]` only in light, user-positive moments. Use `[sigh]` rarely; it can
sound annoyed. Avoid `[laugh]`, `[whispering]`, or dramatic tags in serious,
financial, medical, legal, safety, or complaint-handling workflows.

Bad:

```text
"[sigh] Looks like your payment failed again."
"[laugh] Your claim was denied."
"<emotion name=\"angry\">That is unacceptable.</emotion>"
```

The XML emotion example is bad for Chatterbox-Turbo unless that exact API/model
contract explicitly supports it. Do not invent control tags.

## Pauses

Preferred local Chatterbox strategy:

```text
split into chunks
insert playback-layer silence
resume next chunk if turn_id is still current
```

Example:

```json
{"type":"speech.chunk","text":"I found the memory thread.","pause_after_ms":400}
{"type":"speech.chunk","text":"The important part is the boundary."}
```

Use SSML `<break>` only when the selected provider/model supports SSML:

```xml
<speak>I need a second.<break time="500ms"/>The source says Ninole is the anchor.</speak>
```

Bad:

```text
"Pause for five seconds, then answer."
"<break time=\"1s\"/>" sent to a model profile that does not support SSML.
```

## Interruption Behavior

When the user interrupts:

1. Stop or duck current playback immediately.
2. Set the old turn's cancellation token.
3. Mark queued chunks from the old turn stale.
4. Cancel pending TTS submissions if safe.
5. Preserve completed memory/search receipts.
6. Start a new `turn_id`.
7. Run memory intent and recall again for the new turn.

Good spoken acknowledgement:

```text
"Got it. I'll stop there."
"Okay, switching to your new question."
"I hear you. Let me redirect."
"Stopping that answer. Give me a second to re-check the right thread."
```

Bad:

```text
Continue speaking queued chunks from the old turn.
Summarize cancelled research as complete.
Answer the new turn with the old memory-route decision.
Delete receipts needed to explain what was interrupted.
```

## Backchannel Handling

Do not treat every sound as a hard interruption. Use VAD, echo cancellation, and
semantic signals when available.

```text
"wait", "stop", "no", "cancel" -> interrupt immediately
new question over agent speech -> interrupt immediately
"uh-huh", "yeah" -> usually continue unless intent is clear
background noise -> ignore
speaker echo -> ignore
```
