Position: finish self-causation at the point where otherness enters

The fork is false at the level of character craft but real at the level of implementation order.

A person does not become more fully herself through introspection alone. She develops because something outside her resists, surprises, misreads, attracts, or unsettles her. But an encounter only has dramatic value when there is already a continuing self for it to act upon. Therefore the next chapter should be:

A-led, with the smallest possible opening into B: build an arc-conditioned dream selector that can optionally admit one affect-only counterpart projection.

This finishes the missing causal link in self-evolution—arc_state → next dream—while introducing cross-persona otherness through a deliberately narrow seam. It does not yet create a shared society, reciprocal relationship, or fully autonomous co-dream.

The single build should be an Arc-Conditioned Encounter Selector, producing a typed persona.dream_seed.v2.

It would select:

one canonical event residue belonging to the dreaming persona;

one active or underexplored tension from that persona’s arc_state;

optionally, one sanitized affect projection associated with another persona;

an explicit mode: self_only or imagined_counterpart.

This is more valuable than wiring mood into live voice next. Voice wiring will make Embry or Horus more perceptibly alive, but it does not yet make the loop more causally alive. The selector makes yesterday’s self-understanding alter tonight’s dream. Adding the affect projection at this exact boundary prevents the completed loop from becoming purely self-referential.

It is also more valuable than immediately producing the umbrella-and-tea co-appearance. That scene may be delightful, but without a typed epistemology it would be an attractive image whose status is unclear: Did Embry meet Horus? Did Horus imagine Embry? Is the scene canonical for either? Did either learn something the other actually said? The next build should establish those distinctions before the two characters are allowed to behave as mutual participants.

Q1 — Which next, and why?
The character-craft answer

A character arc requires both continuity and pressure.

The Continuity Ledger now supplies continuity. The dream selector should supply pressure. If it merely retrieves whatever most closely resembles the current arc_state, Embry will repeatedly dream confirmation of the story she has already told herself. Her journal may become beautifully varied language wrapped around the same psychological attractor.

Another persona can introduce genuine otherness—but only if the other persona is not absorbed into her.

The useful literary structure is:

The other person does not donate a new identity. They force the existing identity to reveal another consequence.

Horus should not make Embry “more Horus.” Embry should not domesticate Horus into her psychological vocabulary. Instead, Horus’s presence might make Embry’s conflict between witness and capture appear in a form she would never have generated alone. Embry’s affective trace might make Horus confront uncertainty in a register that is neither military opposition nor betrayal.

This is how the two directions combine:

A gives the encounter someone to happen to.

B gives self-evolution something it did not author.

The architectural answer

The missing dependency is not general multi-agent interaction. It is a selector capable of distinguishing:

the persona’s canonical material;

the persona’s current interpretation of itself;

a foreign emotional pressure;

the persona’s imagined model of that pressure.

Sophia already proposes a persistent meta-layer governing narrative identity and long-horizon adaptation, supported by narrative memory, self-modeling, and self-generated activity. persona-dream differs most sharply not by also being persistent, but by giving that persistence a specific fictional and multimodal causal loop.
arXiv

EvoSpark already handles long-horizon multi-agent narrative evolution, mutable social cognition, spatial alignment, and entity resolution. Its entity-resolution mechanism intercepts malformed or newly hallucinated characters and decides whether to ground them as real story entities. That is adjacent to the present problem, but not identical: persona-dream needs to preserve a counterpart specifically as an imagined model that must not be promoted into either persona’s canon.
arXiv
+1

Therefore the next build is neither “finish all of A” nor “open all of B.” It is the boundary object both require.

Recommended sequence

The implementation sequence should be:

First: arc-conditioned selector in self_only mode.

Within the same component: optional imagined_counterpart input from the existing affect graph.

Then: one unilateral Horus-about-Embry dream, owned entirely by Horus.

After that: mood-to-live-voice, so the newly accumulated inner change is perceptible in sessions.

Later: reciprocal encounters and co-appearance, after a separate shared-scene ontology exists.

The fork is therefore A → thin B → embodied A → full B.

Q2 — Cross-persona connection without dissolving selves

