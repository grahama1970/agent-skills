# Persona Dream

![Persona Dream card](../../docs/assets/project-cards/persona-dream.webp)

> **Can an AI persona dream about what has happened to it, watch the dream it
> made, learn from it, and still remain recognizably itself?**

Persona Dream gives a persistent multimodal voice persona — a long-lived agent
with durable memory, a stable character, and access to text, images, audio, and
video — a controlled way to turn experience into a synthetic dream and examine
what comes back.

This is not a movie generator. The dream is an **inspectable intermediate
representation**: synthetic cinematic conflict is a form the persona can observe,
interpret, and be measured against, in a way a prose summary cannot be. The
durable output is an explicitly synthetic dream memory whose every conclusion
stays linked to the memories, media, relationships, and observed scenes that
support it. A dream may influence later reasoning; it may never silently become
literal history or rewrite identity.

## Where to look for what

This README is the durable entry point: purpose, architecture, ownership, and
the current evidence boundary. It is deliberately **not** a status log.

| You want | Read |
|---|---|
| The executable runtime contract | [`SKILL.md`](SKILL.md) |
| Current machine state, blockers, next step | [`CURRENT_STATUS.json`](CURRENT_STATUS.json) |
| Forensic chronology and superseded findings | [`PROJECT_KNOWLEDGE.md`](PROJECT_KNOWLEDGE.md) |
| Operational continuation point | [`local/HANDOFF.md`](local/HANDOFF.md) |
| The immutable goal and gate sequence | [`GOAL.md`](GOAL.md) |
| Per-run evidence | revision-scoped receipts under `reports/` |

## The controlling hierarchy

1. **Build Embry as a persistent persona** whose synthetic dreams produce
   bounded, provenance-linked changes in self-narrative, arc state, session
   mood, and voice while she remains recognizably herself.
2. **PCTOM-R** is the research workstream asking whether counterfactual dreaming
   improves prospective social prediction and planning beyond direct memory,
   under fail-closed controls.
3. **Kling, Watch, Memory, Chatterbox, and Tau** are supporting lanes with their
   own receipts and boundaries.

## Architecture: the bounded loop

```
accepted dream
  -> Watch observations          (what the persona saw, adjudicated)
  -> first-person journal        (grounded, explicitly synthetic)
  -> bounded arc delta           (what may change, and by how much)
  -> continuity ledger           (the authority object; atomic, epoch-checked)
  -> session mood before turn 1  (deterministic, bound before the user speaks)
  -> Chatterbox voice delivery   (the mood made audible)
  -> recognition check           (is it still recognizably Embry?)
```

Each arrow is a gate with its own receipt. The loop is only as strong as the
weakest joined leg, and joining every leg in one run is what P2 is for.

## Current state

Phase **P2_LIVE_CONTINUITY_CHAIN**. Machine-readable state, including the
authoritative blocker list and next step, lives in `CURRENT_STATUS.json`; the
table below is checked against it by
`./run.sh check-current-state-consistency --strict`.

| Lane | Implemented and receipted | Not proven |
|---|---|---|
| Continuity ledger | Atomic writes, epoch compare-and-set, cycle idempotency, identity-core hash guard, read-time validation | Runtime authority across real sessions |
| Session mood | Deterministic mood bound before turn 1, stable across three turns, answer text preserved | Binding inside the production conversation service |
| Chatterbox voice | Live `/synthesize-batch` render of the mood envelope, strict ASR WER 0.0, durable WAV snapshots | Perceived emotion, naturalness, human acceptance |
| Speaker recognition | Long 4.68-6.0s session-mood renders pass resemblyzer identity/adversarial scoring with separation 0.208427 | Human listener recognition, perceived emotion, naturalness, cross-mood identity |
| Joined live chain | One fresh cycle id, `live_chain_20260729t130950z`, joins accepted dream evidence -> Watch binding -> journal -> ledger delta -> pre-turn session mood -> three live Chatterbox turns -> Embry recognition, with 13/13 negative controls blocked | Production conversation-service authority; perceived emotion |
| Session arc bias | `session_arc_bias.v1` publishes bounded deltas from the latest ledger arc, `intensity_delta=0.18`, `valence_delta=-0.18`, with no tone category; `sparta_arc_bias_handoff/SPARTA_CONSUMER_CONTRACT.json` binds the SPARTA consumer contract | SPARTA production consumption; per-turn tone classification; perceived emotion |
| Reliability pilot | Five fresh live-chain cycles passed in `reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json`: 5 attempted, 5 completed, 5 passed, duplicate accepted effects 0, Wilson 95% lower bound 0.565509 | Production reliability; larger campaign; restart/recovery study |
| Blinded listener study | Four preregistered Chatterbox stimuli are restored, hash-matched, and live-ASR verified at WER 0.0 in `blinded_listener_study/STIMULUS_VALIDATION_RECEIPT.json` | Human responses remain 0/20; no perceptual emotion or naturalness result |
| Historical media loop | One accepted canonical dream persistence path and provider return | Repeatability; previous-video attachment causality |
| PCTOM-R | Strong deterministic receipt machinery, live Tau slices | Confidence-bounded planning advantage |

