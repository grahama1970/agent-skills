# Validation Checklist

Use this checklist before claiming a Chatterbox voice-agent path works.

## Required Receipts

Each turn should produce:

```text
request.json
memory-intent.json
memory-recall.json
memory-route-decision.json
task-events.jsonl
speakable-chunks.json
tts-submissions.jsonl
audio-artifacts.json
interruption-events.jsonl, when applicable
final-response.json
optional-asr-verification.json
```

## Evidence Gates

Pass only when all relevant gates have concrete artifacts:

```text
turn_id present on every event
old-turn chunks skipped after interruption
memory intent ran before recall
answer/clarify/deflect route recorded
used_memory_ids are present for factual memory answers
spoken text hash equals TTS submitted text hash
audio artifacts exist and are non-empty
ASR anchors pass when semantic audio fidelity is being judged
no raw user control tags reached TTS
no stale results from old turns were spoken
no pending-work silence gap exceeded 3 seconds without filler/progress speech
long text-reasoner/subagent wait had a filler, transition phrase, or optional hum
hum, if used, ducked or stopped before answer speech
```

## Live vs Mocked

Mocked tests prove wiring only. For voice behavior, require at least one live or
local model run before claiming the path works:

```text
mocked: yes|no
live: yes|no
worker_url or provider endpoint
audio_artifact path
ffprobe duration
text_sha256
tts_submitted_text_sha256
interruption evidence, if tested
```

## Latency Measurements

Measure warm-path latency separately from cold start:

```text
cold_model_load_s
first_synthesis_after_start_s
warm_generation_median_s
warm_roundtrip_median_s
audio_duration_s
real_time_factor
```

Do not mix cold model load into warm response latency.

## Failure Modes To Test

```text
generic greeting instead of answer
holding utterance claims answer before evidence
long monologue cannot be interrupted
queued stale chunks spoken after interruption
memory recall empty
memory route requires clarify
memory route requires deflect
Brave/search timeout
TTS worker exception
emotion tag read aloud
SSML pause ignored or spoken literally
ASR misses required factual anchors
```

## Recommendation Rule

If the voice quality is acceptable but interruption or grounding fails, recommend
fixing the coordinator/receipts, not changing the TTS model.

If the coordinator/receipts pass but audio is unintelligible, recommend a model,
reference audio, or synthesis-parameter bakeoff.

If both fail, stop expanding features and return to the smallest live turn:

```text
one user turn
one memory recall
one holding utterance
one final answer chunk
one interruption test
one receipt bundle
```