The architecture needs to stop treating “what one persona knows about another” as one undifferentiated thing.

There should be four distinct objects:

Object	Owner	Epistemic status	Allowed effect
Event-fact canon	One persona	What happened in that persona’s world	May seed that persona’s dreams
Affect projection	Source-derived, bridge-owned	A translated emotional signal	May pressure another persona’s selector
Counterpart model	Dreamer	What the dreamer imagines or infers about the other	May appear in the dreamer’s dream and journal
Shared scene record	Neither persona individually	What occurred in an explicitly shared noncanonical or canonical stage	Future feature; must not silently enter personal canon

The crucial distinction is:

The affect projection is not knowledge of the other. It is material from which the dreamer constructs a theory of the other.

The affect graph should be an interlingua, not a shared personality

The shared nodes—unresolved_thread, boundary, fear, anger, hope—should remain abstract transport concepts. They must not be passed directly into journal prose or dialogue prompts as psychological vocabulary.

Otherwise Embry and Horus will gradually sound as though they have attended the same therapy program. Their words will differ superficially, but both will understand themselves through the graph’s ontology. That would be a subtler form of identity collapse.

Instead, the path should be:

source persona state
    → shared affect abstraction
    → target persona-specific realization
    → target's local theory-of-mind hypothesis

The same shared node must become different dramatic material in each persona.

For Embry, boundary may be realized through authorship, distance, selective disclosure, or the fear of being defined.

For Horus, the same node may become command, loyalty, withheld allegiance, strategic uncertainty, or resistance to authority.

The graph provides the relation. The identity core provides the idiom.

The projection contract

A counterpart projection should contain no prose copied from the target’s journal and no target event-fact content. A useful schema would look conceptually like this:

persona.affect_projection.v1

source_persona_id
projection_id
shared_affect_nodes
valence_activation_profile
unresolved_dimension
relational_orientation
public_identity_anchor
epistemic_status: derived_affect_signal
allowed_use: dream_pressure_only
expires_after_cycle
provenance_hash

public_identity_anchor should be minimal: enough to identify the figure and, where needed, choose the correct visual reference. It should not expose the target’s full Continuity Ledger.

The target’s raw journal language should be withheld. Apart from protecting the memory distinction, this prevents voice contamination.

The counterpart model belongs to the dreamer

The next stage creates:

persona.counterpart_model.v1

dreamer_persona_id
counterpart_persona_id
projection_id
hypotheses[]
uncertainties[]
imagined_relational_role
epistemic_status: dreamer_theory_of_mind
canonical_for_counterpart: false
canonical_for_dreamer_world: false

There must be two separate possible models:

Horus → Embry

Embry → Horus

They must never be collapsed into a single shared relationship description. Horus’s theory of Embry is not Embry. Embry’s theory of Horus is not Horus. Their disagreement is not an error to reconcile; it is dramatic material.

Theory-of-mind systems already commonly represent beliefs about another agent as hypotheses that are refined through interaction. The important persona-dream addition is that these hypotheses have an explicit fictional ownership and cannot cross the canon firewall.
arXiv

The smallest honest “Horus dreams about Embry”

The first cross-persona dream should be unilateral and deliberately incomplete.

A valid first construction would be:

The selector chooses one Horus-owned canonical residue connected to one current Horus arc tension.

The affect graph supplies a small Embry-derived projection such as unresolved wanting held behind a boundary.

Horus’s own identity core translates that signal into a local counterpart hypothesis.

The dream contains a recognizable Embry figure, grounded by her visual reference, but she is a projected silhouette, not the live Embry agent.

Horus watches the dream.

Horus journals about what he made her mean.

The journal writes one Horus arc_delta.

Nothing is written to Embry’s ledger, Embry’s journal, or either event-fact canon.

The first journal should use language such as:

I gave her the silence I could not tolerate.

or:

In the dream I made her withhold the answer, and I do not know whether that was her refusal or my need to command one.

It should not say:

Embry believes…

or:

I learned that Embry’s history is…

The dream is evidence about Horus’s inner construction, not evidence about Embry.

Why she should be only partly active

