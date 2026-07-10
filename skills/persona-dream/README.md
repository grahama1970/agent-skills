# Persona Dream

![Persona Dream card](../../docs/assets/project-cards/persona-dream.webp)

**Can an AI persona dream about what has happened to it, watch the dream it
made, learn from it, and still remain recognizably itself?**

Persona Dream is a research project for persistent multimodal voice personas.
It recalls grounded memories and present events, turns them into a synthetic
dream, optionally renders that dream as image, audio, or video, and then asks the
persona to examine what was actually created. The purpose is not merely to make
a movie. The purpose is to test whether a bounded synthetic experience can
become useful memory and enrich later Theory-of-Mind reasoning.

The durable result should be a synthetic dream memory whose conclusions remain
linked to the text, images, sounds, video, code activity, relationships, and
observed scenes that produced them. A dream may influence future reasoning, but
it must never be silently promoted into literal history or an unreviewed rewrite
of the persona's identity.

> [`SKILL.md`](SKILL.md) is the current runtime contract. This README explains
> the founding research purpose, the wider architecture, the current proof
> boundary, and the intended closed loop. The implemented runtime remains
> narrower than the complete research system described here.

## Why This Matters

Most agent-memory systems can retrieve facts and prior episodes. They do not give
a persistent persona a controlled way to combine emotionally important
experiences, externalize them, inspect the result, and carry a grounded
interpretation forward.

Persona Dream explores that missing middle. A persona might use a dream to
rehearse a difficult relationship, connect a present event to an older memory,
or surface a conflict it could not express directly. The dream is synthetic, but
its effect on the agent's later reasoning can still be meaningful—provided every
step preserves provenance, uncertainty, and the distinction between imagination
and history.

The same architecture could eventually support persistent companions, game
characters, simulation agents, and other long-lived systems that need to adapt
without losing continuity or inventing a false past.

## Current State

Persona Dream is an advanced research prototype and a substantial Tau hardening
workload. It is not yet a completed personality-evolution product.

| Boundary | Current state |
|---|---|
| Grounded dream packets | Implemented with source links, contradiction reports, reflections, and receipts |
| Image and storyboard production | Live image-generation, visual-review, creator/reviewer, repair, and accepted-frame slices exist |
| Phase 08 Media Lock | Implemented as a stable local boundary over accepted storyboard evidence |
| Phase 09 Video Provider | Provider-neutral scene classification, ranking, and dry-run provider-packet work exist |
| Phase 10 Provider Contract | A fixture-backed local dry-run rung has been proven in current development work; it does not prove live fal.ai compatibility |
| Live provider submit and return | Not authorized and not proven |
| Watch → interpretation → Memory loop | Architected, but not yet proven as one closed acceptance path |
| Later persona behavior | Not yet proven to use a persisted dream while preserving identity |

The interface screenshots below come from an archived Embry/Kai run. That run
has not been regenerated with every newer provider artifact. A fail-closed
screenshot therefore describes the selected run root, not the full set of local
development capabilities.

Provider selection is near the end of the current media-production spine. It is
not the end of the founding research experiment.

## Founding Research Question

Can a persona with a Chatterbox-rendered voice:

1. recall emotionally salient past memories and relevant present events;
2. combine text, images, audio, video, relationships, and project or code
   activity into a synthetic dream;
3. render the dream into inspectable multimodal media;
4. use [`watch`](../watch/SKILL.md) to observe what the generated dream actually
   contains rather than assuming the renderer followed the prompt;
5. interpret those observations against its existing memories and persona
   state;
6. persist grounded Theory-of-Mind tags, graph edges, multimodal embeddings, and
   an explicitly synthetic dream memory; and
7. use that dream appropriately in later reasoning and conversation without
   confusing it with a literal historical event?

The experiment succeeds only when the dream can affect future recall or
behavior while the persona remains recognizably itself.

## How a Dream Works

