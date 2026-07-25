# Peer review of persona-dream -> chatterbox voice

You are a peer reviewer. Be blunt, disagree with the design and with each other,
cite real sources for any research claim (no vague name-drops). Do not pad with
jargon.

## IMMUTABLE GOAL (do not drift from this)

Critique persona-dream and give the ONE next step you would prioritize, judged
against TWO goals only:
  G1. alignment with current, verifiable research (voice/persona/expressive TTS).
  G2. usefully EVOLVING THE PERSONALITY of the chatterbox voice.
A next step that does not move G1 or G2 is out of scope.

## What persona-dream is (from source; this is the object under review)

- A persona (system prompt + its recalled memories) runs a cycle:
  memory -> conflict-seeded dream -> "watch" the dream -> first-person journal
  -> a mood. Runs for any persona (Embry, Horus) from its own corpus.
- A Continuity Ledger per persona: an immutable core + an arc_state that gains
  ONE additive delta each cycle + a fast mood. This is the part that ACCUMULATES
  change over time.
- The voice bridge (scripts/dream_voice_weights.py, live): it reads the latest
  dream's theory-of-mind states and maps them through a FROZEN 5-row table:
    desire->yearning, trust->warmth, stance->boundary, uncertainty->hesitance,
    else->reflection, each to a fixed (emotion_tag, tone, pace).
  weight = mean emotional intensity; synth temperature = 0.6 + 0.3*intensity.
  It then speaks a line via the chatterbox /synthesize service (port 8018).

## Known gaps the maintainer already sees (confirm, correct, or add to these)

1. The voice can only pick among 5 fixed tones; its expressive range is
   hard-coded, so it modulates intensity but does not truly evolve.
2. arc_state (the accumulated, evolving self) is NOT fed to the voice bridge --
   the voice reflects today's dream, never the accumulated character.
3. The map is static: nothing about the voice changes as the persona changes.

## Questions (answer all, briefly, no filler)

Q1. Critique persona-dream against G1 and G2. What is genuinely weak or missing
    for evolving a voice personality? Where does it stand vs current research
    (cite specific papers/repos you can name)?
Q2. Give the ONE next step you would prioritize to move G1 and G2, and why that
    one. Be concrete about what changes in the code/data, not the vibe.
Q3. What would show it worked -- a concrete check a human could hear or measure?

End with: TOP RECOMMENDATION (one line), and any DISAGREEMENT with the gaps above
or with another reviewer.
