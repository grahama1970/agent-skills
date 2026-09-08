---
name: best-practices-cinematography
description: >
  Cinematography grammar for AI-generated video scenes: dialogue coverage
  (shot/reverse-shot, 180-degree rule, eyeline direction), framing vocabulary,
  motivated lighting, lens/equipment language, and the AI-specific failure
  modes that break scenes (over-shoulder shots spawning extra bodies, eyeline
  flips, unmotivated light). Use when composing or reviewing shot prompts for
  Kling/Wan/any video model, when planning storyboard coverage for a dialogue
  scene, when a generated shot violates film grammar, or when persona-dream
  needs look-lock/shot-bible direction.
triggers:
  - cinematography best practices
  - shot reverse shot coverage
  - 180 degree rule eyeline
  - how to frame this dialogue scene
  - lighting for this shot
  - over the shoulder shot broken
provides:
  - shot-grammar-rules
  - coverage-planning
composes:
  - best-practices-kling-video
  - brave-search
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: none
---

# Cinematography Best Practices (AI video)

Film grammar that survives contact with generative video models. Every rule
here is either standard craft (sourced) or a paid-for AI failure mode (dated).
`references/shot_grammar.md` holds the full vocabulary tables; this file is
the decision layer.

## Rule 1: Coverage before prompts

A dialogue scene is a COVERAGE PLAN, not a pile of clips:

1. **Master/establishing shot first** — one wide two-shot that anchors the
   set, character positions, and lighting ("digital backlot"). Every closer
   shot derives from it (chain via last-frame or reuse its refs).
2. **Then singles**: one clip per speaking beat, shot/reverse-shot.
3. The cut carries conversational rhythm. A static two-shot where both
   characters talk in one frame is the weaker form; reserve it for beats that
   dramatically need both faces reacting mid-line.

## Rule 2: The 180-degree line and eyelines

Pick the axis once (who is screen-left, who is screen-right in the master)
and never cross it inside a scene:

- Character on the LEFT faces **camera-right**; character on the RIGHT faces
  **camera-left**, in every single. Say it explicitly in the prompt —
  "facing camera-right" — because AI models flip eyelines freely otherwise.
- Matched framing sizes across the shot/reverse-shot pair (both medium
  close-ups, not one MCU and one wide).
- Looking room: leave frame space on the side the character faces.

Violations to reject in review: eyeline both facing the same screen
direction; a reverse shot framed at a different size; a character who swapped
screen sides between clips.

## Rule 3: Over-the-shoulder shots — bind the shoulder

AI-specific, paid for 2026-09-08: prompting "X seen from behind" while X is
also described at the table SPAWNS A THIRD PERSON (run
kling-tea-DIALOGUE-20260908T103128: a generic coated man appeared as the
foreground shoulder while armored Horus still sat at the table).

- Describe the foreground mass as a BODY PART of the named element with its
  signature costume: "the near foreground is @Element2's massive black-and-
  gold armored pauldron, softly out of focus - the SAME warrior seen from
  behind".
- Negative-prompt the failure: "extra person, third person, man in coat,
  civilian clothing foreground".
- Keep the closed cast line ("exactly two people; no one else present").

## Rule 4: One beat per clip, speaker favored

- Each 5-7s clip carries ONE action/speaking beat.
- Frame the speaker favored: face toward camera, mouth clearly visible (the
  lipsync pass needs it, and so does the audience). The listener reacts in
  profile or as the bound over-shoulder mass.
- End beats with a closed-mouth state ("after speaking she smiles, mouth
  closed") so lipsync passes have no silent re-talk tail.

## Rule 5: Motivated lighting only

Light must appear to come from something in the world (window, lamp, sky,
screen glow). Unmotivated glamour light reads as AI slop.

- Name the practical source in the prompt: "lit by the glowing laptop screen
  and the purple storm sky".
- Keep the source consistent across every clip in the scene (same key
  direction; chain refs carry it).
- Match light hardness to tone: soft/diffused for intimacy, hard for tension.
- Review rejection: shadows contradicting the named source, or key direction
  flipping between shot and reverse-shot.

## Rule 6: Lens and camera language

Models respond to lens/movement vocabulary; use it deliberately, one term per
slot (see references for the full table):

- Intimacy: "85mm portrait compression, shallow depth of field".
- Isolation/scale: "wide 24mm, figure small in frame".
- Movement earns its keep or stays out: "static", "slow push-in", "slow
  lateral drift". Never stack movements; never "epic sweeping drone shot"
  for a conversation.

## Rule 7: Review against grammar, not vibes

A generated clip fails cinematography review if ANY of: crossed axis, flipped
eyeline, mismatched shot-pair sizes, spawned extra body, unmotivated key
light, speaker's mouth not visible on a speaking beat, more than one action
beat, or movement that fights the emotional register. Reject and regenerate
with ONE variable changed (audit discipline from best-practices-kling-video
Rule 6).

## Ownership

This skill owns grammar rules and review criteria. Provider mechanics
(endpoints, elements, lipsync, chaining) belong to best-practices-kling-video.
Full production (score, editing, long-form) belongs to create-movie. The
persona-dream look-lock/script-DNA/shot-bible artifacts should cite rules from
this skill rather than restating them.