```text
create-persona
  canonical persona, identity invariants, voice profile, simulacrum tests
        |
        v
memory + graph-memory-operator
  past memories + present events + text/image/audio/video/code activity
  + Theory-of-Mind state + emotional intensity + graph relationships
        |
        v
persona-dream
  residue selection -> dream synthesis -> optional media production
        |
        v
watch
  frames + transcript + sound + scenes + visible evidence
        |
        v
persona self-interpretation
  intended dream vs observed dream + source-memory grounding
        |
        v
memory + graph-memory-operator
  synthetic dream memory + ToM tags/edges + Qdrant multimodal embeddings
        |
        v
future persona recall, reasoning, conversation, and Chatterbox expression
```

The ordinary experience should eventually be simple: a persona says `dream`, or
`dream about Kai and the surf trip`, and the system performs the grounded loop
behind the scenes. React Flow is an optional human inspection and correction
surface, not a prerequisite for autonomous dreaming.

## Keep the Evidence Classes Separate

The most important safety and research rule is that one kind of evidence must
not silently become another.

| Evidence class | What it means | Owning boundary |
|---|---|---|
| Historical memory or present event | Something stored or observed as part of the persona's real history | Memory / Graph Memory |
| Dream intention | What Persona Dream planned, scripted, or asked a renderer to create | Persona Dream |
| Rendered dream observation | What is actually visible, audible, or temporally present in the returned media | `watch` |
| Persona interpretation | What the persona tentatively thinks the observed dream may mean | Persona Dream interpretation gate |
| Theory-of-Mind inference | A validated candidate belief, fear, desire, trust state, stance, or relationship update | Memory / ToM validation |
| Durable persona change | A promoted change to canonical goals, concerns, worldview, identity, or voice profile | `create-persona` |

For example, if the script asks Kai to answer Embry but the generated video drops
Kai from the final scene, `watch` may report that Kai is absent. Persona Dream
may tentatively interpret that absence as uncertainty about whether Embry's
boundaries will be respected. It must also preserve the alternative explanation
that the renderer simply failed to maintain character continuity.

A dream-derived record should therefore retain facts such as:

```json
{
  "synthetic_origin": true,
  "literal_historical_event": false
}
```

There must be no direct path from a renderer defect to a durable personality
rewrite.

## Pipeline at a Glance

### Current media-production spine

| Phase | Purpose | Status |
|---|---|---|
| 01 — Idea and Memory Residue | Capture the creative directive and inspect grounded multimodal recall | Implemented; D3 graph exploration exists |
| 02 — Story | Turn accepted residue into a story and interaction model | Implemented planning and generation slices |
| 03 — Crew | Select producer, scriptwriter, and director authority | Implemented sequential selection and contract work |
| 04 — Contact Sheets | Lock character, prop, and environment references | Implemented with live assets; still an active hardening area |
| 05 — Voices | Inspect reference voices and plan voice identity boundaries | Audition and planning surface exists |
| 06 — Script | Generate and review screenplay evidence from accepted upstream material | Implemented creator/reviewer contract work |
| 07 — Storyboard | Produce and review panels, start/end frames, and continuity evidence | Accepted frame evidence exists in local receipts |
| 08 — Media Lock | Freeze the accepted provider-facing frame subset, roles, dimensions, and hashes | Implemented |
| 09 — Video Provider | Rank providers and create a provider-specific dry-run packet | Local dry-run routing exists; no live provider claim |
| 10 — Provider Contract | Compile an inspectable request contract, field mapping, cost/entitlement plan, and async plan | Fixture-backed local dry-run proof; no network or provider call |
| 11 — Submit and Return | Authorize one paid call, submit, poll or receive callback, download, and validate media | Blocked pending explicit proof and approval |

### Research loop after provider return

