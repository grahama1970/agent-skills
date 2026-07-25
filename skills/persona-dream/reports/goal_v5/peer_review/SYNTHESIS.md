# Peer review of persona-dream -> chatterbox voice — synthesis

Panel: ChatGPT, Claude, Kimi, Grok (live, 2026-07-25). Immutable goal the panel
was held to: critique persona-dream + give ONE next step, judged only against
G1 (alignment with verifiable voice/TTS research) and G2 (evolving the chatterbox
voice's personality). Object under review stated from source (the real
`dream_voice_weights.py` bridge). Raw seat captures in `r1/`.

Citations below are the panel's; the ONE claim that changes the code was
independently verified (see "Verified" line).

## The critique — all four converged, unprompted

1. **The frozen 5-row table is the wrong shape, not just too small.** Replacing 5
   labels with 50 is still a lookup table. Current controllable-TTS treats style
   as continuous/compositional and separates it from timbre. Cited: GST (Wang et
   al., ICML 2018, arXiv 1803.09017) — Claude; IndexTTS2 / FlexiVoice / P2VA —
   ChatGPT; Fish Audio S2/S2.1, CosyVoice 2, IndexTTS2 — Grok; Lux et al. 2023
   (navigable speaker embeddings), Mohanty 2026 (continuous prosody dims) — Kimi.
   (These are the panel's citations, not independently verified by me.)

2. **The bridge drives the wrong knob.** It scales `temperature` with intensity
   and emits `(emotion_tag, tone, pace)`. **VERIFIED against
   `chatterbox/multilingual_app.py:185,202`:** expressiveness is the
   `exaggeration` parameter (0.25–2.0, neutral 0.5); `temperature` is sampling
   randomness; there is no native "pace" or categorical-emotion input (pace is a
   side effect of `cfg_weight`). So "more intensity" currently renders as "more
   randomly pronounced," and `emotion_tag`/`tone`/`pace` have no landing spot
   unless converted to `exaggeration`/`cfg_weight` or into the text. (Claude +
   ChatGPT; Kimi: retire `temperature` — "intensity is the least interesting
   dimension; a cynical character speaks *differently*, not just hotter.")

3. **arc_state is not fed to the voice, so the voice literally cannot evolve —
   this is THE G2 gap (all four).** The bridge is a pure function of the latest
   dream. "A later Embry with twenty earned arc deltas is acoustically
   indistinguishable from early Embry" (ChatGPT). The ledger already has the right
   structure; it just isn't mirrored into voice-parameter space.

4. **The richest expressive lever is unused: the text line itself.** Chatterbox
   reads emphasis from the text/capitalization; the persona already writes the
   journal line, but it's not used to shape delivery (Claude, ChatGPT).

## The ONE next step — all four converged

**Feed arc_state into the voice as a slow-moving baseline; make the latest dream a
bounded deviation around it; route to the correct knobs.** Concretely, in
`dream_voice_weights.py`:

- `baseline = EMA/summary of arc_state` → sets `base_exaggeration`, `base_cfg`;
  the immutable core sets the reference voice + floor/ceiling.
- `param = clamp(baseline(arc_state) + Δ(today's dream) + mood_offset)`.
- Route intensity → **exaggeration**, deliberateness/pace → **cfg_weight**; stop
  using temperature as the emotion dial.
- (Stretch, same step) let arc_state also bias the generated line's wording /
  emphasis, and/or pick the nearest clip from a small curated Embry anchor bank
  (ChatGPT's timbre/style separation).

Why this one: it's the smallest change that makes the *accumulated* character
audible (the only thing that moves G2) while fixing the knob routing (moves G1).
No new model, no training. Grok: a 5-dim EMA written back to the ledger + one file
read. Claude: baseline+deviation in param space. Kimi: continuous/prompt-based
control fed by arc_state. ChatGPT: `clamp(core + accumulated_arc_voice + mood)` →
nearest anchor clip → synth with exaggeration/cfg_weight.

## How to prove it worked — converged

**Fixed-probe test:** synthesize ONE content-neutral sentence at cycle 0 and after
N cycles, changing only the ledger. Then:
- parametric: do exaggeration/cfg drift monotonically with an arc_state statistic?
- acoustic: pitch mean/range + speaking rate + distance in a speech-emotion
  embedding (wav2vec2/HuBERT SER) between cycle-0 and cycle-N renders of the same
  words.
- causal: ablate the arc_state term → renders collapse back to identical (if not,
  the "evolution" was noise).
- human: ABX — can a listener order early vs late renders in the arc's direction
  (wearier / more guarded / more confident) above chance?

Grok: cycles 1/5/12. Claude: cycle 0 vs N + ablation. ChatGPT: closed-loop logging
of requested vs realized acoustics.

## One safety addition (Kimi)

If the TTS style is generated from persona state, the persona can prosodically
"smuggle attitude" the frozen gate blocks in text — so the gate must extend to
style-param generation: the persona cannot produce a style that contradicts the
factual content.

## Honest status of the research

The Chatterbox knob claim (#2) is verified in the real code. The TTS-research
citations (GST, IndexTTS2, FlexiVoice, P2VA, CosyVoice2, Fish S2, Lux 2023,
Mohanty 2026) are the panel's and are NOT yet independently verified — worth a
direct arxiv/github check before any of them is stated as fact or cited in code
comments.