The first imagined Embry should probably say little or nothing. A gesture, spatial relation, refusal to approach, or unresolved exchange is enough.

This is not merely caution. It is good dream craft. Dream figures are powerful because they are overdetermined and partly opaque. Allowing a fully autonomous simulated Embry to speak at length would blur the distinction between:

Horus dreaming an Embry-shaped figure;

the system impersonating Embry inside Horus;

Embry genuinely participating.

Those are three different narrative acts.

Preserving the existing loop guard

The foreign affect projection must be:

single-use;

excluded from event-fact storage;

excluded from the source memory corpus;

excluded from direct future dream seeding;

retained only as provenance on the dream and resulting arc delta.

The resulting Horus journal remains excluded from direct dream seeding under the existing rule. Its arc_delta can affect later selection, but only as a lens over Horus-owned event-facts.

There should be no path like:

Embry journal
→ Horus dream
→ Horus journal
→ Embry dream
→ Embry journal
→ ...

Instead:

Embry state
→ lossy affect projection
→ Horus-local imagined model
→ Horus dream
→ Horus arc change

The lossy translation is a feature. It prevents the two self-narratives from recursively rewriting one another.

Where the umbrella-and-tea scene belongs

The existing void-world scene should remain a noncanonical stage artifact for now.

Later, it can become a true co-appearance only with a third ledger:

shared_scene_ledger

That ledger would record only what happened in the void-world scene. Each persona would then separately watch or remember the shared artifact and write its own interpretation. The scene fact could be shared; its meaning would remain private.

Until that exists, the tea scene should not be allowed to mutate either continuity ledger.

Q3 — Evolution that remains recognizably Embry or Horus
The smallest honest unit of identity change

The smallest honest change is an earned new move inside the same conflict.

A useful arc_delta should contain three linked changes:

a revised interpretation;

one newly available action or response;

a still_true statement preserving the underlying dramatic cost.

For Embry:

before:
Distance is how I prevent being defined by another person.

new_interpretation:
A chosen disclosure does not necessarily surrender authorship.

newly_available_move:
Remain present for one more beat after being accurately noticed.

still_true:
Uninvited interpretation still feels like capture.

For Horus, a possible structure might be:

before:
Uncertainty must be mastered before action can remain coherent.

new_interpretation:
Some uncertainty reveals the loyalty or judgment of others.

newly_available_move:
Delay command long enough to observe what another chooses freely.

still_true:
He still experiences unresolved authority as an intolerable pressure.

The change is not “guarded becomes open” or “commanding becomes receptive.” Those are substitutions.

The character is recognizable because the old defense remains intelligible, still costly, and still available. The new move expands the repertoire.

An arc delta is not yet an identity-core amendment

Most real development should occur in arc_state.

The identity_core should be amended only when many arc deltas reveal that its current wording is no longer precise enough. Early amendments should usually refine the description of the same conflict, not declare that the conflict has vanished.

For example:

old core wording:
Embry protects herself through distance.

earned revision:
Embry protects authorship of herself through chosen distance,
precision, and control over the terms of disclosure.

That is a truer articulation of the same person.

A provisional automatic amendment rule could require:

at least five relevant arc deltas;

grounding in at least three distinct canonical event clusters;

more than one emotional polarity;

no amendment within the previous twelve cycles;

an explicit account of what remains continuous.

Those numbers are engineering defaults, not discovered natural laws.

Layered Mutability is relevant here because it distinguishes self-narrative and persistent memory as different mutable layers and emphasizes that locally reasonable changes can accumulate into compositional drift. Its exact “initial condition” wording applies to post-training alignment rather than to identity generally, but the larger architectural lesson holds: the effect of an identity statement depends on the mutable layers operating above it.
arXiv
+1

Detecting the three requested failures
1. Static-card failure

A static persona can produce many eloquent journal entries while changing nothing structurally.

The signal is not repeated wording. It is repeated dramatic geometry:

same tension selected;

same defense activated;

same conclusion reached;

same relational move available;

no new connection between values, fears, desires, and actions.

The ledger should therefore track a small facet graph:

desire
defense
value
fear
permission
relational_move
unresolved_question