| Stage | Purpose | Status |
|---|---|---|
| Watch observation | Extract frames, transcript, sound, scenes, visible facts, and coverage gaps from the actual returned dream | Not yet integrated into one closed run |
| Self-interpretation | Compare dream intention, Watch evidence, source memories, and current persona state | Not yet proven |
| ToM validation | Accept or reject bounded beliefs, fears, desires, trust states, and relationship candidates | Not yet proven |
| Memory and embedding persistence | Write the synthetic dream, graph edges, and Qdrant multimodal points through the owning Memory layer | Not yet proven |
| Recall and behavior evaluation | Retrieve the dream semantically and through graph traversal, then test later persona and Chatterbox behavior | Not yet proven |

## Embry and Kai: A Concrete Example

The current fixture uses an intense but bounded surf scenario. Embry's recalled
images, text memories, audio, video, character evidence, and relationship history
are combined into a dream about obligation, heat, reef risk, Kai, and public
surf etiquette.

The research question is not whether the system can make an attractive surfing
clip. It is whether Embry can later watch what was actually rendered, connect it
back to the memories that shaped it, form a bounded interpretation, and use that
experience in a future conversation without claiming the dream literally
happened. Chatterbox may express the resulting tone, but it does not decide the
psychology or rewrite Embry's durable identity.

## Selected Interface Walkthrough

The current UX Lab surface is a developer-oriented inspection pane over the same
receipt-backed pipeline. These screenshots illustrate selected boundaries, not
every phase and not proof that the full Dream → Watch → Memory loop is complete.

### 01 — Idea and Memory Residue

![Phase 01 Idea and memory residue board](assets/readme/phase01-idea-memory-residue.webp)

Phase 01 begins with the core creative directive and the recalled memory board.
It mixes Embry/Kai surf images, text memories, character sheets, reef references,
video, and audio so the source material can be inspected before story or media
production begins.

### Embry Portrait Memory Graph

![Embry portrait D3 Theory-of-Mind trace graph](assets/readme/phase01-embry-portrait-d3-graph.webp)

The graph affordance on Embry's portrait opens a D3 memory neighborhood. The
selected portrait becomes the root, and related media, text, people, audio, and
relationship nodes expand around it. This is an inspection surface. It does not
by itself create canonical graph edges or accept a psychological interpretation.

### 08 — Media Lock

![Phase 08 Media Lock accepted storyboard frames](assets/readme/phase08-media-lock.webp)

Phase 08 locks accepted storyboard evidence: start and end frames, dimensions,
hashes, identity status, and the receipts that support them. A media lock does
not mean a provider is ready. It means the accepted visual evidence has a stable
local boundary.

### 09 — Video Provider

![Phase 09 Video Provider current fail-closed state](assets/readme/phase09-video-provider-current.webp)

Phase 09 answers one question: which provider best fits the accepted scene, and
why? The archived run shown here is fail-closed because its selected run root
does not contain the provider scorecard and packet. Missing evidence must never
be displayed as a successful provider choice.

### 10 — Provider Contract

![Phase 10 Provider Contract current fail-closed state](assets/readme/phase10-provider-contract-current.webp)

Phase 10 answers a different question: exactly what would eventually be sent,
against which endpoint and schema evidence, using which media plan, cost policy,
and asynchronous return path? The current development rung is fixture-backed and
dry-run only. The archived run shown here has not been regenerated with that
contract artifact, so the correct UI state remains blocked.

## Theory of Mind and Graph Memory

A stored dream should be explicitly synthetic and connected to its evidence.
Typical relationships include:

```text
persona --dreamed--> dream

dream --derived_from--> source memory
dream --incorporates_event--> present event
dream --features_person--> persona or user
dream --features_place--> location
dream --references_media--> image/audio/video/code memory
dream --observed_in_scene--> Watch scene evidence
dream --supports_interpretation--> grounded ToM candidate
```

Theory-of-Mind candidates may represent beliefs, desires, fears, trust, distrust,
avoidance, obligation, uncertainty, emotion, stance, preference, or relationship
state. Every candidate should retain its subject and target, source-memory IDs,
Watch observation IDs where applicable, confidence, emotional intensity,
synthetic origin, and the gate receipt that accepted or rejected it.

