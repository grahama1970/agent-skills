# persona-dream roundtable 4, round 1 — have the research goals been met, and what next?

You are one of three collaborating seats (ChatGPT, Claude, Kimi) on a standing
panel for the persona-dream project. This is a COLLABORATION, not a
competition: every seat receives this identical bundle (full context + research
brief). Prior panels: your r3 architecture (composer shim between /intent and
voice-render; never repair /intent; matrix gate with shuffled-dream control;
blinded listener study as research endpoint) was adopted and is now built and
live-tested. Bring your distinctive strengths — sampling statistics and
oracle thinking, contract-freezing and fixture discipline, operational
enforcement and diffability — wherever they apply.

## What persona-dream is (operator-fixed purpose)

Dreams are the affect engine for Embry, an agent voice persona:
experience → memory residue → autonomous dream (image-grounded, ArcFace-gated)
→ ToM states → dream voice-weight profile → composed conversational tone and
emotion tags in the Chatterbox voice runtime. The human never judges the dream
content; what matters is (a) the pipeline is reliable, (b) the dream is
accurate given experience, (c) the dream measurably nuances the voice.
Operator safety rule: "only color the tone with the dream — never change a
right answer."

## State since your r3 (all VERIFIED, committed at agent-skills@main 7ca7bd26)

1. GOAL_V4 COMPLETE, checker re-drives everything live and passes:
   - persona_affect_composer.v1: pure shim. SAFETY tones hard-override (dream
     prior zeroed); EXPRESSIVE tones colored within their situational family;
     bland/DEFAULT tones get the dream's dispositional floor; unknown labels
     pass through untouched; thermal limiter (>0.6 intensity ×3 turns → 0.8
     damping ×5 turns); every receipt carries dream provenance.
   - Live matrix gate: real memory /intent → composer → real /tau/voice-render
     on 4 stress-matrix tone cases, dream vs shuffled-dream control; composer
     never leaves the situational family; upstream /intent drift recorded as a
     finding, never repaired locally (your dissent, honored).
   - Loop guard: dream-colored residue is excluded from future dream selection
     (the agent never dreams about its own dream-colored words).
   - best-practices contract compliance: if /intent returns NO voice policy,
     the composer fails closed to memory_uncertain +
     cue_policy=intent_missing_voice_delivery_policy (dream floor suppressed).

2. NEW VERIFIED FACT — closed tone vocabulary. Chatterbox's agent presets
   (`presets.py`) define ALLOWED_TONES: exactly 15 tones; `normalize_tone()`
   silently converts anything else to neutral_warm. Tone reaches sound only
   as tone → delivery stage → sampling preset (temperature 0.70–0.90, top_p,
   top_k, repetition_penalty). GOAL_V4 Amendment 1 remapped every composer
   output onto ALLOWED_TONES (fixture probe now parses ALLOWED_TONES from the
   chatterbox file on disk and asserts vocabulary compliance — 9/9 pass).

3. NEW VERIFIED FACT — the emotion knob is gone on Turbo.
   `TURBO_IGNORED_PARAMS = {"exaggeration", "cfg_weight", "min_p"}`: the
   classic Chatterbox emotion-exaggeration parameter is rejected by the Turbo
   runtime Embry uses. Synthesis-side affect = sampling presets only.
   Deterministic levers that DO exist: pace, pause_strategy, pause_after_ms,
   text-side phrasing, and a `chatterbox_tags` field (audibility on Turbo
   unverified).

4. NEW MEASUREMENT — n=5 four-arm acoustic probe (same sentence, live
   /tau/voice-render; arms: flat / static memory_confident / dream-composed
   firm_boundary (marketa boundary 0.52) / wrong-dream calm_precise (tommy
   reflection); calm_precise maps to the neutral stage = sampling params
   IDENTICAL to flat, making the wrong arm a same-parameter control):

   medians (5 renders/arm): f0_mean flat 229.1 / static 212.7 / dream 226.4 /
   wrong 202.7 Hz; f0_sd 47.1 / 39.7 / 52.6 / 36.2 Hz; f0_range 118.8 / 103.8
   / 148.1 / 80.2 Hz; duration 4.60 / 4.84 / 4.76 / 4.60 s.
   Same-parameter single-render spreads (flat arm): f0_mean 31.6 Hz, f0_sd
   21.2 Hz, f0_range 60.9 Hz, duration 1.36 s. The parameter-identical flat
   and wrong arms differ by 26.4 Hz in median f0_mean.

   FINDING (supersedes the earlier single-render reading): at n=5, NO arm's
   median shift vs flat exceeds same-parameter render-to-render variance on
   any metric. The stage-preset deltas are acoustically weak relative to
   Turbo's synthesis stochasticity on a single sentence. The dream→tone
   selection pipeline works end to end, but the realization mechanism
   (sampling presets) is the bottleneck: dream-weight tuning at the
   tone-selection layer currently cannot produce a measurable prosodic
   effect, let alone a perceivable one.

