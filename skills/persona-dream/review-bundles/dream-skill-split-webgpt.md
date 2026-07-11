# WebGPT Review Request: Dream Ability Split From Create Movie

## Request

Return:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED
```

Question: should the persona dream ability be split out of the broad
`create-movie` workflow into a narrower skill and possibly a dedicated
`dream-director` or `movie-director` subagent?

## Current Understanding

The broad movie skill is overcomplicated for the use case we care about most.
It currently describes a full filmmaking pipeline:

```text
hardware check -> research -> script -> casting -> expert review -> generate
-> assemble -> learn
```

That is useful for full audiovisual production, but the dream/persona-memory
use case is much narrower.

The dream ability appears to be:

```text
persona memory residue
-> dream scenes
-> image/contact-sheet representation
-> short reflection
-> memory writeback
-> optional BDI/persona-state update
```

The likely simplification is that most dream output should distill down to:

```text
1. a concise dream prompt
2. a contact sheet of generated images or visual frames
3. a persona reflection
4. memory records capturing insights, mood, bridges, and residue links
```

The final MP4/movie assembly may be optional rather than the primary path.

## Source-Derived Evidence

The movie skill contract currently says it creates mockumentaries, short films,
music videos, and educational content through a phased workflow. It composes
memory, create-image, dogpile, assess, and task-monitor.

The dream implementation says:

```text
Dream Movie Orchestrator
- Fetch day residue with contradiction detection
- Generate dream scenes
- Optional dream casting
- Optional dream storyboard
- Generate global score
- Optional sound design
- Process scenes
- Assemble
- Store dream
- Dream reflection: meta-cognitive note stored to memory
- Optional quality assessment
- Optional theme enrichment
```

Important implementation facts:

```text
- Any registered persona can dream.
- Persona scope is derived automatically as persona memories, persona dreams,
  and persona dream journals.
- Day residue is fetched from persona memory.
- If no residue exists, there is no dream.
- Dream reflection writes a short stream-of-consciousness note.
- Reflection is stored to memory under the persona dream-journal scope.
- Reflection bridge tags and mood are preserved.
- BDI state may be updated with dream mood and dream bridge beliefs.
```

The current code also does expensive/full-production work:

```text
- casting
- storyboard
- score
- sound design
- video rendering
- TTS
- audio mixing
- FFmpeg assembly
```

Those are valuable for full movie creation, but not required for persona
insight extraction.

## Proposed Split

Add a narrower skill, perhaps:

```text
dream
```

or:

```text
persona-dream
```

Owned output:

```text
dream_packet.json
contact_sheet.png
dream_prompt.txt
dream_reflection.md
memory_write_receipt.json
optional_bdi_update.json
```

Core workflow:

```text
1. Recall persona day residue from memory.
2. Detect contradictions or tensions.
3. Generate a compact dream prompt and 4-12 visual frame prompts.
4. Generate a contact sheet using image generation or reuse existing image assets.
5. Ask the persona to reflect on the dream.
6. Store reflection, mood, bridge tags, and source residue ids to memory.
7. Return receipts and insight summary.
```

Full `create-movie` can remain the heavy production pipeline:

```text
script -> casting -> storyboard -> video/audio generation -> assembly
```

But it should call the dream skill when it wants persona dream residue, not own
the memory-insight loop directly.

## Persona Question

Should this require a top-level `movie-director` persona?

Candidate answers:

1. No new top-level persona. Add a `dream` or `persona-dream` skill, owned by
   an existing creative persona only when used.
2. Add top-level `dream-director`, because the work product is recurring,
   memory-writing, persona-state-shaping, and should be gated carefully.
3. Add top-level `movie-director`, but scope it broadly to `create-movie`,
   `create-storyboard`, `create-score`, `create-sound-design`, and dream.

My current leaning:

```text
Do not add broad movie-director yet.
Prefer a narrower dream/persona-dream skill.
If a persona is needed, use dream-director rather than movie-director,
because the core work product is persona insight and memory writeback, not film
production.
```

## Questions For WebGPT

1. Is the current `create-movie` skill over-scoped for the dream/persona-memory
   objective?
2. Should dream become a separate skill?
3. Should the separate skill be named `dream`, `persona-dream`, or something
   else?
4. Should there be a top-level `dream-director` or `movie-director` subagent, or
   should this remain a skill used by existing personas?
5. What are the ownership boundaries with `memory`, `create-image`,
   `create-movie`, `designer`, `reporter`, and persona profiles?
6. What minimal artifact contract should this skill produce?

Please give exact recommended persona/skill ownership and any patches needed.
