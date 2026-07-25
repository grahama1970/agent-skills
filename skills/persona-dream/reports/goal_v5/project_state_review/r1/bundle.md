# persona-dream project-state review (chatterbox usage + research goals)

You are a reviewer. Be blunt; cite real papers/repos for any research claim (no
vague name-drops); no jargon padding. Inspect the pushed commit be2a9afb on
grahama1970/agent-skills@main (skills/persona-dream).

## IMMUTABLE GOAL (do not drift)

Assess the CURRENT project state of persona-dream against exactly two axes:
  A. Functional usage in the chatterbox voice — is the dream->voice path real,
     wired, and does it actually evolve the spoken voice, or is it a demo?
  B. Research goals — where does it stand vs current expressive-TTS / persona-
     voice research, and what (if anything) is a genuine contribution vs
     engineering integration?
Anything not serving A or B is out of scope.

## BUILT + VERIFIED (from source)

- Loop: memory -> conflict-seeded dream -> watch -> first-person journal -> mood.
  Per-persona Continuity Ledger: immutable core + arc_state (one additive
  delta/cycle) + fast mood. (continuity_ledger.py, autonomous_dream_cycle.py)
- Voice bridge dream_voice_weights.py: deterministic frozen 5-row ToM ->
  (tag, tone, pace) table + temperature = 0.6 + 0.3*intensity; PLUS new
  --arc-voice (Path B): reads arc_state and generates the spoken line as the
  persona speaks now via the tau_text_reasoning adapter (routes through /tau; zero
  direct scillm), fallback-guarded to the raw dream statement. Proven live:
  fallback_used:false, line "If you're available, Kai, I'd prefer your assessment
  before I proceed." from Embry's real arc_state.
- Verified chatterbox Turbo constraints (live /presets, /synthesize): the engine
  IGNORES exaggeration and cfg_weight; tags are NOT interpreted; stage presets are
  "not validated as an affect channel"; real controls = tone, pace, delivery_stage,
  voice_delivery, temperature, top_p; a single default reference clip, no bank.

## PROPOSED / NOT built

- arc_state -> acoustic params (the exaggeration route is dead on Turbo).
- A per-persona reference-clip bank (needed for timbre/style variety).
- Audio-level proof the voice evolves (fixed-probe: same sentence cycle 0 vs N).
- Wiring --arc-voice into the default render + the chatterbox interruptible-agent
  path (best-practices-chatterbox-agent).

## Questions (answer against A and B; cite real sources)

Q1. Is the persona-dream -> chatterbox link functional usage or a demo? What is
    missing to ship an evolving-personality voice inside the chatterbox agent?
Q2. Given Turbo ignores the expressive knobs, what is the highest-value path to an
    audibly evolving voice -- reference-clip bank, the text channel (Path B), or
    an engine change -- and why?
Q3. What here is a genuine research contribution vs integration, and what concrete
    experiment would falsify "the voice evolves with the persona"?

End with: STATE (one line: is the chatterbox usage real or demo), TOP NEXT STEP
for A, TOP NEXT STEP for B, and any DISAGREEMENT with the framing above.
