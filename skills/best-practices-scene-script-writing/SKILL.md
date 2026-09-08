---
name: best-practices-scene-script-writing
description: >
  Writing standard for scene scripts and beat descriptions that feed AI video
  generation: how to describe environment, weather, lighting, and every
  character/prop interaction with concrete physical states and motion verbs so
  the persona-dream panel gate passes and rendered clips have life instead of
  static tableaus. Use when writing or reviewing a scene script, storyboard
  panel text, dream story beat, or provider prompt whose elements lack
  physical state, environmental interaction, weather, or lighting sources.
triggers:
  - scene script writing best practices
  - describe the environment and weather in this scene
  - the clip looks static add life
  - write the beat description for this shot
  - review this panel script for descriptiveness
provides:
  - scene-script-standard
  - beat-description-review
composes:
  - best-practices-cinematography
  - best-practices-kling-video
  - brave-search
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: none
---

# Scene Script Writing Best Practices

The writing layer under persona-dream's Panel Continuity Gate: that gate
REJECTS scripts whose elements lack physical state and environmental
interaction; this skill says how to WRITE scripts that pass. Paid-for origin
(2026-09-08): tea-dream clips rendered as beautiful static tableaus because
the only behavior verb in the whole prompt was "steam rising".

## Rule 1: Every named element carries a state verb

A noun without a physical state is set dressing the model may freeze or drop.
The persona-dream gate's standard, as writing practice:

- Prop: "the umbrella fabric shivers in the storm wind" — not "an umbrella".
- Surface: "tea trembles in the cups when she taps the table".
- Creature: gait + speed + attention + exit: "a Tyranid drags its bulk slowly
  through the ruins, ignoring the patio, vanishing behind a spire".
- Stillness is a choice, stated: "the banners hang dead still in the airless
  calm" — never an accident of omission.

Motion verbs carry physics: "stumbles" implies weight, "glides" implies ease.
Choose the verb for the physics you want simulated.

## Rule 2: Environment and weather are actors

Name place + time + weather + at least one FORCE acting on the scene:

- Weak: "a stormy void world".
- Strong: "void-world terrace at perpetual dusk; storm wind pushes across the
  table, purple lightning strobes the flagstones every few seconds".

The force must touch the characters (Rule 3) or it reads as a backdrop
painting.

## Rule 3: Characters interact with the environment

At least one character<->environment contact per beat: hair or clothing moved
by the named wind, breath visible in named cold, hand steadying a cup against
the named tremor, eyes narrowing at the named lightning. This is what welds
figures into the scene instead of compositing them onto it.

## Rule 4: Lighting has a source and a behavior

Per best-practices-cinematography Rule 5, light is motivated. In the script,
name the source AND its behavior: "the laptop's cyan glow flickers on their
faces; lightning overexposes the terrace for a single beat". Keep the same
sources across every beat of a scene.

## Rule 5: The slot budget (for provider-bound beats)

A beat description destined for a ~800-char video prompt allocates:

```text
1. cast + framing            (identity via refs, not prose)
2. speaker/primary action    one beat, physics-bearing verb
3. dynamic behaviors x3      (a) primary actor detail
                             (b) one foreground prop state
                             (c) one background life cue
4. environment + weather     place, time, one force
5. lighting                  source + behavior
6. negatives                 cast/text/overlay guards
```

Three specific behaviors beat ten vague ones. Do not spend behavior slots
restating identity - references carry identity.

## Rule 6: Review = the panel gate, written down

A beat description FAILS review if any of: a required element has no state
verb; weather/force named but touching nothing; unmotivated or sourceless
light; an interaction claimed that the environment cannot support; stillness
by omission; identity prose crowding out behavior slots. Repair the script
first; regenerate media only when the repaired script still requires missing
visual facts (persona-dream self-repair order).

## Worked example (tea dream, gate-compliant)

Weak (what we shipped first): "They sit at the tea table, steam rising from
teacups. Storm sky with eclipsed sphere. Tyranids in background."

Strong: "Storm wind pushes across the terrace, shivering the umbrella fabric.
Embry taps the table as she speaks - the tea trembles in both cups, steam
tearing sideways. Purple lightning strobes their faces between laptop-glow
beats. Behind them a Tyranid drags its bulk through the ruins, ignoring the
patio, vanishing behind a spire."

## Ownership

This skill owns the WRITING standard for beat/panel/scene text. The panel
gate (persona-dream) owns enforcement and receipts. Cinematography owns
camera/coverage grammar. kling-video owns provider mechanics and prompt
compilation. references/scene_element_checklist.md holds the per-element
checklist tables.
