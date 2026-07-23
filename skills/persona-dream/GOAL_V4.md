# GOAL_V4 (immutable): dreams shape Embry's live voice

Chartered 2026-07-23 from the operator's directive to proceed with research
goal 3 ("dreams shaping her voice — the actual point of the project") under
the roundtable's unanimously converged architecture (r3, commit f11b0b4d)
and the operator's safety rule: "only color the tone with the dream — never
change a right answer."

## Primary proof

`python3 scripts/check_goal_v4_boundary.py --json` exits 0 with
`PASS_GOAL_V4_BOUNDARY`, re-driving all evidence live.

## Completion criteria

- V4.1 COMPOSER: `scripts/persona_affect_composer.py` — a pure,
  deterministic library composing (live memory /intent voice_delivery,
  dream voice-weight profile, frozen policy) -> the existing
  TauVoiceChunk/voice_delivery fields plus a composition receipt
  (situational, prior, delta, final, fallback_fired, thermal state,
  dream provenance). Frozen policy tables in-file: SAFETY tones are hard
  overrides (dream prior zeroed); EXPRESSIVE tones are dream-biased;
  DEFAULT/bland tones get the dispositional floor. Proven by a committed
  fixture probe (`scripts/probe_affect_composer.py`) covering: safety
  override, expressive bias, dispositional floor, never-change-a-right-
  answer, thermal dampening after sustained high intensity.
- V4.2 LIVE MATRIX GATE: `scripts/run_affect_matrix_probe.py` drives the
  chatterbox stress-matrix simple tone cases through the REAL path — live
  memory /intent -> composer -> live /tau/voice-render — under three
  conditions: (baseline: no composer), (dream: Embry's newest active dream
  profile), (shuffled: a maximally-distant dream profile). Gate: with the
  dream prior, the failing hostile/discouraged cases compose into their
  EXPECTED tone families while the passing frustrated/warm case stays in
  family (zero regression); the overlap case remains safety-overridden
  (composer must NOT touch it); renders return ok with audio on disk.
  The shuffled condition is recorded for direction analysis, never as a
  pass condition.
- V4.3 LOOP GUARD (before any sixth dream cycle): every composed turn's
  receipt carries dream provenance; `autonomous_dream_cycle.py` selection
  down-weights/excludes residue descended from dream-influenced turns;
  an anchor-cosine circuit breaker and per-window activation cap are
  enforced in the composer state; fixture-proven.

## Forbidden drift

- Never modify /intent's situational decision or the voice-render server.
- No "affect engine" research claims from matrix results (listener study
  remains the research endpoint, per panel dissent).
- No weakening of any GOAL_V2/V3 gate.

## Retry/stop rule
Two focused attempts per blocker, then a blocker report.
