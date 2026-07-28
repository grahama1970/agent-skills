# Persona Dream

## Current state (2026-07-27)

Persona Dream is controlled by one hierarchy:

1. Build Embry as a persistent persona whose synthetic dreams produce bounded,
   provenance-linked changes in self-narrative, arc state, session mood, and
   voice while she remains recognizably herself.
2. Keep PCTOM-R as the research workstream that asks whether counterfactual
   dreaming improves prospective social prediction and planning beyond direct
   memory under fail-closed controls.
3. Treat Kling, Watch, Memory persistence, Chatterbox, and Tau as supporting
   technology lanes with their own receipts and boundaries.

Current evidence is mixed. The deterministic research and provenance machinery
is strong: the PCTOM-R evidence recorded in `GOAL.md` reports 15/15 coverage
ids, 43 child evidence receipts, 19 live positive rows, 12 negative rows, 128
deterministic social episodes, and a 32/32 live Tau planning slice. That proves
the reliability of the experiment machinery within its text-first scope. It
does not yet prove a confidence-bounded planning advantage or that Embry has
durable lived continuity.

The persona lane has a first continuity-ledger artifact:
`reports/goal_v5/continuity/embry.continuity_state.v1.json`. It records an
identity core, arc state, one recent arc delta, and provenance links. That is
the right authority object, but the full live chain is still unproven:
accepted dream -> Watch observations -> first-person journal -> bounded arc
delta -> persisted continuity ledger -> session mood before first user turn ->
same mood reread throughout a session -> Chatterbox voice delivery -> recognition
check.

The Chatterbox actuator path is now practical evidence, not aspiration:
`reports/goal_v5/emotion_proof/asr_batch/RECEIPT.json` is live and non-mocked,
uses `POST http://127.0.0.1:8018/synthesize-batch`, selects
`chatterbox_base`, preserves weighted `voice_delivery`, and passes ASR with
WER 0.0. This proves transport/content preservation for that ASR batch path. It
does not prove perceived emotion, stable Embry identity, naturalness, browser or
microphone behavior, or durable dream-derived session mood.

The historical media loop produced meaningful receipts, including one accepted
canonical dream persistence path. It is not currently a routinely rerunnable
product pipeline. Provider/video continuation and previous-video attachment
remain historical or experimental until a fresh paired receipt proves them.

Machine-readable current state lives in `CURRENT_STATUS.json`.

**Operational next step (P2):** build
`reports/goal_v5/continuity/live_chain/RECEIPT.json`, but harden the continuity
ledger first. `scripts/continuity_ledger.py` needs atomic write/replace, epoch
compare-and-set, cycle-derived idempotency, recomputed identity-core hash
validation, read-time ledger validation, and Embry schema normalization before a
live continuity receipt can be trusted. After that, bind one session mood before
turn 1, reread the same mood across turns, preserve answer propositions, route
the derived voice delivery to Chatterbox, and run the adversarial recognition
check. Do not expand PCTOM-R, generate a new Kling clip, or run another broad
assessment before this receipt.

| Lane | Current proof | Boundary |
|---|---|---|
| Historical Kling loop | One accepted successor return and canonical persistence path | Not repeatability or prior-video attachment causality |
| Watch | Restored Tau-routed adjudication for the accepted successor | Not routine availability across fresh cycles |
| Dream persistence | One canonical write and exact reread path | Not multi-cycle reliability |
| Continuity ledger | Initial Embry state artifact | Not runtime authority until P2 live-chain receipt |
| Chatterbox | Live weighted render path with WER 0.0 | Not perceived emotion or stable Embry identity |
| PCTOM-R | Strong deterministic receipt machinery | No confidence-bounded planning advantage yet |


![Persona Dream card](../../docs/assets/project-cards/persona-dream.webp)

> **Can a persistent AI persona turn its own experiences into a synthetic dream,
> inspect what was actually rendered, learn from the result, and express the
> resulting emotional conflict without confusing imagination with history or
> losing its identity?**

Persona Dream is a research system for **multimodal autobiographical
consolidation**. It gives a long-lived voice persona a controlled way to select
emotionally important memories, externalize an unresolved conflict as a bounded
cinematic episode, observe the returned media, form grounded interpretations,
store an explicitly synthetic dream in graph memory, and use it later in
reasoning and speech.

