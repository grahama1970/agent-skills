# Technical Architecture

Extracted from `README.md` so the README stays a map rather than an
encyclopedia. The README links here; this file is the detail.

### Memory, Graphs, and Retrieval

A stored dream remains explicitly synthetic and connected to its evidence.
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

ToM candidates can represent beliefs, desires, fears, trust, distrust,
avoidance, obligation, uncertainty, emotion, stance, preference, or relationship
state. Every candidate retains:

- its subject and target;
- source-memory IDs;
- Watch observation IDs where applicable;
- confidence;
- emotional intensity;
- synthetic origin; and
- the gate receipt that accepted or rejected it.

Qdrant and ArangoDB solve different retrieval problems:

- **Qdrant** finds semantically similar dream, text, image, audio, video, and code
  memories even when a later question uses different words.
- **ArangoDB** explains how a candidate connects through explicit people, events,
  scenes, evidence, beliefs, and relationships.

Future recall uses semantic retrieval to find candidates and graph traversal to
establish the grounded relationship chain. Emotional intensity can rank memories
that already pass identity, scope, evidence, and graph checks. It cannot
override those checks.

### Phase 01: From D3 Explorer to React Flow Canvas

The current developer UX includes a D3-based multimodal memory and ToM explorer.
The intended user-facing evolution is a React Flow canvas backed by the same
canonical Memory and Graph Memory records.

The canvas should let a human inspect or correct:

- the core idea;
- present events;
- recalled text, images, audio, video, and code activity;
- people, places, objects, emotions, and conflicts;
- typed relationships;
- emotional salience;
- accepted or rejected dream residue.

D3 can remain the force-layout engine. React Flow should own editable custom
nodes, typed connections, selection, grouping, saved layout, undo/redo, and
multimodal playback.

User-created links are not canonical until Memory accepts and receipts the
write.

### Ownership Boundaries

| Component | Owns |
|---|---|
| [`create-persona`](../create-persona/SKILL.md) | Canonical persona construction, identity invariants, voice profile, durable persona updates, and identity-consistency tests |
| [`memory`](../memory/SKILL.md) and [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) | Canonical multimodal memories, ArangoDB graph state, ToM records and edges, Qdrant embeddings, recall, and persistence |
| `persona-dream` | Dream-residue selection, synthetic dream construction, creative and media orchestration, self-interpretation proposals, and receipts linking the cycle |
| [`watch`](../watch/SKILL.md) | Evidence-first perception of rendered media: frames, transcript, sound, scenes, visual descriptions, and coverage gaps |
| Chatterbox / voice lane | Audible expression of the current persona response and performance direction; it does not decide beliefs or memory truth |
| [`create-movie`](../create-movie/SKILL.md) | Long-form audio, score, mixing, assembly, and polished movie production beyond the bounded dream sequence |

Persona Dream does not create a second persona database or a parallel memory
store. It can emit proposal and evidence artifacts, but accepted memories,
relationships, ToM state, and embeddings belong to Memory and Graph Memory.

Durable canonical persona changes belong to `create-persona`.

### Artifacts

#### Every Run

| Artifact | Purpose |
|---|---|
| `dream_request.json` | Persona, memory residue, mode, and run metadata |
| `response.json` | Model or fixture response captured for audit |

#### Successful Dream Runs

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

`memory_write_receipt.json` remains `skipped` unless `--write-memory` was
explicitly requested and the Memory API confirmed the write.

#### `video_plan` Runs

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

#### Provider-Hardening Artifacts

Hardened provider experiments can additionally emit artifacts such as:

```text
video_provider_scorecard.json
video_provider_packet.json
provider_payload_mapping_receipt.json
phase10_provider_contract.json
phase10_provider_contract_receipt.json
```

Their existence proves only the boundary named by the artifact or receipt. A
Phase 10 contract does not prove live schema compatibility, media publication,
authorization, submission, or provider return.

#### Intended Closed-Loop Evidence

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

---
