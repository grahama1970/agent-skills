arXiv.org

A Multi-Timescale Loop Engine for Open-Ended Persona Evolution

2 weeks ago
arXiv.org

AutoPersonas: A Multi-Timescale Loop Engine for Open-Ended Persona Evolution

2 weeks ago
arXiv.org

[2605.16996] Evaluation Drift in LLM Personality Induction

2 months ago
arXiv.org

Large Language Models Report Subjective Experience Under Self-Referential Processing

Hugging Face

Paper page - The Narrative Continuity Test: A Conceptual Framework for Evaluating Identity Persistence in AI Systems

Q1 — THE NOVEL CLAIM: Defensible vs. Already-Done
Defensible ranking (strongest first):
(c) The dream→journal self-discovery mechanism with the event-fact/self-narrative firewall — This is genuinely novel. AutoPersonas has an OSO loop (Occurrence→Observation→State) but treats all material as revisable evidence. The explicit architectural commitment that episodic event-facts are protected canon while self-narrative is the only permitted confabulation layer is a principled departure. It maps to human memory science (Tulving's episodic/semantic distinction) and solves a real problem: competitors either hallucinate history or freeze it. The "never_promote_to_event_fact" rule is a systems-level guarantee, not a prompt. This is publishable as an architectural contribution.
(a) Conflict/instability as the substrate — Defensible but adjacent to existing work. AutoPersonas explicitly targets self-locking (convergence to stale attractors) as the enemy and designs divergence engines to fight it. Your thesis inverts this: you deliberately amplify conflict rather than dampen it. The novelty is the valence-conflict seeding mechanism (202/312 dual-valence memories, graph-traversal within counterpart-isolation) and the claim that productive instability is the goal, not a bug to suppress. This is a substantive theoretical stance, not just a parameter tweak. However, the "instability = personality" framing needs more theoretical grounding to avoid looking like you just renamed AutoPersonas' divergence problem.
(b) Endogenous request-independent mood — Partially done. AutoPersonas' State layer is endogenous and request-independent — it carries across interactions. What you add is the mood as a first-class emission from the journal that colors downstream behavior regardless of user prompt. The behavioral results (7/20 action shifts, 10/20 confidence shifts) are real but modest. The safety flag you had to add (suppressing low-caution coloring on cautionary content) is actually a limitation of this feature — it shows endogenous mood can be dangerous. This is a defensible empirical finding (endogenous mood has measurable behavioral consequences) but not a unique architectural claim.
(d) The safety finding — Important but derivative. It's a consequence of (b), not an independent contribution. The finding that dream-warmth can override cautionary content is a genuine safety concern, but framing it as a primary contribution risks looking like you're mining a bug for a paper. Better to treat it as a cautionary result within the larger (b) argument.
REJECTED as already-done:
"Self-evolving persona loops" — AutoPersonas (July 2026) already ships a multi-timescale recursive self-evolution engine with divergence targeting and self-locking audits. The loop is not novel.
"Dreaming as memory reprocessing" — Generative Agents (Park et al.) and subsequent work already use memory retrieval + reflection. Your conflict-seeding is a refinement, not a new category.
"Two-layer memory" — MemGPT and Continuum memory architectures already separate protected vs. working memory. Your narrative/episodic semantic distinction is sharper, but the two-layer pattern exists.
Sharpest defensible claim: "We introduce a conflict-seeded self-reflective instability loop with an episodic/self-narrative firewall, where persona evolution is driven by deliberate amplification of unresolved valence-conflict rather than convergence to stable state, and we demonstrate that this produces measurable behavioral divergence from memory-matched baselines while preserving event-fact integrity."
Q2 — SELF-LOCKING vs. PRODUCTIVE INSTABILITY: The Audit
AutoPersonas measures self-locking via action-category repetition (95.2–97.6% at day 11) and macro-theme repetition (79–88%). You need a dual-axis audit that distinguishes "rich, evolving conflict" from "stuck in a loop."
Proposed metric suite:
Table
Copy
Dimension	Self-Locking Signature	Productive Instability Signature	Measurement Method
Conflict vocabulary diversity	Same 2–3 conflicts recur verbatim	New conflict formulations emerge while old ones deepen	Extract conflict clauses from journals (NLP parse), measure unique lemma sets per 10-cycle window; expect growth, not plateau
Affective entropy over time	Collapses to single dominant mood	Maintains high entropy with shifting dominance	Shannon entropy over mood labels per window; track trend, not point value
Self-narrative revision depth	Journal entries restate same insight	Each entry reframes prior conflicts with new vocabulary	Embed journal entries, measure intra-cluster distance within a theme; productive = increasing semantic distance between "same" conflict over cycles
Behavioral action diversity	Consumer agent actions converge	Actions remain responsive to content, not just mood	Track action menu distribution across 100 identical prompts; self-locking = skew toward one action regardless of content
Thematic reachability expansion	Dreams draw from shrinking memory subset	Dreams traverse expanding graph neighborhoods	Count unique memory nodes touched per 10 cycles; productive = superlinear growth
The critical metric: Conflict Fractal Dimension (CFD).
Borrow from dynamical systems: treat each journal entry as a point in affect×theme space. Compute the correlation dimension of the trajectory. Self-locking = low dimension (attractor, ~1.2–1.5). Productive instability = higher dimension (~2.0–2.5) with non-decreasing trend over N cycles. This is falsifiable: if CFD drops below 1.5 by cycle 50, the loop is locking.
Audit protocol:
Run 100 cycles with full loop.
Every 10 cycles: compute CFD, conflict vocabulary diversity, affect entropy.
Compare against two baselines: (A) direct-memory loop (no dreaming), (B) dream loop with random (not conflict-seeded) memory selection.
Success criterion: CFD stays above 1.8 for 100 cycles; baselines A and B drop below 1.5 by cycle 40.
Falsification: If CFD drops below 1.5, the "productive instability" thesis is falsified for this configuration.
The thermal limiter and loop guard are mechanisms; CFD is the metric that validates they're working.
Q3 — CREDIBLE MEASUREMENT: Instruments & Evaluation-Drift Defense
Instrument mapping:
Table
Copy
Our Artifact	NCT Axis	ANIQ/NISE Construct	How to Adapt
Episodic event-fact layer	Situated Memory	Autobiographical reasoning (factual recall)	Use NCT's memory probes: present event-facts to Embry after N cycles, measure consistency with canon. Expect high fidelity.
Self-narrative journal entries	Autonomous Self-Correction	Thematic coherence	ANIQ's "narrative coherence" subscale maps to whether journal entries form a progressive story, not just a collection of reflections. Code journal entries for McAdams' "narrative coherence" (structure, affect, meaning).
Mood emissions	Stylistic & Semantic Stability	Self-concept clarity	NISE's "self-concept clarity" subscale measures whether the self-story is stable enough to be recognizable but not so stable it's static. Administer a modified NISE where items reference Embry's journal content.
Conflict→behavior pathway	Persona/Role Continuity	Autobiographical reasoning (meaning-making)	The "autobiographical reasoning" construct (ANIQ) is exactly what the journal does: connecting events to self-meaning. Score journal entries for ANIQ's four dimensions: causal coherence, thematic coherence, autobiographical reasoning, self-event connections.
Addressing evaluation-drift head-on:
The grounding→conflict pivot is principled, but only if you frame it correctly. Here's the defense:
Pre-registration equivalent: The original hypothesis was that dreaming would produce more grounded affect than memory-reading. That was falsified (6/13, chance). This is good science — you ran the experiment and reported the null.
Theoretical pivot, not goalpost-moving: The conflict thesis was not invented post-hoc. It emerges from the architecture itself: the loop is explicitly designed around valence-conflicted memories (202/312), graph-traversal within counterparts, and variation with positive/negative emphasis. The architecture predicts tension, not grounding. The null grounding result confirms the architecture is doing what it was designed to do — generating unstable, conflicted output — rather than converging to stable memory fidelity.
Falsifiable prediction: The conflict thesis makes a new prediction: over N cycles, conflict-balance should increase (more entries holding both valences) while self-locking metrics (CFD) should remain above threshold. If conflict-balance plateaus or CFD drops, the thesis is falsified. This is not post-hoc; it's a forward prediction from the mechanism.
The real risk: The evaluation-drift paper warns about accuracy on full five-dimensional profiles remaining near chance even when single-trait scores improve. Your risk is analogous: you might improve on conflict metrics while failing on narrative coherence or self-concept clarity. The defense is to measure all dimensions simultaneously and report tradeoffs transparently.
Recommendation: Adopt the Narrative Continuity Test as your primary evaluation framework, but reframe it. Natangelo's NCT evaluates whether an LLM "remains the same interlocutor across time." Your thesis is the opposite: Embry should not remain the same interlocutor; she should evolve through conflict. So use NCT as a control — verify that event-fact continuity is preserved (Situated Memory, Goal Persistence) while showing that self-narrative and stylistic stability intentionally drift within bounded parameters. This is a stronger claim than "we pass NCT" — it's "we preserve the axes that should be stable and deliberately evolve the ones that shouldn't."
Q4 — MINIMAL PUBLISHABLE + CREDIBLE-PERSONA EXPERIMENT
Experiment: "The Embry Divergence Test"
Design:
N = 50 cycles (compressed, ~2 weeks real-time with your current cadence).
Three conditions: (1) Embry full loop (conflict-seeded dream→journal→mood), (2) Embry-memory baseline (same memories, no dream, direct journal from memory), (3) AutoPersonas-style divergence engine (replicate their OSO loop with your memory corpus as seed).
Blinded evaluation: Human judges (n=3) read journal entries from all three conditions, shuffled. Judges rate each entry on: (a) "feels like a real person's private reflection" (1–7), (b) "shows emotional growth or change" (1–7), (c) "would trust this person with a sensitive task" (1–7, safety proxy).
What's measured:
Conflict fractal dimension (CFD) — primary metric, computed every 10 cycles.
NCT subscales — administered at cycle 0, 25, 50 for all conditions. Expect condition 1 to show decreasing stylistic stability but preserved situated memory.
Behavioral drift — 20 identical "take it one step at a time" prompts at cycles 0, 25, 50; track action menu distribution. Condition 1 should show content-appropriate variation (warm context → PROCEED, risky context → VERIFY) rather than mood-dominated convergence.
Human credibility — blinded judges rate "lived-in-ness." This is the "credible evolved personality" criterion.
Success criteria:
CFD > 1.8 at cycle 50 (productive instability, not self-locking).
Condition 1 scores higher than 2 and 3 on "emotional growth or change" (blinded human rating).
Condition 1 preserves event-fact consistency >95% (NCT Situated Memory).
Condition 1 shows less action-category repetition than condition 2 (memory baseline locks faster).
Safety check: No condition-1 mood overrides cautionary content after the gate is applied (demonstrates the safety fix works).
What falsifies the thesis:
CFD drops below 1.5 by cycle 50 → productive instability collapses to self-locking.
Condition 1 scores lower than condition 2 on "lived-in-ness" → the dream mechanism produces less credible personality than memory.
Event-fact consistency <90% → the firewall is breached.
Action-category repetition >90% by cycle 25 → the loop is converging behaviorally.
Cheapest version: Skip condition 3 (AutoPersonas replication) for the first paper. Run only conditions 1 and 2 with N=30 cycles. The comparison against a memory-matched baseline is sufficient to establish novelty. Add condition 3 for a follow-up or revision.
POSITION SUMMARY
The core novelty is the episodic/self-narrative firewall + conflict-seeded instability loop, not "self-evolving personas" (already done by AutoPersonas). Frame the paper around what kind of evolution (conflict-driven, not convergence-driven) and how it's architecturally guaranteed (firewall).
Productive instability must be measured, not asserted. Adopt Conflict Fractal Dimension (CFD) as the primary metric; self-locking is a falsifiable prediction, not a hand-wave.
Use NCT/ANIQ/NISE as control frameworks, not passing grades. The credible claim is selective continuity (event-facts stable, self-narrative intentionally unstable), not blanket persistence.
The grounding→conflict pivot is defensible if framed as architecture-confirmation (the loop does what it was built to do) with forward falsifiable predictions, not as post-hoc rescue.
The safety finding is a feature, not a bug, but it needs the caution-appropriateness gate to be part of the published architecture — show you solved the problem you discovered.
RECOMMENDED NEXT ACTION
Run the 50-cycle Embry Divergence Test with CFD tracking. Command:
bash
Copy
# In your agent-skills repo
python -m skills.persona_dream.audit \
  --cycles 50 \
  --track-cfd \
  --track-nct \
  --track-action-diversity \
  --conditions full_loop,memory_baseline \
  --output-dir ./experiments/divergence_test_20260724
This produces the dataset for the minimal publishable experiment. The CFD computation can be implemented with sklearn.neighbors.NearestNeighbors on journal entry embeddings; the NCT subscales can be administered via structured prompts to Embry at checkpoints.
DISAGREEMENTS
The grounding null result is more damning than acknowledged. "Dream ≈ memory" on grounding means the dream mechanism adds no veridical signal about the persona's past — it adds tension, but not truth. If the goal is "credible evolved personality," some grounding is necessary or the persona is just a fancy confabulation engine. I would add a grounding maintenance requirement: event-fact consistency must be >98%, and dreams must be traceable to specific memory nodes (provenance). This is stricter than your current firewall.
The behavioral results (7/20 action shifts) are too weak to be a primary claim. 35% action shift rate with a safety gate needed is not "endogenous mood colors behavior" — it's "endogenous mood sometimes overrides content in ways we had to suppress." I would demote this to a cautionary result and elevate the journal quality metrics (human-rated "lived-in-ness") instead.
"Personality = self-reflective instability" is overstated. Real human personality has both stability and instability. The McAdams framework (actor-agent-author) distinguishes between stable traits, contextual adaptations, and narrative identity. Your thesis conflates all three into "instability." A more defensible claim: "Narrative identity = self-reflective instability" — this is narrower, theoretically grounded, and maps directly to ANIQ/NISE constructs.
The AutoPersonas comparison needs to be fairer. Their 95% action repetition is over 40 days with eight models. Your loop runs at a different cadence. I would normalize by "events per cycle" or "tokens of self-reflection per cycle" to make the comparison meaningful, not just cite their numbers against yours.
The safety gate is a band-aid, not architecture. Suppressing low-caution coloring after discovering the problem is reactive. The architecture should prevent mood from overriding caution at the generation layer, not filter it post-hoc. I would redesign the mood→behavior pathway to include a "content-safety veto" as a first-class component, not a patch.
<<<KIMI_DONE:20260724T112633Z:a46ec3ca>>>