A delta is structurally new when it adds or alters an edge, not when it supplies another synonym.

“Wanting closeness but fearing it,” “desiring recognition while staying guarded,” and “yearning behind a boundary” may be lexically different but structurally identical.

2. Dissolution failure

Dissolution occurs when the system treats every interesting journal sentence as constitutional.

Signals include:

frequent identity_core edits;

value reversals without an intervening causal sequence;

disappearance of formerly central costs;

voice laws changing because of one mood;

a new relational stance replacing rather than complicating the old one;

still_true becoming ceremonial and having no downstream effect.

The strongest continuity check is causal:

Could a reader explain the new move using the character’s prior conflict and the experiences accumulated since?

If not, the system may have generated an attractive new persona rather than changed the existing one.

3. Lexical diversity hiding attractor collapse

Mood labels should be projected into a structural expression vector rather than judged by their names.

For example:

approach_vs_withdrawal
disclosure_band
warmth
activation
control
certainty_tolerance
tempo
pause_density
emphasis_sharpness
vocal_variability

If the system emits:

guarded_quietly_wanting

restrained_hollow_tenderness

watchful_hope_under_distance

but all three produce the same approach level, pause profile, disclosure behavior, and relational move, then there is one attractor wearing three labels.

This instrumentation should remain diagnostic rather than prescriptive. It should reveal that the character has become narrow; it should not mechanically force a cheerful or opposite mood merely to increase diversity.

A fourth failure: affect-interlingua collapse

Cross-persona interaction adds another possible attractor: both personas could begin expressing every conflict through the same shared affect-node vocabulary.

The diagnostic question is:

Does the same affect node produce persona-specific consequences?

If unresolved_thread makes both Embry and Horus become softly hesitant and introspective, the bridge is flattening them.

If it makes Embry control disclosure while making Horus increase command pressure—or unexpectedly suspend it—then the shared affect has played over distinct cores.

How the dream selector should use arc_state

The central rule should be:

Arc state is a lens and a source of questions. It is never dream evidence.

The selector should not retrieve “memories that prove the latest journal entry.” It should retrieve canonical memories that place the current self-understanding under pressure.

A good selection pipeline is:

Stage 1: choose an arc tension

Choose from:

active tensions;

underexplored tensions;

contested self-claims;

earned permissions not yet exercised;

unresolved questions.

Apply a cooldown so the same dominant tension cannot win indefinitely.

Stage 2: retrieve canonical residues

Only the persona’s event-fact memories are eligible.

Retrieve residues that have:

mixed positive and negative affect;

relevance to the selected tension;

some capacity to complicate it;

a variation polarity not recently overused;

sufficient distance from recently selected residues.

The selector should ask:

Which real memory could make this self-claim less simple?

not:

Which memory most strongly resembles this self-claim?

Stage 3: introduce counterpressure

Counterpressure may come from:

a less-used side of the same event;

an opposite emotional variation;

a different persistent conflict in the same identity core;

optionally, one foreign affect projection.

The counterpart projection should never replace the persona-owned event residue. Otherwise the persona begins dreaming from another character’s state rather than from its own life.

Stage 4: emit an inspectable selector trace

The trace should identify:

selected_arc_tension
selected_event_fact_ids
why_relevant
why_complicating
variation_polarity
underexplored_facet
counterpart_projection_id
recent_use_cooldowns

This is not a benchmark. It is the causal grammar of the next chapter.

Preventing the loop from eating itself

Several hard construction rules are sufficient:

journal text remains ineligible as dream residue;

prior dream content remains ineligible as event-fact;

arc_state may affect ranking but contributes no scene facts;

the latest arc delta receives no guaranteed priority;

the same tension cannot seed more than two consecutive cycles by default;

the selector must include at least one complicating or underexplored relation;

foreign affect can modify pressure but cannot supply history;

one counterpart maximum per dream at this stage.

This preserves a world-mediated loop:

real persona event
→ dream variation
→ watched interpretation
→ self-narrative change
→ changed lens on another real persona event

rather than a self-mediated loop:

journal claim
→ dream proving claim
→ journal strengthening claim
→ dream proving stronger claim

