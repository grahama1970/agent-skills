---
name: analyze-chatterbox-emotions
description: >
  Evaluate generated Chatterbox voice files as voice-quality artifacts: affect match, arousal/valence proxies, pause placement, intelligibility inputs, clipping, loudness, and discontinuity flags. Use when reviewing Chatterbox emotional tags, pauses, Turbo/base affect delivery, Persona Dream utterance renders, or whether generated speech matches an intended product-facing affect.
triggers:
  - analyze Chatterbox emotions
  - evaluate Chatterbox voice
  - Chatterbox pause analysis
  - Chatterbox affect match
  - voice quality evaluation
  - analyze emotional TTS
runtime_self_improvement: basic
provides:
  - voice-quality-evaluation
  - chatterbox-affect-analysis
  - pause-placement-analysis
  - audio-artifact-checks
composes:
  - ops-chatterbox
  - triage-error
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - precision
  - validation
  - affect
  - voice-audio
disciplines:
  - voice-audio
  - evaluation-quality
---

# analyze-chatterbox-emotions

Evaluate a generated Chatterbox render as a **voice-quality artifact**, not as a claim about the speaker's real emotion.

Use this when a Chatterbox or Persona Dream render needs proof that emotional tags, pauses, pace, and audio quality behaved as requested.

## Contract

Input:

```bash
./run.sh analyze --audio path/to/render.wav \
  --expected-text "optional source text" \
  --target-label reassuring \
  --target-arousal 0.35 \
  --target-valence 0.4 \
  --out /tmp/chatterbox_voice_eval.json \
  --report /tmp/chatterbox_voice_eval.md
```

Output JSON schema: `analyze_chatterbox_emotions.voice_eval.v1`.

The evaluator reports:

- `affect`: target label plus acoustic arousal/valence proxies and a compatibility score.
- `prosody`: duration, estimated speech rate, RMS/loudness proxy, F0 estimates when available.
- `pauses`: silence ratio, detected pause spans, and planned-vs-measured pause comparison when a Chatterbox render plan or conversation turn is supplied.
- `quality`: clipping, peak amplitude, discontinuity flags, and low-signal warnings.
- `intelligibility`: expected-text word count and optional transcript fields; this skill does not silently invent ASR.

## Optional inputs

- `--render-plan path.json`: Chatterbox `render_plan.json`, Persona Dream journal receipt, dynamic conversation receipt, or a conversation turn JSON carrying `chatterbox_pause_plan`.
- `--transcript "text"`: caller-supplied ASR transcript. If omitted, transcript similarity is `null` and listed as a non-claim.

## Verdicts

- `pass`: no hard technical failures and score >= 75.
- `review`: score 50-74 or important missing evidence such as no ASR transcript.
- `fail`: hard technical issue, unusable audio, severe clipping, missing audio, or score < 50.

The score is a weighted evaluation signal, not ground truth:

```text
0.35 affect_match + 0.25 intelligibility + 0.20 prosody + 0.20 technical_quality
```

## Important boundaries

- Do not say the person or persona "is sad/angry/happy". Say the waveform and available classifiers/proxies are compatible or incompatible with the requested target.
- Speech-emotion recognition models are optional signals. If unavailable, this skill still emits acoustic proxy metrics and records `emotion_classifier.available=false`.
- Exact pauses are verified from the waveform when possible; `pause_after_ms` in a render plan is only the requested pause.

## Maintenance

Run:

```bash
./sanity.sh
../agentic-evals/run.sh run fixtures/agentic_eval.json --output /tmp/analyze-chatterbox-emotions-agentic-eval.json
```
