---
name: chatterbox-speak
description: >
  Thin front door for speaking a line through the live Chatterbox service with a
  named voice, tone, context note, and emotional intensity. Use when a project
  agent says "speak", "say this out loud", "speak as embry", "chatterbox speak",
  "render this with a sigh", or wants one-shot voiced output with a receipt
  without the full embry-voice-control turn pipeline.
triggers:
  - speak this as embry
  - chatterbox speak
  - say something out loud
  - render this line with chatterbox
  - speak with high intensity
provides:
  - voice-render
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-chatterbox
runtime_self_improvement: basic
taxonomy:
  - voice-audio
---

# chatterbox-speak

One-shot speech: text + voice + tone + intensity -> live Chatterbox render ->
WAV + JSON receipt. Rendering, backend routing, tag handling, and affect
receipts are owned by the Chatterbox service (`http://127.0.0.1:8018`); this
skill only validates the request, calls `/synthesize`, validates the response,
and writes a receipt. It is NOT the conversation control plane — that is
`embry-voice-control`.

## Usage

```bash
./run.sh speak --voice embry --text 'Say something. [sigh]' \
  --context 'operator asked for a firm demo line' \
  --intensity high --tone firm_boundary --play

./run.sh voices        # list known voices and live tones
./run.sh speak --help
```

- `--voice`: named voice from the voice map (`embry` today; add entries in
  `scripts/speak.py` VOICES). Or pass `--ref-audio <container path>` directly.
- `--intensity low|medium|high` maps to 0.3 / 0.6 / 0.9. Omit it to let inline
  tags like `[sigh]` be consumed natively on turbo. Explicit intensity routes
  to the base-affect backend, which speaks tags as literal words — the receipt's
  `tag_handling` / `affect_effect` fields record which side of that tradeoff
  you got.
- `--tone`: any live calibrated tone (see `./run.sh voices`), e.g.
  `neutral_warm`, `grief_safe`, `firm_boundary`, `playful_light`.
- `--context`: caller-supplied grounding note. Stored in the receipt for audit;
  it does not change rendering. Choose tone/intensity from it yourself (see
  `$best-practices-chatterbox`).
- `--play`: local playback via `pw-play`.

Receipts and copies of the WAV go to
`/mnt/storage12tb/skills/chatterbox-speak/outputs/`.

## Boundaries

- Speaks only caller-approved text; no answer generation, memory routing, or
  wake word (use `embry-voice-control` for that).
- Fails closed when the service is down, `ok`/`live` are false, or the WAV is
  missing/unreadable; errors carry the service's Pydantic-style detail.
- Waveform quality judgment stays with `/analyze-chatterbox-emotions`.