It is not primarily a movie generator. The media pipeline is an **inspectable
intermediate representation of the persona's self-model**.

[`SKILL.md`](SKILL.md) is the operational contract. This README explains the
research thesis, current proof boundary, architecture, active hardening work,
and the intended integration with
[Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator)
and [Chatterbox](https://github.com/grahama1970/chatterbox).

## Research Thesis

Most persistent-agent systems store events, retrieve memories, and produce text
reflections. Persona Dream tests a stronger loop:

```text
experience and memory
    -> unresolved emotional conflict
    -> story, crew, blocking, camera, lens, light, color, sound and dialogue
    -> rendered synthetic episode
    -> independent perception of the returned artifact
    -> bounded interpretation and social-state proposals
    -> explicitly synthetic graph memory
    -> later recall, behavior and voice expression
```

The claim is not that filmmaking terminology automatically creates a better
hidden latent space. The claim is that cinematic construction creates a **richer
externalized constraint space** than a short text summary. It forces an implicit
interpretation to become concrete across many human-inspectable choices:

- who owns agency in the scene;
- who initiates, waits, warns, commands, yields or leaves;
- whether care is staged as support or control;
- how physical risk embodies emotional risk;
- whether camera distance creates intimacy, equality or dominance;
- whether lighting and color make the memory nostalgic, threatening or unresolved;
- whether timing, silence, pauses and sound support the stated conflict;
- and whether the generated artifact contradicts the persona's declared values.

A human can inspect those commitments. `watch` can independently report what is
visible and audible. Persona Dream can then compare intention with observation
instead of treating its own prompt as proof.

### Novelty Boundary

The individual ideas are not new. Prior work already covers agent memory and
reflection, offline consolidation or “dreaming,” multimodal long-term memory,
agentic filmmaking, render-and-review learning loops, and emotionally expressive
speech agents.

Persona Dream's potentially distinctive contribution is their integration into a
single provenance-governed autobiographical loop:

> **cinematic conflict externalization -> independent perceptual verification ->
> graph-governed synthetic memory -> evidence-linked voice expression**

This is a research hypothesis, not a world-first claim. The system must still
show that the cinematic path provides measurable value over a matched-budget
text reflection.

## Current State

**Snapshot: 2026-07-19.** The founding Embry/Kai experiment has crossed its
machine-decidable closed-loop boundary on one accepted successor return.

| Boundary | Current evidence |
|---|---|
| Phases 01-10 | Active successor revision `rev_successor_943b01ecd9a3` is qualified and `PASS_ACTIVE_CONSISTENT`; the pipeline bundle and accepted storyboard evidence reread exactly. |
| Phase 11 | One hash-bound successor provider request returned a valid 10.041667-second H.264 video. The post-return continuity and audio/dialogue gates pass at agent level. |
| Phase 12 | Watch-derived frames, transcript/audio facts, coverage gaps and adjudication evidence exist. The accepted successor is consumed through an acceptance-bound observation path; the earlier failed return remains superseded evidence. |
| Phases 13-14 | Four grounded self-interpretations and four bounded ToM candidates passed deterministic citation and subset gates. Model drafting routes through Tau; code decides admissibility. |
| Phase 15 | The first canonical synthetic dream was persisted through the Memory API. Current code uses typed transitions, staged verification, published rereads, an active commit manifest, and materialized Watch-evidence vertices. |
| Phase 16 | Semantic recall, strict graph traversal, grounded later use, synthetic-versus-literal distinction and an honest identity-stability slice pass for the canonical dream. |
| Chatterbox expression | The general voice runtime and delivery-arc interfaces exist, but the dream-derived **Embry** affective-performance bridge is the next research boundary. |
| Human acceptance | Remains a human judgment and is not inferred from machine gates. |

The deterministic contract suite is currently reported as **342 passed, 0
failed, 0 skipped**. The recent correctness work also fixed three important
closed-loop defects: ungated phase transitions, non-transactional canonical
persistence, and graph traversal over missing Watch vertices.

### What This Proves

The current run demonstrates that one persistent persona can:

1. select grounded multimodal residue;
2. construct a bounded synthetic dream with traceable source lineage;
3. receive and inspect a real rendered artifact;
4. distinguish renderer evidence from psychological interpretation;
5. persist a synthetic dream, observation vertices, ToM candidates and edges;
6. retrieve the dream from differently worded queries;
7. use the dream in a later response while marking it as a dream; and
8. preserve the literal-history boundary and protected source records.

### What This Does Not Yet Prove

It does not yet prove:

- that multimodal dreaming is better than structured text reflection;
- generality across many personas, relationships, conflicts and providers;
- durable personality evolution across unrelated future situations;
- strong predictive Theory of Mind or false-belief reasoning;
- embedding-certified whole-clip character identity;
- frame-accurate lip synchronization;
- ideal or even reliably distinguishable emotional voice performance; or
- human subjective acceptance of the dream video.

## The Honesty Rule

One kind of evidence must never silently become another.

| Evidence class | Meaning | Owning boundary |
|---|---|---|
| Historical memory or present event | Something that belongs to the persona's real history | Memory / Graph Memory |
| Dream intention | What Persona Dream planned, scripted or asked a renderer to create | Persona Dream |
| Rendered observation | What is actually visible, audible, spoken, absent or temporally present | `watch` |
| Persona interpretation | A tentative reading of the observed dream against grounded memory | Persona Dream interpretation gate |
| ToM or social-state candidate | A bounded belief, fear, desire, trust, stance, relationship or uncertainty proposal | Graph Memory validation |
| Adaptive state proposal | A proposed change to a disposition, relationship expectation or coping strategy | Graph Memory promotion policy |
| Durable identity change | A promoted change to canonical identity, worldview, goals or voice identity | `create-persona` |
| Voice performance | Audible expression of an already accepted response state | Chatterbox |

A dream record therefore remains explicit:

```json
{
  "synthetic_origin": true,
  "literal_historical_event": false
}
```

A renderer defect can be psychologically suggestive, but it cannot become a
fact about the persona merely because the generated video contains it. A dream
may propose a state change; it may not silently rewrite identity.

## Architecture

```text
create-persona
  protected identity, values, voice identity and regression tests
        |
        v
graph-memory-operator
  historical events, multimodal memories, relationships, current affect,
  social-state evidence, emotional salience and recall policy
        |
        v
persona-dream
  residue selection -> conflict model -> story -> crew -> contact sheets
  -> script DNA -> look lock -> storyboard -> provider contract
        |
        v
renderer / provider
  bounded synthetic media
        |
        v
watch
  frames, transcript, sound, scenes, visible entities, actions, absences,
  identity evidence, speaker visibility and coverage gaps
        |
        v
persona-dream interpretation
  intended dream vs observed dream + source-memory grounding + uncertainty
        |
        v
graph-memory-operator
  dream episode + observation vertices + interpretation vertices + ToM/social
  state candidates + causal lineage + commit visibility + semantic retrieval
        |
        v
future conversation
  literal memories and synthetic dreams retrieved as distinct evidence classes
        |
        v
chatterbox
  evidence-linked affective performance; expression, not psychological authority
```

## Pipeline: 01-16

| Phase | Core question | Durable output | State |
|---|---|---|---|
| 01 - Idea and Memory Residue | What conflict is worth dreaming about, and which memories support it? | Immutable idea, residue links, contradictions, source IDs | Qualified |
| 02 - Story | What bounded drama emerges from the accepted residue? | Story contract and relationship pressure | Qualified |
| 03 - Crew | Which creative lenses shape the transformation? | Producer, writer, director and reviewer authority contracts | Qualified |
| 04 - Contact Sheets | Which people, objects and environments must remain stable? | Character, prop, environment and reference evidence | Qualified |
| 05 - Voices | How should characters sound without giving voice authority over psychology? | Voice references, boundaries and handoff plan | Qualified |
| 06 - Script | How does conflict become timed action and dialogue? | Script contract, beats, interaction coverage and physical stakes | Qualified |
| 07 - Storyboard | What must each shot visibly contain? | Accepted frames, prompt contracts, identity and continuity receipts | Qualified |
| 08 - Media Lock | Which accepted assets are frozen for provider use? | Hash-bound media subset | Qualified |
| 09 - Provider Selection | Which provider best fits the scene and constraints? | Registry evidence, scorecard and selected route | Qualified |
| 10 - Provider Contract | Exactly what will be sent, under which cost and authorization boundary? | Canonical payload and approval contract | Qualified |
| 11 - Submit and Return | Did one authorized request produce a valid artifact? | Submit, poll, download and FFprobe evidence | Live accepted successor return |
| 12 - Watch Observation | What actually exists in the returned media? | Evidence-only observation packet and Watch vertices | Live |
| 13 - Self-Interpretation | What might the observed dream mean against source memory? | Grounded interpretations with uncertainty and alternatives | Live |
| 14 - ToM Validation | Which social-state proposals are sufficiently grounded? | Accepted and rejected ToM candidates | Live |
| 15 - Persistence | Can the synthetic episode be stored without becoming false history? | Staged write set, canonical records, commit manifest and exact rereads | Live |
| 16 - Recall and Behavior | Does the persona later use the dream appropriately and remain itself? | Recall, traversal, literal-boundary and identity-stability receipts | Machine-decidable slice live-proven |

The ordinary interface is intended to become simple: a persona says `dream` or
`dream about Kai and the surf trip`, and the system executes the accepted loop
behind the scenes. The current runtime still exposes specialist commands and
receipts because this remains a research system.

## Embry and Kai: Working Example

The founding example begins with a stolen sick day at Kahaluʻu Bay. Embry and
Kai want to surf, but the scene is built around several linked conflicts:

- autonomy versus obligation;
- independence versus accepting correction;
- desire versus restraint;
- competence versus fatigue and vulnerability;
- and intimacy versus control in Embry's relationship with Kai.

The pipeline does not merely label those themes. It turns them into observable
mechanics:

- Embry's phone buzzes from the beach as a physical reminder of obligation;
- heat and humidity soften the board wax;
- her palm slips and she must reset her grip;
- the lava reef and lineup etiquette make restraint materially necessary;
- Kai gives one practical warning rather than taking over her decision;
- Embry waits, then commits through the safe channel when the choice is hers.

The accepted Script DNA names the conflict as **autonomy versus obligation** and
the theme as **earned autonomy: choosing carefully is the rebellion**. The Look
Lock uses waterline photography, a moderate wide lens, hard June daylight, warm
natural color, restrained camera drift and identity-readable blocking. The final
beat gives Embry the forward movement while Kai remains outside the decision
point.

This is why the production stages matter. Story, crew, camera and color are not
just decoration: they determine how the persona distributes agency, stages care,
embodies danger and resolves conflict.

### What a Human Can Learn From the Dream

A human reviewer can ask:

- Does the visual staging actually preserve Embry's autonomy?
- Is Kai framed as a trusted equal, a controller, or a passive witness?
- Does the environment make her caution competent or fearful?
- Does the editing allow her hesitation to exist?
- Does the voice sound restrained, defensive, relieved or falsely resolved?
- Does the generated artifact expose a contradiction that the text reflection hid?

Even if the cinematic path does not outperform text reflection as machine
learning, it can still be valuable as an inspectable performance of the agent's
current self-model.

## Graph Memory Operator Integration

Graph Memory Operator is the canonical persistence, retrieval and state-promotion
authority. Persona Dream should submit typed evidence and proposals; it should
not own a parallel memory database or directly mutate durable personality.

### Current Stored Structure

The current closed-loop implementation stores or traverses:

```text
persona_memory                 synthetic dream and source memories
persona_dream_watch_evidence   immutable evidence-only Watch vertices
tom_candidates                 bounded social-state candidates
persona_memory_edges           derived_from and observed_in_scene edges
tom_edges                      supports_interpretation edges
persona_dream_canonical_staging
persona_dream_commit_manifests
```

The commit path now stages and rereads the complete write set before publication,
then binds the published records to an active commit manifest.

### Active Hardening Work

The integration is being hardened around these principles:

1. **Graph Memory owns the schema.** Dream collections, indices, migrations,
   commit visibility and vector synchronization belong in Graph Memory Operator.
2. **Every key is namespaced.** Dream, observation, interpretation, ToM and voice
   records include persona, dream and revision identity to prevent cross-dream
   collisions.
3. **Interpretations are vertices.** The graph preserves the full chain from
   observation to tentative interpretation to validated social-state proposal.
4. **Causal families are explicit.** Derived frames, observations and reflections
   do not count as independent evidence merely because one event produced many
   records.
5. **Synthetic depth is bounded.** A dream can reorganize evidence but cannot
   create a new historical root or recursively confirm itself.
6. **Commit visibility is enforced at recall.** Pending, incomplete, quarantined
   or uncommitted records are excluded from ordinary retrieval.
7. **State changes use a promotion ladder.** Episodic affect may change quickly;
   adaptive dispositions require repeated independent evidence; protected identity
   changes require a separate `create-persona` workflow.
8. **Dream-aware recall is typed.** Literal memories, synthetic dreams, active
   conflicts, adaptive dispositions and protected identity are returned as
   separate evidence classes.

A target state-delta proposal looks like:

```json
{
  "state_key": "relationship.kai.accepts_correction_without_loss_of_autonomy",
  "proposed_delta": 0.06,
  "root_event_ids": ["event-014", "event-027"],
  "dream_support_ids": ["dream-004"],
  "independent_real_event_count": 2,
  "synthetic_support_count": 1,
  "confidence": 0.58,
  "counterevidence_ids": [],
  "decay_policy": "decay_unless_reinforced",
  "status": "proposed"
}
```

The dream may support that proposal. It must not be the sole evidence that
promotes it.

## Chatterbox Integration

Chatterbox is the speech renderer. It already accepts structured tone, delivery
stage, pace, pause strategy and chunk-level delivery arcs through the Tau voice
request path. Memory and the coordinator decide the response and affective
policy; Chatterbox makes the accepted plan audible.

The next boundary is not merely “render a line from the dream.” It is to compile
the dream's accepted conflict into an **affective-performance contract** for the
persona who experienced it.

A target contract includes:

```json
{
  "schema": "persona_dream.affective_performance_contract.v1",
  "persona_id": "embry",
  "dream_id": "dream-004",
  "conflict": {
    "pole_a": "personal autonomy",
    "pole_b": "accepting trusted correction",
    "agency_owner": "embry",
    "resolution": "correction informs her choice without replacing it",
    "resolution_state": "partial",
    "residual_uncertainty": 0.32
  },
  "protected_identity": [
    "independence",
    "competence",
    "honesty about uncertainty"
  ],
  "performance_arc": [
    {"role": "recall obligation", "tone": "memory_uncertain", "pace": "measured"},
    {"role": "acknowledge warning", "tone": "careful_concerned"},
    {"role": "reassert chosen agency", "tone": "firm_boundary"},
    {"role": "settled recognition", "tone": "relieved"}
  ]
}
```

The chunk arc must follow semantic clauses, not generic sentence position. A
complex emotional conflict should not be reduced to a single global label such
as `concerned` or `positive`.

### Voice Evaluation

Text and audio must be evaluated separately.

**Text route**

- Was the dream retrieved from active canonical memory?
- Was it identified as synthetic?
- Did the answer preserve the source evidence and protected identity?
- Did it express the intended conflict without inventing history?

**Audio route**

- Was speaker identity preserved?
- Did timing, energy, pitch, rate and pauses follow the intended arc?
- Did the audio contradict or flatten the text?
- Can blind human listeners perceive the intended ambivalence, agency and
  resolution?

ASR verifies wording. It does not verify emotional performance.

## Research Evaluation

The central experiment is a matched comparison, not another demonstration video.

| Condition | Memory treatment |
|---|---|
| A | Source memories only |
| B | Source memories plus ordinary summary |
| C | Structured text reflection |
| D | Cinematic dream plan without rendered media |
| E | Rendered dream without Watch |
| F | Rendered dream plus Watch and graph consolidation |
| G | Full condition F plus dream-derived Chatterbox performance plan |

This design isolates the value of each layer:

- C vs D: does rich production planning add value before rendering?
- D vs E: does the artifact add value beyond the plan?
- E vs F: does independent re-perception prevent false assumptions and improve use?
- F vs G: does the consolidated conflict survive into audible performance?

Measure:

- human insight into conflict, agency and unresolved tension;
- grounded later recall;
- social prediction and ToM calibration;
- identity stability and contradiction rate;
- literal-memory confusion;
- appropriate adaptive-state change;
- text-route persona consistency;
- audio-route persona and emotion consistency;
- cost, latency and failure rate.

The full system earns its complexity only if it beats a simpler reflection on at
least one important outcome without increasing false memories, identity drift or
unsafe personalization.

## Quick Start

```bash
cd skills/persona-dream

# Read current project knowledge.
./run.sh read

# Run the offline deterministic contract suite.
./run.sh test-suite

# Build a fixture-backed dream packet without memory side effects.
./run.sh generate \
  --persona embry \
  --fixture scripts/fixtures/sample_residue.json \
  --output-dir /tmp/persona-dream-smoke

# Recall live persona residue.
./run.sh generate --persona embry

# Bias residue selection toward a topic.
./run.sh generate --persona embry --about "Kai, trust and autonomy"

# Create bounded video-planning material.
./run.sh generate --mode video_plan --persona embry
```

Writing a reflection remains explicit:

```bash
./run.sh generate --persona embry --write-memory
```

The full accepted provider, Watch, interpretation, commit and voice loop is still
operated through specialist phase commands and receipts while the unified
`dream` / `resume` interface is being hardened.

## Evidence and Project History

The README intentionally contains one current state rather than a stack of
chronological updates. Detailed execution history, superseded states and repair
notes belong in:

- [`HANDOFF.md`](HANDOFF.md);
- [`PROJECT_KNOWLEDGE.md`](PROJECT_KNOWLEDGE.md);
- `reports/pipeline-complete/`; and
- revision-scoped receipts under
  `reports/pipeline-complete/.persona-dream/revisions/`.

Primary current evidence includes:

```text
rev_successor_943b01ecd9a3/acceptance_rung_receipt.v1.json
phase_11_submit_return/.../post_return_acceptance_receipt.v2.json
watch_gauntlet/59b9ff3155d6/cognitive_loop/cognitive_loop_receipt.json
watch_gauntlet/59b9ff3155d6/cognitive_loop/retroactive_reconciliation_receipt.v1.json
phase_16_behavior_evaluation/corrected_traversal_receipt.v1.json
phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json
.persona-dream/state/green_canonical_lane_reconciliation_receipt.v1.json
```

A receipt proves only the boundary it names. Human acceptance remains human.

## Proof Discipline

- Do not invent residue when recall is empty.
- Preserve source IDs, hashes, timestamps, run IDs, revision IDs and causal roots.
- Treat prompts and scripts as intention, not evidence of rendered contents.
- Treat Watch outputs as observations, not automatic psychological truth.
- Keep literal history, synthetic dreams, interpretations and state proposals
  structurally distinct.
- Do not count derived records as independent confirmation of their root event.
- Do not expose incomplete commits through ordinary recall.
- Do not promote one dream into a durable identity rewrite.
- Let models propose; deterministic policy and owning systems decide promotion.
- Evaluate spoken persona on both text and audio routes.
- Publish failures and null results, including dreams that add cost without adding
  insight.

## Related Research

Persona Dream is informed by, but not equivalent to:

- [Generative Agents](https://arxiv.org/abs/2304.03442) — experience streams,
  reflection and later behavior;
- [Reflexion](https://arxiv.org/abs/2303.11366) — verbal feedback stored as
  episodic memory;
- [M3-Agent](https://arxiv.org/abs/2508.09736) — multimodal long-term episodic and
  semantic memory;
- [Auto-Dreamer](https://arxiv.org/abs/2605.20616) — offline provenance-linked
  memory consolidation;
- [Camera Artist](https://arxiv.org/abs/2604.09195) — multi-agent cinematic
  planning and recursive storyboards;
- [ManimAgent](https://arxiv.org/abs/2606.30296) — render, visually evaluate and
  retain cross-task positive and negative experience;
- [PED](https://aclanthology.org/2026.findings-acl.445/) — separate text-route and
  audio-route persona diagnostics; and
- [ActorMind](https://aclanthology.org/2026.findings-acl.1718/) — role, emotional
  state reasoning and expressive speech delivery.

## Internal References

- [`SKILL.md`](SKILL.md) — current operational contract
- [`GOAL.md`](GOAL.md) — immutable goal and acceptance criteria
- [`create-persona`](../create-persona/SKILL.md) — identity authority
- [`memory`](../memory/SKILL.md) — Memory First and persistence contract
- [`watch`](../watch/SKILL.md) — evidence-first media perception
- [`create-movie`](../create-movie/SKILL.md) — long-form media and audio lane
- [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator)
- [Chatterbox](https://github.com/grahama1970/chatterbox)