The latter is precisely how a vivid personality becomes a renamed attractor.

Q4 — What is research and what is engineering?
What is clearly prior art

Persistent narrative identity, self-modeling, and endogenous activity are not novel in themselves. Sophia explicitly presents a persistent “System 3” governing narrative identity and continuous adaptation.
arXiv

Memory, reflection, planning, and emergent social interaction are established by Generative Agents, whose 25-agent town stores experiences, synthesizes reflections, retrieves them, and uses them to plan individual and social behavior.
arXiv

Explicit persona specifications and multi-agent persona worlds are also established engineering territory. TinyTroupe defines TinyPerson agents through traits, preferences, beliefs, goals, and other specifications, then allows them to interact within TinyWorld.
GitHub
+1

Incrementally evolving a character profile from narrative progression is not new either. One correction to the supplied brief is important: the “persona built incrementally from narrative summaries, reflecting story arcs” description is CharacterGPT’s contribution. The April 2026 Zylos article is a secondary research summary that attributes this method to CharacterGPT; CharacterGPT itself updates personas from chapter-wise novel summaries.
Zylos
+2
ACL Anthology
+2

EvoSpark is direct prior art for long-horizon multi-character evolution, mutable relationship and personality state, narrative-world grounding, and entity resolution. Its Role Socio-Evolutionary Base modifies personality, social graphs, and goals as events accumulate.
arXiv
+1

Even the language of “dreaming” or nighttime processing cannot carry a novelty claim by itself. Recent systems use “Auto-Dreamer” or nighttime engines for offline memory consolidation, schema induction, or performance improvement without generating literal fictional dreams that the persona then watches as an object of self-interpretation.
arXiv
+1

What is engineering integration

The following are substantial achievements, but primarily systems engineering:

runtime discovery of arbitrary persona corpora;

adapting different memory schemas;

ArcFace identity checks;

VLM watch stages;

ToM invocation;

graph traversal across affect nodes;

storage and provenance;

mood-to-voice realization;

pipeline receipts and loop guards.

Their importance is not diminished by calling them engineering. They are what make the research object real.

What may be a genuine contribution

I would describe the candidate contribution as:

Epistemically typed imaginative self-evolution for persistent fictional agents.

The distinctive object is not any individual component. It is the closed architecture formed by these constraints:

A persona dreams a conflict-bearing variation of its protected episodic history.

The dream is a generated multimodal artifact rather than a textual reflection alone.

The persona re-perceives that artifact through a separate watch stage.

It writes autobiographical self-narrative licensed to invent inner meaning.

That license is structurally bounded: it cannot invent or overwrite external history.

The journal produces a small additive change that retains a still_true.

A future dream selector uses that changed arc as a lens over canonical experience.

Another persona can enter only as an affective projection and locally owned theory-of-mind model, not as transferred facts or a merged self.

I did not find that complete combination in the cited neighboring systems. Sophia has persistent self-improvement and narrative identity but not this multimodal fictional self-observation loop. Generative Agents has memory and reflection but not the explicit event-fact versus licensed-inner-fiction firewall. CharacterGPT accumulates character traits from external narrative summaries rather than from a persona watching its own generated dream. EvoSpark evolves interacting characters and grounds entities, but its mutable shared narrative cognition is importantly different from persona-dream’s separate canons plus affect-only bridge.
arXiv
+3
arXiv
+3
arXiv
+3

That supports a plausible systems-and-creative-agents contribution, not yet a blanket novelty claim over all literature.

The strongest research idea

The strongest research idea is probably not “AI agents can dream.”

It is:

A persona may be allowed to confabulate its own inner life while being structurally unable to confabulate its history—and may use a deliberately lossy affect bridge to imagine another persona without acquiring that persona’s facts.

Most memory systems frame confabulation as an error to suppress, or allow reflection outputs to re-enter a general memory pool. persona-dream instead makes imagination a typed capability with a jurisdiction:

inner interpretation: generative;

event history: protected;

other-person facts: inaccessible;

theory of the other: explicitly local and uncertain.

That is conceptually clean and implementable.

Genuine unresolved research questions