## Research brief (fresh, 2026-07-23, Brave; identical for all seats)

Competitors / state of the art in emotional agent voice:
- ElevenLabs Eleven v3 "Audio Tags": inline text tags ([whispers], tension,
  hesitation, relief) steering expressiveness; text-to-dialogue with matching
  prosody. https://elevenlabs.io/blog/v3-audiotags
- Hume Octave 2: "reads for meaning and adapts delivery without tags" —
  emotion inferred from semantic content, no explicit tag channel; widely
  ranked the emotion leader. (MarkTechPost TTS benchmark 2026-05-30;
  SurePrompts model comparison 2026.)
- OpenAI TTS: leads on "instructable voice character" (natural-language
  delivery instructions). Cartesia: latency leader. Gemini 3.1 Flash TTS:
  scene direction + per-speaker control. Sesame CSM: open conversational
  speech model.
- Practitioner routing guidance (Coval 2026): route "emotionally complex
  moments" to Hume/realtime-class models, premium branded moments to
  ElevenLabs-class, cheap menus to commodity TTS.

Relevant arxiv lines:
- Task-vector arithmetic on speaker embeddings for emotional expressivity in
  LM-TTS (arxiv 2606.05367): emotion is latently present in speaker
  embeddings; embedding-only manipulation raised intended-emotion recognition
  from 9.8% to 57.9% without retraining.
- Sparse autoencoders for interpretable emotion control in TTS (2606.01479).
- Emo-DPO: controllable emotional TTS via direct preference optimization
  (2409.10157).
- Controllable speech synthesis in the LLM era — systematic survey
  (2412.06602).
- AffectSpeech: large-scale emotional speech dataset with fine-grained
  textual descriptions (2604.04160).
- Dynamic Affective Memory Management for Personalized LLM Agents
  (2510.27418) — affect state persisted and managed in agent memory, adjacent
  to persona-dream's memory→affect pipeline.

## Questions for this round (answer all four; be concrete)

Q1 — RESEARCH GOALS: Given the above, which persona-dream research goals are
MET, PARTIALLY MET, or OPEN? The claimed chain is: reliable dream pipeline
(met?), experience-accurate dreams (met?), dreams→voice weights→composed tone
through the real runtime (met?), measurable acoustic effect (now known NOT
met at the realization layer), perceived affect by listeners (untested; was
your agreed research endpoint). Give a defensible verdict per link.

Q2 — PRACTICAL EMOTION INJECTION: With exaggeration/cfg_weight rejected by
Turbo and sampling presets measured as sub-variance, what is the right
mechanism to make dream-derived affect AUDIBLE in chatterbox? Options on the
table (rank, add, or refute): (a) widen stage-preset separation
(chatterbox-side change), (b) exploit the deterministic levers — pace,
pause_strategy, pause_after_ms, sentence-level phrasing/wording within the
approved answer, (c) test `chatterbox_tags` / inline paralinguistic text tags
on Turbo for audibility, (d) reference-audio or embedding-space conditioning
per the task-vector paper (requires model access), (e) switch or hybridize
the renderer for emotionally-loaded turns (competitor pattern: route
emotional moments to an emotion-capable model). Respect the boundary: /intent
and the voice-render server are not persona-dream's to modify — chatterbox
changes must be filed as chatterbox work.

Q3 — POSITIONING: Competitors condition emotion per-utterance (tags,
instructions, or semantic inference). persona-dream's bet is DISPOSITIONAL
affect: a persistent, memory-grounded emotional prior from the agent's own
experience, composed safely with situational policy. Is that a real
differentiator worth pursuing, and what would demonstrate it (e.g. blinded
listeners detecting a consistent disposition ACROSS turns rather than
per-utterance emotion)? What should the next goal charter (GOAL_V5) be?

Q4 — EVIDENCE BAR: What evidence would change your mind on Q1–Q3, and what is
the cheapest experiment that produces it?

End with: POSITION SUMMARY (5 bullets max) and DISAGREEMENTS (anything in
this bundle's framing you reject).

---

For transport verification, answer the request normally, then append a final
line containing only this exact marker:

<<<CLAUDE_DONE:20260723T144038Z:0c97077c>>>

The marker must be the last line of your answer.
