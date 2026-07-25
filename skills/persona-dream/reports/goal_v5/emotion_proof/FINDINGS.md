# Emotion works in chatterbox — proof (as simple as possible)

**Claim proven:** emotion / conversational tone is a *real, measurable* acoustic
control in chatterbox — through the **base** `ChatterboxTTS` `exaggeration` +
`cfg_weight` params. It is **dead** through the Turbo engine persona-dream
currently renders with.

## What was done

One fixed sentence, one fixed seed (`torch.manual_seed(1234)` before every
render), sweeping **only** `exaggeration`/`cfg_weight` on base
`ChatterboxTTS.from_pretrained` (container `chatterbox-fork-agent-server`,
torch 2.6.0+cu124, CPU). Same text + same seed means the knob is the only
variable, so any acoustic delta is attributable to it.

Text: *"I already told you where I stand. Do not ask me again."*

| cond | exaggeration | cfg_weight | duration | loudness | F0 mean | F0 range |
|------|-----|-----|-------|-----------|-----|-----|
| calm | 0.3 | 0.5 | 3.92 s | **−18.41 dB** | 157 Hz | 278 Hz |
| default | 0.5 | 0.5 | 3.32 s | **−17.93 dB** | 125 Hz | 113 Hz |
| expressive | 0.8 | 0.3 | 2.76 s | **−16.49 dB** | 174 Hz | 261 Hz |
| intense | 1.2 | 0.3 | 2.96 s | **−15.41 dB** | 193 Hz | 130 Hz |

**Clean, defensible signal:**
- Loudness rises **strictly monotonically, +3.0 dB** with `exaggeration`.
- Duration **shortens** (speech rate rises) as `exaggeration` climbs 0.3→0.8.
- All four WAV SHA-256 differ → genuinely different renders.
- F0 mean/range is noisier (crude `detect_pitch_frequency`, differing voiced-frame
  counts) — loudness + duration are the load-bearing deltas, so those are what
  the claim rests on.

Verified twice, independently: the torch measurement and a stdlib
`wave`+`audioop` read-back on the pulled WAVs agree to 0.01 dB.

## Negative control (why this matters for persona-dream)

The Turbo service on `:8018` — the one the voice bridge currently calls —
**self-declares** these as dead (raw `/presets` contract in
`turbo_presets.contract.json`):

```
supported_params:     norm_loudness, repetition_penalty, temperature, top_k, top_p
ignored_turbo_params: cfg_weight, exaggeration, min_p
dedicated_tag_channel: unsupported     accepted_tags: []
```

So the emotion knobs that measurably work on the base model are exactly the ones
the wired engine throws away. That is why earlier Turbo tone-preset renders came
out acoustically identical — the engine was ignoring the affect input.

## Next step for persona-dream (the actual value)

Point the affect→voice bridge (`dream_voice_weights.py`) at a **base-ChatterboxTTS
render path** instead of the Turbo presets, and map the persona state onto the
two knobs that are now proven to move the audio:

- `arc_state` / mood **intensity** → `exaggeration` (0.3 calm … 1.2 intense)
- affect **valence** (guarded/deliberate vs open) → `cfg_weight` (~0.5 → ~0.3)

That turns the existing text-channel evolution (Path B, already live) into an
*audible* one, using controls this receipt shows are real — not the buzzword
route, the measured one.

## Reproduce

```bash
docker cp base_emotion_proof.py chatterbox-fork-agent-server:/tmp/
docker exec chatterbox-fork-agent-server /usr/bin/python3.11 /tmp/base_emotion_proof.py
```