Qdrant and Arango solve different parts of the retrieval problem:

- **Qdrant** finds semantically similar dream, text, image, audio, video, and code
  memories even when a later question uses different words.
- **Arango** explains how a candidate is related through explicit people, events,
  scenes, evidence, beliefs, and relationships.

A future recall should use semantic retrieval to find candidates and graph
traversal to establish the grounded relationship chain. Emotional intensity may
rank memories that already pass identity, scope, evidence, and graph checks. It
must never override those checks.

## Phase 01: From D3 Explorer to React Flow Canvas

The current developer UX already includes a D3-based multimodal memory and
Theory-of-Mind explorer. The intended user-facing evolution is a React Flow
canvas backed by the same canonical Memory and Graph Memory records.

The canvas should let a human inspect or correct the core idea, present events,
recalled text, images, audio, video, code activity, people, places, objects,
emotions, conflicts, typed relationships, salience, and accepted or rejected
dream residue.

D3 may remain the force-layout engine. React Flow should own editable custom
nodes, typed connections, selection, grouping, saved layout, undo/redo, and
multimodal playback. User-created links are not canonical until Memory accepts
and receipts the write.

## Use It Today

| Need | Start here |
|---|---|
| Explore a persona's memory residue | `./run.sh generate --persona <name>` |
| Build a fixture-backed dream packet | `./run.sh generate --persona <name> --fixture <file>` |
| Bias recall toward a topic | `./run.sh generate --persona <name> --about "<topic>"` |
| Create bounded video-planning material | `./run.sh generate --mode video_plan --persona <name>` |
| Write an explicitly approved reflection to Memory | `./run.sh generate --persona <name> --write-memory` |

A future ordinary path should remain just as simple even when it closes the full
cognitive loop.

## Artifacts

### Every run

| Artifact | Purpose |
|---|---|
| `dream_request.json` | Persona, memory residue, mode, and run metadata |
| `response.json` | Model or fixture response captured for audit |

### Successful dream runs

| Artifact | Purpose |
|---|---|
| `residue_links.json` | Provenance from the dream packet to recalled source memories |
| `contradiction_report.json` | Tensions or contradictions detected in selected residue |
| `dream_packet.json` | Structured synthetic dream material for downstream tools |
| `dream_prompt.txt` | Human-readable synthetic dream prompt |
| `frame_prompts.json` | Visual planning prompts when frames are requested |
| `contact_sheet.png` | Inspectable visual review surface when images are produced |
| `dream_reflection.md` | Human-readable reflection, not a canonical persona rewrite |
| `memory_write_receipt.json` | Proof that a Memory write succeeded or was deliberately skipped |

`memory_write_receipt.json` must remain `skipped` unless `--write-memory` was
explicitly requested and the Memory API confirmed the write.

### `video_plan` runs

```text
dream_story.md
dream_story.json
character_scene_bible.json
technique_selection.json
script_dna_selection.json
storyboard.json
timed_transcript.json
multimodal_prompts.json
voice_handoff_plan.json
pipeline_stage_report.json
pipeline_stage_report.md
manifest.json
```

Hardened video experiments may add media-lock, provider-selection, payload, and
provider-contract receipts. Their existence proves only the boundary named by
the receipt.

### Intended closed-loop evidence

The complete research loop should eventually produce evidence such as:

```text
rendered_dream.mp4
watch/frames_manifest.json
watch/transcript.json
watch/scenes.json
watch/report.json
dream_observation_packet.json
dream_self_interpretation.json
tom_edge_proposals.json
dream_memory_record.json
qdrant_embedding_receipt.json
graph_edge_write_receipt.json
persona_before_after_evaluation.json
```

These names describe the intended contract. They are not a claim that every
artifact is currently implemented.

## Ownership Boundaries

