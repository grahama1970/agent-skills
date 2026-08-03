# Pipeline: 01-16

Extracted from `README.md` so the README stays a map rather than an
encyclopedia. The README links here; this file is the detail.

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