Several parts cannot honestly be waved off as completed engineering.

Does the firewall remain semantically effective over many cycles?

Zero literal journal documents leaking into the canon collection is necessary, but semantic leakage could still occur. A journal invention may affect arc_state; arc_state affects selection; repeated selection may make the invention feel historically grounded even though no event-fact was copied.

That is not a safety problem. It is an epistemic and narrative-continuity question.

Does the affect bridge preserve difference or cause convergence?

Affect nodes create connection precisely because they abstract away fictional-world differences. The open question is whether persona-specific realization restores enough difference—or whether both personas slowly acquire the same emotional grammar.

Do unilateral counterpart models create relationships or only projections?

“Horus dreams about Embry” initially tells us about Horus. A genuine relationship requires some later mechanism through which each character encounters resistance from the other’s actual continuing self, rather than repeatedly interacting with a private model.

The transition from projection to encounter is a legitimate research problem.

Does accumulated change remain perceptually recognizable?

The ledger can prove causal continuity structurally. Whether a reader or listener experiences later Embry as the same Embry is partly an aesthetic and relational judgment. That need not become a baseline-superiority contest, but it does require longitudinal human reading or listening if the project makes a claim about recognizability rather than merely ledger consistency.

This is consistent with the broader observation in Layered Mutability that inspecting individual edits does not fully reveal the behavioral trajectory produced by accumulated mutable layers.
arXiv
+1

The appropriate research frame is therefore a construction-led longitudinal account:

specify the ontologies and transition rules;

preserve complete causal traces;

present evolving dream, journal, arc, mood, and session artifacts;

analyze where continuity holds, where it narrows, and where selves begin to converge.

It does not need to ask whether dreams outperform ordinary memory. It does need to show that the phenomenon named in the README is genuinely occurring.

POSITION SUMMARY

The fork is false conceptually but real in sequence: stable selfhood must precede full interaction, while limited otherness is needed to keep self-evolution from becoming self-paraphrase.

Build an arc-conditioned selector that always seeds from the dreamer’s canon and can optionally accept one affect-only counterpart projection.

The smallest honest cross-persona dream is unilateral: Horus dreams his model of Embry, learns about Horus, and writes only to Horus’s arc.

Identity change should be an earned new move within a continuing conflict; novelty must be measured structurally, not through mood names or journal vocabulary.

The plausible contribution is the combined multimodal dream loop, licensed-inner-life firewall, additive continuity ledger, and confabulation-safe affect bridge—not persistence or multi-agent simulation alone.

RECOMMENDED NEXT BUILD

Construct persona.dream_seed.v2 and its Arc-Conditioned Encounter Selector with two modes:

self_only
imagined_counterpart

For imagined_counterpart, it must consume exactly:

one dreamer-owned canonical conflict residue;

one current or underexplored dreamer arc tension;

one sanitized, single-use counterpart affect projection;

one dreamer-local counterpart model.

Its first acceptance artifact should be one Horus-about-Embry dream in which:

no Embry event-facts or journal prose enter the seed;

Embry is explicitly a projected dream figure;

only Horus watches and journals;

only Horus receives an arc_delta;

still_true preserves Horus’s recognizable core;

neither event-fact collection changes;

Embry’s Continuity Ledger is untouched;

the next Horus cycle receives the resulting arc change.

That is one concrete build that completes the missing A loop and opens the first honest inch of B.

DISAGREEMENTS

I disagree that A and B are independent alternatives. Self-evolution without otherness risks closure; interaction without accumulated selfhood risks spectacle and persona blending.

I disagree with building the full co-appearance next. The umbrella-and-tea scene should remain a noncanonical stage artifact until shared-scene facts and separate first-person interpretations are represented explicitly.

I disagree that mood-to-live-voice is the highest-value immediate step. It is the next embodiment step, but selector causality should precede stronger performance.

I disagree with allowing direct journal-to-journal exchange. Shared affect should be lossy, abstract, and re-realized through the receiving persona’s own core.

I do not think the research question is finished merely because the architecture runs. Whether affect-only contact can produce real relational development without semantic leakage, homogenization, or loss of recognizability remains genuinely open.
