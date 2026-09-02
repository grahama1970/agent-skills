---
name: best-practices-chatterbox
description: >
  Best practices for using Chatterbox and Chatterbox Turbo as an emotional voice renderer: memory-grounded utterance planning, native paralinguistic tags, spaced ellipsis pauses, render_chunks pause_after_ms, intensity/valence routing, reference-audio selection, and retained analyzer evals. Use when coding or reviewing Chatterbox answer_text, emotional tags, tone, pause policy, Persona Dream speech, or non-robotic Embry voice quality.
triggers:
  - best practices chatterbox
  - Chatterbox emotion tags
  - Chatterbox pauses
  - Chatterbox emotional quality
  - Chatterbox non robotic voice
  - Embry voice quality
  - Chatterbox render chunks
runtime_self_improvement: basic
provides:
  - chatterbox-render-guidance
  - emotional-utterance-contract
  - pause-policy
  - voice-quality-eval-policy
composes:
  - memory
  - analyze-chatterbox-emotions
  - ops-chatterbox
  - best-practices-python
  - best-practices-skills
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - voice
  - affect
  - validation
  - precision
disciplines:
  - voice-audio
  - evaluation-quality
  - engineering-standards
---

# Best Practices: Chatterbox

Use this skill when an agent writes, reviews, or evaluates text that Chatterbox will speak.

Chatterbox is the renderer. The agent owns context, affect intent, utterance text, pause plans, receipts, and quality gates. Do not put emotion only in `voice_delivery.tone`; Chatterbox Turbo needs affect in the spoken payload and exact pauses in the render plan.

## Required pipeline

```text
clean text
  -> extract salient entities
  -> $memory recall for source context
  -> choose product affect + intensity
  -> choose Chatterbox backend/tone/tag policy
  -> write exact answer_text
  -> compile render_chunks pause_after_ms
  -> render through Chatterbox
  -> analyze with /analyze-chatterbox-emotions
  -> store JSON receipt + waveform metrics
```

Minimum planner inputs:

- clean text to speak;
- grounded source context from `$memory recall`;
- target affect label, intensity, valence, and arousal when available;
- live Chatterbox tone names, supported tag vocabulary, backend support, and reference-audio constraints.

## Tag vocabulary

Verified local Chatterbox Turbo native vocal event tags:

```text
[clear throat], [sigh], [shush], [cough], [groan], [sniff], [gasp], [chuckle], [laugh]
```

Extended tokenizer tokens may be used sparingly when the line genuinely needs them:

```text
[angry], [fear], [surprised], [whispering], [advertisement], [dramatic], [narration], [crying], [happy], [sarcastic]
```

Use tags where the vocal event belongs, usually before a breath, turn, interruption, or affect shift. Do not prefix every sentence with the same tag, and do not place a tag inside a noun phrase or immediately before a proper name.

## Text preprocessing and SSML import

Normalize renderer text before it reaches Chatterbox:

- Convert intentional markdown emphasis to vocal stress: `*cannot*` becomes `CANNOT`.
- Normalize ASCII dashes to em dashes when the dash is meant as a breath or interruption.
- Preserve explicit pause controls as `[pause:750ms]` or `[pause:1.2s]` for the pause compiler.
- Convert small SSML fragments at the boundary: `<break time="800ms"/>` becomes `[pause:800ms]`, `<emphasis>` becomes uppercase, and `<express-as type="gasp">` becomes a native inline tag.
- Reject broad SSML passthrough. Chatterbox is not an SSML engine; conversion must produce plain `answer_text` plus `render_chunks`.

Helper commands:

```bash
./run.sh preprocess --text 'I *cannot* -- [SIGH] keep pretending.'
./run.sh ssml --text '<speak>Wait <break time="800ms"/><express-as type="gasp">look out</express-as></speak>'
```

## Pause policy

Spaced ellipsis is the reliable text form:

```text
Good:  bottle rocket ... a room where grief could sit down
Bad:   bottle rocket... a room where grief could sit down
```

When a pause matters, do not rely on punctuation alone. Split the utterance into `render_chunks` and set `pause_after_ms`. `[pause:500ms]` and `[pause:1.2s]` are source-side directives that must be compiled out of `answer_text` and into chunk metadata before render:

```json
{
  "answer_text": "[sniff] [sniff] ... give me a second. This is tender, and I can keep going.",
  "render_chunks": [
    {"text": "[sniff] [sniff] ...", "pause_after_ms": 1400, "tone": "grief_safe", "role": "collect_herself"},
    {"text": "give me a second. This is tender, and I can keep going.", "pause_after_ms": 0, "tone": "grief_safe", "role": "recover"}
  ]
}
```

Compile exact silence with:

```bash
./run.sh plan-silence --text 'I need a second. [pause:1.2s] [sniff] [sniff] ... give me a second.' --tone grief_safe
```

Suggested pause bands:

| Situation | Suggested pause |
|---|---:|
| punctuation breath | 300-500 ms |
| tag reset such as `[sigh]` or `[gasp]` | 650-900 ms |
| ellipsis hesitation | 900-1100 ms |
| `[sniff] [sniff] ... give me a second` | 1200-1600 ms |
| grief/tenderness with `[crying]` | 900-1400 ms |

## Backend and parameter routing

Use the live backend contract, not generic advice.

- Chatterbox Turbo/Nano: prefer for real-time speech and native paralinguistic tags. In this environment, Turbo ignores `exaggeration` and `cfg_weight`; use inline tags and `render_chunks.pause_after_ms` for affect and pauses.
- Base affect path: use when explicit `exaggeration`, `cfg_weight`, `intensity`, or `valence` knobs are required and the backend reports support.
- Multilingual/narrative backends: use when speaker similarity, language transfer, hallucination suppression, or acoustic stability is more important than lowest latency.

Advisory starting points for backends that actually honor the knobs:

- Dramatic: `exaggeration=0.7-0.8`, `cfg_weight=0.25-0.35`.
- Conversational: `exaggeration=0.4-0.5`, `cfg_weight=0.5`.
- Fast reference speaker: lower `cfg_weight` toward `0.3` to reduce rushed cadence.
- Cross-language cloning: consider `cfg_weight=0.0` only after backend support is verified.

Sweep only when the backend exposes those parameters:

```bash
./run.sh sweep-plan \
  --backend chatterbox_base \
  --text 'I cannot believe you pulled this off! ... [gasp] That was incredible.'
```

Do not rerun the same failing prompt hoping for luck. Use the sweep manifest, render each cell once through the supported backend, run `/analyze-chatterbox-emotions`, and pick from measured pause, clipping, F0 variation, transcript similarity, and human listening notes.

## Intensity example

```json
{
  "clean_text": "This is tender. Give me a second. I can keep going.",
  "memory_context": {
    "entities": ["Kai", "bottle rocket", "glowing box"],
    "recall_summary": "Warmth feels dangerous when it becomes proof."
  },
  "target_affect": {
    "label": "tender_collecting",
    "intensity": 0.72,
    "valence": 0.15,
    "arousal": 0.32
  },
  "chatterbox": {
    "backend": "chatterbox_turbo",
    "tone": "grief_safe",
    "answer_text": "[sniff] [sniff] ... give me a second. This is tender, and I can keep going.",
    "tags": ["[sniff]", "[sigh]", "[crying]"],
    "render_chunks": [
      {"text": "[sniff] [sniff] ...", "pause_after_ms": 1400, "tone": "grief_safe", "role": "collect_herself"},
      {"text": "give me a second. This is tender, and I can keep going.", "pause_after_ms": 0, "tone": "grief_safe", "role": "recover"}
    ]
  }
}
```

## Reference audio

- Use a 5-10 second reference clip that already has the baseline affect you want.
- Prefer clips inside the `3-12` second usable window; `5-10` seconds is the normal target.
- Avoid background noise, music, reverb, clipped source audio, and long silent margins.
- Check WAV references before render for sample rate, RMS level, clipping, active-speech ratio, and energy-derived SNR.
- Keep persona reference IDs and hashes in the render receipt.

Reference gate:

```bash
./run.sh check-reference --audio reference_speaker.wav
```

Default thresholds: duration `3-12s`, clipping ratio `<=0.001`, SNR `>=18dB`, speech ratio `>=0.60`, RMS between `-35dB` and `-3dB`.

## Evaluation gate

After rendering, run `/analyze-chatterbox-emotions` or the Chatterbox retained eval case.

Minimum evidence:

- decoded waveform duration and RMS;
- clipping fraction;
- F0 median and variation;
- measured pause spans and silence ratio;
- planned-vs-measured pause comparison;
- optional ASR transcript similarity;
- JSON artifact path read back by `$agentic-evals`.

Never claim the voice is emotionally good from tags alone. A pass means the waveform and receipts match the requested voice-quality contract; human listening still decides final perceived naturalness.

## Streaming boundary

Chunked streaming is valid when the product needs low-latency playback, but it belongs in the Chatterbox service layer, not in planning code. A streaming endpoint must preserve the same contract as file renders:

- every yielded PCM chunk has declared sample rate, channel count, and format;
- chunk boundaries come from the same `render_chunks` plan used for non-streamed output;
- programmatic silence is emitted as audio samples, not as a comment in metadata;
- the final receipt still records the complete `answer_text`, chunk list, reference ID, and analyzer result.