| Component | Owns |
|---|---|
| [`create-persona`](../create-persona/SKILL.md) | Canonical persona construction, identity invariants, voice profile, durable persona updates, and simulacrum validation |
| [`memory`](../memory/SKILL.md) and [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) | Canonical multimodal memories, Arango graph state, Theory-of-Mind records and edges, Qdrant embeddings, recall, and persistence |
| `persona-dream` | Dream-residue selection, synthetic dream construction, creative and media orchestration, self-interpretation proposals, and receipts linking the cycle |
| [`watch`](../watch/SKILL.md) | Evidence-first perception of rendered media: frames, transcript, sound, scenes, visual descriptions, and coverage gaps |
| Chatterbox / voice lane | Audible expression of the current persona response and performance direction; it does not decide beliefs or memory truth |
| [`create-movie`](../create-movie/SKILL.md) | Long-form audio, score, mixing, assembly, and polished movie production beyond the bounded dream sequence |

Persona Dream must not create a second persona database or a parallel memory
store. It may emit proposal and evidence artifacts, but accepted memories,
relationships, Theory-of-Mind state, and embeddings belong to Memory and Graph
Memory. Durable canonical persona changes belong to `create-persona`.

## Research Acceptance Boundary

The founding experiment is complete only when one non-mocked run proves all of
the following:

1. A persona autonomously selects grounded multimodal residue and current events.
2. It creates a synthetic dream with complete source provenance.
3. When media is rendered, the returned artifact is technically valid and
   independently analyzed by `watch`.
4. Self-interpretation claims cite Watch observations and source memories.
5. Accepted Theory-of-Mind records and graph edges are written through Memory and
   Graph Memory.
6. Qdrant retrieves the dream from a semantically related, differently worded
   query.
7. Arango traverses from the persona through the dream to source memories,
   observations, people, events, and Theory-of-Mind state.
8. A later persona response uses the dream appropriately while preserving the
   synthetic-versus-literal distinction.
9. Simulacrum probes show bounded evolution without destructive identity drift.
10. Chatterbox audibly expresses the resulting persona state without becoming the
    authority that invented it.

## Proof Discipline

- Do not invent memory residue when recall is empty.
- Label fixture, synthetic, inferred, observed, and literal evidence distinctly.
- Preserve source IDs, scopes, hashes, timestamps, and revision boundaries.
- Treat prompts as intent, not proof of generated-media contents.
- Treat Watch observations as evidence, not automatic psychological conclusions.
- Treat image, video, graph, embedding, persona, and Memory receipts as claims
  until their underlying artifacts and side effects are inspected.
- Do not turn one dream into an unreviewed durable identity rewrite.
- Never claim final video or personality-evolution success without concrete
  media, Watch evidence, persisted graph and embedding receipts, and later
  behavior proof.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Calling Persona Dream a finished movie generator | Treat media generation as one optional part of a graph-memory consolidation experiment |
| Treating the script as proof of what the dream video contains | Run `watch` and interpret observed evidence |
| Creating a second persona or memory database | Persist through `create-persona`, `memory`, and Graph Memory Operator |
| Letting a dream silently rewrite canonical identity | Store bounded synthetic memory and ToM state; promote durable changes only through the owning gate |
| Making React Flow mandatory for autonomous dreaming | Use it as the human inspection and correction canvas over the same graph-native backend |
| Treating a contact sheet as final output | Use it as an inspectable review artifact |
| Treating provider selection as research completion | Close Watch, graph and Qdrant persistence, and future-behavior evaluation |

## References

- [`SKILL.md`](SKILL.md) — current operational contract
- [`create-persona`](../create-persona/SKILL.md) — persona authority and simulacrum validation
- [`memory`](../memory/SKILL.md) — Memory First, multimodal recall, ToM, and persistence contract
- [`watch`](../watch/SKILL.md) — evidence-first dream-media perception
- [`create-movie`](../create-movie/SKILL.md) — downstream polished media lane
- [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) — graph, retrieval, and persistence implementation
- Nested creative helpers live under `skills/persona-dream/skills/`.