**The active gate** is no longer producing the first joined live-chain receipt
or the five-cycle engineering pilot; both now exist. The next gate is
production conversation-service authority plus perceptual Chatterbox evidence:
route the validated
`sparta_arc_bias_handoff/SPARTA_CONSUMER_CONTRACT.json` target to the
SPARTA-owned production conversation lane, then collect the human responses for
the blinded listener study of dream-derived emotion, Embry identity, and
naturalness. Persona Dream does not own SPARTA service edits. Do not expand
PCTOM-R, generate a new Kling clip, or run another broad assessment before that
gate unless the operator explicitly reprioritizes.

## PCTOM-R, and why its numbers are not a result

PCTOM-R asks whether counterfactual dreaming improves *prospective* Theory of
Mind — predicting what another agent will do — beyond what direct memory gives.

The machinery is strong and the receipt counts are large. Neither fact is a
finding. Receipt volume measures the reliability of the experiment apparatus
within its text-first scope; it does not measure benefit. Until a preregistered
proper-scoring or planning-regret metric separates CD from the strongest M/R/D
baseline on a held-out slice, PCTOM-R has no result to report.

## Ownership boundaries

Persona Dream owns the dream packet, continuity ledger, session-mood binding,
and the receipts that join them. It does **not** own: Graph Memory (persistence
and recall), Watch (observation and adjudication), Tau (model routing and
creator/reviewer loops), Kling and other providers (media generation),
Chatterbox (speech synthesis), or the voice-evaluation lane (speaker backends).
Each has its own proof boundary; Persona Dream may cite their receipts but may
not restate their guarantees. See [Technical Architecture](#technical-architecture).

## What this project does not claim

None of the following is proven, and no commit, single historical run, ASR word
error rate, speaker-embedding score, or volume of receipts establishes any of
them:

- end-to-end pipeline reliability across repeated cycles;
- dream-derived mood binding inside the production conversation service;
- perceived emotion, naturalness, or human acceptance of synthesized speech;
- that a human listener recognizes Embry;
- a confidence-bounded PCTOM-R planning advantage;
- that attaching a previous video causally improves continuity.

Claims here are retired only by a named receipt read back from disk.

---

## Quick Start

| What you want | Command |
|---|---|
| Explore a persona's memory residue | `./run.sh generate --persona <name>` |
| Build a fixture-backed dream packet | `./run.sh generate --persona <name> --fixture <file>` |
| Bias recall toward a topic | `./run.sh generate --persona <name> --about "<topic>"` |
| Create bounded video-planning material | `./run.sh generate --mode video_plan --persona <name>` |
| Write an explicitly approved reflection to Memory | `./run.sh generate --persona <name> --write-memory` |

These commands exercise the current runtime. They do not perform the unproven
live-provider, Watch, graph-persistence, or behavior-evaluation stages.

---

## Research

### Why This Matters

Most agent-memory systems retrieve facts and prior episodes. They do not give a
persistent persona a controlled way to combine emotionally important
experiences, externalize them, inspect the result, and carry a grounded
interpretation forward.

Persona Dream explores that missing middle. A persona could use a dream to
rehearse a difficult relationship, connect a present event to an older memory,
or surface a conflict it could not express directly. The dream is synthetic,
but its effect on later reasoning can still matter, provided every stage
preserves provenance, uncertainty, and the boundary between imagination and
history.

The same architecture could support persistent companions, game characters,
simulation agents, and other long-lived systems that need to adapt without
losing continuity or inventing a false past.

### Founding Research Question

Can a persona whose speech is rendered through Chatterbox, the voice layer:

1. recall emotionally salient past memories and relevant present events;
2. combine text, images, audio, video, relationships, and project or code
   activity into a synthetic dream;
3. render that dream into inspectable multimodal media;
4. use [`watch`](../watch/SKILL.md) to observe what the generated dream actually
   contains instead of assuming the renderer followed the prompt;
5. interpret those observations against its existing memories and persona state;
6. persist grounded ToM tags, graph edges, multimodal embeddings, and an
   explicitly synthetic dream memory; and
7. use that dream appropriately in later reasoning and conversation without
   confusing it with a literal historical event?

The experiment succeeds only when the dream can affect later recall or behavior
while the persona remains recognizably itself.

### The Rule That Keeps the Experiment Honest

One kind of evidence must never silently become another.

| Evidence class | What it means | Owning boundary |
|---|---|---|
| **Historical memory or present event** | Something stored or observed as part of the persona's real history | Memory / Graph Memory |
| **Dream intention** | What Persona Dream planned, scripted, or asked a renderer to create | Persona Dream |
| **Rendered dream observation** | What is actually visible, audible, or temporally present in returned media | `watch` |
| **Persona interpretation** | What the persona tentatively thinks the observed dream may mean | Persona Dream interpretation gate |
| **Theory-of-Mind inference** | A validated candidate belief, fear, desire, trust state, stance, or relationship update | Memory / ToM validation |
| **Durable persona change** | A promoted change to canonical goals, concerns, worldview, identity, or voice profile | `create-persona` |

Suppose the script asks Kai to answer Embry, but the generated video drops Kai
from the final scene. `watch` can report that Kai is absent. Persona Dream may
tentatively connect that absence to Embry's uncertainty about whether her
boundaries will be respected, but it must also preserve the simpler explanation:
the renderer failed to maintain character continuity.

A dream-derived record therefore keeps facts such as:

```json
{
  "synthetic_origin": true,
  "literal_historical_event": false
}
```

There is no direct path from a renderer defect to a durable personality rewrite.

### How a Dream Works

```text
create-persona
  canonical identity, voice profile, and identity-consistency tests
        |
        v
memory + graph-memory-operator
  past memories + present events + text/image/audio/video/code activity
  + ToM state + emotional intensity + graph relationships
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
future recall, reasoning, conversation, and Chatterbox expression
```

The ordinary experience should eventually be simple: a persona says `dream`, or
`dream about Kai and the surf trip`, and the system performs the grounded loop
behind the scenes. React Flow remains an optional human inspection and
correction surface, not a prerequisite for autonomous dreaming.

---

## Current Proof Boundary

Persona Dream is an advanced research prototype and a substantial hardening
workload for Tau, the agentic harness that runs and verifies the pipeline. It is
not yet a completed personality-evolution product.

### Status Vocabulary

The README uses these proof terms consistently:

| Status | Meaning |
|---|---|
| **Implemented** | Code, scripts, artifacts, or a UX surface exist |
| **Accepted evidence** | The selected run contains a receipt-backed artifact accepted by its current gate |
| **Fixture-proven** | Deterministic fixture-backed checks pass; no live external behavior is implied |
| **Live slice proven** | A real external operation or generated artifact was executed and inspected |
| **Qualified revision** | The immutable revision, required evidence, Memory projection, active pointer, and terminal repair event agree |
| **Blocked** | A named prerequisite is missing or intentionally disallowed |
| **Designed** | The architecture and evidence contract exist, but the implementation proof does not |
| **Not implemented** | No working rung currently exists |

| Boundary | State | What that proves |
|---|---|---|
| Grounded dream packets | **Implemented** | Source links, contradiction reports, reflections, and receipts exist |
| Image and storyboard production | **Live slices proven** | Live image generation, visual review, creator/reviewer repair, and accepted-frame evidence exist |
| Phases 01-10 - Qualified successor revision | **Qualified revision at acceptance rung** | `rev_successor_943b01ecd9a3` is `PASS_ACTIVE_CONSISTENT`; the explicit human idea has 10/10 phase lineage bindings, 10 phase + 16 required-artifact Memory records and the 42-step bundle exactly reread, and the rebuilt artifact index makes the eight Phase C storyboard frames (8/8 actual-pixel identity PASS, 7/7 continuity) the active Phase 07 evidence while the montage-derived frames stay stale |
| Phase 11 - Submit and Return | **Live successor return received and accepted (agent level)** | The successor made exactly one hash-bound authorized submit (request `sha256:97688ec5…`, fal request id `019f77f0…`) and received a valid 10.041667s H.264 720p return (`sha256:59b9ff31…`). Step 36 continuity PASS v2 (ArcFace + Tau-routed pose/occlusion adjudication); steps 37-38 PASS v2 (exact line muxed and force-aligned 4.74-7.86s; visible-speaker inapplicable-by-composition per the lane C design). The earlier `rev_upstream_bf3b05d47fb8` return remains superseded historical evidence. Human subjective acceptance of the video remains open |
| Phase 12 - Watch Observation | **Live slice proven for perception-on-historical-return** | The `watch` post-return gauntlet (`scripts/watch_post_return_gauntlet.py`) runs the `watch` skill over the frozen historical Kling return, extracts scene-driven frames + Whisper transcript, and independently localizes the identity-drift and visible-speaker windows. Validated against ground truth: `watch_gauntlet/991c311f365f/watch_gauntlet_validation_receipt.v1.json` (`PASS_WATCH_GAUNTLET_VALIDATED`, 5/5 expectations). The gauntlet has since also run on the accepted successor return (`watch_gauntlet/59b9ff3155d6/`); its observation packet remains `DEGRADED` (per-frame VLM entities pending), with the authoritative visual verdicts carried by the step-36 v2 receipt |
| Phases 13-15 - Interpretation through persistence | **Live slice proven on accepted return** | On the ACCEPTED successor return, phase 13/14 text reasoning routes through the Tau node (tau `09e64a44`; no direct scillm), 4 interpretations + 4 ToM candidates pass the deterministic gates, and phase 15 wrote the FIRST canonical dream memory (19 records, exact reread-by-key) permitted only by a binding agent-level acceptance receipt; superseded/historical returns stay fail-closed |
| Phase 16 - Recall and later persona behavior | **Machine-decidable slice LIVE-PROVEN (`PASS`)** | `scripts/phase16_behavior_evaluation.py` → `phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json` (`overall_status: PASS`): (a) semantic recall returns the dream from 3 differently-worded queries (ranks 1/3/7, dense 0.59/0.43/0.74) while a `orbital telemetry` negative control does NOT; (b) multi-hop traversal resolves all 14 canonical edges live to 3 source memories + 7 Watch observations + 4 ToM nodes; (c) the persona uses the dream and marks it as a dream, with context assembled ONLY from live recall; (d) it denies literal occurrence and the `synthetic_origin=true`/`literal_historical_event=false` flags reread exactly; (e) identity is stable (loop write-set is dream+edges+ToM only, source anchors literal/unchanged, Tau values Q&A stable). All LLM probes route through the Tau node (no direct scillm). **Out of scope this slice: Chatterbox voice expression (item 10) and human subjective acceptance of the video** |

The screenshots below come from an archived Embry/Kai run. That run has not been
regenerated with every newer provider artifact. A blocked screenshot describes
the selected run root, not the full set of current development capabilities.

Provider selection is near the end of the media-production spine. It is not the
end of the founding research experiment.

---

## Pipeline: 01-16

The complete Persona Dream pipeline has two connected parts:

- **Phases 01-11** create, ground, plan, and eventually render the dream.
- **Phases 12-16** let the persona observe, interpret, store, and later use that
  experience.

### Media-Production Spine

| Phase | Question | Primary evidence or output | Status |
|---|---|---|---|
| **01 - Idea and Memory Residue** | What is the persona dreaming about, and which memories actually support it? | Core directive, grounded multimodal residue, source IDs, relevance, contradictions | **Qualified revision** |
| **02 - Story** | What bounded story emerges from the accepted residue? | `story_contract.json`, interaction and relationship coverage, story intent | **Qualified revision** |
| **03 - Crew** | Who has creative authority over this dream? | Producer, scriptwriter, director, reviewer, and authority contracts | **Qualified revision** |
| **04 - Contact Sheets** | Which characters, props, and environments must remain visually stable? | Character, prop, environment, and reference-pack evidence | **Qualified revision** |
| **05 - Voices** | How should each persona sound without confusing voice expression with psychological authority? | Voice references, audition state, identity boundaries, voice handoff plan | **Qualified revision** |
| **06 - Script** | How does story intent become timed action and dialogue? | `script_contract.json`, beats, dialogue/action coverage, interaction matrix | **Qualified revision** |
| **07 - Storyboard** | What must each shot visibly contain, and has it passed visual review? | Accepted panels, start/end frames, prompt contracts, visual-review receipts | **Qualified revision** |
| **08 - Media Lock** | Which accepted visual assets are frozen for provider-facing use? | Locked frame subset, roles, hashes, dimensions, identity state | **Qualified revision** |
| **09 - Video Provider** | Which provider best fits the accepted scene, and why? | Provider registry refresh, scorecard, selected provider, dry-run packet | **Qualified revision; no live call** |
| **10 - Provider Contract** | Exactly what would eventually be sent, against which endpoint and contract? | Request body, payload hash, field mapping, media plan, cost/entitlement plan, async plan, non-claims | **Qualified revision; no live call** |
| **11 - Submit and Return** | Can one explicitly authorized provider call produce a valid returned dream artifact? | Media URLs, approval, paid authorization, submit receipt, task ID, polling/callback, downloaded video, FFprobe | **Blocked** |

### Cognitive and Memory Loop

| Phase | Question | Primary evidence or output | Status |
|---|---|---|---|
| **12 - Watch Observation** | What is actually visible, audible, spoken, absent, or changed in the returned dream? | Frames, transcript, sound, scene table, visual descriptions, coverage gaps | **Live slice proven (historical return)** — `watch_post_return_gauntlet.py` + `watch_gauntlet_observation_packet.v1`; validated on the frozen Kling return, not yet on a successor return |
| **13 - Persona Self-Interpretation** | What might the observed dream mean in the context of the persona's grounded memories? | Observation-backed interpretations, source references, uncertainty, alternative explanations | **Implemented; fixture-and-live-slice proven (historical return)** — `phase13_self_interpretation.py` + `dream_self_interpretation.v1`; scillm gpt-5.5 drafts, deterministic gate rejects uncited claims. NOT the closed-loop research claim |
| **14 - Theory-of-Mind Validation** | Which proposed beliefs, fears, desires, trust states, or relationship updates are sufficiently grounded? | Accepted or rejected ToM candidates with subject, target, confidence, intensity, and receipts | **Implemented; fixture-and-live-slice proven (historical return)** — `phase14_tom_validation.py` + `tom_candidate.v1`; LLM proposes, deterministic gate decides admissibility against parent grounding. NOT the closed-loop research claim |
| **15 - Memory, Graph, and Qdrant Persistence** | Can the accepted synthetic dream be stored and retrieved without becoming false history? | Dream memory record, ArangoDB edges, Qdrant points, cross-store validation receipts | **Implemented; fixture-and-live-slice proven (historical return)** — `phase15_dream_persistence.py`; default dry-run plan with zero canonical writes, real write proven into non-canonical `persona_dream_loop_validation`, canonical write hard-fails on the superseded return. NOT the closed-loop research claim |
| **16 - Recall and Behavior Evaluation** | Does the persona later use the dream appropriately while remaining recognizably itself? | Semantic recall, multi-hop traversal, identity-consistency probes, before/after conversation and Chatterbox evidence | **Not implemented as a closed proof** |

### Current Qualified Runtime Boundary

The active revision is `rev_successor_943b01ecd9a3` (run `pipeline-complete`),
reported `PASS_ACTIVE_CONSISTENT`. Memory contains one revision, ten phase
records, sixteen required-artifact references, one run-scoped active pointer, and
the durably reread 42-step pipeline bundle, all with Qdrant semantic sync
metadata. The rebuilt immutable artifact index contains 398 revision-scoped local
artifacts and binds the eight regenerated Phase C storyboard frames as the active
accepted Phase 07 evidence. This qualifies Phases 01-10 and reaches the
acceptance rung; it does not prove a successor provider call, returned dream,
lip sync, Watch analysis, interpretation, or later persona behavior. The earlier
`rev_idea_f3f9c48d5cc2` qualification is historical and superseded.

Primary receipts:

- `.persona-dream/revisions/rev_successor_943b01ecd9a3/acceptance_rung_receipt.v1.json`
- `.persona-dream/revisions/rev_successor_943b01ecd9a3/revision_memory_prepare_receipt.json`
- `.persona-dream/revisions/rev_successor_943b01ecd9a3/revision_memory_verify_receipt.json`
- `.persona-dream/revisions/rev_successor_943b01ecd9a3/revision_activation_receipt.json`
- `.persona-dream/state/pipeline_step_memory_receipt_rev_successor_943b01ecd9a3.json`
- `.persona-dream/repair/queue-events/repair-454b255245a1a162/000001-completed.json`

### Cognitive Loop 13-15: Fixture-and-Live-Slice Proof (Historical Return)

Phases 13-15 are implemented and proven on the HISTORICAL Kling return
(`991c311f365f`), whose observation packet failed identity continuity (DRIFT)
and lip sync. Those failures are themselves ground-truth observations. This is
NOT the closed-loop research claim (Acceptance items 4-8), which still requires a
non-superseded successor return.

- Runner: `scripts/run_cognitive_loop.py` chains 12 -> 13 -> 14 -> 15 from an
  observation packet and emits a loop receipt.
- Phase 13 (`scripts/phase13_self_interpretation.py`): scillm gpt-5.5 drafts
  tentative interpretations; a deterministic gate rejects any claim that does not
  cite at least one Watch observation id AND at least one source-memory id, or
  that treats a renderer defect as psychological truth. The honesty rule fired on
  the identity-DRIFT observation: the accepted claim carries both a psychological
  and a renderer-defect reading with the renderer defect favored.
- Phase 14 (`scripts/phase14_tom_validation.py`): the LLM proposes bounded ToM
  candidates; a deterministic gate rejects any whose grounding is not a subset of
  its parent accepted interpretation. Four grounded candidates accepted
  (trust / stance / uncertainty / belief).
- Phase 15 (`scripts/phase15_dream_persistence.py`): default dry-run emits an
  exact canonical would-write plan (dream memory doc + `derived_from`,
  `observed_in_scene`, `supports_interpretation` edges + Qdrant embedding note)
  with hashes and ZERO canonical writes. A canonical write requires
  `--allow-canonical-write` AND a non-superseded return id and HARD-FAILS (exit 1)
  on this superseded return. The write path is proven by 16 exact-reread-matched
  documents in the non-canonical `persona_dream_loop_validation` collection.

Receipts:
`.persona-dream/revisions/rev_successor_943b01ecd9a3/cognitive_loop/991c311f365f/`
(`cognitive_loop_receipt.json`, `dream_self_interpretation.json`,
`tom_validation_receipt.json`, `dream_persistence_receipt.json`,
`cognitive_loop_memory_governance_receipt.json`). Deterministic logic is covered
by `tests/test_cognitive_loop_phases.py` (16 cases, no live calls).

### Remaining Work Beyond the Qualified Revision

The remaining live and closed-loop work is:

1. verify the current provider endpoint and API schema;
2. publish and externally probe provider-accessible input media;
3. verify cost, entitlement, manual acceptance, and paid authorization;
4. submit one bounded provider request and retrieve the returned artifact;
5. run `watch` against the actual returned media;
6. produce grounded self-interpretation and ToM candidates;
7. persist only accepted synthetic memory and graph/embedding records; and
8. prove later retrieval and bounded behavior change without identity drift.

---

## Embry and Kai: The Working Example

The current fixture begins with a deceptively ordinary choice: Embry and Kai
fake a sick day from their summer jobs to surf Kahaluʻu Bay on Hawaiʻi's Big
Island. Heat softens the board wax. A lava reef narrows the safe choices. The
lineup adds social pressure, while Embry's history with Kai gives every warning
and hesitation relational weight.

One voice-test line captures the tension:

> "Kai, wait. If we paddle now, we're cutting across the lineup."

The pipeline can draw on character images, older text memories, surf audio,
video references, environmental evidence, and relationship history.

The test is not whether it can make an attractive surf clip. The test is
whether Embry can later watch the actual returned media, distinguish a renderer
failure from a meaningful pattern, form a bounded interpretation, and use that
experience in a future conversation without claiming the dream literally
happened.

Chatterbox can express the resulting tone. It does not decide the psychology or
rewrite Embry's durable identity.

---

## Interface Walkthrough

The current UX Lab surface is a developer-oriented inspection pane over the
pipeline and its machine-readable receipts.

The walkthrough lists every pipeline phase in order. Screenshots are included
where committed README assets exist. A phase without a screenshot is still
shown because it is a real research boundary, not hidden implementation detail.

### 01 - Idea and Memory Residue

![Phase 01 Idea and memory residue board](assets/readme/phase01-idea-memory-residue.webp)

Phase 01 begins with the core creative directive and the recalled memory board.
It mixes Embry/Kai surf images, text memories, character sheets, reef
references, video, and audio so the source material can be inspected before
story or media production begins.

**What to notice:** the system exposes multiple memory modalities before it asks
a story model or renderer to transform them.

#### 01A - Memory Relationship Graph

![Embry portrait D3 Theory-of-Mind trace graph](assets/readme/phase01-embry-portrait-d3-graph.webp)

The graph affordance on Embry's portrait opens a D3 memory neighborhood. The
selected portrait becomes the root, and related media, text, people, audio, and
relationship nodes expand around it.

**What to notice:** this is an explorer, not a write surface. It does not create
canonical graph edges or accept a psychological interpretation.

### 02 - Story

![Phase 02 Story contract surface](assets/readme/phase02-story-content-pane.webp)

Phase 02 turns accepted memory residue into a story contract: the narrative
premise, relationship pressure, surf-etiquette stakes, contradiction checks,
and interaction model that later phases must preserve.

**What to notice:** this is where the Embry/Kai sick-day idea becomes a bounded
story rather than a loose prompt.

### 03 - Crew

![Phase 03 Crew selection surface](assets/readme/phase03-crew-content-pane.webp)

Phase 03 selects the creative authorities for the run: producer, scriptwriter,
director, and reviewer roles. Those choices determine which creative standards
control later script, storyboard, and visual-review decisions.

**What to notice:** crew selection is part of the evidence chain. It is not a
cosmetic cast list.

### 04 - Contact Sheets

![Phase 04 Contact Sheets surface](assets/readme/phase04-contact-sheets-content-pane.webp)

Phase 04 gathers character, environment, surfboard, lineup, and lava-reef
references. Contact sheets are source and planning evidence; they do not
automatically become provider-ready upload packs.

**What to notice:** Embry, Kai, Kahaluʻu Bay, the lava reef, and the public
lineup are grounded before the script and storyboard try to reuse them.

### 05 - Voices

![Phase 05 Voices surface](assets/readme/phase05-voices-content-pane.webp)

Phase 05 inspects voice references, dialogue readiness, and voice-identity
boundaries. It can preserve conversational intent and Chatterbox tone without
claiming provider voice IDs or live voice readiness.

**What to notice:** a voice surface can support the dream's emotional tone while
still blocking live provider voice submission.

### 06 - Script

![Phase 06 Script contract surface](assets/readme/phase06-script-content-pane.webp)

Phase 06 converts the accepted story into timed action, dialogue, interaction
coverage, and screenplay evidence. The Embry/Kai fixture uses this phase to
make surf etiquette, hesitation, pressure, and boundary-setting concrete.

**What to notice:** this is the bridge from story intent to frameable action.

### 07 - Storyboard

![Phase 07 Storyboard surface](assets/readme/phase07-storyboard-content-pane.webp)

Phase 07 produces and reviews storyboard panels, start/end frames, identity
continuity, prompt contracts, and visual-review receipts. Accepted storyboard
evidence is what Phase 08 is allowed to lock.

**What to notice:** Media Lock does not create visual truth. It freezes the
accepted storyboard evidence produced here.

### 08 - Media Lock

![Phase 08 Media Lock accepted storyboard frames](assets/readme/phase08-media-lock.webp)

Phase 08 locks accepted storyboard evidence: start and end frames, dimensions,
hashes, identity status, and the receipts that support them.

**What to notice:** a media lock proves a stable local evidence boundary. It
does not prove that any provider is ready.

### 09 - Video Provider

![Phase 09 Video Provider dry-run scorecard](assets/readme/phase09-video-provider-scorecard-20260710.webp)

Phase 09 answers one question: which provider best fits the accepted scene, and
why?

The selected Embry/Kai run currently shows a local provider scorecard and
dry-run routing state. It remains explicitly non-live: no paid call, no
provider submission, and no provider-ready claim.

**What to notice:** provider ranking is an inspectable recommendation. It is
not authorization to call Kling, fal.ai, or any other live provider.

### 10 - Provider Contract

![Phase 10 Provider Contract current fail-closed state](assets/readme/phase10-provider-contract-current.webp)

Phase 10 answers a different question: exactly what would eventually be sent,
against which endpoint and schema evidence, using which media plan, cost policy,
and asynchronous return path?

The canonical run contains a deterministic compiler, independent validator,
live zero-call adapter preflight, and Memory-persisted fail-closed boundary.
The archived screenshot shown here predates that current contract artifact.

**What to notice:** the screenshot is correctly blocked even though newer local
contract tooling exists. Neither state proves live fal.ai compatibility.

### 11 - Submit and Return

Phase 11 is the live-provider boundary. It requires:

- current provider schema evidence;
- externally accessible and probed media URLs;
- verified cost and entitlement;
- manual acceptance bound to the exact payload;
- paid-call authorization;
- one bounded submission;
- task-ID extraction;
- polling or callback handling;
- returned-media download;
- hash and FFprobe validation.

**What to notice:** this phase is intentionally blocked. The README must not
claim that the persona watched a dream until a provider return exists and Watch
has analyzed the actual media.

Current canonical evidence for `rev_idea_f3f9c48d5cc2`:

```text
request_body_sha256: sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41
validator_status: PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED
adapter_status: PASS_PHASE11_ADAPTER_PREFLIGHT
gate_status: BLOCKED_AWAITING_HUMAN_APPROVAL
technical_blockers: []
missing_approval_count: 5
actual_provider_call_attempts: 0
memory_key: pd_phase11_eb5dbe1257f6152103d1ce1e2700f9582d8ef6e5fb87e90e
memory_dense_recall_max: 0.7866844
provider_ready: false
live_submit_ready: false
```

That zero-call receipt is the current corrected-request authority. Two prior
requests remain immutable failed-attempt history. Request `444a5a27...` failed
because all four prompts exceeded 512 characters. Request `9966f6b6...` failed
because fal rejects `end_image_url` with `multi_prompt`:

```text
request_id: 019f6b89-e69a-7371-9b98-313a96f5f020
request_body_sha256: sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16
state: FAILED
actual_provider_call_attempts: 1
provider_result_http_status: 422
provider_error: End Image Url is not supported with Multi Prompt
automatic_resubmit_allowed: false
returned_video: false
```

### 12 - Watch Observation

Phase 12 sends the actual returned dream to [`watch`](../watch/SKILL.md).
`watch` extracts frames, transcript, sound, scene changes, visible facts, missing
elements, and coverage gaps.

**What to notice:** Watch reports evidence. It does not decide what the dream
means or how the persona should change.

### 13 - Persona Self-Interpretation

Phase 13 compares:

- the grounded source memories;
- the intended dream;
- the actual Watch observations; and
- the persona's current state.

It produces tentative interpretations with source references, observation
references, confidence, uncertainty, and alternative explanations.

**What to notice:** interpretation remains a proposal. A generated symbol is not
automatically psychological truth.

### 14 - Theory-of-Mind Validation

Phase 14 accepts or rejects bounded ToM candidates such as beliefs, fears,
desires, trust, distrust, avoidance, obligation, uncertainty, emotion, stance,
preference, or relationship state.

**What to notice:** a candidate must identify its subject, target, source
memories, Watch observations, confidence, emotional intensity, and accepting or
rejecting receipt.

### 15 - Memory, Graph, and Qdrant Persistence

Phase 15 writes only accepted records through the owning Memory and Graph Memory
layers.

The intended result includes:

- an explicitly synthetic dream memory;
- source and observation relationships in ArangoDB;
- accepted ToM edges;
- multimodal semantic points in Qdrant; and
- receipts proving cross-store consistency.

**What to notice:** Persona Dream does not create a second memory database or
write directly around the Memory contract.

### 16 - Recall and Behavior Evaluation

Phase 16 asks whether the dream has become useful without destabilizing the
persona.

It should prove that:

- Qdrant retrieves the dream from differently worded queries;
- ArangoDB reconstructs the multi-hop relationship chain;
- later conversation uses the dream appropriately;
- the persona still distinguishes the dream from literal history;
- identity-consistency probes remain stable; and
- Chatterbox expresses the resulting state without inventing it.

**What to notice:** this is the completion boundary for the founding research
experiment, not provider selection and not video generation alone.

---

## Technical Architecture

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

## Acceptance and Proof

### Research Acceptance Boundary

The founding experiment is complete only when one non-mocked run proves all of
the following. Per-item state as of 2026-07-18 (Phase 16 completion):

1. A persona autonomously selects grounded multimodal residue and current events.
   — **PROVEN** (phase 01 idea/residue selection, live).
2. It creates a synthetic dream with complete source provenance.
   — **PROVEN** (canonical `dream_dream_successor_943b01ecd9a3`,
   `synthetic_origin: true`, 3 source memories + Watch/ToM provenance).
3. When media is rendered, the returned artifact is technically valid and
   independently analyzed by `watch`.
   — **PROVEN for the frozen historical return** (watch post-return gauntlet,
   5/5). The accepted successor return is validated; the observation packet is
   `DEGRADED` (authoritative verdicts carried by the step-36 v2 receipt).
4. Self-interpretation claims cite Watch observations and source memories.
   — **PROVEN** (phase 13, 4 interpretations, deterministic citation gate).
5. Accepted ToM records and graph edges are written through Memory and Graph
   Memory. — **PROVEN** (phase 15, 19 canonical records, exact reread-by-key).
6. Qdrant retrieves the dream from a semantically related, differently worded
   query. — **PROVEN** (phase 16 probe a: dream returned by 3 differently-worded
   queries, ranks 1/3/7; negative control excludes it).
7. ArangoDB traverses from the persona through the dream to source memories,
   observations, people, events, and ToM state. — **PROVEN** (phase 16 probe b:
   14/14 canonical edges resolve live to 3 sources + 7 Watch observations + 4
   ToM nodes; actual vertex/edge keys recorded).
8. A later persona response uses the dream appropriately while preserving the
   synthetic-versus-literal distinction. — **PROVEN** (phase 16 probes c and d:
   grounded dream use marked as a dream; literal occurrence denied; DB flags
   reread exactly). LLM routed through the Tau node; checks deterministic.
9. Identity-consistency probes show bounded evolution without destructive
   identity drift. — **PROVEN for the honest slice** (phase 16 probe e: the dream
   loop's canonical write-set is dream+edges+ToM only — it never wrote/updated an
   identity or source record; source anchors reread as literal/unchanged;
   create-persona working tree clean; Tau values/relationship Q&A stable). No
   standalone Embry persona-definition file or runnable create-persona identity
   suite exists; labeled as the honest slice.
10. Chatterbox audibly expresses the resulting persona state without becoming
    the authority that invented it. — **NOT PROVEN / OUT OF SCOPE this slice**
    (no Chatterbox/voice runtime exercised; factually out of scope). Human
    subjective acceptance of the dream video also remains the human's.

### Proof Discipline

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

### Common Mistakes

| Mistake | Better move |
|---|---|
| Calling Persona Dream a finished movie generator | Treat media generation as one optional part of a graph-memory consolidation experiment |
| Treating the script as proof of what the dream video contains | Run `watch` and interpret observed evidence |
| Creating a second persona or memory database | Persist through `create-persona`, `memory`, and Graph Memory Operator |
| Letting a dream silently rewrite canonical identity | Store bounded synthetic memory and ToM state; promote durable changes only through the owning gate |
| Making React Flow mandatory for autonomous dreaming | Use it as the human inspection and correction canvas over the same graph-native backend |
| Treating a contact sheet as final output | Use it as an inspectable review artifact |
| Treating provider selection as research completion | Close Watch, graph and Qdrant persistence, and future-behavior evaluation |

---

## References

- [`SKILL.md`](SKILL.md) - current operational contract
- [`create-persona`](../create-persona/SKILL.md) - persona authority and identity-consistency validation
- [`memory`](../memory/SKILL.md) - Memory First, multimodal recall, ToM, and persistence contract
- [`watch`](../watch/SKILL.md) - evidence-first dream-media perception
- [`create-movie`](../create-movie/SKILL.md) - downstream polished media lane
- [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) - graph, retrieval, and persistence implementation
- Nested creative helpers live under `skills/persona-dream/skills/`.
