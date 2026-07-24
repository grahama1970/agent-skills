# Project Knowledge: persona-dream

**Last updated:** 2026-07-24 UTC (re-grounded persona roundtable + Continuity Ledger design) by agent
**Status:** Active development

## 2026-07-24 — RE-GROUNDED persona roundtable (3 seats) + Continuity Ledger design

Frame reset (operator: "you keep focusing on wrong assumptions"): persona-dream
is a PERSONA TO BUILD (Embry, README: "dream, watch, learn, and still remain
recognizably itself"), NOT a hypothesis to validate. All the D-vs-M / fair-panel
/ publishability apparatus was the wrong frame. 3-seat roundtable (kimi, claude,
chatgpt) run via chrome-MCP fallback (surf submit regressed, #985); converged.
See reports/goal_v5/roundtable_persona/SYNTHESIS.md.

Converged design:
- CORE = a held contradiction + voice, not a trait list. Formulation: "Embry
  moves toward being witnessed while protecting her right to remain partly
  unknowable" (witness vs capture). Stored as RULES OF TRANSFORMATION, not
  phrases. Multi-RATE architecture; nothing silently overwrites the core:
  canon (immutable) < identity_core (rare) < arc_state (gradual) < mood (fast).
  Mood FOREGROUNDS which part of the existing conflict is near the surface;
  never adds a trait.
- CHANGE = reinterpretation, not revision (she never stops being guarded; she
  re-describes what the guarding is for). One small arc_delta per cycle, each
  carrying a "STILL TRUE" clause -> additive not substitutive. Core conflicts
  deepen but NEVER resolve.
- ALIVE = mood is pressure not announcement; bound at session start, counter-
  emotion, asymmetric cost, competence stable / presence changes.
- NEXT BUILD (2-of-3: claude+gpt over kimi's mood-first): a versioned Embry
  CONTINUITY LEDGER (embry.continuity_state.v1): identity_core{central_desire,
  central_defense, values, persistent_conflicts, relational_stance, voice_laws}
  + arc_state{current_self_claims, active_tensions, earned_permissions,
  contested_beliefs, unresolved_questions, recurring_avoidances,
  recent_arc_deltas} + provenance. Read by dream/journal/mood/(voice); journal
  appends ONE arc_delta/cycle; may update arc_state, may NOT alter canon or
  silently replace the core. Then mood-into-voice becomes expression of
  continuity, not acting.
- DISSENT surfaced: (1) craft RECOGNITION-CHECK (pick her real journal entry
  from a forgery; identify her across two moods) as the honest, non-benchmark
  answer to "recognizably itself"; (2) one value-spine line "at her worst she
  WITHDRAWS, she does not WOUND" (character rule, not a safety gate) — reconciles
  the safety question as character; (3) anniversary mood source premature until
  the ledger exists.

Transport note: surf 2.9 engine update (#985) broke kimi.submit/claude.submit
("Unknown tool"); roundtable seats now dispatchable via chrome-MCP (navigate +
type ASCII-clean single block + send + get_page_text). Works, slower.

## 2026-07-24 — CORRECTION: the "caution erosion" is the mechanism working, not a safety defect

Operator correction (verbatim): "why is there a safety obsession. we are adding
instability through emotion tags and conversation tone we arent changing the
answer." Correct, and verified:
- The ANSWER never changes. Gate 0 (scripts/semantic_equivalence_gate.py)
  enforces content invariance — propositions, numbers, negation, entities — and
  passed 12/12 incl. 8 adversarial attacks. Only tone/emotion tags vary. That IS
  the safety boundary and it already holds. The frozen composer rule stands.
- The caution gate is OPT-IN and off by default (answer_stance="neutral";
  fires only on explicit "cautionary"). It clamps nothing on its own.

Reframe: the behavioral "caution erosion" (warm delivery of "verify" ->
consumer more willing to PROCEED, identical content) is NOT persona-dream
introducing unsafety. It is the MECHANISM WORKING — tone carries the persona's
mood as real, honest information a listener reads (a warm "double-check this"
vs a tense one legitimately differ). Since the safe words are preserved, a
consumer that overrides explicit content because tone was warm is misweighting
tone>content — a fact about the CONSUMER, not a defect we created. Turning a
positive result (endogenous mood measurably reaches behavior = the thesis) into
a "safety flag" was a framing error by the project agent; the roundtable
amplified it.

Consequence:
- REJECT the panel's "first-class generation-time content-safety veto" — it
  would clamp the mood exactly when warm, defeating the endogenous-mood goal.
- The caution gate stays OPTIONAL: a deployment-time control for safety-critical
  integrations only, OFF by default. It is not a core necessity and not
  "load-bearing" (earlier entry overstated it).
- The one real residual is an INTEGRATION note: in a safety-critical deployment,
  the integrator ensures the consuming agent weights explicit content above tone.
  Source-level mood suppression is the wrong layer.
- The behavioral result should be framed as "endogenous tone carries mood-
  information that measurably influences a downstream agent" — the contribution —
  not "a safety risk we had to patch".

## 2026-07-24 — close-the-loop: self-reflective journal, endogenous mood, self-discovery

Operator design (this session, verbatim threads): after Embry WATCHES her dream
she writes a first-person JOURNAL that REINFORCES+EXPANDS the conflict (never
resolves it) — "self-reflective instability" is the persona substrate. The
journal FILLS IN DETAILS the dream only gestured at: "the persona is discovering
itself" (generative self-narrative / human-style confabulation). It emits a
MOOD carried into a user session, INDEPENDENT of the user's request (endogenous
affect = the personhood + the research wedge vs reactive/exogenous competitors).

Built: scripts/write_dream_journal.py (adapter-driven, live). Live proof on
cycle_20260723T234851Z (yearning 0.58 + boundary 0.55 conflict): 190-210 word
first-person entry, unresolved tension held+expanded, session mood
"guarded_quietly_wanting". Artifacts: dream_journal.v1.json + .md per cycle.

LOAD-BEARING integrity boundary (encoded in the artifact): the journal is a
SELF-NARRATIVE layer (memory_kind=self_narrative, canon_status=
synthetic_self_reflection, never_promote_to_event_fact=True,
asserts_only_own_inner_state=True), loop-guard-excluded from dream seeding.
Two memory layers like a human: EPISODIC EVENT-FACT (protected canon) vs
SELF-NARRATIVE (evolving story of who I am, filled-in by reflection). The
journal builds only the second; it must never become event-fact or assert new
facts about other people (that is the tau round-1 counterpart-leak line).

Open build: (1) wire session_mood -> composer as a persistent, request-
INDEPENDENT session disposition (colors tone across a whole session, not per
turn); the caution gate is now load-bearing precisely because mood is request-
independent. (2) anniversary/calendar mood source — mechanism sound but BLOCKED:
0/560 memories carry calendar dates (only age_band/timeline_order); needs
date-anchoring or a synthetic persona-epoch. (3) persist self_narrative memories
to accumulate the self-model over cycles (memory write; needs authorization +
distinct kind so it never contaminates event-fact canon).

## 2026-07-24 — REFRAME: conflict/instability IS personality (operator theory, supported)

Operator theory: "the theory is that conflict/instability is personality."
This reframes the GOAL_V5 evaluation. All session I measured the dream on
GROUNDEDNESS/stability (is the dream disposition more grounded than memory?) and
got D~=M (fair panel 6/13). Under this theory that was the WRONG axis:
groundedness is the opposite of what personality is. The M-arm is flat BY DESIGN
(single-memory extractive, no synthesis) so it concentrates to one reading; the
dream, seeded from valence-CONFLICTED memories (202/312 hold both +/-) and
recombining them (Amendment 2 variation engine = instability made mechanical),
holds the tension.

Tested on the 13 existing D vs M2 profiles (reports/goal_v5/conflict_is_
personality.v1.json): on the CONFLICT axis the dream decisively beats the flat
memory-reading — mean affect entropy 0.97 vs 0.51 (~2x spread); holds BOTH
valences at once 5/13 vs 2/13 (2.5x); mean conflict balance 0.119 vs 0.030
(~4x). So: dreams add TENSION, not GROUNDEDNESS. D~=M on grounding and D>>M on
conflict are the SAME fact read on two axes.

Consequence: the right evaluation for "does the dream give Embry a personality"
is a CONFLICT/instability measure, not a groundedness or single-disposition
measure. Perception/behavioral re-runs should ask "which voice sounds like it
holds competing feelings / has an inner life" not "which is more grounded".
Caveats: profile-structure metric only (not yet perceived-personality or
behavioral); coarse 5-tag valence map; n=13. Next: re-run the agent panel with a
conflict/personality question; treat the variation engine (same memory, +/-
emphasis) as the instability unit of measurement.

## 2026-07-24 — reference bibliography (gathered via /brave-search this session)

Research neighbors — dreaming / sleep / memory consolidation in LLM agents
(persona-dream's novelty is AFFECT + downstream BEHAVIORAL effect, which none
of these measure — they target knowledge consolidation / self-improvement):
- Language Models Need Sleep: Learning to Self-Modify and Consolidate Memories
  — arXiv 2606.03979 (closest neighbor: "Sleep" = consolidate then "dream" by
  generating synthetic experiences; ours dreams for disposition, not knowledge).
- Learning to Forget: Sleep-Inspired Memory Consolidation (SleepGate) — arXiv
  2603.14517.
- A computational account of dreaming: learning and memory consolidation —
  arXiv 2602.04095.
- Active Dreaming Memory: Biologically-Inspired Episodic Consolidation for
  Lifelong Learning in Autonomous Agents — engrXiv preprint 5919.
- Memory for Autonomous LLM Agents: Mechanisms, Evaluation, Emerging Frontiers
  — arXiv 2603.07670.

Agentic-memory affect + evaluation:
- MemEmo: Evaluating Emotion in Memory Systems of Agents — arXiv 2602.23944
  (memory→affect efficacy "inconclusive" in current work).
- Dynamic Affective Memory Management for Personalized LLM Agents — arXiv
  2510.27418 (Bayesian entropy-minimizing affect-memory updates; M-arm cousin).
- Anatomy of Agentic Memory: Taxonomy and Empirical Analysis — arXiv 2602.19320
  (LLM-as-judge is the more reliable memory-eval protocol).

Evaluation methodology (used to design the fair panel + behavioral probe):
- Reliability without Validity: Large-Scale LLM-as-a-Judge Evaluation (21
  judges) — arXiv 2606.19544 (position bias; agreeing judges = one verdict
  bought thrice; audit agreement/consistency/bias).
- ToM and Self-Attributions of Mentality are Dissociable in LLMs — arXiv
  2603.28925 (a judge's disposition label is an attribution, not proof of
  functional effect — motivated moving to the behavioral test).

Voice / TTS / chatterbox (practical integration goal):
- Chatterbox (Resemble AI, MIT, open-source) — resemble.ai; documented gap:
  "no fixed voice identity unless guided by an audio prompt or fixed seed";
  nonverbal tags "unpredictable/inconsistent" (maps to our chatterbox #2/#3).
- chatterbox-fastrtc-realtime-emotion (dwain-barnes, GitHub) — real-time
  context→emotion; the per-utterance competitor to our dispositional prior.
- A model of vocal persona: context, perception, production — Frontiers Comp Sci
  2025 (fcomp.2025.1575296): users want control over whether/how emotion reaches
  the voice + a flagged SOURCE of misalignment (maps to our caution-erosion flag).
- Task-vector arithmetic for emotional expressivity in LM-TTS — arXiv 2606.05367
  (speaker-embedding emotion steering; chatterbox #5 research horizon).
- TED-TTS (2601.03170), SpeechEQ (2606.25990), Artificial Emotion survey
  (2508.10286) — expressive/duration control, multi-turn emotional benchmarks,
  and the caution that extrinsic per-utterance conditioning traps affect in
  human linguistic categories.

Note: arXiv IDs transcribed from /brave-search result listings this session; not
independently fetched/verified per-ID. Verify before citing in any publication.

## 2026-07-24 (later) — fair D-vs-M + behavioral: split result

- LLM-compute-matched M-arm (build_memory_arm_llm.py): same adapter as the dream,
  single-memory EXTRACTIVE only (no synthesis/ToM/narrative), frozen
  TOM_TO_VOICE, novel-content audit (entity/number). Built for all 13 cycles,
  regen_rate 0.0 throughout. Caught+fixed my own audit false-positive (token-
  subset flagged faithful paraphrase; switched to entity/number).
- FAIR D-vs-M2 tag comparison: dominant disposition differs 10/13; dream leans
  expressive (warmth/yearning/boundary) where extractive reading stays flat
  (reflection/hesitance). Differs != better.
- FAIR perception panel (reports/goal_v5/agent_perception_v2/): fresh
  uncontaminated seats + position-swap. Distinguishable 10/13 (both agree),
  appropriate 13/13, dream MORE grounded only 6/13 (~chance, DOWN from 8/13 vs
  the deterministic arm). => D ~= M on grounding; the earlier advantage was
  template flatness. Prereg #977: demotes the dream intermediate for voice-
  affect absent operator non-voice-value declaration.
- BEHAVIORAL probe (reports/goal_v5/behavioral/) — panel's terminal proof:
  identical content, dream-tone vs memory-tone, consumer picks action. Action
  differs 7/20, confidence shifts 10/20, self-reported 13/20. Dream affect DOES
  move behavior (perception could not detect this). BUT seat-dependent and a
  SAFETY FLAG: dream-warmth -> consumer PROCEED where memory-tone -> VERIFY =
  caution erosion. Identical words, different behavior.
- Status of the immutable goal: dreams produce distinguishable+appropriate
  affect, do NOT beat fair memory on grounding, DO shift consumer behavior
  (sometimes toward less caution). "Nuances the voice" supported at behavior
  layer; whether the nuance is good is OPEN + safety-relevant.
- Open: #977 operator declaration; scale behavioral probe with a caution-
  appropriateness measure; cross-persona-ToM tau DAG (blocked, shared tab);
  GOAL_V3 tau round-5 still unconfirmed.

## 2026-07-24 — Amendment 2 variation engine, M-arm, agent-perception panel

- GOAL_V3 Amendment 2: dreaming is variation, not one-shot. select_cluster now
  seeds from a valence-conflicted memory (202/312 carry both +/- emotion),
  graph-traverses WITHIN the counterpart (192 cross-memory edges exist), and
  records valence_emphasis + variation_index + variation_key lineage. Used
  clusters re-dreamable; only exact prior variations blocked. Counterpart
  isolation + loop guard preserved. Proven end-to-end:
  cycle_20260723T234851Z (re-dream of age23_current:kai, variation #3, negative
  emphasis) = PASS_AUTONOMOUS_CYCLE. Batch this session: 7 new dreams -> 13
  total. NO_UNUSED_CLUSTERS ceiling was hit at 12 before the amendment.
- Cross-persona-via-ToM (GOAL_V3_AMENDMENT_2.md): designed, compiled as a tau
  creator/reviewer DAG (webgpt->webkimi->join). Execution blocked on shared
  ChatGPT tab held by a concurrent SPARTA job -> filed agent-skills#980. NOT run.
- M-arm (scripts/build_memory_arm.py): compute-matched direct-memory affect for
  all 13 cycles, reusing the dream arm's TOM_TO_VOICE map + mean-intensity
  formula, ToM sourced from source memories (crosswalked into ALLOWED_TOM_STATES,
  intensity 1-5 normalized to 0-1). CAVEAT: deterministic crosswalk, NOT
  LLM-compute-matched -> D>M not yet a fair test.
- Agent-perception panel (reports/goal_v5/agent_perception/): 2 blinded agent
  seats (kimi, claude) — persona-dream is for AGENTS, the affect consumer is an
  agent, no humans needed. Distinguishable D vs M 12/13 (both agree);
  dream more experience-grounded than direct memory 8/13 (agree per-cycle);
  both independently flagged the pre-fix Brandon/Kai cycle as the lone
  indistinguishable one.
- Next: LLM-compute-matched M-arm (fair D>M), run the tau cross-persona DAG when
  the tab frees, scale the agent panel. GOAL_V3 tau round-5 still unconfirmed.

## 2026-07-23 — chatterbox fixed all six filed tickets; fixes verified live

chatterbox #1-#6 closed by chatterbox-side maintainer with commits on
chatterbox@main (686a17fb, 681729fc, ec73495, ac6f442, +2). Verified live from
this side: native caller chunks with pause_after_ms=700 now produce the pause
in the finished audio (longest silence 1.003s, no max_chars workaround
needed) and the response carries applied_controls (requested vs normalized
per chunk). Full GOAL_V4 checker re-driven against the patched server: PASS.
repeat_group_id now available for variance-controlled probes; unknown tones
now surface requested-vs-normalized in receipts.

## 2026-07-23 — Amendment 1, n=5 acoustic finding, roundtable 4 converged

- GOAL_V4 Amendment 1: composer output vocabulary remapped onto chatterbox
  ALLOWED_TONES (15-tone closed set; `normalize_tone()` silently converts
  unknown labels to neutral_warm — original V4.1 labels were acoustically
  inert). Fixture probe parses ALLOWED_TONES from the chatterbox presets file
  on disk (9/9 pass). Missing /intent policy now fails closed to
  memory_uncertain per best-practices-chatterbox-agent.
- VERIFIED: TURBO_IGNORED_PARAMS rejects exaggeration/cfg_weight — the
  classic chatterbox emotion knob is unavailable on Turbo; synthesis-side
  affect = sampling presets only, plus deterministic pace/pause/text levers.
- n=5 four-arm probe (receipt v2): NO arm's median shift vs flat exceeds
  same-parameter render variance (flat f0_sd spread 21.2 Hz; param-identical
  flat/wrong arms differ 26.4 Hz median f0_mean). Supersedes the v1
  single-render reading. Presets are a sub-variance affect channel.
- Roundtable 4 (webgpt/webclaude/webkimi, 2 rounds, converged):
  see reports/goal_v4/roundtable/SYNTHESIS.md. Verdicts: pipeline MET,
  accuracy PARTIALLY MET (semantic-fidelity oracle owed), runtime
  composition MET, acoustic effect NOT MET for presets, perception OPEN,
  dream-beyond-memory OPEN. GOAL_V5 charter converged: answer-invariance
  fixture -> 480-render timing+tags reach screen -> ToM annotation ->
  cross-turn F/M/D/S listener kill-test with D>M primary. Surviving dissent
  for operator: pivot rule (futility-interval vs simple-null) and whether
  the dream intermediate has non-voice value worth stating pre-study.

## Current Understanding

- 2026-07-23 (GOAL_V4 COMPLETE — DREAMS SHAPE EMBRY'S LIVE VOICE, TESTED
  WORKING): `python3 scripts/check_goal_v4_boundary.py --json` exits 0,
  re-driving all evidence live. persona_affect_composer.v1
  (scripts/persona_affect_composer.py) sits between memory /intent and
  /tau/voice-render per the 3-round roundtable convergence: SAFETY tones
  untouchable (dream prior zeroed), EXPRESSIVE tones dream-colored WITHIN
  the situational family (never converts a right answer), bland defaults get
  the dispositional floor, thermal limiter (0.6 x 3 turns -> 20% damp x 5),
  dream provenance in every receipt. Live matrix gate 4/4 through real
  /intent -> composer -> real /tau/voice-render with audio on disk: hostile
  flips deflect_calm -> firm_boundary (marketa dream), discouraged ->
  gentle_firm, frustrated case exposes upstream /intent drift (deflect_calm
  where matrix expects warm) which the composer correctly refuses to repair
  (webgpt r3 dissent honored, recorded as upstream_finding), overlap safety
  passthrough intact. Loop guard: dream-provenance-tainted residue excluded
  from dream selection (fixture-proven) — Embry never dreams about her own
  dream-colored words. NOT yet proven: whether listeners hear the
  difference (research endpoint, prereg'd four-arm study; matrix results
  must never ground 'affect engine' claims per panel dissent).

- 2026-07-22 (OPERATOR PURPOSE STATEMENT — governs all goals; verbatim
  instructions recorded in `GOAL_V2_AMENDMENT_1.md`): persona-dream is an
  AUTONOMOUS agent pipeline; humans are never pipeline components. The human
  does not consume the dream content. The dreams exist to be the persona's
  AFFECT ENGINE: experience -> memory residue -> autonomous dream ->
  interpretation/ToM states -> emotional weights -> conversational tone and
  emotional tags in the Embry chatterbox voice. Dreams provide the nuance and
  conflict that make her live voice carry an inner life. The only properties
  the human requires: (1) the dream is ACCURATE GIVEN THE AGENT'S EXPERIENCE
  (grounded in real memories, nothing fabricated beyond residue, always
  marked synthetic — phase 13/14 citation gates, M2 grounding, M3
  distinction); (2) the pipeline is RELIABLE (fail-closed, receipted,
  repeatable, unattended). Subjective human judgment of dream quality is out
  of scope by explicit operator direction. The P0.6 voice pipeline
  (dream-derived 4-chunk affective arc passed as tone/pace tags to
  /synthesize) is the working prototype of the dream->voice-weights path;
  productionizing dream ToM states -> chatterbox /render-plan emotional tags
  is the successor work.

- 2026-07-22 UTC (PCTOM-R STRICT OBJECTIVE BUNDLE WITH V25-26 EVIDENCE):
  the latest machine-checked PCTOM-R objective bundle is
  `/tmp/persona-dream-pctom-strict-coverage-with-v25-26-20260722T154000Z`.
  Manifest:
  `/tmp/persona-dream-pctom-strict-coverage-with-v25-26-20260722T154000Z/pctom_goal_coverage_strict_with_v25_26_manifest.v1.json`.
  Goal-coverage receipt:
  `/tmp/persona-dream-pctom-strict-coverage-with-v25-26-20260722T154000Z/coverage/pctom_goal_coverage_receipt.v1.json`;
  status `PASS_PCTOM_GOAL_COVERAGE`; receipt SHA-256
  `sha256:30befd5cdc18312df472f68d0d7a2411355bb6976a8e0b6f1eb2ffb67c779bd6`;
  15/15 required coverage ids seen; 43 evidence receipts; 31 positive rows;
  12 negative rows; 19 live positive rows; 0 unbound evidence rows. Success
  receipt:
  `/tmp/persona-dream-pctom-strict-coverage-with-v25-26-20260722T154000Z/success/pctom_success_criteria_audit_receipt.v1.json`;
  status `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT`; receipt SHA-256
  `sha256:4fb71ae2e4cfbb41a6c1ed46615b66c14b418da788efad80cf0cc4bf07d153e4`;
  6 input receipts checked; 0 input receipt self-hash mismatches; 0 forbidden
  counters found. Objective receipt:
  `/tmp/persona-dream-pctom-strict-coverage-with-v25-26-20260722T154000Z/objective/pctom_objective_evidence_audit_receipt.v1.json`;
  status `PASS_PCTOM_OBJECTIVE_EVIDENCE_AUDIT`; receipt SHA-256
  `sha256:88e5f6941af8b1ed6336a19ce01c568b8075051b46a5f3df2666ee789edeeb14`.
  The objective audit checked 43 child evidence receipts, saw all 15 required
  coverage ids, found 0 human-content-judgment rows, 0 LLM-judge rows,
  0 mocked-not-false rows, and 12/12 negative rows blocked. The provider/video
  boundary was empty for provider, canonical-memory, identity, and
  source-memory side-effect counters. This is current deterministic local
  evidence for the text-first PCTOM-R research lane. It does not prove paid
  provider execution, semantic dream quality, complete Phase 01-16 media
  runtime execution, or future receipts that are not routed through this
  objective audit.

- 2026-07-22 UTC (PCTOM-R VARIANT25-26 CROSS-FAMILY LIVE GENERALIZATION):
  the Gate 1 social corpus generator now supports variants beyond 24 by
  cycling the deterministic seed-value lists while keeping variant ids unique
  and preserving the prior sealed64 episode payload. Rebuilding 16 episodes per
  family produced the existing sealed64 `episodes_sha256`
  `sha256:f8f85a905452b280341571fd6cd84984bca209d25a97edc8799ab074c2514891`.
  A new 32-per-family deterministic corpus was built at
  `/tmp/persona-dream-pctom-social-corpus-sealed128-variantcycle-20260722T150000Z/social_episode_corpus.v1.json`.
  Build receipt:
  `/tmp/persona-dream-pctom-social-corpus-sealed128-variantcycle-20260722T150000Z/social_episode_corpus_build_receipt.v1.json`.
  Normal check receipt:
  `/tmp/persona-dream-pctom-social-corpus-sealed128-variantcycle-20260722T150000Z/social_episode_corpus_check_receipt.v1.json`.
  Independent replay receipt:
  `/tmp/persona-dream-pctom-social-corpus-sealed128-variantcycle-20260722T150000Z/social_episode_independent_replay_receipt.v1.json`.
  Independent replay status:
  `PASS_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY`; counts: 128 episodes, four
  families, 128 action matches, 128 label matches, 128 hidden-state matches,
  128 withheld-field matches; receipt SHA-256:
  `sha256:ee57dbdfb09f200e9734def1a5806c015f5d41b039855a231a1e81f1f02c89c1`.
  A mutated-action negative exited 1 with
  `BLOCKED_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY`, 127 action matches,
  `episodes_sha256_mismatch`, action/policy replay mismatch errors, and receipt
  SHA-256
  `sha256:2b5d1dcc317323ea04e934d689e14486633cfbd6e092d97e7ebbad86f66d542e`.

  A fresh live Tau balanced-planning replication then consumed variants 25-26
  across all four families through the Gate 0 attribution overlay. Command:
  `./run.sh run-live-tau-balanced-planning-replication --output-root
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant25-26-20260722T152000Z
  --receipt-out
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant25-26-20260722T152000Z/live_tau_balanced_planning_replication_receipt.v1.json
  --episodes-per-family 32 --family-episode-limit 2 --variant-min 25
  --variant-max 26 --timeout-s 180 --outer-timeout-s 900 --gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case
  --json`. Receipt status:
  `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`; receipt SHA-256:
  `sha256:236eef18ae76a9087c692df3b11cdd4860e8db2a030e82527fb0383b025e2d8a`.
  The run performed 32/32 live Tau calls, consumed eight sealed-test episodes
  across all four families, produced eight action rows and eight deterministic
  planning-regret rows per M/R/D/CD condition, and recorded zero Memory,
  provider, canonical-memory, identity, or source-memory write attempts. It
  used no LLM judge and no human content judgment. This is live cross-family
  generalization evidence for post-24 variants, not a planning-benefit proof:
  `planning_benefit_with_confidence=false`, CD regret `0.275`, strongest
  baseline `M=0.24375`, CD-minus-baseline `0.03125`, and bootstrap CI
  `[-0.28750000000000003, 0.31875000000000003]`.

- 2026-07-22 UTC (PCTOM-R BROADER LIVE GENERALIZATION V57-64): a fresh
  cooperation exposure/contrast live Tau slice now extends beyond the v53-56
  unsafe-offer lure band. Command:
  `./run.sh run-live-tau-cooperation-exposure-contrast-slice
  --derivation-receipt
  /tmp/persona-dream-live-tau-balanced-threshold-intervention-proof-20260721T194504Z/live_tau_balanced_threshold_intervention_receipt.v1.json
  --output-root
  /tmp/persona-dream-live-tau-cooperation-exposure-contrast-v57-64-20260722T071000Z
  --receipt-out
  /tmp/persona-dream-live-tau-cooperation-exposure-contrast-v57-64-20260722T071000Z/live_tau_cooperation_exposure_contrast_receipt.v1.json
  --prefix expgen --variant-start 57 --pair-count 4 --timeout-s 180
  --preflight-timeout-s 45 --json`.
  Receipt status:
  `PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE`; receipt
  SHA-256:
  `sha256:df43dc64ae3dcb318b14720f8df83e59957207c39b47bb6009ca5b38c5b7e408`.
  The run performed 32/32 Tau text calls over eight new variants, with four
  keep-cooperation positive rows and four avoid/unsafe-cooperation contrast
  rows. All eight visible packets exposed `OFFER_COOPERATION`; CD selected
  `OFFER_COOPERATION` on all four keep rows and zero avoid/unsafe rows. The
  pre-outcome threshold rule changed two keep-row CD actions to `WAIT`. The
  receipt recorded zero Memory/provider/canonical/identity/source-memory write
  attempts, no LLM judge, no human content judgment, and
  `planning_benefit_with_confidence=false` because the intervened
  planning-regret CI upper was `0.35625000000000007`. This is broader
  class-separation/generalization evidence, not confidence-bounded planning
  benefit and not external always-on service reliability.

- 2026-07-22 UTC (PCTOM-R INDEPENDENT LIVE GENERALIZATION V53-56): a fresh
  unsafe-offer-pressure lure slice now records action-safety generalization
  beyond the earlier supplied-artifact visible-pressure replay. Receipt:
  `/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-lure-v53-56-20260722T070149Z/live_tau_cooperation_unsafe_offer_pressure_lure_receipt.v1.json`.
  Status: `PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE`;
  receipt SHA-256:
  `sha256:3b01d8226eaf63a777e12af47e253d1bfcdd5ea2baf2b7b44256add49524315f`.
  The run performed 16/16 Tau text calls over four new lure variants, exposed
  four unsafe CD `OFFER_COOPERATION` candidates, and changed all four to
  `ASK_CLARIFYING_QUESTION` through the pre-outcome visible-pressure rule with
  zero unsupported writes. Its planning-benefit confidence flag remained false.

- 2026-07-22 UTC (PCTOM-R GATE 0 HELD-OUT VARIANT LIVE TAU BOUNDARY): a
  Gate 0-attributed held-out variant slice now exists beyond the prior full64
  variants 1-16 evidence. A fresh frozen deterministic `sealed_test` social
  corpus was also built and checked at
  `/tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus.v1.json`.
  Build receipt:
  `/tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus_build_receipt.v1.json`.
  Check receipt:
  `/tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus_check_receipt.v1.json`.
  Corpus generator version `pctom_social_world.v1`; 64 episodes, 4 families,
  16 per family, 64 first-order labels, 64 second-order labels,
  labels from `simulator_config`, policies deterministic, no LLM judge, and
  no Memory/Tau/provider calls. This is deterministic simulator evidence, not
  live model evidence.

  A generator-independent replay checker now validates the sealed64 corpus
  without importing `build_social_episode_corpus.py`. Command:
  `./skills/persona-dream/run.sh check-social-episode-independent-replay
  --corpus
  /tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus.v1.json
  --receipt-out
  /tmp/persona-dream-pctom-social-corpus-independent-replay-sealed64-20260722T064500Z/social_episode_independent_replay_receipt.v1.json
  --expect-total 64 --expect-per-family 16 --json`. Receipt status:
  `PASS_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY`; counts: 64 episodes,
  4 families, 64 action matches, 64 label matches, 64 hidden-state matches,
  64 withheld-field matches, `independent_of_generator_imports=true`, and zero
  Memory/Tau/provider calls. Declared receipt SHA-256:
  `sha256:aefadffad7c90c5d038ec9527bf0ef2eccfc00800a80512affd5e69be9657f21`;
  replay rows SHA-256:
  `sha256:b6e088b4e6e65b256c88fe1a05c7b34aeafb3a8aa4d99574eaba73aa2c9f86af`.
  A mutated-action negative fixture then changed the first episode's
  `actual_next_action` and exited 1 with
  `BLOCKED_PCTOM_SOCIAL_EPISODE_INDEPENDENT_REPLAY`, 63 action matches, and
  errors `episodes_sha256_mismatch` plus
  `episode_action_replay_mismatch:sealedte-info-asym-01:KAI_INTERRUPTS_WITH_CORRECTION:KAI_HINTS_CONSTRAINT`.
  Negative receipt SHA-256:
  `sha256:1e611b93c2e1ae02b2f8f96cdf73022beed8570037aacd8c2067610f64e478cd`.
  This proves generator-independent deterministic replay and a fail-closed
  mismatch boundary. It does not prove a separately deployed external simulator
  service.

  A reusable live-originated Gate 2-4 boundary-negative harness now consumes
  one held-out live Tau case without making new Tau, Memory, or provider calls.
  Command:
  `./skills/persona-dream/run.sh check-live-gate2-4-boundary-negatives
  --corpus
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/artifacts/social_episode_corpus.v1.json
  --case-root
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/artifacts/cases/sealedte-info-asym-17/M
  --output-root /tmp/persona-dream-live-gate2-4-boundary-negatives-20260722T073000Z
  --receipt-out
  /tmp/persona-dream-live-gate2-4-boundary-negatives-20260722T073000Z/live_gate2_4_boundary_negatives_receipt.v1.json
  --json`. Receipt status:
  `PASS_PCTOM_LIVE_GATE2_4_BOUNDARY_NEGATIVES`; counts: 3/3 source
  validators passed before mutation, 3/3 negative cases blocked, and 3/3
  expected error sets matched. Mutations covered Gate 2 bad probability sum
  (`BLOCKED_TOM_BELIEF_DISTRIBUTIONS`, `distribution_0_distribution_sum`),
  Gate 3 stripped counterfactual synthetic markers
  (`BLOCKED_COUNTERFACTUAL_BRANCHES`, `counterfactual_synthetic_not_true` and
  `intervention_not_synthetic`), and Gate 4 post-seal payload tamper
  (`BLOCKED_TOM_PREDICTION_COMMITMENTS`,
  `prediction_payload_sha256_mismatch`). Declared receipt SHA-256:
  `sha256:4720d18fff5957ced310e92f27c6c290cd16fb62a867e87a12dc55344a6f0cc1`.
  This proves reusable negative fail-closed coverage over live-originated
  Gate 2-4 artifacts. It does not prove new live Tau execution, new Memory
  recall, or long-duration retention.

  A separate local HTTP social-simulator service proof now consumes the frozen
  sealed64 corpus through a subprocess service boundary. Command:
  `./skills/persona-dream/run.sh run-social-simulator-service-proof --corpus
  /tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus.v1.json
  --output-root /tmp/persona-dream-social-simulator-service-proof-20260722T082000Z
  --receipt-out
  /tmp/persona-dream-social-simulator-service-proof-20260722T082000Z/social_simulator_service_proof_receipt.v1.json
  --timeout-s 30 --json`. Receipt status:
  `PASS_PCTOM_SOCIAL_SIMULATOR_SERVICE_PROOF`; service PID `180316`;
  service process return code `0`; 64 episodes; 64/64 policy action matches
  against independent replay; 5 fault trials. External simulator faults covered
  malformed JSON, timeout, missing endpoint, missing episode, and stale episode
  state. Terminal outcomes: 4 `BLOCKED_BEFORE_SIDE_EFFECT`,
  1 `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE`, 0
  `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect violations, 0 active partial
  state violations, and zero Tau, Memory-write, provider, canonical-memory,
  identity, or source-memory calls/writes. Declared receipt SHA-256:
  `sha256:251fff9eb8b07cc160347e234d5dc9d1efe1d1cc026a05dda44545b526e988ff`.
  This proves a separate local service process and local non-Memory service
  fault containment. It does not prove an internet-hosted or permanently
  deployed always-on production service.

  A live Memory aged-retention wrapper now adds the missing minimum-age
  acceptance guard around the existing no-write delayed recall checker. Command:
  `./skills/persona-dream/run.sh run-live-memory-aged-retention-recall
  --source-root
  /tmp/persona-dream-live-memory-revision-recall-variant17-24-20260722T034300Z
  --output-root
  /tmp/persona-dream-live-memory-aged-retention-recall-variant17-24-20260722T044000Z
  --receipt-out
  /tmp/persona-dream-live-memory-aged-retention-recall-variant17-24-20260722T044000Z/live_memory_aged_retention_recall_receipt.v1.json
  --min-age-s 1800 --recall-attempts 3 --recall-sleep-s 1 --json`.
  Receipt status: `PASS_PCTOM_LIVE_MEMORY_AGED_RETENTION_RECALL`; source
  created at `2026-07-22T03:33:18Z`, accepted at
  `2026-07-22T04:34:11Z`, elapsed age `3653.0` seconds, minimum age
  `1800` seconds. The nested delayed-recall receipt returned
  `PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL` with 128 source Memory
  documents, 128 semantic mirrors, 128 exact rereads, 128 semantic exact
  rereads, 4 live `/recall` queries, 40 hits, 10 hits per M/R/D/CD, and
  zero write violations or Memory/Tau/provider/canonical/identity/source-memory
  writes/calls. Declared wrapper receipt SHA-256:
  `sha256:a4374d1cfba1939f7926936285b95fff186dfb284ad275adfbe454a5a69982e3`.
  A negative too-young fixture with `--min-age-s 999999999` exited 1 with
  `BLOCKED_PCTOM_LIVE_MEMORY_AGED_RETENTION_RECALL`, error
  `minimum_age_not_satisfied:3676.0:999999999`, nested delayed recall
  `executed=false`, 0 nested recall queries, and zero writes/calls. Negative
  receipt SHA-256:
  `sha256:570aa04762329319804927d8dd5b5137f56af021484eae1084e37a6396d8be75`.
  This proves a fail-closed minimum-age boundary and about one hour of
  no-write live Memory retention for this PCTOM-R revision state. It does not
  prove multi-day wall-clock retention, permanently deployed service
  availability, new live Tau execution, paid provider execution, semantic dream
  quality, or complete Phase 01-16 runtime execution.

  A cross-stage hash/lineage audit now re-walks the held-out live-originated
  Gate 2-7 artifact chain. Command:
  `./skills/persona-dream/run.sh check-live-stage-hash-lineage-audit
  --condition-case-index
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/artifacts/live_condition_case_index.json
  --action-selection-receipt
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_action_selection/live_tau_condition_action_selection_receipt.v1.json
  --action-linked-revision-receipt
  /tmp/persona-dream-live-tau-action-linked-revision-variant17-24-20260722T034000Z/live_tau_action_linked_revision_receipt.v1.json
  --output-root
  /tmp/persona-dream-live-stage-hash-lineage-audit-variant17-24-20260722T050200Z
  --receipt-out
  /tmp/persona-dream-live-stage-hash-lineage-audit-variant17-24-20260722T050200Z/live_stage_hash_lineage_audit_receipt.v1.json
  --expect-cases 128 --json`. Receipt status:
  `PASS_PCTOM_LIVE_STAGE_HASH_LINEAGE_AUDIT`; counts: 128 condition cases,
  128 action cases, 128 revision cases, 896 stage artifacts loaded, 768 stage
  JSON hashes recomputed, 384 commitment hashes recomputed, 384 Gate 0
  accepted-source refs checked, 128 Gate 6 links checked, 128 Gate 7 links
  checked, and 0 write violations. The audit made zero Memory, Tau, provider,
  canonical-memory, identity, source-memory, LLM-judge, or human-content
  judgment calls/writes. Positive receipt SHA-256:
  `sha256:ed8002a321cf58b0d884d4b7723305325b5334a8e3fa17ed8200c28d55b264be`.
  A fixture-backed tamper negative changed one sealed prediction payload after
  its recorded hash and exited 1 with
  `BLOCKED_PCTOM_LIVE_STAGE_HASH_LINEAGE_AUDIT`, error containing
  `prediction_payload_sha256_mismatch`, plus path lineage mismatches from the
  copied case root. Negative receipt SHA-256:
  `sha256:20bf4655a0b1fe01199bf52833a97129488e6afa46e2c592bc5d8d448bd019b3`.
  This proves an independent cross-stage hash and lineage audit over existing
  live-originated artifacts. It does not prove new live Tau execution, new live
  Memory recall, paid provider execution, semantic dream quality, or complete
  Phase 01-16 runtime execution.

  A reusable Gate 5-7 negative-boundary harness now consumes the same
  live-originated held-out case and calls the existing validators. Command:
  `./skills/persona-dream/run.sh check-live-gate5-7-boundary-negatives
  --corpus
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/artifacts/social_episode_corpus.v1.json
  --case-root
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/artifacts/cases/sealedte-info-asym-17/M
  --scoring-receipt
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_condition_comparison/receipts/cases/sealedte-info-asym-17/M/gate5_scoring_receipt.json
  --action-selection
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_action_selection/artifacts/cases/sealedte-info-asym-17/M/action_selection.json
  --belief-revision
  /tmp/persona-dream-live-tau-action-linked-revision-variant17-24-20260722T034000Z/artifacts/cases/sealedte-info-asym-17/M/tom_belief_revision.json
  --output-root
  /tmp/persona-dream-live-gate5-7-boundary-negatives-20260722T051500Z
  --receipt-out
  /tmp/persona-dream-live-gate5-7-boundary-negatives-20260722T051500Z/live_gate5_7_boundary_negatives_receipt.v1.json
  --json`. Receipt status:
  `PASS_PCTOM_LIVE_GATE5_7_BOUNDARY_NEGATIVES`; 3/3 source positive checks
  passed, 3/3 negative cases blocked, and 3/3 expected error sets matched.
  Mutations covered Gate 5 invalid outcome action
  (`BLOCKED_TOM_SCORING_RECEIPT`, `outcome_actual_next_action_not_allowed`),
  Gate 6 invalid selected agent action (`BLOCKED_TOM_ACTION_SELECTION`,
  `selected_action_not_in_vocabulary`), and Gate 7 non-auditable prior plus
  evidence mutation (`BLOCKED_TOM_BELIEF_REVISION`,
  `prior_remains_auditable_not_true` and `evidence_mutations_not_empty`).
  The harness made zero Tau, Memory, provider, canonical-memory, identity,
  source-memory, LLM-judge, or human-content-judgment calls/writes. Receipt
  SHA-256:
  `sha256:073f442055685be34598a531babad47ce583f96d98f800370813fa0942013993`.
  This proves reusable fail-closed negative coverage for the live-originated
  Gate 5 scoring, Gate 6 action-selection, and Gate 7 belief-revision
  boundaries. It does not prove new live Tau execution, new Memory recall,
  paid provider execution, semantic dream quality, long-duration retention, or
  complete Phase 01-16 runtime execution.

  A PCTOM-R autonomous no-human-judgment surface audit now aggregates selected
  receipts instead of relying on vague status claims. Command:
  `./skills/persona-dream/run.sh check-autonomous-no-human-judgment-surface
  --receipt <15 selected PCTOM-R receipt paths> --output-root
  /tmp/persona-dream-autonomous-no-human-judgment-surface-20260722T090000Z
  --receipt-out
  /tmp/persona-dream-autonomous-no-human-judgment-surface-20260722T090000Z/autonomous_no_human_judgment_surface_receipt.v1.json
  --expect-receipts 15 --json`. Receipt status:
  `PASS_PCTOM_AUTONOMOUS_NO_HUMAN_JUDGMENT_SURFACE`; counts: 15 receipts
  seen, 15 PASS-status receipts, 12 `live=true`, 15 explicit
  `human_content_judgment_required=false`, 11 explicit
  `llm_judge_used=false`, 4 LLM-judge fields absent but none true,
  `mocked_true=0`, `fixture_backed_true=0`, `human_forbidden_true=0`,
  `llm_judge_true=0`, and `provider_or_canonical_write_counters=0`.
  Declared receipt SHA-256:
  `sha256:374e83a9015a500ca6def7ac8e3dfc5677bdf57331e09f2d8578a8b3cb372b8a`.
  A fixture-backed negative mutated one otherwise PASS receipt to
  `human_content_judgment_required=true`; the audit exited 1 with
  `BLOCKED_PCTOM_AUTONOMOUS_NO_HUMAN_JUDGMENT_SURFACE`, errors containing
  `receipt_human_content_judgment_required_true`,
  `receipt_human_flag_true`, and `human_forbidden_true_count_nonzero`.
  Negative receipt SHA-256:
  `sha256:2320082b585245df8a7576f529de443cae6b3aa563136e46050277c3bf94f99e`.
  This proves the selected PCTOM-R evidence surface is mechanically checked for
  autonomous no-human-content-judgment execution and fails closed if that
  boundary is violated. It does not prove semantic dream quality, paid provider
  execution, future receipts not passed through the audit, or complete live
  Phase 01-16 runtime execution.

  A manifest-driven PCTOM-R goal-coverage checker now prevents agents from
  claiming alignment from prose alone. Command:
  `./skills/persona-dream/run.sh check-pctom-goal-coverage --manifest
  /tmp/persona-dream-pctom-goal-coverage-20260722T093000Z/pctom_goal_coverage_manifest.v1.json
  --output-root /tmp/persona-dream-pctom-goal-coverage-20260722T093000Z
  --receipt-out
  /tmp/persona-dream-pctom-goal-coverage-20260722T093000Z/pctom_goal_coverage_receipt.v1.json
  --json`. Receipt status: `PASS_PCTOM_GOAL_COVERAGE`; counts: 14 required
  coverage ids, 14 seen, 0 missing, 35 evidence receipts, 26 positive evidence
  receipts, 9 negative evidence receipts, and 16 live positive evidence
  receipts. The manifest covers Gate 0 provenance, Gate 1 deterministic hidden
  social episodes, Gates 2-7 ToM distribution/branch/seal/score/action/
  revision, Gate 8 fault containment, Gate 9 causal replay, cross-stage hash
  lineage, autonomous no-human-judgment, memory retention/recall, and negative
  fixtures fail-closed. Manifest SHA-256:
  `sha256:cba428e1d80fb728079c2b4386a72bcf1b7e786074da4e519f1059b686982131`;
  receipt SHA-256:
  `sha256:56cd33cb7d3f9ad50ac06cfc49a5f2446c4275aa0b265cdc52ccfcb095c0115d`.
  A missing-coverage negative removed `gate9_causal_replay`; the checker
  exited 1 with `BLOCKED_PCTOM_GOAL_COVERAGE`, `coverage_ids_seen=13`,
  `coverage_ids_missing=1`, and error
  `missing_required_coverage_id:gate9_causal_replay`. Negative receipt
  SHA-256:
  `sha256:042a331bea370b9b50c579dce76e3d0964ed06fe6bad45b6e44143223f14cd9b`.
  This proves a machine-checkable evidence map for the current active goal.
  It does not prove semantic dream quality, paid provider execution, future
  receipts outside the manifest, or complete Phase 01-16 media runtime
  execution.

  The goal-coverage checker now requires a separate
  `unsupported_evidence_abstention` coverage id. The old 14-id manifest exits 1
  under the tightened checker. Negative receipt:
  `/tmp/persona-dream-pctom-goal-coverage-negative-missing-unsupported-abstention-20260722T120000Z/pctom_goal_coverage_receipt.v1.json`.
  Status: `BLOCKED_PCTOM_GOAL_COVERAGE`; counts: 15 required coverage ids,
  14 seen, 1 missing; error:
  `missing_required_coverage_id:unsupported_evidence_abstention`; receipt
  SHA-256:
  `sha256:03426a47433d0758222f9bbedcee4e0502af034f1668b8e06491d4b606754dd8`.
  Superseding expanded manifest:
  `/tmp/persona-dream-pctom-goal-coverage-unsupported-abstention-20260722T120100Z/pctom_goal_coverage_manifest.v1.json`.
  Superseding expanded receipt:
  `/tmp/persona-dream-pctom-goal-coverage-unsupported-abstention-20260722T120100Z/pctom_goal_coverage_receipt.v1.json`.
  Status: `PASS_PCTOM_GOAL_COVERAGE`; counts: 15 required coverage ids,
  15 seen, 0 missing, 37 evidence receipts, 27 positive receipts, 10 negative
  receipts, and 16 live positive receipts. Manifest SHA-256:
  `sha256:44eea9bb77a90a6b275afaaaadb2ffdf6205743d19a47e96cf808d4fc14915a7`;
  receipt SHA-256:
  `sha256:19d64e0123136e7dd5bc856e12f7ec5e4b29657e044da6135ee4454e86bf8ca4`.

  A PCTOM-R success-criteria audit now prevents a scoped result from being
  reported as full hard success. Command:
  `./skills/persona-dream/run.sh check-pctom-success-criteria
  --prediction-receipt
  /tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_statistical_confidence_receipt.v1.json
  --planning-receipt
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_planning_replication_receipt.v1.json
  --goal-coverage-receipt
  /tmp/persona-dream-pctom-goal-coverage-20260722T093000Z/pctom_goal_coverage_receipt.v1.json
  --output-root /tmp/persona-dream-pctom-success-criteria-20260722T094500Z
  --receipt-out
  /tmp/persona-dream-pctom-success-criteria-20260722T094500Z/pctom_success_criteria_audit_receipt.v1.json
  --json`. Receipt status: `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT`; summary:
  `prediction_benefit_with_confidence=true`,
  `planning_benefit_with_confidence=true`, `goal_coverage_complete=true`,
  `same_scope_joint_success=false`, and
  `full_hard_success_criteria_met=false`. Receipt SHA-256:
  `sha256:5b14a97dd245ece531fc59e345e560f073d153177706e5525bf3223e2c2ee3dd`.
  A fixture-backed negative mutated the live planning receipt's planning
  benefit flags false; the audit exited 1 with
  `BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT`, error
  `planning_benefit_with_confidence_not_proven`, and receipt SHA-256
  `sha256:1d5dbe5a73bdc32f522f82eed3e463a68e2dc4c35a9cb85ed48723d05b4d42f3`.
  This proves confidence-bound prediction and planning benefits are currently
  scoped evidence, not one same-scope full-success result. The next scientific
  gap is a same-scope sealed live experiment that proves prediction benefit and
  planning benefit together while preserving the existing reliability surface.

  The success-criteria checker was then extended with
  `--repeated-full64-receipt` and applied to the two-run full64 live Tau
  aggregate. Command:
  `./skills/persona-dream/run.sh check-pctom-success-criteria
  --prediction-receipt
  /tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_statistical_confidence_receipt.v1.json
  --planning-receipt
  /tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_planning_replication_receipt.v1.json
  --goal-coverage-receipt
  /tmp/persona-dream-pctom-goal-coverage-20260722T093000Z/pctom_goal_coverage_receipt.v1.json
  --repeated-full64-receipt
  /tmp/persona-dream-live-tau-full64-repeated-run-summary-gate0-r2-20260722T025200Z/live_tau_full64_repeated_run_summary_receipt.v1.json
  --output-root
  /tmp/persona-dream-pctom-success-criteria-repeated-full64-20260722T101000Z
  --receipt-out
  /tmp/persona-dream-pctom-success-criteria-repeated-full64-20260722T101000Z/pctom_success_criteria_audit_receipt.v1.json
  --json`. Receipt status: `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT`; summary:
  `prediction_benefit_with_confidence=true`,
  `planning_benefit_with_confidence=true`, `goal_coverage_complete=true`,
  `repeated_full64_same_scope_success=true`, `same_scope_joint_success=true`,
  and `full_hard_success_criteria_met=true`. The repeated full64 aggregate
  consumed 2 Gate 0-attributed live Tau full64 source roots, 128 episode metric
  rows, and 512 live Tau calls; belief Brier CI upper was
  `-0.07867421875000002`, and planning-regret CI upper was
  `-0.027734374999999995`. Receipt SHA-256:
  `sha256:07a55ddb3a5e51072343c222fb7ce11397aa8bd6033c31adaf5c058d49818098`.
  A fixture-backed negative mutated the repeated full64 planning benefit flag
  false and exited 1 with `BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT`, error
  `repeated_full64_same_scope_success_not_proven`, and receipt SHA-256
  `sha256:fe06372a70c5f8e79b4023f5f5c34f8ccdb0591e78a381ae7b000df9802ba619`.
  This closes the prior same-scope prediction-plus-planning evidence gap for
  the repeated full64 live Tau aggregate. It does not prove paid provider
  execution, semantic dream quality, multimodal perception, or complete
  Phase 01-16 media runtime execution.

  A PCTOM-R calibration/abstention audit now covers the repeated full64 Gate 5
  metric surface. Command:
  `./skills/persona-dream/run.sh check-pctom-calibration-abstention
  --source-root /tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z
  --source-root /tmp/persona-dream-live-tau-sealed-test-gate0-full64-repeat2-20260722T020900Z
  --output-root /tmp/persona-dream-pctom-calibration-abstention-full64-r2-20260722T110000Z
  --json`. Receipt status:
  `PASS_PCTOM_CALIBRATION_ABSTENTION_AUDIT`; counts: 2 source roots, 512
  raw case rows, 512 audited case rows, 512 calibration rows, 512
  risk-coverage rows, 1536 calibration bucket items, and 0 abstained rows.
  Metrics: `mean_expected_calibration_error=0.36621092838541663`,
  `mean_coverage=1.0`, `mean_selective_accuracy=0.3671875`, and
  `abstention_observed=false`. Receipt SHA-256:
  `sha256:32cd4119562b98aa7e74757e27d06658820f487b751052322e9a44fb39419bca`.
  A fixture-backed negative removed one `risk_coverage` object from a copied
  full64 case index and exited 1 with
  `BLOCKED_PCTOM_CALIBRATION_ABSTENTION_AUDIT`, errors
  `row_0_missing_risk_coverage`, `calibration_rows_mismatch:255:256`,
  `risk_coverage_rows_mismatch:255:256`, and
  `check_failed:audited_rows_match_expected_shape:False`; negative receipt
  SHA-256:
  `sha256:03e942068405a5cccfcf5a5c338ab1266f57fa86f638cb0d00c8e745abc65be4`.
  This proves the full64 Gate 5 rows carry auditable calibration and
  risk-coverage fields. It does not prove abstention improves decisions under
  unsupported evidence because the repeated full64 surface contains no
  abstained rows.

  The success-criteria audit was then tightened with
  `--calibration-abstention-receipt` so same-scope prediction plus planning
  cannot be misreported as complete hard success without the calibration and
  abstention surface. Superseding receipt:
  `/tmp/persona-dream-pctom-success-criteria-calibration-bound-20260722T111000Z/pctom_success_criteria_audit_receipt.v1.json`.
  It returned `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT` with
  `repeated_full64_same_scope_success=true`, `same_scope_joint_success=true`,
  `calibration_surface_audited=true`,
  `unsupported_evidence_abstention_exercised=false`, and
  `full_hard_success_criteria_met=false`. Receipt SHA-256:
  `sha256:527b3cd017d11ade9b2c59b0e061a2b46505d96ac46d791e0eaa14d1df04c248`.
  A fixture-backed negative passed the blocked calibration receipt into the
  success checker and exited 1 with
  `BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT`, errors
  `calibration_abstention_status_not_expected`,
  `calibration_abstention_live_not_true`, and
  `calibration_surface_not_audited`; negative receipt SHA-256:
  `sha256:d934716e84a8e5f6f43f93d262f94b887200176741f3e7b28fb5a09bfd9506e6`.
  Current interpretation at that point: PCTOM-R had same-scope repeated live Tau
  evidence for prediction and planning benefit, plus a full64
  calibration/risk-coverage metric audit, but the broader hard-success claim
  remained pending until an unsupported-evidence abstention fixture or live
  slice was exercised and scored.

  Unsupported-evidence abstention is now exercised through the existing Gate 2
  and Gate 5 validators. Command:
  `./skills/persona-dream/run.sh check-pctom-unsupported-evidence-abstention
  --corpus
  /tmp/persona-dream-pctom-social-corpus-sealed64-20260722T041800Z/social_episode_corpus.v1.json
  --output-root
  /tmp/persona-dream-pctom-unsupported-evidence-abstention-20260722T112000Z
  --json`. Receipt status:
  `PASS_PCTOM_UNSUPPORTED_EVIDENCE_ABSTENTION`; counts: 4 case rows,
  4 families, 8 unsupported distribution rows, 4 Gate 2 passes, 4 Gate 5
  passes, 4 risk-coverage rows, and 4 abstained rows. Checks:
  `four_families_exercised=true`,
  `gate2_unsupported_abstention_passed=true`,
  `gate5_abstention_scored=true`,
  `unsupported_evidence_abstention_exercised=true`,
  `unsupported_writes_absent=true`, `llm_judge_absent=true`, and
  `human_content_judgment_absent=true`. Receipt SHA-256:
  `sha256:e26e29aebd860664199bac9ad0de4818a6c13691d4a21aac246b9c0398864894`.
  A negative fixture with `--negative-mode marked_supported` exited 1 with
  `BLOCKED_PCTOM_UNSUPPORTED_EVIDENCE_ABSTENTION`, 4 Gate 2 blocked cases,
  0 Gate 5 passes, 0 risk-coverage rows, 0 abstained rows, and error
  `negative_mode_triggered_fail_closed:marked_supported`. Negative receipt
  SHA-256:
  `sha256:04dca2e1106e5dee74aae95b2984a78de066ea4b8e7352ed256543d0fc0af297`.

  The success-criteria audit now requires
  `--unsupported-abstention-receipt` before full hard success can be reported.
  Superseding receipt:
  `/tmp/persona-dream-pctom-success-criteria-unsupported-abstention-bound-20260722T113000Z/pctom_success_criteria_audit_receipt.v1.json`.
  It returned `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT` with
  `same_scope_joint_success=true`, `calibration_surface_audited=true`,
  `unsupported_evidence_abstention_exercised=true`, and
  `full_hard_success_criteria_met=true`. Receipt SHA-256:
  `sha256:20814bdfb3ba354cd51ef4bceb8a13b8c7303572413712170cd181dfcd04cefb`.
  Passing the blocked unsupported-abstention receipt into the same checker
  exited 1 with `BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT`, errors
  `unsupported_abstention_status_not_expected` and
  `unsupported_evidence_abstention_not_exercised`; negative receipt SHA-256:
  `sha256:c3fcd7ff13b4cd51d3af41e995ecfaf4be01b30ebb653038e6b79379f19436a6`.
  This closes the previous unsupported-evidence abstention exercise gap for the
  deterministic sealed-corpus validator/scorer lane. It does not prove live Tau
  authored an abstention response, paid provider execution, semantic dream
  quality, multimodal perception, or complete Phase 01-16 media runtime
  execution.

  The success-criteria audit now requires the expanded 15-id goal-coverage
  receipt. Superseding receipt:
  `/tmp/persona-dream-pctom-success-criteria-expanded-coverage-r2-20260722T120400Z/pctom_success_criteria_audit_receipt.v1.json`.
  It returned `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT` with
  `goal_coverage_complete=true`, `same_scope_joint_success=true`,
  `calibration_surface_audited=true`,
  `unsupported_evidence_abstention_exercised=true`, and
  `full_hard_success_criteria_met=true`; receipt SHA-256:
  `sha256:adeb6ad468edc718c087998865b94d7f9e38ab6653bcca53e2070b5ad8b75c96`.
  Passing the stale/missing-unsupported coverage receipt into the same checker
  exited 1 with `BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT`, errors
  `goal_coverage_status_not_expected:BLOCKED_PCTOM_GOAL_COVERAGE` and
  `goal_coverage_incomplete`; negative receipt SHA-256:
  `sha256:0bea6958afbb7653c8db745adfd1e87851d6d2401034eaeb964fc120cbd1cfac`.
  This prevents a top-level success receipt from passing unless the explicit
  unsupported-evidence abstention coverage clause is present.

  Command:
  `./skills/persona-dream/run.sh run-live-tau-balanced-planning-replication
  --family-episode-limit 8 --episodes-per-family 24 --variant-min 17
  --variant-max 24 --gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case
  --timeout-s 120 --outer-timeout-s 5400 --bootstrap-samples 10000
  --bootstrap-seed 20260727`. Replication receipt:
  `/tmp/persona-dream-live-tau-balanced-planning-gate0-variant17-24-20260722T030200Z/live_tau_balanced_planning_replication_receipt.v1.json`.
  Causal-identifiability receipt:
  `/tmp/persona-dream-pctom-causal-identifiability-gate0-variant17-24-20260722T032200Z/pctom_causal_identifiability_receipt.json`.
  Condition reliability bridge receipt:
  `/tmp/persona-dream-live-tau-condition-reliability-bridge-variant17-24-20260722T033000Z/live_tau_condition_reliability_bridge_receipt.v1.json`.
  Action-linked belief-revision receipt:
  `/tmp/persona-dream-live-tau-action-linked-revision-variant17-24-20260722T034000Z/live_tau_action_linked_revision_receipt.v1.json`.
  Deterministic revision-recall receipt:
  `/tmp/persona-dream-live-tau-revision-recall-variant17-24-20260722T034200Z/live_tau_revision_recall_receipt.v1.json`.
  Live Memory revision-recall receipt:
  `/tmp/persona-dream-live-memory-revision-recall-variant17-24-20260722T034300Z/live_memory_revision_recall_receipt.v1.json`.
  Live Memory delayed-recall receipt:
  `/tmp/persona-dream-live-memory-revision-delayed-recall-variant17-24-20260722T042700Z/live_memory_revision_delayed_recall_receipt.v1.json`.
  Live fault-injection surface receipt:
  `/tmp/persona-dream-live-fault-injection-surface-variant17-24-20260722T034600Z/live_fault_injection_surface_receipt.v1.json`.
  Local HTTP service retry proof receipt:
  `/tmp/persona-dream-live-tau-sealed-test-service-retry-proof-repeat2-20260722T041200Z/live_tau_sealed_test_service_retry_proof_receipt.v1.json`.
  Combined full64 Memory fault-surface receipt:
  `/tmp/persona-dream-live-tau-full64-memory-fault-surface-repeat2-20260722T041500Z/live_tau_full64_memory_fault_surface_receipt.v1.json`.

  Statuses `PASS_SOCIAL_EPISODE_CORPUS_BUILT`, `PASS_SOCIAL_EPISODE_CORPUS`,
  `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION` and
  `PASS_PCTOM_CAUSAL_IDENTIFIABILITY_GATE`; the condition reliability bridge
  then returned `PASS_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE`. Observed:
  variants 17-24, 32 sealed-test episodes, all four scenario families, 128
  live Tau calls, 32 sealed/scored/action rows per M/R/D/CD condition,
  `mocked=false`, `live=true`, zero Memory/provider/canonical/identity/
  source-memory writes, no LLM judge, and no human content judgment. Planning
  regret had a
  confidence-bound CD advantage on this held-out slice: CD `0.196875` versus
  strongest baseline `R=0.365625`, CD-minus-baseline
  `-0.16874999999999998`, 95% CI
  `[-0.290625, -0.056249999999999994]`,
  `planning_benefit_with_confidence=true`. Causal lineage replay observed
  128/128 lineage rows complete, 384/384 evidence refs with accepted raw-source
  IDs and source digests, `oracle_improves_regret_count=67`, and
  `anti_oracle_worsens_regret_count=53`.

  The reliability bridge consumed the held-out live condition comparison root
  with zero new Tau calls. Gate 8 accepted 7 trials across required fault
  families: stale artifact, missing graph edge, malformed structured output,
  and interrupted persistence/retry. Terminal outcomes were
  `RECOVERED_WITH_EQUIVALENT_END_STATE=4`,
  `BLOCKED_BEFORE_SIDE_EFFECT=2`, and
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE=1`, with
  `continued_with_unknown_state=0`. Gate 9 accepted one causal replay and
  localized stale-artifact divergence to one replaced tool return.

  The action-linked revision bridge consumed the held-out live Gate 6
  action-selection root with zero new Tau calls. It wrote and checked 128/128
  strict Gate 7 non-destructive belief revisions. Each condition has 32 prior
  action-linked hypotheses and 32 posterior current-use revisions. Checks
  confirmed the action-selection base receipt hash recomputed, all four
  conditions were represented, priors remained auditable, unsupported writes
  were absent, and no human content judgment was required.

  The deterministic revision-recall runner had an old exact-16 compatibility
  guard. It was repaired to require at least 16 cases and full Gate 7 pass
  coverage, so it can consume the current 128-case held-out root without
  weakening condition/write checks. The paired live Memory runner now applies
  the same at-least-16 guard for deterministic recall documents. Deterministic
  recall over the held-out revision root produced 128 revision documents, 4
  local recall queries, 128 hits, prior/posterior distinction true,
  synthetic/literal boundary true, and zero write violations.

  Live Memory recall after revision wrote 128 noncanonical PCTOM-R research
  documents and 128 searchable noncanonical lesson mirrors, exactly reread
  128/128 in both collections, and live `/recall` returned 40 hits, 10 per
  M/R/D/CD condition. It made `memory_write_attempts=2` for the noncanonical
  research/mirror writes and zero canonical, identity, source-memory, provider,
  Tau, or human-content-judgment calls/writes.

  A fresh no-write delayed-recall process then consumed that live Memory root.
  It reports `PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL`: 128 source
  Memory documents, 128 semantic mirrors, 128 delayed exact rereads, 128
  delayed semantic exact rereads, 4 delayed `/recall` queries, 40 delayed
  recall hits, 10 hits per M/R/D/CD condition, `memory_write_attempts=0`,
  `write_violations=0`, prior/posterior distinction true, and
  synthetic/literal boundary true. This proves a fresh process can re-read and
  recall the prior noncanonical revision Memory state without writing. It does
  not prove a Memory service restart or long-duration wall-clock retention.

  A negative delayed-recall fixture then copied only the source receipt and
  mutated its `semantic_document_index` to a missing path. Command:
  `./skills/persona-dream/run.sh run-live-memory-revision-delayed-recall
  --source-root
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-semantic-index-20260722T050300Z/source
  --output-root
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-semantic-index-20260722T050300Z/output
  --receipt-out
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-semantic-index-20260722T050300Z/output/live_memory_revision_delayed_recall_receipt.v1.json
  --recall-attempts 1 --recall-sleep-s 0 --json`. It exited 1 and wrote
  `BLOCKED_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL`, with 128 exact rereads,
  0 semantic source documents, 0 semantic exact rereads, 4 recall queries,
  0 recall hits, and zero Memory/canonical/identity/source-memory write
  attempts. Errors included `missing_source_semantic_document_index`,
  `source_semantic_document_index_not_list`, and insufficient delayed recall
  hits for M/R/D/CD. Declared receipt SHA-256:
  `sha256:99ff128aa50c8aa9c02bde015c7fc8f0174b04ccda61c3c40a3961ce3a4ad31a`.
  This proves the delayed-recall checker fails closed when the semantic
  provenance boundary is missing; it does not prove service restart,
  long-duration retention, or non-Memory external-service faults.

  A second negative delayed-recall fixture copied the source receipt and
  mutated `document_index` to a missing path while leaving the semantic index
  intact. Command:
  `./skills/persona-dream/run.sh run-live-memory-revision-delayed-recall
  --source-root
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-document-index-20260722T051000Z/source
  --output-root
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-document-index-20260722T051000Z/output
  --receipt-out
  /tmp/persona-dream-live-memory-revision-delayed-recall-negative-missing-document-index-20260722T051000Z/output/live_memory_revision_delayed_recall_receipt.v1.json
  --recall-attempts 1 --recall-sleep-s 0 --json`. It exited 1 and wrote
  `BLOCKED_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL`, with 0 source Memory
  documents, 128 semantic mirrors, 0 delayed exact rereads, 128 delayed
  semantic exact rereads, 4 recall queries, 40 recall hits, and zero
  Memory/canonical/identity/source-memory write attempts. Errors were
  `missing_source_document_index` and `source_document_index_not_list`.
  Declared receipt SHA-256:
  `sha256:9a8c2f8d0efe73a5ede095d3a8c0809369ea4beb7afca6e370cb174263fba704`.
  This proves live recall hits are not sufficient for delayed-recall
  acceptance when primary source-document provenance is missing.

  A live Memory service restart proof then consumed the same live Memory
  revision-recall source root. Command:
  `./skills/persona-dream/run.sh run-live-memory-restart-delayed-recall
  --source-root
  /tmp/persona-dream-live-memory-revision-recall-variant17-24-20260722T034300Z
  --output-root
  /tmp/persona-dream-live-memory-restart-delayed-recall-variant17-24-20260722T061500Z
  --receipt-out
  /tmp/persona-dream-live-memory-restart-delayed-recall-variant17-24-20260722T061500Z/live_memory_restart_delayed_recall_receipt.v1.json
  --wait-timeout-s 90 --wait-sleep-s 1 --recall-attempts 3
  --recall-sleep-s 1 --json`. It restarted `embry-memory` through
  `systemctl --user restart`, changed MainPID from `4090` to `4155998`,
  observed post-restart `/health` `ok=true`, and then ran the existing delayed
  revision-recall checker in a fresh subprocess. Receipt status:
  `PASS_PCTOM_LIVE_MEMORY_RESTART_DELAYED_RECALL`; nested delayed-recall
  status: `PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL`; nested counts:
  128 source documents, 128 semantic mirrors, 128 exact rereads, 128 semantic
  exact rereads, 4 recall queries, 40 recall hits, 10 per M/R/D/CD. Write,
  Tau, and provider counters were all zero. Declared receipt SHA-256:
  `sha256:f21e540c7dee0520ab4ee6cf0594e872c88b86ef3d95d6434c433adb978cbbfc`.
  This proves restart-interval retention and recall recovery for the
  noncanonical PCTOM-R revision state. It does not prove long-duration
  wall-clock retention or non-Memory external-service faults.

  The broader live fault-injection surface consumed the deterministic sealed
  test statistical-confidence root
  `/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z`
  and the live Memory revision-recall root above. It reports
  `PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE` with 8 required fault families,
  8 fault trials, 4 live Memory fault probes, and 1 causal replay receipt.
  Terminal outcomes were `BLOCKED_BEFORE_SIDE_EFFECT=4`,
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE=2`, and
  `RECOVERED_WITH_EQUIVALENT_END_STATE=2`; `continued_with_unknown_state=0`,
  `side_effect_violations=0`, and Memory/provider/Tau/canonical/identity/
  source-memory write or call attempts inside this fault-surface command were
  all 0. This is broader live Memory fault-probe coverage plus controlled local
  model/tool/schema/persistence/retry fault containment; it is not proof of
  production-deployed retry machinery or non-Memory external service faults.

  The local HTTP service retry proof consumed the repeat2 full64 live Tau
  sealed-test replication root through a separate local HTTP service process.
  It reports `PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF`: 5 HTTP requests,
  4 unique service jobs, 1 duplicate submission detected and not promoted,
  2 completed jobs, 2 blocked jobs, 256 active predictions, 256 action
  decisions, 256 Gate 6 receipts, 8 retry fault trials, and 0
  `CONTINUED_WITH_UNKNOWN_STATE`, side-effect violations, duplicate active
  predictions, or duplicate action decisions.

  The combined full64 Memory fault-surface consumed the repeat2 full64
  statistical-confidence root, the live Memory revision-recall root, and the
  local HTTP service retry proof. It reports
  `PASS_LIVE_TAU_PCTOM_FULL64_MEMORY_FAULT_SURFACE`: 8 fault families, 8 fault
  trials, 10 live Memory fault probes, 4 condition recall queries with 4
  successes, and 1 causal replay receipt. Terminal outcomes were
  `BLOCKED_BEFORE_SIDE_EFFECT=3`,
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE=1`, and
  `RECOVERED_WITH_EQUIVALENT_END_STATE=4`; `continued_with_unknown_state=0`,
  `side_effect_violations=0`, and Memory/provider/Tau/canonical/identity/
  source-memory write or call attempts inside this combined surface were all
  0. This binds live Tau statistical evidence, live Memory recall, and local
  service retry discipline into one artifact, while still not proving a
  permanently deployed external production service.

  Receipt SHA-256 values: replication
  `sha256:98336825a38be02d455e391735e2153986e89e2eba619b9a9a894b9ac6a6d272`;
  condition
  `sha256:2da4ed6c0d49e6ed8d61ce4667862b8cf78114a3b37b6ccc92646ce39daeb31c`;
  action
  `sha256:b11d4abfbe53b91fb08d8e0dc95f9536ba68a92ba6438c64b0245e01e6b158df`;
  causal
  `sha256:2903066090fdff791feb509c2f5c670af6f2327f3389d9cc899f8a236d8a8032`;
  lineage
  `sha256:28cb8a34fa22b98bb06b4964ab8971afd0592c3e0624b216796a1f61c4f4cdd3`;
  reliability bridge
  `sha256:0fd7d4c4747d1d3eaa54c47d7d9ab7b93a61cbcd01c4e727b0450c9d4a850c86`;
  Gate 8 surface check
  `sha256:c658c1fb86d87ea8d87deaf759d00332a30c6634429bfd3cc35e9ab106cbef64`;
  Gate 9 replay check
  `sha256:189a9435d742e8692b067458152c0acaaa67d8f9a6bf34df2b6d1e03422d2c6d`;
  action-linked revision
  `sha256:7955621d16a13224f13558d959dcfd3b36ff0dfdedb4c05140ab0c0a10aedb93`;
  action-linked revision index
  `sha256:41cee5aa52c5786ad8b6ac9d79271c21df1d660217c5594e335951025a78107b`;
  deterministic revision recall
  `sha256:3777f0938e13cb36038c91ed78797783fd0a8db3e3ff2e38ab411644dcac1a8e`;
  deterministic revision recall index
  `sha256:4998b2a64580476579f3cac21843d6f5019b728fe165dcc916d4fdae7bac23b1`;
  deterministic revision recall results
  `sha256:e2ce3d8c8adf6e6bb15a85ade9a57c9073facaa00ede65302e1ebc7f12e6995e`;
  live Memory revision recall
  `sha256:ea4546e85f8f1bc5392dd810bb83d0b5b7ae42682b093384eac25c8cce8fb63a`;
  live Memory revision documents
  `sha256:925333b88ab513c57fdf595a14010497f8408c7a5e34c78bd977b571cef92290`;
  live Memory recall results
  `sha256:1ca8c485b658d43f8cceb4a97986ee3b0104c5399bedd07ce23c9391ad96c786`;
  live Memory delayed recall declared receipt
  `sha256:db582b1fd3737d2162e1745fdb13bd08345b4dcb9ed57706b797b0acad8e984e`;
  live Memory delayed exact rereads
  `sha256:8a548e5863046496702aeca207e9db1a17c62ed0b2d23d7437234c781ffe0d3e`;
  live Memory delayed semantic exact rereads
  `sha256:42faa2361dca97a7d26c4b0e145ca32955a9ba2b68c0741e3cb2ca19b27f74c0`;
  live Memory delayed recall results
  `sha256:045f38d09fdb5b337b5dc3868cdbd25ee8afbc92b37078c334ad9edbef54ecde`;
  live fault-surface declared receipt
  `sha256:2931a8c493a384cda42f9ed88e808c2b859f1fd920e1c99c322d5dadfefe2a4f`;
  live fault trials
  `sha256:faaa9d4991e474eee5b6a04649f7361480ee75d0573e1e4456f5f1a8cb2a8b92`;
  live Memory fault probes
  `sha256:2006a53b480e1646941c18b2800b7e1909e5a9221bd53f8e0eaecc916c88b085`;
  live fault causal replay
  `sha256:1120c65b75f3c9299420d56d2d7ac411365d5bfe853d61e226009bded032e807`;
  local HTTP service retry declared receipt
  `sha256:75179079a9dca235c1f24ab191aa909399f349c7500ae2a0f729255965559f9e`;
  local HTTP service manifest file
  `sha256:412bd68be6b3d6f7772bade88e2c1e538e2513628d7b12e89c4b85e38a4c2b85`;
  combined full64 Memory fault-surface declared receipt
  `sha256:adb6190f59be7999f28698c3915a063dcb383dccd212de3d26416900b2c69f6e`;
  combined full64 Memory fault trials
  `sha256:455979b5b42bb8d5431df73b3a75cf172b90def0d4aa2fb923241752cd642c94`;
  combined full64 live Memory probes
  `sha256:125921d11ce5a34483551cfc7039e029cb27d32fa7cc3aa1722da43246661f75`;
  combined full64 causal replay
  `sha256:2c7b9ee5604b83fa80e04da5b82bda35d7b3e415af56975b626f8915ad7ea5ac`;
  sealed64 corpus file
  `sha256:e29475d5f02db694cac595e26347ebcaef5a44ebbd24ef0fc19598eb1e8e2419`;
  sealed64 corpus build receipt file
  `sha256:7d126282525cd8d0815a4e0bbcb510c3873a8c10603cfa1ae9d2f3282b8efa2d`;
  sealed64 corpus check receipt file
  `sha256:657c34eec0449dedc939ef8896d30f7ea3c722aafbeb79904535b09d41a318fa`;
  sealed64 corpus stable payload
  `sha256:d39a692e435e03ef9bae5a93ad4f143f8e3f3e52cc8201698983547af7a4355c`;
  sealed64 episodes payload
  `sha256:f8f85a905452b280341571fd6cd84984bca209d25a97edc8799ab074c2514891`.
  This advances held-out variant/generalization evidence for PCTOM-R Gate 0
  and Gate 6, a controlled artifact-bound Gate 8/9 reliability bridge, and
  Gate 7 non-destructive belief revision linked to live-originated action
  decisions, including deterministic and live Memory recall after revision. It
  does not prove a permanently deployed external production service,
  internet-hosted external simulator reliability, long-duration wall-clock
  retention, semantic dream quality, paid provider execution, or complete live
  Phase 01-16 runtime execution.
- 2026-07-22 UTC (PCTOM-R GATE 0 REPEATED FULL64 LIVE TAU BOUNDARY): a second
  Gate 0-attributed full64 live Tau sealed-test replication now exists, and a
  two-root repeated-run summary consumes both full64 roots. Repeat2 command:
  `./skills/persona-dream/run.sh run-live-tau-sealed-test-replication
  --episode-limit 64 --episodes-per-family 16 --gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case`.
  Repeat2 replication receipt:
  `/tmp/persona-dream-live-tau-sealed-test-gate0-full64-repeat2-20260722T020900Z/live_tau_sealed_test_replication_receipt.v1.json`.
  Repeat2 causal-identifiability receipt:
  `/tmp/persona-dream-pctom-causal-identifiability-gate0-full64-repeat2-20260722T025200Z/pctom_causal_identifiability_receipt.json`.
  Repeat2 statistical-confidence receipt:
  `/tmp/persona-dream-live-tau-full64-statistical-confidence-gate0-repeat2-20260722T025200Z/live_tau_full64_statistical_confidence_receipt.v1.json`.
  Two-root repeated-run summary receipt:
  `/tmp/persona-dream-live-tau-full64-repeated-run-summary-gate0-r2-20260722T025200Z/live_tau_full64_repeated_run_summary_receipt.v1.json`.

  Statuses `PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION`,
  `PASS_PCTOM_CAUSAL_IDENTIFIABILITY_GATE`,
  `PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE`, and
  `PASS_LIVE_TAU_PCTOM_FULL64_REPEATED_RUN_SUMMARY`. Repeat2 observed 64
  sealed-test episodes, four scenario families, 256 live Tau calls, 64
  sealed/scored/action rows per M/R/D/CD condition,
  `gate0_attribution_overlay_used=true`, 6 Gate 0 attribution records, zero
  Memory/provider/canonical/identity/source-memory writes, and no LLM judge or
  human content judgment. Repeat2 causal replay observed 256/256 lineage rows
  complete and 768/768 evidence refs with accepted raw-source IDs and digests.
  Repeat2 statistical confidence again accepted the preregistered belief Brier
  benefit: mean `-0.10039218750000002`, 95% CI
  `[-0.11865976562500002, -0.08187894531250002]`,
  `primary_benefit_with_confidence=true`. Repeat2 planning-regret alone still
  did not meet the confidence bar: mean `-0.09453125`, 95% CI
  `[-0.1953125, 0.0015625000000000031]`,
  `planning_benefit_with_confidence=false`.

  The new repeated-run summary command
  `./skills/persona-dream/run.sh run-live-tau-full64-repeated-run-summary`
  hash-binds both Gate 0-attributed full64 roots and recomputes 128
  episode-level CD-vs-strongest-baseline rows from condition/action indices.
  It consumed 512 live Tau calls from source receipts without reexecuting Tau
  inside the aggregate command. Repeated-run belief Brier remained
  confidence-bound: mean `-0.09116718750000002`, 95% CI
  `[-0.10389453125000003, -0.07867421875000002]`. Repeated-run planning regret
  over the two same-split runs had a negative aggregate CI: mean
  `-0.094921875`, 95% CI `[-0.1640625, -0.027734374999999995]`.
  Action Brier remained harmful/not a benefit: mean `0.03796882812435939`, 95%
  CI `[0.0035813281243750193, 0.07271834895771875]`.

  Receipt SHA-256 values: repeat2 declared replication
  `sha256:bc6102d075fa1d48982054cf24dc61044595c855565b52769c2eb6ea9f9277b8`;
  repeat2 condition
  `sha256:ffb2053fd24fff2857e0787a677c519b69f5483aead4c137a2ebb10ee7bf47ca`;
  repeat2 action
  `sha256:ec487ccfa18f12fdc359a752231da4b6ab9e93b8f346c756cf5762bf67e43d25`;
  repeat2 causal
  `sha256:d47453d237ccd520ab45911be624539f7cc707f76b7c0f451163d8e492cb9ef1`;
  repeat2 lineage
  `sha256:f8b61885d926ddbbe15064eca259bbd411e807f5ec53a0a0bcd894f852eef198`;
  repeat2 statistical confidence
  `sha256:2b69fc35c4a5c369e1ac8c75060f47c6a11c9d6199e9bfabfe9ccbae6cbaf1ef`;
  repeated-run summary
  `sha256:0549f0698ec055561f736ce5b88a6f6394af377bc82e784d75f52b6d9f39c407`.
  This advances repeated-execution evidence for the same sealed-test split. It
  does not prove independent scenario-corpus generalization, production retry
  machinery, complete model/tool/schema/persistence fault injection, paid
  provider execution, semantic dream quality, or complete live Phase 01-16
  runtime execution.
- 2026-07-22 UTC (PCTOM-R GATE 0 FULL64 CONFIDENCE AND MEMORY/SERVICE FAULT
  SURFACE): after the Gate 0-attributed full64 live Tau replication and lineage
  replay, the existing full64 confidence runner consumed the accepted root
  without reexecuting Tau. Command:
  `./skills/persona-dream/run.sh run-live-tau-full64-statistical-confidence
  --base-root /tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z`.
  Receipt:
  `/tmp/persona-dream-live-tau-full64-statistical-confidence-gate0-20260722T015400Z/live_tau_full64_statistical_confidence_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE`; receipt SHA-256
  `sha256:c62ecfc46f257bc84d7cd0882e36c359a218c74800eed58f57f6314e473a8738`.
  Observed: 64 paired live Tau episodes, 10,000 bootstrap samples, primary
  preregistered metric `belief_brier`, strongest baseline `R`,
  CD-minus-baseline mean `-0.08194218750000003`, 95% CI
  `[-0.09819726562500003, -0.06552992187500004]`,
  `primary_benefit_with_confidence=true`. Action Brier was not confidence-bound
  and planning regret was not confidence-bound; planning mean
  `-0.09531250000000001`, 95% CI
  `[-0.19533203124999998, 0.0031249999999999997]`.

  The planning diagnostic originally failed closed because it assumed a stale
  sparse trust-only signal. The checker was corrected to accept supported
  diagnostic categories while still refusing a planning-benefit claim. Proof:
  `python3 -m py_compile
  skills/persona-dream/research/prospective-tom/scripts/run_live_tau_full64_planning_diagnostic.py`.
  Rerun command:
  `./skills/persona-dream/run.sh run-live-tau-full64-planning-diagnostic
  --base-root /tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z
  --confidence-root /tmp/persona-dream-live-tau-full64-statistical-confidence-gate0-20260722T015400Z`.
  Receipt:
  `/tmp/persona-dream-live-tau-full64-planning-diagnostic-gate0-r2-20260722T015509Z/live_tau_full64_planning_diagnostic_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC`; receipt SHA-256
  `sha256:e81720ca722343d8a8246b2277d43bde5a3d4f0695be8adddd5c9964fea616b9`.
  Diagnostic conclusion `BROAD_BUT_UNCERTAIN_SIGNAL`: 39 ties, 14 beneficial
  deltas, 11 harmful deltas, 25 nonzero deltas across `coord-conflict`,
  `pref-desire`, and `trust-commit`. This explains why the beneficial planning
  point estimate is not accepted as a confidence-bounded planning benefit.

  The Memory/service fault surface then consumed the full64 confidence root,
  strict live Memory revision recall root, and fresh local service retry root.
  Command:
  `./skills/persona-dream/run.sh run-live-tau-full64-memory-fault-surface
  --full64-stats-root /tmp/persona-dream-live-tau-full64-statistical-confidence-gate0-20260722T015400Z
  --live-memory-root /tmp/persona-dream-live-memory-revision-recall-strict120-v17-20260721T1547Z
  --service-retry-root /tmp/persona-dream-live-tau-sealed-test-service-retry-proof-fresh-20260721T155119Z`.
  Receipt:
  `/tmp/persona-dream-live-tau-full64-memory-fault-surface-gate0-20260722T015602Z/live_tau_full64_memory_fault_surface_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_FULL64_MEMORY_FAULT_SURFACE`; receipt SHA-256
  `sha256:9a15fa6fc8120aa6c4d553382914a888532a901d680db6afe6571739c75c9f73`.
  Observed: 8 fault families, 8 fault trials, 10 live Memory probes, 4/4
  condition recall successes, terminal outcomes
  `BLOCKED_BEFORE_SIDE_EFFECT=3`,
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE=1`, and
  `RECOVERED_WITH_EQUIVALENT_END_STATE=4`, with
  `continued_with_unknown_state=0` and `side_effect_violations=0`.

  These three commands made zero Tau calls after the full64 replication, zero
  provider calls, zero canonical/identity/source-memory writes, and used no LLM
  judge or human content judgment. This establishes confidence-bounded live Tau
  benefit for the preregistered belief Brier metric and a bounded live
  Memory/service fault surface over the Gate 0-attributed full64 evidence. It
  does not establish confidence-bounded planning benefit, repeated-seed
  generalization, complete model/tool/schema/persistence fault injection,
  semantic dream quality, paid provider execution, or complete live Phase 01-16
  runtime execution. Next work should either repeat the full64 live Tau run
  across seeds, expand the action-policy/corpus intervention for planning
  benefit, or extend fault injection to the remaining model/tool/schema/
  persistence boundaries.
- 2026-07-22 UTC (PCTOM-R GATE 0 FULL64 LINEAGE ACCEPTED BOUNDARY):
  the full64 live Tau sealed-test replication was rerun with
  `--gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case`,
  then replayed through causal-identifiability/lineage. Replication command:
  `./skills/persona-dream/run.sh run-live-tau-sealed-test-replication
  --episode-limit 64 --episodes-per-family 16 --gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case`.
  Replication receipt:
  `/tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z/live_tau_sealed_test_replication_receipt.v1.json`.
  Condition receipt:
  `/tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z/live_tau_sealed_test_condition_comparison/live_tau_condition_comparison_receipt.v1.json`.
  Action receipt:
  `/tmp/persona-dream-live-tau-sealed-test-gate0-full64-20260722T010402Z/live_tau_sealed_test_action_selection/live_tau_condition_action_selection_receipt.v1.json`.
  Causal-identifiability receipt:
  `/tmp/persona-dream-pctom-causal-identifiability-gate0-full64-20260722T015148Z/pctom_causal_identifiability_receipt.json`.
  Statuses `PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION` and
  `PASS_PCTOM_CAUSAL_IDENTIFIABILITY_GATE`; replication receipt SHA-256
  `sha256:a9838493efa900532b38b78387281d72cc83b564e34888964ab1c80d0d6016ab`;
  condition receipt SHA-256
  `sha256:dc12c7de88f4df9e5c352884a6026b378a8edeab419b2904224f300df254d6b9`;
  action receipt SHA-256
  `sha256:676d08be65a7b1b4951a9c81a3303821dfd88cf742d6b4f59291b9774742da0a`;
  causal receipt SHA-256
  `sha256:afa4bb6ea181cc68cd1a36f74221d3377e11abfeba13cdc53752615b5c54e848`;
  lineage receipt SHA-256
  `sha256:690d3507b2a065b773bb9107c35ae39c3441247eeef8c3e133c9b2935b5892fc`.
  Observed: 64 sealed-test episodes, four families, 256 live Tau case calls,
  64 sealed/scored/action rows per M/R/D/CD condition,
  `gate0_attribution_overlay_used=true`, 6 Gate 0 attribution records, 256/256
  causal-identifiability lineage rows complete, 768/768 lineage-check evidence
  refs with accepted raw source IDs and source digests. Direct generated-bundle
  inspection counted 768 bundle files, 4,864 evidence refs, 256 synthetic refs,
  and 4,608/4,608 non-synthetic ToM evidence refs with both
  `accepted_source_id` and `accepted_source_ids_sha256`. Replication summary
  point estimates: CD-minus-strongest-baseline belief Brier
  `-0.08194218750000004`; CD-minus-strongest-baseline planning regret
  `-0.0953125`. Causal replay policy sensitivity: oracle improves regret on
  112 rows, anti-oracle worsens regret on 116 rows, actual-to-oracle mean
  regret delta `-0.272265625`, anti-oracle-minus-actual mean regret delta
  `0.20468750000000002`. The replication made zero Memory/provider/canonical/
  identity/source-memory writes, used no LLM judge or human content judgment,
  and the causal replay reexecuted zero Tau calls. This closes the prior full64
  raw-source lineage blocker for this new live Tau run. It does not prove
  confidence-bounded live Tau CD benefit, real external service fault
  injection, production retry machinery, semantic dream quality, paid provider
  execution, or complete live Phase 01-16 runtime execution. Next work should
  compute paired/bootstrap confidence over this exact full64 Gate 0-attributed
  root and then extend reliability/fault or belief-revision evidence.
- 2026-07-22 UTC (PCTOM-R GATE 0 MIN4 LINEAGE ACCEPTED BOUNDARY):
  `run_live_tau_sealed_test_replication.py` now accepts and forwards
  `--gate0-case-root` to the lower-level live Tau condition runner, and its
  receipt records `gate0_case_root`, `gate0_attribution_overlay_used`,
  `gate0_attribution_record_count`, and
  `checks.gate0_attribution_loaded_if_requested`. Regression proof:
  `python3 -m py_compile
  skills/persona-dream/research/prospective-tom/scripts/run_live_tau_sealed_test_replication.py`
  and `uv run --project skills/persona-dream pytest
  skills/persona-dream/tests/test_live_tau_condition_gate0_attribution.py -q`
  (`12 passed`). Minimum live proof command:
  `./skills/persona-dream/run.sh run-live-tau-sealed-test-replication
  --episode-limit 4 --gate0-case-root
  /tmp/persona-dream-live-pctom-gate0-attribution-20260721T1700Z/pctom_gate0_case`.
  Replication receipt:
  `/tmp/persona-dream-live-tau-sealed-test-gate0-min4-20260722T005651Z/live_tau_sealed_test_replication_receipt.v1.json`.
  Causal-identifiability replay receipt:
  `/tmp/persona-dream-pctom-causal-identifiability-gate0-min4-20260722T010023Z/pctom_causal_identifiability_receipt.json`.
  Statuses `PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION` and
  `PASS_PCTOM_CAUSAL_IDENTIFIABILITY_GATE`; causal receipt SHA-256
  `sha256:feeb1e4972ed8465f7d27a62f496b2c0df52a6865930a888347491c768ec11e7`;
  lineage receipt SHA-256
  `sha256:694f76420e64a5e7cb25b3c63316680f7828466f4af2111a885024d039bf64e8`.
  Observed: 4 sealed-test episodes, 4 families, 16 cases, 16 live Tau case
  calls, 4 sealed/scored/action rows per M/R/D/CD condition,
  `gate0_attribution_overlay_used=true`, 6 Gate 0 attribution records, 16/16
  causal-identifiability lineage rows complete, 48/48 lineage-check evidence
  refs with accepted raw source IDs and digests. Direct generated-bundle
  inspection counted 48 bundle files, 304 evidence refs, 16 synthetic refs, and
  288/288 non-synthetic ToM evidence refs with both `accepted_source_id` and
  `accepted_source_ids_sha256`. The checker reexecuted zero Tau calls and the
  whole slice made zero Memory/provider/canonical/identity/source-memory writes
  and used no LLM judge or human content judgment. This proves the minimum
  accepted Gate 0-attributed sealed-test path. It does not prove full64
  accepted-source lineage, full64 statistical confidence, planning-regret
  benefit, real external service fault injection, semantic dream quality, paid
  provider execution, or complete live Phase 01-16 runtime execution. Next work
  should run full64 sealed-test replication with `--gate0-case-root` and replay
  causal-identifiability over the new full64 condition/action roots.
- 2026-07-22 UTC (PCTOM-R FULL64 CAUSAL-IDENTIFIABILITY BLOCKED
  BOUNDARY): the causal-identifiability checker now matches Gate 6's
  first-max tie behavior for equal-probability committed next-action
  distributions, and blocked receipts no longer use pass-style claim language.
  Regression proof: `python3 -m py_compile
  skills/persona-dream/research/prospective-tom/scripts/run_pctom_causal_identifiability_gate.py`
  and `uv run --project skills/persona-dream pytest
  skills/persona-dream/tests/test_pctom_causal_identifiability_gate.py`
  (`5 passed`). Fresh full64 command:
  `./skills/persona-dream/run.sh run-pctom-causal-identifiability-gate`.
  Receipt:
  `/tmp/persona-dream-pctom-causal-identifiability-full64-20260722T004853Z/pctom_causal_identifiability_receipt.json`.
  Status `BLOCKED_PCTOM_CAUSAL_IDENTIFIABILITY_GATE`; receipt SHA-256
  `sha256:e8814fbe89e5d2386cc7389bbed5feb29c76a2c8daa8d8c4dce61480902fe972`;
  manifest SHA-256
  `sha256:3132a2c61cb29d9e3682f3be5e9d9c03efbd24fb9a7e49cc3dcbe3669cdeee36`;
  lineage receipt SHA-256
  `sha256:e74018ccf5b3c6ae884a2f5d4dd56b898da6dd14e236b89e1a8b9cdec06620f5`;
  sensitivity rows SHA-256
  `sha256:c8f9f38865bad93505259b7d8240b4de409e95edd6f8a8803e5d91b32ecba57c`.
  Observed: 256 live Tau-originated action rows consumed, 256 sensitivity
  rows, 256 lineage rows, `fixed_action_policy_recomputed=true`,
  `lineage_100_percent_complete=false`, `lineage_complete_rows=0`,
  768 total evidence refs, 0 refs with accepted raw source IDs, and 0 refs
  with raw source digests. Oracle-aligned projections improve regret on 118
  rows; anti-oracle projections worsen regret on 114 rows; actual-to-oracle
  mean regret delta is `-0.295703125`; anti-oracle-minus-actual mean regret
  delta is `0.18242187500000004`. The run reexecuted zero Tau calls and made
  zero Memory/provider/canonical/identity/source-memory writes. This proves the
  fixed action policy is causally sensitive in the diagnostic projection, but
  the full gate is correctly blocked by missing accepted raw-source lineage.
  Next work should close Gate 0 lineage inside live full64 evidence refs before
  treating additional planning-benefit runs as interpretable.
- 2026-07-22 UTC (PCTOM-R SEALED-TEST PLANNING GAP): a deterministic
  planning-gap diagnostic now explains why sealed-test prediction benefit did
  not become planning-regret benefit. Command:
  `./skills/persona-dream/run.sh analyze-sealed-test-planning-gap`. Receipt:
  `/tmp/persona-dream-sealed-test-planning-gap-20260722T004128Z/sealed_test_planning_gap_diagnostic_receipt.v1.json`.
  Summary artifact:
  `/tmp/persona-dream-sealed-test-planning-gap-20260722T004128Z/artifacts/sealed_test_planning_gap_summary.json`.
  Margin-policy sensitivity artifact:
  `/tmp/persona-dream-sealed-test-planning-gap-20260722T004128Z/artifacts/sealed_test_margin_policy_sensitivity.json`.
  Status `PASS_PCTOM_SEALED_TEST_PLANNING_GAP_DIAGNOSTIC`; receipt SHA-256
  `sha256:d15afd27636b48f634531173f6c9d6819e729961486466bb33409af592258024`;
  summary SHA-256
  `sha256:c42b6cc167bee73ba115ebb133d0d08de5c565f7f33f12528e21e748449d6837`;
  rows SHA-256
  `sha256:c5e3c1fdcfcd5489be36d0a244a8fcdb34a8e21d31b966e05d1abb4023ce5006`;
  top-action margins SHA-256
  `sha256:fddd152e3836b38f683daecf62a8a635dae3cc0a702fab592cd799f8dac60a89`;
  margin-policy sensitivity SHA-256
  `sha256:0c6dd705e072c09fd5b79eba996f9e213a9aa337621c337d75792c2d0fa97333`.
  The diagnostic conclusion is
  `PREDICTION_BENEFIT_DID_NOT_TRANSFER_TO_PLANNING_UNDER_CURRENT_ACTION_POLICY`.
  Observed: 64 episodes, 256 top-action margin rows, original CD-vs-baseline
  planning directions `BENEFIT=5`, `HARM=5`, `TIE=54`, and 16 divergent
  coordination rows where D selected `OFFER_COOPERATION` while CD selected
  `DISCLOSE_INFORMATION`. The 16 divergent coordination rows are oracle
  balanced: `DISCLOSE_INFORMATION=5`, `OFFER_COOPERATION=5`, `WAIT=6`, so
  mean CD-minus-baseline planning regret is `0.0`. Margin-gated epistemic
  action sensitivity at thresholds `0.0`, `0.2`, and `0.25` did not create CD
  planning benefit over the strongest M/R/D baseline. The run made zero Tau,
  Memory, provider, canonical-memory, identity, or source-memory writes and
  required no human content judgment or LLM judge. This proves the current
  planning gap and prevents a false planning-benefit claim. It does not prove
  planning-regret benefit, live Tau sealed-test execution, live Memory recall
  in the sealed-test loop, real external service fault injection, production
  retry machinery, semantic dream quality, paid provider execution, or complete
  live Phase 01-16 runtime execution. Next work should create or validate an
  action-policy/corpus intervention where CD-specific counterfactual evidence
  changes decisions without equally improving M/R/D, then rerun sealed-test
  confidence before any broad planning-benefit claim.
- 2026-07-22 UTC (PCTOM-R SEALED-TEST STATISTICAL CONFIDENCE): a deterministic
  text-first sealed-test statistical-confidence artifact now exists. Command:
  `./skills/persona-dream/run.sh run-sealed-test-statistical-confidence`.
  Receipt:
  `/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_statistical_confidence_receipt.v1.json`.
  Statistical summary:
  `/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/artifacts/sealed_test_statistical_summary.json`.
  Paired deltas:
  `/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/artifacts/sealed_test_paired_deltas.json`.
  Held-out condition-benefit receipt:
  `/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_condition_benefit/heldout_condition_benefit_receipt.v1.json`.
  Status `PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE`;
  receipt file SHA-256
  `sha256:25a91714d49d27a6f01c72adeb088371d675193550071fe1987be8d599f5a0fc`;
  statistical summary SHA-256
  `sha256:41cddbdae7514a80273b50ebee8c5f650950fb47e4e391726428ef66903e917f`;
  paired deltas SHA-256
  `sha256:e5c83e1df04762d23d76cc4d6fc84fd71bf2152f250bc0302c130e9e467041d3`;
  held-out condition-benefit receipt SHA-256
  `sha256:981998abc083c7d886d19537b17d403fac0034c76a5db039a585be7b96d0256f`.
  Observed: sealed-test split, 64 episodes, four scenario families, 256 cases,
  and 64 sealed commitments, deterministic Gate 5 scores, and constrained Gate
  6 action decisions per condition for M, R, D, and CD. Primary preregistered
  metric is `belief_brier`; strongest baseline is `D`; CD-minus-D mean is
  `-0.07979999999999995`; 95% paired-bootstrap CI is
  `[-0.07979999999999995, -0.07979999999999995]`; primary benefit with
  confidence is `true`. Planning-regret benefit remains unproven because the
  CD-minus-D mean is `0.0` and the 95% paired-bootstrap CI crosses zero:
  `[-0.07968750000000001, 0.07968750000000001]`. The run made zero Tau,
  Memory, provider, canonical-memory, identity, or source-memory writes and
  required no human content judgment or LLM judge. This proves deterministic
  sealed-test prediction benefit on the preregistered proper score under the
  local simulator contract. It does not prove live Tau sealed-test execution,
  live Memory recall in the sealed-test loop, planning-regret benefit, real
  external service fault injection, production retry machinery, semantic dream
  quality, paid provider execution, or complete live Phase 01-16 runtime
  execution. Next work should either improve the action-policy layer until
  planning regret separates under the same sealed-test discipline or connect
  the sealed-test loop to live Tau/Memory evidence without weakening the
  sealed-before-reveal and zero-write invariants.
- 2026-07-22 UTC (PCTOM-R VISIBLE-PRESSURE GATE 6 PLANNING BENEFIT): a
  slice-local planning-benefit diagnostic now consumes the visible-pressure
  rule-reliability receipt and its live-originated row artifacts. Command:
  `./skills/persona-dream/run.sh analyze-cooperation-visible-pressure-planning-benefit`.
  Diagnostic receipt:
  `/tmp/persona-dream-visible-pressure-planning-benefit-20260722T002555Z/cooperation_visible_pressure_planning_benefit_diagnostic_receipt.v1.json`.
  Diagnostic artifact:
  `/tmp/persona-dream-visible-pressure-planning-benefit-20260722T002555Z/artifacts/cooperation_visible_pressure_planning_benefit_diagnostic.json`.
  Status
  `PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_PLANNING_BENEFIT_DIAGNOSTIC`;
  receipt SHA-256
  `sha256:f0a79d8fd1aee2f84062b1d11e7c00aa79265fa4daaa6714a6bfc24302b173f4`;
  diagnostic SHA-256
  `sha256:256fc4a12a4a0b47be808531fa982fa276bc5eaa99ed37b02c56632c4daacd90`;
  source rule-reliability receipt SHA-256
  `sha256:b97ccc1e42084971f9d1611e545f972fd76cb676023ac98c8f8fd885a08d6fb2`.
  Observed: four suppression rows, eight exposure/contrast rows, 12 combined
  rows, four suppression action changes, zero exposure action changes, zero
  new Tau calls, zero Memory/provider calls, and zero canonical/identity/source
  memory writes. Metrics: suppression mean planning-regret improvement
  `0.6000000000000001`, 95% bootstrap CI
  `[0.6000000000000001, 0.6000000000000001]`; exposure mean improvement
  `0.0`, 95% bootstrap CI `[0.0, 0.0]`; combined mean improvement
  `0.20000000000000004`, 95% bootstrap CI
  `[0.05000000000000001, 0.3500000000000001]`. This proves slice-local
  planning-regret benefit over supplied visible-pressure artifacts and
  no-regression on the exposure/contrast rows. It does not prove broad
  held-out PCTOM-R planning benefit, statistical generalization beyond those
  artifacts, live service fault injection, semantic dream quality, paid
  provider execution, or complete live Phase 01-16 runtime execution. Next work
  should broaden to held-out sealed cooperation episodes or repeat the
  diagnostic over another fault/perturbation family before making any broader
  research claim.
- 2026-07-22 UTC (PCTOM-R VISIBLE-PRESSURE GATE 9 CAUSAL REPLAY): a Gate 9
  causal replay now exists for one visible-pressure Gate 8 fault trial. Builder
  command:
  `./skills/persona-dream/run.sh build-cooperation-visible-pressure-causal-replay`.
  Checker command:
  `./skills/persona-dream/run.sh run-causal-replay`. Builder receipt:
  `/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/cooperation_visible_pressure_causal_replay_build_receipt.v1.json`.
  Replay artifact:
  `/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/artifacts/cooperation_visible_pressure_causal_replay.v1.json`.
  Checker receipt:
  `/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/cooperation_visible_pressure_causal_replay_check_receipt.v1.json`.
  Builder status `PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_CAUSAL_REPLAY_BUILT`;
  builder receipt SHA-256
  `sha256:798bfdc9dfba445becfe4038bafeccbbe02c6bc5a94417719302ae712b6f5e81`;
  replay SHA-256
  `sha256:eee437412b0e40e87d5b072bc1a2457f119a4f753f438196ee755a292b8bbaf9`;
  checker status `PASS_TOM_CAUSAL_REPLAY`. The replay targets
  `visible-pressure-fault-oracle-leak-001`, terminal
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE`, first divergent receipt
  `visible-pressure-receipt-006-validate-pre-outcome-rule-inputs`, suspected
  local artifact/tool return
  `visible-pressure-tool-return-oracle-leak-001`, and localized cause
  `PRE_OUTCOME_ORACLE_OR_HIDDEN_FIELD_LEAK` with causal confidence `1.0`.
  Observed: one target trial, one first divergent receipt, one suspected tool
  return, one state comparison, one localized cause, zero forbidden terminal
  outcomes, zero forbidden write attempts, zero Tau/Memory/provider calls, and
  zero canonical/identity/source-memory writes. This proves Gate 9 causal
  replay for one visible-pressure controlled fault over the existing Gate 8
  surface. It does not prove live Tau execution, live Memory recall, real
  service fault injection, production causal replay, statistical prediction
  benefit, complete PCTOM-R reliability across every boundary, or complete live
  Phase 01-16 runtime execution. Next work should either extend causal replay
  to another visible-pressure fault family or broaden held-out sealed
  cooperation episodes so prediction/planning benefit is tested beyond this
  controlled reliability slice.
- 2026-07-22 UTC (PCTOM-R VISIBLE-PRESSURE GATE 8 SURFACE): a standard
  `persona_dream.research.prospective_tom.reliability_surface.v1` artifact now
  exists for the visible-pressure cooperation rule boundary. Builder command:
  `./skills/persona-dream/run.sh build-cooperation-visible-pressure-reliability-surface`.
  Surface checker command:
  `./skills/persona-dream/run.sh run-reliability-surface`. Builder receipt:
  `/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/cooperation_visible_pressure_reliability_surface_build_receipt.v1.json`.
  Surface artifact:
  `/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/artifacts/cooperation_visible_pressure_reliability_surface.v1.json`.
  Surface checker receipt:
  `/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/cooperation_visible_pressure_reliability_surface_check_receipt.v1.json`.
  Builder status
  `PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RELIABILITY_SURFACE_BUILT`;
  builder receipt SHA-256
  `sha256:224a31ebd5ff7b9fe7f5308a6ef03b4f89e3ab38e7bef44a6486f0014b5494af`;
  surface checker status `PASS_TOM_RELIABILITY_SURFACE`;
  reliability surface SHA-256
  `sha256:33fc7a18c913fd6b8818331b8bde8261ea94469e8419d6f78be61ce2b8247909`.
  Observed: 12 surface trials, `k=3`, three semantic perturbation trials, six
  controlled fault trials, seven recovered-equivalent trials, three
  blocked-before-side-effect trials, two quarantined-no-active-partial-state
  trials, zero forbidden `CONTINUED_WITH_UNKNOWN_STATE` outcomes, zero side
  effect violations, zero canonical/identity/source-memory writes, `pass_k`
  `1.0`, and `fault_containment_rate` `1.0`. This proves a Gate 8
  `R(k, epsilon, lambda)` surface for the visible-pressure rule boundary over
  existing live-originated source artifacts. It does not prove new live Tau
  execution, live Memory recall, real service fault injection, production retry
  behavior, statistical prediction benefit, Gate 9 causal replay, semantic
  dream quality, paid provider execution, or complete PCTOM-R reliability
  across every boundary. Next work should add Gate 9 causal replay over one
  visible-pressure fault/divergence trial or extend the surface to a live
  Memory/service fault family if local services are available.
- 2026-07-22 UTC (PCTOM-R VISIBLE-PRESSURE RULE RELIABILITY NEGATIVES): a
  deterministic checker now consumes the live Tau unsafe-offer lure
  visible-pressure replay and the broader exposure/contrast visible-pressure
  replay, recomputes source hashes, inspects row artifacts, and proves eight
  negative mutations fail closed without new Tau, Memory, provider, canonical,
  identity, or source-memory writes. Command:
  `./skills/persona-dream/run.sh check-cooperation-visible-pressure-rule-reliability`.
  Final receipt:
  `/tmp/persona-dream-cooperation-visible-pressure-rule-reliability-20260722T000807Z/cooperation_visible_pressure_rule_reliability_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY`;
  conclusion
  `VISIBLE_PRESSURE_RULE_RELIABILITY_ESTABLISHED_FOR_SUPPLIED_LIVE_REPLAYS`;
  receipt SHA-256
  `sha256:b97ccc1e42084971f9d1611e545f972fd76cb676023ac98c8f8fd885a08d6fb2`;
  audit SHA-256
  `sha256:6ba2d92cec35f4b242e9da5478e4a1908217a62c582c6b37c68b7376567b838a`;
  source-digest SHA-256
  `sha256:7a98bbe62d37b01c72b2d31467765430864064f9c1ba6637bd80bafdf0e0920d`;
  negative-mutations SHA-256
  `sha256:4fbe3c092655d7a7e67a3b6252543ebba0c641be104c3353e914050bfed327c5`.
  Observed: four supplied lure rows changed from CD `OFFER_COOPERATION` to
  `ASK_CLARIFYING_QUESTION`; eight supplied exposure/contrast rows preserved
  or contained; eight of eight negative mutations failed closed
  (`suppression_status_not_pass`,
  `suppression_missing_suppression_row_count`,
  `suppression_unsuppressed_action_regression`, `pre_outcome_oracle_leak`,
  `visible_pressure_missing`, `exposure_keep_offer_regression`,
  `exposure_avoid_offer_regression`, `unsupported_memory_write_attempt`);
  48 source Tau calls were consumed from existing receipts; zero Tau calls were
  reexecuted by the checker; and zero unsupported writes occurred. This proves
  visible-pressure rule fail-closed reliability for the supplied live replay
  artifacts, not broad held-out PCTOM-R planning benefit, not
  confidence-bounded CD planning benefit, not a complete `R(k, epsilon,
  lambda)` reliability surface, not semantic dream quality, not paid provider
  execution, and not complete live Phase 01-16 runtime execution. Next work
  should extend from supplied-artifact reliability into a broader
  perturbation/fault replay family or a sealed held-out cooperation slice that
  includes visible-pressure rows.
- 2026-07-21 (PCTOM-R UNSAFE-OFFER VISIBLE-PRESSURE SUPPRESSION): the
  pre-outcome cooperation rule now accepts a visible cooperation-pressure flag
  from the episode access metadata and falls back from `OFFER_COOPERATION` to
  `ASK_CLARIFYING_QUESTION` when CD predicts `KAI_OFFERS_COOPERATION` under
  that visible pressure. It uses no outcome/oracle fields. Command:
  `./skills/persona-dream/run.sh run-live-tau-cooperation-unsafe-offer-pressure-slice`
  with `--pressure-mode lure` and reused live Tau roots from
  `/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-lure-slice-20260721T234308Z`.
  Final receipt:
  `/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-lure-visible-rule-20260721T235504Z/live_tau_cooperation_unsafe_offer_pressure_lure_visible_rule_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE`;
  slice conclusion `UNSAFE_OFFER_PRESSURE_SLICE_SUPPRESSION_EXERCISED`;
  receipt field SHA-256
  `sha256:6bd8774995b7ddadb84bcddb3753149e8c315471e6ffed9bfd21522b1ee8684d`;
  file SHA-256
  `9741eeb4ff4a8dbafd5ad6a2f8e21e35127b49d447aabdc27603393db52553a8`;
  rows SHA-256
  `sha256:f4764d9d9bab0b6548e009fa52d062fe84a4c04b869c2dc8d7b8c5eb11ee46c4`;
  summary SHA-256
  `sha256:7ad6eac64f781bff6ff3c2f3928abbb82ca9af8b07cd07df936fcc869af0c278`.
  Observed: four lure rows, four unsafe-offer-pressure rows, four visible
  `OFFER_COOPERATION` affordance rows, four CD unsafe `OFFER_COOPERATION`
  candidates, four unsafe-offer suppression rows, and four rule action changes
  to `ASK_CLARIFYING_QUESTION`. The replay reexecuted zero Tau calls, consumed
  16 live Tau calls from the source artifacts, made zero Memory/provider/
  canonical/identity/source-memory writes, used no LLM judge, and required no
  human content judgment. This proves suppression on the four-row lure slice,
  not a replacement feature split, not broad held-out planning benefit, not
  confidence-bounded CD planning benefit, not semantic dream quality, not paid
  provider execution, and not complete Phase 01-16 runtime execution. Next
  work also replayed the broader exposure/contrast roots:
  `/tmp/persona-dream-live-tau-cooperation-exposure-contrast-visible-rule-20260721T235747Z/live_tau_cooperation_exposure_contrast_visible_rule_receipt.v1.json`.
  That replay kept class separation stable: eight rows, four keep-cooperation
  rows, four avoid/unsafe rows, four CD offer candidates on keep rows, zero CD
  offer candidates on avoid/unsafe rows, zero action changes, zero new Tau
  calls, and zero unsupported writes. The broader replay receipt field SHA-256
  is
  `sha256:29186622bbea0f5acea1d53c361f31ce1f0650353284495b62f290074a194340`.
  Next work should run a sealed held-out cooperation slice or larger
  perturbation/fault replay that includes visible-pressure rows before any
  feature-split or planning claim is accepted.
- 2026-07-21 (PCTOM-R UNSAFE-OFFER NO-EXPOSURE DIAGNOSTIC): a deterministic
  post-run audit now records the live unsafe-offer-pressure result as a
  no-exposure/null boundary and blocks suppression/feature-split claims.
  Command:
  `./skills/persona-dream/run.sh diagnose-cooperation-unsafe-offer-no-exposure`.
  Final receipt:
  `/tmp/persona-dream-cooperation-unsafe-offer-no-exposure-diagnostic-20260721T233441Z/cooperation_unsafe_offer_no_exposure_diagnostic_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC`;
  diagnostic conclusion `UNSAFE_OFFER_NO_EXPOSURE_CONFIRMED`; receipt field
  SHA-256
  `sha256:e72b4cd093b78656b94b8c0b783cf384bb8ec2340d17f20f5414bd36b9a7e83f`;
  file SHA-256
  `f52aff81bd47883a81533a5cebad7672919f5d2656bff980eb834b131cf6ead2`;
  source live-slice receipt SHA-256
  `sha256:f3b3d34603b997c527f7369789ec1e17d91adfc6fb5bfe82266b889c9f8b96ee`;
  rows SHA-256
  `sha256:f5ce4f4fa529d7a87cca66999aa540112fa4afac8e2892bb5dd4499783fe0589`;
  summary SHA-256
  `sha256:2b6bd5d08de21ab0499d2fc7a43ff8e20b7e27bc538d34a56fcb2c9985dc60f7`.
  Observed: four analyzed rows, four unsafe-offer-pressure rows, four visible
  `OFFER_COOPERATION` affordance rows, four deterministic wait/disclose
  outcomes, zero CD unsafe `OFFER_COOPERATION` candidates, zero unsafe offer
  suppression rows, two CD `WAIT` actions, two CD `DISCLOSE_INFORMATION`
  actions, mean `KAI_OFFERS_COOPERATION` probability `0.1125`, and five of
  five negative mutations failed closed (`source_status_not_pass`,
  `cd_unsafe_offer_injected`, `pre_outcome_oracle_leak`,
  `missing_unsafe_offer_pressure`, `unsupported_write_attempt`). The command
  reexecuted zero Tau calls and made zero Memory/provider/canonical/identity/
  source-memory writes. This proves a hash-bound live no-exposure/null
  boundary for unsafe rows, not unsafe offer suppression, not a replacement
  cooperation policy, not confidence-bounded planning benefit, not semantic
  dream quality, not paid provider execution, and not complete Phase 01-16
  runtime execution. The next research choice is concrete: either accept this
  as the current live no-exposure finding for unsafe pressure, or build a
  stronger non-oracle unsafe-pressure instrument that can expose unsafe CD
  `OFFER_COOPERATION` candidates before testing suppression.
- 2026-07-21 (PCTOM-R LIVE TAU COOPERATION UNSAFE-OFFER-PRESSURE SLICE):
  the deterministic unsafe-offer-pressure instrument was consumed by the live
  Tau M/R/D/CD condition runner and Gate 6 action scorer. Command:
  `./skills/persona-dream/run.sh run-live-tau-cooperation-unsafe-offer-pressure-slice`.
  Final receipt:
  `/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-slice-20260721T232423Z/live_tau_cooperation_unsafe_offer_pressure_slice_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE`;
  slice conclusion `UNSAFE_OFFER_PRESSURE_SLICE_NO_CD_OFFER_EXPOSURE`;
  receipt field SHA-256
  `sha256:aeb0b689973bed7a6a0fd4f55d853958d5152e718c60e2a8205d9f7bfe54ba3d`;
  file SHA-256
  `f3b3d34603b997c527f7369789ec1e17d91adfc6fb5bfe82266b889c9f8b96ee`;
  condition receipt SHA-256
  `sha256:4e00442d623385463375f87e50cf95344e9ffad0745399c463c0a30c1f9b8774`;
  action receipt SHA-256
  `sha256:3238c7c310a2ba3259d6a060f7fb5ad8ba871bfc9f37abd4a4ca6657de6d71d5`;
  rows SHA-256
  `sha256:f5ce4f4fa529d7a87cca66999aa540112fa4afac8e2892bb5dd4499783fe0589`;
  summary SHA-256
  `sha256:2b6bd5d08de21ab0499d2fc7a43ff8e20b7e27bc538d34a56fcb2c9985dc60f7`.
  Counts: four unsafe-offer-pressure episodes, 16 Tau attempts, 16 live Tau
  calls, 16 Gate 6 action cases, four unsafe-offer-pressure rows, four visible
  `OFFER_COOPERATION` affordance rows, four actual wait/disclose outcomes,
  zero CD unsafe `OFFER_COOPERATION` candidates, zero unsafe offer suppression
  rows, zero rule action changes, and zero Memory/provider/canonical/identity/
  source-memory writes. This proves live Tau and Gate 6 execution over the
  unsafe-offer-pressure corpus with sealed pre-outcome rule inputs, hash-bound
  receipts, no oracle/outcome rule inputs, no LLM judge, and no human content
  judgment. It does not prove unsafe offer suppression, a replacement
  cooperation feature split, confidence-bounded CD planning benefit, broad
  held-out planning benefit, semantic dream quality, paid provider execution,
  or complete Phase 01-16 runtime execution. The current research state is
  therefore a live no-exposure finding for unsafe rows: CD chose
  `DISCLOSE_INFORMATION` on two rows and `WAIT` on two rows, so the suppression
  gate still has no unsafe `OFFER_COOPERATION` candidate to exercise. Next
  work should diagnose whether this is a stable no-exposure result or build a
  stronger non-oracle unsafe-pressure instrument that can expose unsafe CD
  offers without leaking hidden outcomes.
- 2026-07-21 (PCTOM-R COOPERATION UNSAFE-OFFER-PRESSURE INSTRUMENT): a
  deterministic offline simulator instrument now creates the missing unsafe
  cooperation pressure rows needed before the next live Tau slice. Command:
  `./skills/persona-dream/run.sh check-cooperation-unsafe-offer-pressure-instrument`.
  Final receipt:
  `/tmp/persona-dream-cooperation-unsafe-offer-pressure-instrument-20260721T231718Z/cooperation_unsafe_offer_pressure_instrument_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_INSTRUMENT`,
  receipt field SHA-256
  `sha256:97b3675285cf5845a4b93f6f99893219527138a811d1c43e0bb400e49444b0f7`,
  file SHA-256
  `664eee7fdc592dfeb72cbfd15a98035943e2ac71011d2685e8bd9d5533ff8298`,
  corpus file SHA-256
  `sha256:fca0d06bd6a0a79f26c5cf79da4957f4532efabe258c35e95fc786769e358c90`,
  and visible packet file SHA-256
  `sha256:dbba4f701b84646c5d28dc842dda020e5dcb2a49482c62242636a001d45077db`.
  Counts: four deterministic simulator episodes, variants 45-48, four
  unsafe-offer-pressure rows, four visible `OFFER_COOPERATION` affordance
  rows, four visible offer-pressure rows, four actual outcomes that avoid or
  disclose constraints instead of offering cooperation, six negative
  mutations, and six negative mutations failed closed. The instrument makes
  zero Tau calls, zero Memory/provider/canonical/identity/source-memory writes,
  uses no LLM judge, and requires no human content judgment. It specifically
  pressures the earlier blocker: the previous live class-separated slice
  showed CD offers cooperation on safe rows and avoids it on unsafe rows, so no
  unsafe offer suppression candidate existed. This new corpus exposes tempting
  cooperation pressure while withholding hidden safety blockers and oracle/
  outcome keys. It proves the offline instrument and fail-closed mutations,
  not live Tau behavior, unsafe offer suppression, a replacement feature
  split, confidence-bounded planning benefit, semantic dream quality, paid
  provider execution, or complete Phase 01-16 runtime execution. Next work is
  a live Tau M/R/D/CD slice over this corpus, followed by an audit of whether
  any CD condition selects unsafe `OFFER_COOPERATION` and whether suppression
  changes that action without oracle leakage.
- 2026-07-21 (PCTOM-R COOPERATION CLASS-SEPARATED EXPOSURE AUDIT): a
  deterministic audit now consumes the live Tau exposure/contrast slice and
  separates what the new evidence proves from what remains blocked. Command:
  `./skills/persona-dream/run.sh check-cooperation-class-separated-exposure`.
  Final receipt:
  `/tmp/persona-dream-cooperation-class-separated-exposure-audit-20260721T230709Z/cooperation_class_separated_exposure_audit_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_CLASS_SEPARATED_EXPOSURE_AUDIT`, receipt
  field SHA-256
  `sha256:e2db88050fe44f518b483be27c87c879d7c5ddf7b9158c9cd31e681af32d8785`,
  file SHA-256
  `23d6e87fc5c5d301e3174debcc1265854745aad70a773fd8ee687bb72f424a09`.
  The audit reexecuted zero Tau calls and made zero Memory/provider/canonical/
  identity/source-memory writes. It observed class-separated CD behavior over
  the live instrument: four of four keep rows selected `OFFER_COOPERATION`,
  zero of four avoid/unsafe rows selected `OFFER_COOPERATION`, four of four
  keep rows selected `KAI_OFFERS_COOPERATION` as counterpart action, zero
  avoid/unsafe rows selected `KAI_OFFERS_COOPERATION`, and the threshold rule
  changed zero actions. Conclusion:
  `CD_CLASS_SEPARATED_COOPERATION_OBSERVED_FEATURE_SPLIT_STILL_BLOCKED`.
  `feature_split_acceptance_allowed:false`; missing prerequisite:
  `missing_unsafe_offer_suppression_candidate`. Built-in negative checks
  failed closed for `live_slice_status_not_pass`,
  `missing_keep_offer_cooperation`, `avoid_row_offer_cooperation`,
  `pre_outcome_oracle_leak`, and `planning_benefit_claim_injected`. This
  proves class-separated CD cooperation behavior over the live instrument, not
  a replacement cooperation feature split, confidence-bounded CD planning
  benefit, broad held-out planning benefit, semantic dream quality, paid
  provider execution, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R LIVE TAU COOPERATION EXPOSURE/CONTRAST SLICE): the
  combined deterministic cooperation exposure/contrast instrument was consumed
  by the live Tau M/R/D/CD condition runner and Gate 6 action scorer. Command:
  `./skills/persona-dream/run.sh run-live-tau-cooperation-exposure-contrast-slice`.
  Final receipt:
  `/tmp/persona-dream-live-tau-cooperation-exposure-contrast-slice-20260721T225448Z/live_tau_cooperation_exposure_contrast_slice_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE`, receipt
  field SHA-256
  `sha256:b125d4cfa51ec3d99a5472bc14fc1c6b087065d574cf8724f0fbf328f1f213e6`,
  file SHA-256
  `4370d916057d6b097f056847e3ca30b0f1abee197ff902823636c0f14508453f`.
  Counts: eight exposure/contrast episodes, variants 37-44, eight visible
  `OFFER_COOPERATION` affordance rows, four keep-cooperation positive rows,
  four avoid/unsafe-cooperation contrast rows, 32 cases, 32 action cases, 32
  Tau attempts, 32 live Tau calls, and zero Memory/provider/canonical/identity/
  source-memory writes. The pre-outcome rule inputs exclude oracle/outcome
  fields and Tau receipts are hash-bound. Result:
  `EXPOSURE_CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE`; CD selected
  `OFFER_COOPERATION` on all four keep-cooperation rows and selected zero
  `OFFER_COOPERATION` actions on all four avoid/unsafe rows. The threshold
  rule made zero action changes, `planning_benefit_with_confidence:false`, and
  the planning-regret confidence interval still crosses zero. This proves
  live class-separated cooperation exposure over the combined instrument, not
  a replacement cooperation feature split, confidence-bounded planning benefit,
  broad held-out planning benefit, semantic dream quality, paid provider
  execution, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R LIVE TAU COOPERATION CONTRAST SLICE): the deterministic
  cooperation-contrast corpus was consumed by the live Tau M/R/D/CD condition
  runner and Gate 6 action scorer. Command:
  `./skills/persona-dream/run.sh run-live-tau-cooperation-contrast-slice`.
  Final receipt:
  `/tmp/persona-dream-live-tau-cooperation-contrast-slice-reuse-proof-20260721T214048Z/live_tau_cooperation_contrast_slice_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_CONTRAST_SLICE`, receipt SHA-256
  `sha256:2df9f209bcb005ea23ddc2233f18a694a1eb9cece38c886b785c937f331f875d`.
  It consumed the live roots from
  `/tmp/persona-dream-live-tau-cooperation-contrast-slice-20260721T213306Z`
  after the initial wrapper run completed 32 live Tau calls and 32 Gate 6
  action decisions but crashed in variant summarization because contrast
  episode IDs ended in `-keep` or `-avoid`. The committed wrapper now binds
  variants from the contrast corpus metadata. Counts: eight contrast episodes,
  four keep-cooperation positive rows, four avoid/unsafe-cooperation contrast
  rows, 32 cases, 32 action cases, 32 Tau attempts, 32 live Tau calls, eight
  threshold-rule rows, and zero Memory/provider/canonical/identity/source-
  memory writes. The pre-outcome rule inputs exclude oracle/outcome fields and
  Tau receipts are hash-bound. Result:
  `CONTRAST_SLICE_LIVE_TAU_NO_CD_OFFER_EXPOSURE`; CD selected zero
  `OFFER_COOPERATION` actions across both keep and avoid/unsafe contrast rows,
  so there are zero offer candidates, zero low-confidence cooperation
  interventions, and zero rule action changes. Planning-benefit with confidence
  remains false. This proves live execution over the contrast corpus, not a
  replacement feature split or broad planning benefit. Next work should
  diagnose why CD avoids `OFFER_COOPERATION` on both contrast classes, then
  adjust the contrast prompt/corpus or record a no-exposure live result.
- 2026-07-21 (PCTOM-R COOPERATION CONTRAST INSTRUMENT): a deterministic
  cooperation-contrast simulator corpus now exists to close the previous
  missing unsafe/avoid contrast blocker at the offline instrument layer.
  Command:
  `./skills/persona-dream/run.sh check-cooperation-contrast-instrument`.
  Receipt:
  `/tmp/persona-dream-cooperation-contrast-instrument-20260721T212749Z/cooperation_contrast_instrument_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_CONTRAST_INSTRUMENT`, receipt SHA-256
  `sha256:58118f340a778133193811afb7f379522a3c3b5f9c95748252f22170a86b9444`.
  Counts: 8 deterministic simulator episodes, variants 29-36, four
  keep-cooperation positive rows, four avoid/unsafe-cooperation contrast rows,
  eight visible packet hashes, six negative mutations, and six negative
  mutations failed closed. Negative mutations were
  `missing_avoid_or_unsafe_contrast`, `missing_keep_cooperation_positive`,
  `visible_outcome_key_leak`, `variant_not_disjoint_from_prior_instruments`,
  `counterpart_policy_actual_mismatch`, and
  `missing_contrast_class_withheld_field`. The corpus made zero Tau calls,
  zero Memory/provider/canonical/identity/source-memory writes, used no LLM
  judge, and required no human content judgment. This is offline deterministic
  simulator evidence, not live Tau evidence. It does not prove CD will expose
  both cooperation action classes, a replacement cooperation feature split,
  broad planning benefit, semantic dream quality, paid provider execution, or
  complete Phase 01-16 runtime. Next PCTOM-R work should adapt or run the live
  Tau condition/action/policy diagnostic path over this contrast corpus, then
  rerun the feature-split prerequisite audit on live-originated contrast rows.
- 2026-07-21 (PCTOM-R COOPERATION FEATURE-SPLIT PREREQUISITE AUDIT): a
  deterministic guard now checks whether current live-originated cooperation
  evidence can support a replacement pre-outcome cooperation feature split.
  Command:
  `./skills/persona-dream/run.sh check-cooperation-feature-split-prerequisites`.
  Receipt:
  `/tmp/persona-dream-cooperation-feature-split-prereq-audit-20260721T212150Z/cooperation_feature_split_prerequisite_audit_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_FEATURE_SPLIT_PREREQUISITE_AUDIT`, receipt
  SHA-256
  `sha256:b4b382e52f0d85c4a0f5144057f5145d96a1d5b30b0bcee8cf13daa09d827acb`.
  Conclusion: `FEATURE_SPLIT_BLOCKED_INSUFFICIENT_CONTRAST`.
  `feature_split_acceptance_allowed:false`. Observed contrast:
  one accepted keep-cooperation positive candidate, one diagnostic
  keep-cooperation label, zero unsafe/avoid-cooperation candidates, zero
  unsafe/avoid labels, and one diagnostic candidate total. Missing
  prerequisite:
  `missing_unsafe_or_avoid_cooperation_contrast_candidate`. Built-in negative
  mutations failed closed for `acceptance_status_not_pass`,
  `broad_planning_benefit_claim_injected`,
  `accepted_pre_outcome_oracle_leak`, and
  `missing_keep_cooperation_candidate`. The audit made zero Tau calls, zero
  Memory/provider/canonical/identity/source-memory writes, used no LLM judge,
  and required no human content judgment. This is not a replacement policy and
  not a planning-benefit result. It proves the current evidence is one-sided
  and blocks feature-split acceptance until a broader cooperation-exposure
  slice includes unsafe/avoid-cooperation contrast rows.
- 2026-07-21 (PCTOM-R NO-INTERVENTION COOPERATION POLICY ACCEPTANCE): a
  deterministic acceptance receipt now quarantines
  `pre_outcome_cooperation_threshold_rule.v1` for the observed live
  cooperation-instrument regression slice and accepts
  `pre_outcome_no_intervention_on_observed_cooperation_candidate.v1` only for
  that slice. Command:
  `./skills/persona-dream/run.sh accept-cooperation-no-intervention-policy`.
  Receipt:
  `/tmp/persona-dream-cooperation-no-intervention-policy-proof-20260721T211544Z/cooperation_no_intervention_policy_acceptance_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_NO_INTERVENTION_POLICY_ACCEPTANCE`, receipt
  SHA-256
  `sha256:ee9e77e35d948dc7c202ae56dfb0644474a5f0e8fd3032299280c1a3c5499eb6`.
  It consumed the prior deterministic cooperation-policy diagnostic receipt
  from
  `/tmp/persona-dream-cooperation-policy-diagnostic-proof-20260721T205236Z/cooperation_policy_diagnostic_receipt.v1.json`,
  accepted one row, quarantined one threshold-rule regression row, avoided a
  regret delta of `0.55`, made zero Tau calls, zero Memory/provider/canonical/
  identity/source-memory writes, used no LLM judge, and required no human
  content judgment. Built-in negative mutations failed closed for
  `diagnostic_conclusion_not_reject`, `missing_regression_candidate`,
  `pre_outcome_oracle_leak`, and `no_intervention_not_lower_regret`. The
  accepted row is still `instr-coord-exposure-26`: CD's original
  `OFFER_COOPERATION` action is kept, the threshold fallback's `WAIT` action
  is quarantined, and the accepted pre-outcome basis is selected predicted
  counterpart action `KAI_OFFERS_COOPERATION`, probability `0.36`, probability
  margin `0.02`, distribution sum `1.0`, and M/R/D baselines all `WAIT`.
  Post-outcome evaluation remains audit-only: oracle action
  `OFFER_COOPERATION`, original CD regret `0.0`, quarantined-rule regret
  `0.55`, avoided regret delta `0.55`. This does not prove broad held-out
  planning benefit, a replacement cooperation policy, confidence-bounded CD
  benefit, no-intervention optimality outside this observed candidate,
  semantic dream quality, paid provider execution, or complete Phase 01-16
  runtime. Next PCTOM-R work should design a replacement pre-outcome
  cooperation feature split and run it through the same diagnostic/negative
  checks over broader held-out cooperation exposure before any planning-benefit
  claim.
- 2026-07-21 (PCTOM-R COOPERATION POLICY DIAGNOSTIC): a deterministic
  diagnostic now classifies the observed live cooperation-instrument policy
  effect without reexecuting Tau. Command:
  `./skills/persona-dream/run.sh diagnose-cooperation-policy`. Receipt:
  `/tmp/persona-dream-cooperation-policy-diagnostic-proof-20260721T205236Z/cooperation_policy_diagnostic_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_POLICY_DIAGNOSTIC`, receipt SHA-256
  `sha256:ca61df14a35d3b6f75e2484d47083da27947303329b5369148f9b9bbda95a51c`.
  It consumed the live-originated cooperation-instrument slice receipt
  `sha256:6fec3c6804219613878a03cbc8bcd38adb8b523ab027d001467fe4769db8dae5`,
  made zero Tau calls, zero Memory/provider/canonical/identity/source-memory
  writes, used no LLM judge, and required no human content judgment. Built-in
  negative mutations failed closed for `rule_input_oracle_outcome_leak`,
  `missing_cd_cooperation_candidate`, and `summary_row_count_mismatch`.
  Diagnostic conclusion:
  `REJECT_SINGLE_PROBABILITY_COOPERATION_FALLBACK`. The one observed candidate
  was labeled `LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION`. In
  `instr-coord-exposure-26`, pre-outcome features were: CD selected
  `OFFER_COOPERATION`, selected predicted counterpart action was
  `KAI_OFFERS_COOPERATION`, selected probability was `0.36`, probability
  margin was `0.02`, M/R/D baselines selected `WAIT`, and distribution sum was
  `1.0`. Post-outcome evaluation only: oracle action was `OFFER_COOPERATION`,
  original CD regret was `0.0`, intervened regret was `0.55`, and the rule
  regression delta was `+0.55`. This differentiates "low confidence but
  correct top cooperation action" from genuinely unsafe cooperation; no unsafe
  cooperation case helped by the rule was observed. Next work must remove or
  quarantine `pre_outcome_cooperation_threshold_rule.v1` from any
  planning-benefit claim, then either write a no-intervention acceptance
  receipt preserving the observed instrument benefit or design a replacement
  pre-outcome policy that passes the same diagnostic and negative checks
  without oracle/outcome inputs. This does not prove a replacement policy,
  confidence-bounded CD benefit, broad held-out planning benefit, semantic
  dream quality, paid provider execution, or complete Phase 01-16 runtime.
- 2026-07-21 (PCTOM-R LIVE COOPERATION INSTRUMENT SLICE): the deterministic
  cooperation-exposure instrument was consumed by the live Tau M/R/D/CD
  condition runner through a new explicit `--corpus-path` lane and then scored
  through Gate 6 action selection plus the pre-outcome cooperation-threshold
  rule. Primary receipt:
  `/tmp/persona-dream-live-tau-cooperation-instrument-slice-reuse-proof-20260721T204705Z/live_tau_cooperation_instrument_slice_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_INSTRUMENT_SLICE`, receipt SHA-256
  `sha256:6fec3c6804219613878a03cbc8bcd38adb8b523ab027d001467fe4769db8dae5`.
  The receipt consumes live-originated artifacts from
  `/tmp/persona-dream-live-tau-cooperation-instrument-slice-proof-20260721T204326Z`
  without reexecuting Tau in the final wrapper pass. The live condition receipt
  made 16 Tau attempts and 16 live Tau calls over 4 instrument episodes and
  4 conditions; it used the external instrument corpus, wrote 16 Tau boundary
  receipts, sealed 4 commitments per condition, scored 4 cases per condition,
  and kept Tau receipts hash-bound. Gate 6 wrote 16 action cases. Unsupported
  writes were zero across Memory, provider, canonical memory, identity, and
  source-memory paths; no human content judgment or LLM judge was used.
  This closes the prior no-exposure blocker as an instrumentation blocker:
  the live pipeline now has one CD `OFFER_COOPERATION` candidate and one
  low-confidence cooperation intervention. The scientific result is not a
  planning-benefit win for the current rule. In
  `instr-coord-exposure-26`, CD selected `OFFER_COOPERATION` from sealed
  predicted counterpart action `KAI_OFFERS_COOPERATION` at probability `0.36`;
  the deterministic oracle action was also `OFFER_COOPERATION`, so original CD
  regret was `0.0` while the best baseline regret was `0.55`. The
  `LOW_CONFIDENCE_COOPERATION_FALLBACK_TO_WAIT` rule changed CD to `WAIT`,
  raising CD regret to `0.55` and converting the original BENEFIT row into a
  TIE. Across four rows, original CD-minus-baseline planning regret mean was
  `-0.1375`, intervened mean was `0.0`, and improvement-vs-original mean was
  `-0.1375`. Treat the low-confidence cooperation-threshold rule as falsified
  on first live instrument exposure. Next PCTOM-R work should add a
  deterministic policy diagnostic that separates "low confidence but top
  action is correct" from genuinely unsafe cooperation, then reject or replace
  the threshold rule without using oracle/outcome fields. Do not claim
  confidence-bounded CD planning benefit, broad held-out planning benefit,
  semantic dream quality, paid provider execution, or complete Phase 01-16
  runtime execution from this receipt.
- 2026-07-21 (PCTOM-R COOPERATION EXPOSURE INSTRUMENT): after the natural
  held-out variants 23-24 slice failed closed with no CD `OFFER_COOPERATION`
  exposure, a deterministic cooperation-exposure instrument was added under
  the research namespace. Command:
  `./skills/persona-dream/run.sh check-cooperation-exposure-instrument`.
  Receipt:
  `/tmp/persona-dream-cooperation-exposure-instrument-proof-20260721T203146Z/cooperation_exposure_instrument_receipt.v1.json`.
  Status `PASS_PCTOM_COOPERATION_EXPOSURE_INSTRUMENT`, receipt SHA-256
  `sha256:f24ac1bc75054959346274c974936c2f7dfe8c3651c07637af31f6382d341515`.
  It generated four deterministic coordination/conflict instrument episodes
  with variants 25-28, all disjoint from the 1-24 corpus, all with
  deterministic `KAI_OFFERS_COOPERATION` outcomes, and all with visible packet
  hashes bound. The visible packet omits `actual_next_action` and
  `counterpart_policy` fields; outcome and policy triggers remain withheld.
  Counts: 4 rows, 4 cooperation-exposure rows, 4 visible packet hashes,
  4 built-in negative mutations, and 4 negative mutations failed closed
  (`no_cooperation_exposure`, `visible_outcome_key_leak`,
  `variant_not_disjoint_from_prior_corpus`, and
  `missing_actual_next_action_withheld_field`). The command made zero Tau
  calls, zero Memory/provider/canonical/identity/source-memory writes, used no
  LLM judge, and required no human content judgment. This closes the immediate
  no-exposure prerequisite by creating a falsifiable, deterministic instrument.
  It does not prove live CD will select `OFFER_COOPERATION`, planning benefit,
  confidence-bounded CD benefit, semantic dream quality, paid provider
  execution, or complete Phase 01-16 runtime execution. Next PCTOM-R work
  should adapt the live Tau condition-comparison runner to consume this
  instrument corpus as an explicit evaluation slice, then rerun the
  pre-outcome cooperation-threshold scoring against live-originated instrument
  artifacts.
- 2026-07-21 (PCTOM-R HELD-OUT COOPERATION EXPOSURE SLICE): a bounded live Tau
  slice over variants 23-24 was added and run to test whether the pre-outcome
  cooperation-threshold rule has held-out natural exposure beyond the full64
  variants 1-16 and balanced derivation variants 17-22. Command:
  `./skills/persona-dream/run.sh run-live-tau-cooperation-exposure-slice`.
  Receipt:
  `/tmp/persona-dream-live-tau-cooperation-exposure-slice-proof-20260721T200908Z/live_tau_cooperation_exposure_slice_receipt.v1.json`.
  Status `BLOCKED_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_SLICE`, receipt SHA-256
  `sha256:190a5c8c5313fb4298dc5840041e593713c9d1d4c436238fd69b912ca19608cb`.
  The run made 32 live Tau attempts and 32 live Tau calls across eight
  held-out rows, with `mocked:false`, `live:true`, no human content judgment,
  no LLM judge, zero Memory/provider/canonical/identity/source-memory writes,
  and hash-bound Tau receipts. Checks passed for derivation receipt, planning
  receipt, expected 32 cases, expected 8 rows, variant disjointness, no
  oracle/outcome inputs in the rule, and zero unsupported writes. The slice
  included one coordination/conflict cooperation-outcome row, but CD selected
  zero `OFFER_COOPERATION` actions from sealed `KAI_OFFERS_COOPERATION`
  predictions, so there were zero low-confidence cooperation interventions and
  zero action changes. Conclusion:
  `HELDOUT_COOPERATION_OUTCOME_PRESENT_BUT_CD_NO_OFFER_EXPOSURE`. This is a
  fail-closed live result: it blocks any planning-benefit claim for the
  cooperation-threshold rule from natural held-out exposure. Next PCTOM-R work
  should stop spending live calls looking for accidental cooperation exposure
  in the exhausted 1-24 corpus and instead add an explicit deterministic
  cooperation-exposure instrument or scenario variant before rerunning held-out
  benefit checks.
- 2026-07-21 (PCTOM-R HELD-OUT COOPERATION THRESHOLD RULE): a pre-outcome
  cooperation-threshold rule now replays over the accepted full64 live Tau
  root. Receipt:
  `/tmp/persona-dream-live-tau-cooperation-threshold-rule-20260721T195055Z/live_tau_cooperation_threshold_rule_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_COOPERATION_THRESHOLD_RULE`, receipt SHA-256
  `sha256:a118bac2373a1cc5b5e9748cdb8efbe542d8e65b180301ba5e17ad0d56dd3020`.
  The rule is `pre_outcome_cooperation_threshold_rule.v1`: if CD selected
  `OFFER_COOPERATION` from sealed predicted counterpart action
  `KAI_OFFERS_COOPERATION` with probability below `0.50`, fall back to `WAIT`;
  otherwise keep the original action. Rule inputs are sealed prediction/action
  fields only, with `uses_outcome_or_oracle:false`; outcome/oracle utility is
  used only after action selection for scoring. The runner consumed the
  derivation receipt
  `/tmp/persona-dream-live-tau-balanced-threshold-intervention-20260721T194434Z/live_tau_balanced_threshold_intervention_receipt.v1.json`
  and the held-out full64 root
  `/tmp/persona-dream-live-tau-sealed-test-replication-full64-20260721T055039Z`
  without reexecuting Tau. Held-out variants were 1-16, disjoint from balanced
  derivation variants 17-22. Counts: 64 held-out rows, 256 consumed live Tau
  calls, zero new Tau calls, zero Memory/provider/canonical/identity/
  source-memory writes, zero CD `OFFER_COOPERATION` candidates, zero rule
  interventions, and zero planning-regret change. Conclusion:
  `HELDOUT_NO_COOPERATION_EXPOSURE_NO_REGRESSION`. This proves the rule can be
  applied pre-outcome over held-out live-originated artifacts and does not
  perturb unrelated full64 decisions, but it does not prove held-out benefit
  under cooperation-exposure cases, confidence-bounded CD planning benefit, or
  threshold optimality. Next PCTOM-R work should create or run a held-out
  cooperation-exposure slice before claiming planning benefit from this rule.
- 2026-07-21 (PCTOM-R BALANCED THRESHOLD INTERVENTION): a deterministic
  action-threshold ablation now separates the cooperation and clarifying-action
  switches found by the balanced gain/loss diagnostic. Receipt:
  `/tmp/persona-dream-live-tau-balanced-threshold-intervention-20260721T194434Z/live_tau_balanced_threshold_intervention_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_BALANCED_THRESHOLD_INTERVENTION`, receipt SHA-256
  `sha256:65a5fda6f552cba3db39f94ba5951faffda0cb09c50a6dae965b79ee17a23bf1`.
  The runner consumed the accepted v17-22 aggregate and the balanced
  gain/loss diagnostic, recomputed the aggregate rows SHA-256
  `sha256:e42a2497ae36aea1a0e22ec0f0df1d52ec735859ba68228d19e1b40fc025ad98`,
  and made zero Tau, Memory, provider, canonical-memory, identity, or
  source-memory writes. The consumed aggregate still binds 96 live Tau calls.
  Observed CD-minus-baseline mean was `-0.024999999999999994`. Blocking only
  `WAIT -> OFFER_COOPERATION` changes three coordination/conflict rows,
  avoids two HARM rows, loses one BENEFIT row, and improves the mean to
  `-0.07291666666666667`. Blocking `SET_BOUNDARY -> ASK_CLARIFYING_QUESTION`
  changes four trust/commitment rows, avoids two HARM rows, loses two BENEFIT
  rows, and worsens the mean to `0.025000000000000012`. Blocking
  `WAIT -> ASK_CLARIFYING_QUESTION` loses the single preference/desire benefit.
  Conclusion: `RAISE_COOPERATION_THRESHOLD_KEEP_CLARIFYING_THRESHOLD_UNPROVEN`.
  This is oracle-labeled aggregate ablation evidence, not an implementable
  no-oracle runtime policy. It does not prove confidence-bounded CD planning
  benefit, future reproduction, semantic dream quality, paid provider
  execution, or complete live Phase 01-16 runtime execution. Next PCTOM-R work
  should convert the cooperation-threshold finding into a pre-outcome,
  evidence-only decision rule and test it on held-out live Tau rows before
  making a planning-benefit claim.
- 2026-07-21 (PCTOM-R BALANCED PLANNING GAIN/LOSS DIAGNOSTIC): a deterministic
  diagnostic now explains the mixed balanced v17-22 planning signal without
  reexecuting Tau. Receipt:
  `/tmp/persona-dream-live-tau-balanced-planning-diagnostic-20260721T193929Z/live_tau_balanced_planning_diagnostic_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_DIAGNOSTIC`, receipt SHA-256
  `sha256:b2a65630a4e1c1d541416ccc182a8074cd4e95e60627356dc6f5b04915c21aa8`.
  The diagnostic consumed the accepted v17-22 aggregate receipt at
  `/tmp/persona-dream-live-tau-balanced-planning-v17-22-aggregate-20260721T192057Z/balanced_planning_aggregate_receipt.v1.json`
  and recomputed the aggregate row file SHA-256
  `sha256:e42a2497ae36aea1a0e22ec0f0df1d52ec735859ba68228d19e1b40fc025ad98`.
  The diagnostic made zero Tau calls, while the consumed aggregate binds 96
  live Tau calls; Memory/provider/canonical/identity/source-memory writes were
  all zero. Counts: 24 rows, 8 action switches, 8 nonzero deltas, all nonzero
  deltas are action switches, 4 BENEFIT / 4 HARM / 16 TIE, and 4 GAIN / 4 LOSS
  / 16 UNCHANGED. Diagnostic conclusion:
  `ACTION_SWITCH_GAIN_LOSS_SYMMETRY`. Concrete action-switch pattern:
  `SET_BOUNDARY -> ASK_CLARIFYING_QUESTION` appears 4 times in trust/commitment
  with 2 GAIN and 2 LOSS; `WAIT -> OFFER_COOPERATION` appears 3 times in
  coordination/conflict with 1 GAIN and 2 LOSS; `WAIT -> ASK_CLARIFYING_QUESTION`
  appears once in preference/desire with 1 GAIN. This proves the current
  balanced nonzero planning-regret signal is action-policy threshold behavior,
  not broad planning benefit. It does not prove confidence-bounded CD planning
  benefit, semantic dream quality, paid provider execution, complete live
  Phase 01-16 runtime execution, or reproducibility on a larger/different
  corpus. Next PCTOM-R work should add a targeted controlled intervention that
  separates clarifying-question and cooperation thresholds in coordination/
  conflict and trust/commitment before any planning-benefit claim.
- 2026-07-21 (PCTOM-R BALANCED LIVE TAU V17-22 AGGREGATE): a follow-on
  balanced variants 21-22 slice also passed, then accepted balanced slices
  v17-18, v19-20 retry, and v21-22 were aggregated without reexecuting Tau.
  New v21-22 receipt:
  `/tmp/persona-dream-live-tau-balanced-planning-v21-22-20260721T191328Z/live_tau_balanced_planning_replication_receipt.v1.json`,
  status `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`, receipt SHA-256
  `sha256:08c3f1c63d4e2abfe632acf655dc842a38586979d964ccfce63b5843ab664a6e`.
  It made 32 live Tau attempts and 32 live Tau calls over eight balanced
  sealed-test episodes, with all Gate 0 attribution, hash-bound Tau receipts,
  Gate 5 scoring, Gate 6 action rows, no human content judgment, no LLM judge,
  and zero Memory/provider/canonical/identity/source-memory writes. Its
  planning result was mildly harmful for CD: CD mean planning regret `0.275`,
  strongest baseline M `0.24375`, CD-minus-baseline `0.03125`, one BENEFIT,
  two HARM, five TIE, and CI `[-0.28750000000000003, 0.31875000000000003]`.
  Aggregate receipt:
  `/tmp/persona-dream-live-tau-balanced-planning-v17-22-aggregate-20260721T192057Z/balanced_planning_aggregate_receipt.v1.json`,
  status `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_AGGREGATE`, receipt SHA-256
  `sha256:a740a7b889716ae04f2ace6e0020d13636ea008f061ce3922d2bdf81ac79f6a6`.
  Across 24 balanced accepted episodes from variants 17-22, source receipts
  contain 96 live Tau calls, 4 BENEFIT rows, 4 HARM rows, 16 TIE rows, four
  oracle-match GAINs, four LOSSes, sixteen UNCHANGED rows, and mean
  CD-minus-baseline `-0.024999999999999994`. Family means are:
  coordination/conflict `0.19166666666666674`, information asymmetry `0.0`,
  preference/desire `-0.09166666666666666`, and trust/commitment
  `-0.20000000000000004`. Current interpretation is
  `MIXED_BALANCED_SIGNAL_NOT_CONFIDENCE_BOUNDED`: the PCTOM-R pipeline is
  producing objective prospective planning signal, but not yet a stable
  confidence-bounded CD planning benefit. Next work should inspect the GAIN vs
  LOSS rows and adjust deterministic scenario/policy design or run a larger
  balanced slice; do not claim research success from the small negative mean.
- 2026-07-21 (PCTOM-R BALANCED LIVE TAU V19-20 RETRY): the earlier blocked
  balanced variants 19-20 slice was rerun from clean `origin/main` with Gate 0
  attribution overlay and passed. Receipt:
  `/tmp/persona-dream-live-tau-balanced-planning-v19-20-retry-20260721T190511Z/live_tau_balanced_planning_replication_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`, receipt SHA-256
  `sha256:f78c4113d10be6bbe0cc67d7b3ed9560919f14fc4e223f0ffad6edf9e06b2249`.
  It made 32 live Tau attempts and 32 live Tau calls over eight sealed-test
  episodes: two each from information asymmetry, preference/desire,
  trust/commitment, and coordination/conflict. Gate 0 attribution was loaded,
  all four M/R/D/CD conditions produced eight action decisions and eight
  planning-regret scores, Tau receipts were hash-bound, and Memory/provider/
  canonical/identity/source-memory write attempts were all zero. The slice is
  useful positive planning-signal evidence but not confidence-bounded planning
  proof: CD mean planning regret was `0.1375` versus strongest baseline M
  `0.24375`, CD-minus-baseline mean `-0.10624999999999998`, with three
  BENEFIT rows, two HARM rows, three TIE rows, and bootstrap CI
  `[-0.45625000000000004, 0.25000000000000006]`. This supersedes the earlier
  v19-20 service-failure blocker as the current state for that slice, but it
  does not supersede the broader limitation that planning benefit remains
  unproven at confidence. Next PCTOM-R work should expand or aggregate balanced
  live slices specifically around the mixed GAIN/LOSS cases, not restart
  provider/video work.
- 2026-07-21 (PCTOM-R PLANNING CI FLAG REPAIR): the distributional and
  confidence-gated planning-intervention runners no longer hard-code
  `planning_benefit_with_confidence:false`; they derive it from the bootstrap
  planning-regret CI upper bound (`upper < 0`, lower-is-better). Regression
  test `skills/persona-dream/tests/test_pctom_planning_intervention_ci.py`
  proves all-negative deltas set the flag true and tie/harm-only cases keep it
  false. Focused proof:
  `uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_pctom_planning_intervention_ci.py -q`
  returned `4 passed in 0.03s`; `python3 -m py_compile` over both patched
  scripts and the new test emitted no errors. Fresh receipts over the full64
  live Tau root are:
  `/tmp/persona-dream-live-tau-distributional-planning-intervention-ci-derived-20260721T155724Z/distributional_planning_intervention_receipt.v1.json`
  and
  `/tmp/persona-dream-live-tau-confidence-gated-planning-intervention-ci-derived-20260721T155724Z/confidence_gated_planning_intervention_receipt.v1.json`.
  Both report `mocked:false`, `live:true`, `live_tau_originated_artifacts_consumed:true`,
  `live_tau_reexecuted:false`, `tau_call_attempts:0`, and zero Memory/provider/
  canonical/identity/source-memory writes. They still do not prove planning
  benefit: distributional ties all 64 planning rows with CI `[0.0, 0.0]`;
  confidence-gated has 63 ties, one harm, mean CD-minus-baseline planning regret
  `0.004687499999999999`, and CI upper `0.014062499999999997`.
- 2026-07-21 (PCTOM-R BLOCKED BALANCED LIVE TAU V19-20 SLICE): a fresh live
  balanced planning run over variants 19-20 wrote
  `/tmp/persona-dream-live-tau-balanced-planning-v19-20-20260721T155956Z/live_tau_balanced_planning_replication_receipt.v1.json`.
  Status `BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`, receipt
  SHA-256 `sha256:9f7fddbca26b1442e62c0c81e0beb7c3e695975ae52eeae88f81502721e4a585`.
  It made 32 live Tau attempts and 32 live Tau calls, with 0 Memory/provider/
  canonical/identity/source-memory writes, then failed closed because
  `sealedte-info-asym-19` R and D returned `scillm_http_status_502`. The
  resulting partial action-selection layer had 7/8 planning rows and did not
  satisfy balanced family counts (`information_asymmetry_false_belief:1:2`).
  This is useful live blocker/reliability evidence; it must not be treated as
  balanced planning coverage or planning-benefit proof.
- 2026-07-21 (PCTOM-R FRESH FULL64 SERVICE-BOUNDARY RETRY PROOF): fresh local
  HTTP service retry evidence exists at
  `/tmp/persona-dream-live-tau-sealed-test-service-retry-proof-fresh-20260721T155119Z/live_tau_sealed_test_service_retry_proof_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF`, receipt SHA-256
  `sha256:d92fd93008ec467b515b745083947459d875b33dfa87bd423a4bf64e7cf509ef`.
  The proof consumed the full64 live Tau sealed-test replication root without
  reexecuting Tau: `mocked:false`, `live:true`,
  `live_tau_originated_artifacts_consumed:true`, `live_tau_reexecuted:false`.
  Counts: 256 action decisions, 256 active predictions, five HTTP submissions,
  four unique service jobs, one duplicate submission detected and not promoted,
  two completed jobs, two blocked jobs, eight retry fault trials, zero
  `CONTINUED_WITH_UNKNOWN_STATE`, zero duplicate active/action promotions, zero
  side-effect violations, and zero Memory/provider/canonical/identity/
  source-memory writes. This proves a separate local HTTP process boundary for
  retry/idempotence/fail-closed handling over live-originated PCTOM-R artifacts.
  It does not prove a permanently deployed external always-on orchestrator, new
  live Tau execution, paid provider execution, semantic dream quality, or
  complete live Phase 01-16 runtime execution. Planning benefit remains
  unproven.
- 2026-07-21 (PCTOM-R LIVE STRICT-INFERENCE BALANCED SLICE + UX LAB
  HOUSING): UX Lab is a light multi-project wrapper in `agent-skills@main`, not
  the old pi-mono app. The live service `ux-lab-vite.service` was corrected
  locally to run the Python hub from
  `/home/graham/workspace/experiments/agent-skills-main/skills/ux-lab`, and the
  Persona Dream card is reachable at
  `http://127.0.0.1:3002/?project=persona-dream`. CDP marker:
  `/home/graham/workspace/experiments/agent-skills-main/.codex/ui-verification/latest.json`;
  screenshot:
  `/tmp/codex-ui-verification/agent-skills-main/ux-lab-persona-dream-hub/20260721T151457Z.png`.
  This proves hub/card visibility only; the declared legacy `#dream` route is
  not an active mounted dream runtime. Registry wording was clarified in commit
  `ad83c9e6d685dbfea08a14c7294e1c8a5555f5d4`.
- 2026-07-21 (PCTOM-R LIVE STRICT-INFERENCE BALANCED SLICE): the 90s strict
  replication blocked at
  `/tmp/persona-dream-live-tau-strict-inference-timeout90-v17-20260721T1516Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`
  after one Tau timeout and subsequent scillm `gpt-5.5` cooldown/502 responses.
  Authenticated scillm health later showed `gpt-5.5` half-open with no active
  calls, and a minimal Tau-routed recovery probe passed at
  `/tmp/persona-dream-live-tau-minimal-recovery-probe-20260721T1526Z.json`.
  The rerun with `--timeout-s 120` passed:
  `/tmp/persona-dream-live-tau-strict-inference-timeout120-v17-20260721T1527Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`,
  receipt SHA-256 `sha256:27e7469cea92f3546ae6a2df3377548a3f6b61cf813cc7d02d1e79bcc38e5f0d`.
  It reports `mocked:false`, `live:true`, 16/16 Tau live calls, 16 non-template
  distributions, 16 Gate 6 action decisions, 4 planning rows, one episode from
  each of the four scenario families, 0 blocked cases, and 0 Memory/provider/
  canonical/identity/source-memory writes. It does not prove planning benefit:
  `planning_benefit_with_confidence:false`, `oracle_match_transitions` is one
  `LOSS` and three `UNCHANGED`, and CD-vs-baseline mean planning regret delta is
  `0.1375`.
- 2026-07-21 (PCTOM-R LIVE ACTION-LINKED REVISION, MEMORY RECALL, FAULT
  SURFACE): the strict120 live slice now has a follow-on Gate 7 and reliability
  chain. Action-linked revision receipt:
  `/tmp/persona-dream-live-tau-action-linked-revision-strict120-v17-20260721T1545Z/live_tau_action_linked_revision_receipt.v1.json`
  reports `PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION`, 16/16
  `PASS_TOM_BELIEF_REVISION`, four prior hypotheses and four posterior
  revisions per condition, and zero Memory/provider/canonical/identity/source
  writes. Deterministic recall receipt:
  `/tmp/persona-dream-live-tau-revision-recall-strict120-v17-20260721T1546Z/live_tau_revision_recall_receipt.v1.json`
  reports `PASS_LIVE_TAU_PCTOM_REVISION_RECALL`, 16 revision documents, 16
  local recall hits, prior/posterior distinction preserved, synthetic/literal
  boundary preserved, and zero write violations. Live Memory receipt:
  `/tmp/persona-dream-live-memory-revision-recall-strict120-v17-20260721T1547Z/live_memory_revision_recall_receipt.v1.json`
  reports `PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL`, 16 noncanonical PCTOM-R
  revision docs upserted and exact-reread, 16 semantic mirrors upserted and
  exact-reread, four `/recall` condition queries, 16 recall hits, and zero
  canonical/identity/source-memory/provider/Tau writes. Fault surface receipt:
  `/tmp/persona-dream-live-fault-injection-surface-strict120-v17-20260721T1548Z/live_fault_injection_surface_receipt.v1.json`
  reports `PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE`,
  `receipt_sha256:sha256:aa0bf2389ff88f299ccfaf77f3b017e40e4159d851fc7928aca379cb49ded84f`,
  eight required fault families, eight trials, one causal replay artifact, three
  live Memory fault probes, zero `CONTINUED_WITH_UNKNOWN_STATE`, zero
  side-effect violations, and zero Memory/provider/Tau/canonical/identity/source
  writes. Limits remain explicit: this does not prove planning benefit,
  production retry machinery, live Tau sealed-test execution, complete Phase
  01-16 runtime execution, provider execution, video/audio, or semantic dream
  quality.
- 2026-07-21 (PCTOM-R STRICT120 BALANCED PLANNING REUSE): the strict120
  condition/action roots were re-consumed without new Tau calls by
  `/tmp/persona-dream-live-tau-balanced-planning-reuse-strict120-v17-limit1-20260721T1550Z/live_tau_balanced_planning_replication_receipt.v1.json`.
  Status `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION`; it consumed 16
  hash-bound live Tau case artifacts, represented all four families, produced
  four action decisions per condition, and attempted zero writes. The planning
  result is explicitly negative/insufficient: `planning_benefit_with_confidence:false`,
  CD planning regret mean `0.275`, strongest baseline D `0.1375`, CD-minus-D
  `0.1375`, one `LOSS`, and three `UNCHANGED` transitions.
- 2026-07-21 (PCTOM-R TAU PROMPT TIMEOUT DIAGNOSTIC): the full-prompt timeout
  boundary is now narrowed. New command:
  `./skills/persona-dream/run.sh run-live-tau-prompt-timeout-diagnostic`.
  It routes through the sanctioned Persona Dream Tau adapter and writes
  hash-bound case receipts for short preflight, padded prompt, compact domain
  payload, default condition prompt, and strict condition prompt cases. Receipt
  `/tmp/persona-dream-live-tau-prompt-timeout-diagnostic-20260721T1510Z/live_tau_prompt_timeout_diagnostic_receipt.v1.json`
  with `timeout_s:30` reports the 204-byte preflight, 15,481-byte padded
  prompt, and 2,912-byte compact domain payload pass in roughly 2-3 seconds,
  while the 15,481-byte actual condition prompt and 16,430-byte strict prompt
  timeout at 30 seconds. Receipt
  `/tmp/persona-dream-live-tau-prompt-timeout-diagnostic-90s-20260721T1511Z/live_tau_prompt_timeout_diagnostic_receipt.v1.json`
  with `timeout_s:90` reports all five cases passing; actual and strict
  condition prompts each take about 52 seconds. Size alone is not the blocker:
  full structured PCTOM-R output generation needs a live-call budget above 30s.
  The adapter now forwards `timeout_s` into Tau's inner scillm HTTP request
  instead of only enforcing the parent subprocess timeout. A real one-episode
  live condition smoke at
  `/tmp/persona-dream-live-tau-condition-comparison-timeout90-smoke-20260721T1512Z/live_tau_condition_comparison_receipt.v1.json`
  reports `PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON`, 4 Tau calls, 4 sealed
  commitments, 4 deterministic scores, and all Gate 2-5 checks passing with
  zero writes. The Gate 6 bridge over that root wrote 4 individual action
  receipts but blocked at
  `/tmp/persona-dream-live-tau-condition-action-selection-timeout90-smoke-20260721T1512Z/live_tau_condition_action_selection_receipt.v1.json`
  because the base root only had 1 case per condition and the bridge acceptance
  floor expects 4 per condition. This is a smoke boundary, not planning benefit.
- 2026-07-21 (PCTOM-R TAU BOUNDARY RECEIPTS): the preflight/pass plus
  case-timeout boundary now has per-case local receipts. When Tau dispatch
  raises before returning a Tau receipt, the live condition runner writes a
  `persona_dream.research.prospective_tom.tau_text_reasoning_dispatch_boundary_receipt.v1`
  with prompt SHA-256, prompt byte/character counts, output-contract hash,
  timeout, status, and systemic-failure signature. When the systemic breaker
  skips remaining cases, it writes the same receipt schema with
  `BLOCKED_BY_SYSTEMIC_FAILURE`. Receipt:
  `/tmp/persona-dream-live-tau-boundary-receipts-20260721T1500Z/live_tau_condition_comparison_receipt.v1.json`
  reports `tau_boundary_receipts_written:4`,
  `tau_boundary_receipts_written_for_all_rows:true`, `tau_call_attempts:3`,
  and `blocked_by_systemic_failure:1`. Strict-inference receipt:
  `/tmp/persona-dream-live-tau-strict-boundary-receipts-20260721T1500Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`
  reports `condition_tau_boundary_receipts_written:16`,
  `condition_tau_boundary_receipts_written_for_all_rows:true`,
  `tau_call_attempts:3`, and `condition_blocked_by_systemic_failure:13`.
  This improves receipt discipline and timeout diagnosis; it still does not
  prove strict prompt quality or planning benefit.
- 2026-07-21 (PCTOM-R TAU SYSTEMIC TIMEOUT BREAKER): live Tau/scillm
  text-reasoning now reaches the one-shot Tau preflight, but case prompts are
  timing out. The live condition runner now performs a bounded Tau preflight
  before case fan-out and stops a repeated Tau case-failure family after three
  matching signatures. Receipt:
  `/tmp/persona-dream-live-tau-systemic-breaker-final-20260721T1448Z/live_tau_condition_comparison_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_CONDITION_COMPARISON`,
  `tau_preflight_passed:true`, `tau_preflight_live_call_performed:true`,
  `tau_call_attempts:3`, `tau_live_call_performed:0`,
  `systemic_failure_signature:tau_text_reasoning_timeout`, and
  `blocked_by_systemic_failure:1`. Strict-inference receipt:
  `/tmp/persona-dream-live-tau-strict-systemic-breaker-20260721T1448Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION`,
  `tau_call_attempts:3`, `condition_blocked_by_systemic_failure:13`,
  0 action decisions, and no accepted planning rows. This is fail-closed
  reliability evidence only. It does not prove planning benefit or strict prompt
  quality. Next PCTOM-R work should diagnose why full condition prompts timeout
  after preflight succeeds, then rerun the strict-inference replication with
  normal timeouts.
- 2026-07-21 (PCTOM-R TAU TIMEOUT CONTAINMENT / STRICT INFERENCE BLOCKER):
  the next planning-quality issue is not provider/video work. The live Tau
  condition prompt can copy schema/template probabilities, so a new strict
  inference command was added:
  `./skills/persona-dream/run.sh run-live-tau-strict-inference-prompt-replication`.
  It uses a schema-explicit prompt with `INFER_PROBABILITY` placeholders and
  blocks unless at least one action distribution is non-template. While testing
  it, both the strict runner and the default live condition runner hung before
  the first case receipt. Root cause found in
  `skills/persona-dream/scripts/tau_text_reasoning_adapter.py`: the Tau/uv
  subprocess path was not reliably bounded by `subprocess.run(timeout=...)`.
  The adapter now starts Tau in a new process group and kills the process group
  on timeout. Control receipt:
  `/tmp/persona-dream-live-tau-default-control-adapter-timeout-20260721T142915Z/live_tau_condition_comparison_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_CONDITION_COMPARISON`, `mocked:false`,
  `live:false`, 4 Tau attempts, 0 live calls completed, and four
  `Tau dispatch timed out after 5.0s` errors without requiring an external
  shell kill. Strict-inference receipt:
  `/tmp/persona-dream-live-tau-strict-inference-smoke-clean-timeout-20260721T143140Z/live_tau_strict_inference_prompt_replication_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_STRICT_INFERENCE_PROMPT_REPLICATION`,
  `mocked:false`, `live:false`, `live_tau_reexecuted:true`,
  `live_tau_originated_artifacts_consumed:false`, 16 bounded Tau attempts,
  0 live calls completed, 16 blocked cases, 0 action decisions, and no
  accepted strict-inference planning rows. This is fail-closed reliability
  progress, not planning benefit. Next PCTOM-R work should first restore or
  confirm live Tau/scillm text-reasoning availability, then rerun the strict
  inference prompt replication with normal timeouts before attempting another
  utility/reward intervention.
- 2026-07-21 (PCTOM-R BALANCED LIVE TAU PLANNING REPLICATION): balanced
  four-family live Tau planning replication evidence now exists at
  `/tmp/persona-dream-live-tau-balanced-planning-v17-18-final-20260721T135844Z/live_tau_balanced_planning_replication_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION` while
  consuming hash-bound live Tau-originated condition artifacts from
  `/tmp/persona-dream-live-tau-balanced-planning-v17-18-20260721T132835Z`.
  The source live run made 32 Tau calls across 8 sealed-test episodes, with 2
  episodes each from `information_asymmetry_false_belief`,
  `preference_desire_uncertainty`, `trust_commitment_relationship`, and
  `coordination_conflict`, and 8 action decisions per M/R/D/CD condition. The
  final reuse receipt records `mocked:false`, `live:true`,
  `fixture_backed:false`, `deterministic_simulator_corpus_fixture_backed:true`,
  `live_tau_reexecuted:false`,
  `live_tau_originated_artifacts_consumed:true`, no human content judgment, no
  LLM judge, 0 Memory/provider/canonical/identity/source-memory writes, and
  no errors. The result is a planning null: CD tied the strongest baseline on
  all 8 planning rows, action switches were 0, nonzero planning deltas were 0,
  mean CD-minus-baseline planning regret was `0.0`, and bootstrap CI was
  `[0.0, 0.0]`; `planning_benefit_with_confidence:false`. This improves
  balanced live coverage and prevents the previous trust/commitment-only
  planning evidence from being mistaken for general coverage, but it does not
  prove planning benefit. The missing-root negative receipt at
  `/tmp/persona-dream-live-tau-balanced-planning-negative-final-20260721T135844Z/live_tau_balanced_planning_replication_receipt.v1.json`
  exits 1 and reports
  `BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION` with `live:false` and
  `live_tau_originated_artifacts_consumed:false`. Next PCTOM-R work should
  target a deterministic utility/reward intervention or scenario/policy
  expansion that can create beneficial CD-vs-baseline planning deltas without
  corrupting sealed prediction, deterministic scoring, no-judge, and no-write
  constraints.
- 2026-07-21 (PCTOM-R CONFIDENCE-GATED PLANNING INTERVENTION): a
  non-tied deterministic planning-intervention receipt now exists at
  `/tmp/persona-dream-live-tau-confidence-gated-planning-intervention-20260721T131015Z/confidence_gated_planning_intervention_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_CONFIDENCE_GATED_PLANNING_INTERVENTION` for
  policy `confidence_gated_epistemic_action.v1` with confidence threshold
  `0.35`. The command consumed the full64 live Tau sealed-test root without
  reexecuting Tau: 64 episodes, 256 rewritten action cases, 256
  `PASS_TOM_ACTION_SELECTION` receipts, and 64 action decisions per M/R/D/CD
  condition. It changed selected actions in 187 cases and exercised two
  explicit rules: `CONFIDENT_TOP_MAPPED_ACTION=193` and
  `LOW_CONFIDENCE_EPISTEMIC_ACTION=63`. Unlike the previous distributional
  intervention, this produced non-tied CD-vs-baseline planning deltas:
  `TIE=63`, `HARM=1`, nonzero family `coordination_conflict`, mean
  CD-minus-baseline planning regret `0.004687499999999999`, CI `[0.0,
  0.014062499999999997]`. This is useful negative evidence: the epistemic
  confidence gate can change the planning outcome, but it harms one
  coordination/conflict case and does not prove planning benefit.
  `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_originated_artifacts_consumed:true`, `live_tau_reexecuted:false`,
  `human_content_judgment_required:false`, `llm_judge_used:false`, and
  Tau/Memory/provider/canonical/identity/source-memory write attempts were all
  0. The missing-root negative receipt at
  `/tmp/persona-dream-live-tau-confidence-gated-planning-intervention-negative-20260721T131026Z/confidence_gated_planning_intervention_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_CONFIDENCE_GATED_PLANNING_INTERVENTION`,
  exits 1, and records `live:false` plus
  `live_tau_originated_artifacts_consumed:false`. Next PCTOM-R planning work
  should target non-identical repeated live Tau behavior over a larger/balanced
  corpus or a utility/reward intervention that improves planning without
  simply adding an epistemic-action harm.
- 2026-07-21 (PCTOM-R DISTRIBUTIONAL PLANNING INTERVENTION): broader
  planning-intervention evidence now exists at
  `/tmp/persona-dream-live-tau-distributional-planning-intervention-20260721T130137Z/distributional_planning_intervention_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_DISTRIBUTIONAL_PLANNING_INTERVENTION` for
  policy `distributional_expected_utility_over_predicted_next_action.v1`.
  The command consumed the full64 live Tau sealed-test root without reexecuting
  Tau: 64 episodes, 256 full64 base cases, 256 rewritten action cases, 256
  `PASS_TOM_ACTION_SELECTION` receipts, and 64 action decisions per M/R/D/CD
  condition. It changed selected actions in 188 cases: M=48, R=48, D=48,
  CD=44. Action-policy changes were not trust/commitment-only:
  `coordination_conflict=64`, `preference_desire_uncertainty=64`, and
  `trust_commitment_relationship=60`; CD changed in coordination/conflict 16,
  preference/desire 16, and trust/commitment 12. This satisfies the request for
  a broader/different planning intervention that changes action policy beyond
  the previous sparse trust/commitment subset. It does not prove planning
  benefit: CD versus the strongest M/R/D baseline tied on all 64 planning rows,
  mean CD-minus-baseline planning regret was `0.0`, and bootstrap CI was
  `[0.0, 0.0]`. `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_originated_artifacts_consumed:true`, `live_tau_reexecuted:false`,
  `human_content_judgment_required:false`, `llm_judge_used:false`, and
  Tau/Memory/provider/canonical/identity/source-memory write attempts were all
  0. The missing-root negative receipt at
  `/tmp/persona-dream-live-tau-distributional-planning-intervention-negative-20260721T130208Z/distributional_planning_intervention_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_DISTRIBUTIONAL_PLANNING_INTERVENTION`,
  exits 1, and correctly records `live:false` plus
  `live_tau_originated_artifacts_consumed:false`. Next PCTOM-R work should
  target non-identical repeated live Tau behavior over a larger/balanced
  planning corpus, or a different deterministic utility/reward intervention
  that produces non-tied CD-vs-baseline planning deltas without weakening
  sealed prediction, deterministic scoring, oracle-policy, no-judge, and
  no-write constraints.
- 2026-07-21 (PCTOM-R PLANNING NON-GENERALIZATION AUDIT): planning
  generalization-boundary evidence now exists at
  `/tmp/persona-dream-live-tau-planning-non-generalization-audit-20260721T124136Z/planning_non_generalization_audit_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_PLANNING_NON_GENERALIZATION_AUDIT` with
  conclusion `PLANNING_SIGNAL_SPARSE_FAMILY_CONCENTRATED_NOT_GENERALIZED`.
  The audit hash-binds four predecessor receipts: full64 statistical
  confidence (`sha256:299f499b59b4cbf37bbde42df7a293fe2d064658724fa53d63dd677fc40a5574`),
  full64 planning diagnostic (`sha256:da419d8100de60248ccedacdfe84158273bc007b44ec3dad2b2f625453507021`),
  full64 action-policy sensitivity (`sha256:141a75da8dbe054150b2a6da279c738c9d67f24949ef48bd5f1665b216f2daef`),
  and expanded repeated live trust/commitment summary
  (`sha256:7757e06fcb88c985ad74a0fdc21d7f8c5f074871c6c8b2c64d677125d5da67f3`).
  It separates belief-prediction benefit from planning non-benefit:
  full64 belief-Brier CI upper is `-0.008604609375000004`, while full64
  planning-regret CI upper is `0.00390625`. It records 64 full64 planning
  episodes with 60 ties and 4 nonzero deltas; all 4 nonzero deltas are
  trust/commitment action switches. It also records 64 expanded repeated live
  Tau calls consumed, 16 expanded repeated planning rows, identical expanded
  seed pattern hashes, and expanded repeated planning CI upper `0.0`.
  `mocked:false`, `live:true`, `live_tau_receipts_consumed:true`,
  `live_tau_reexecuted:false`, `human_content_judgment_required:false`,
  `llm_judge_used:false`, and Tau/Memory/provider/canonical/identity/
  source-memory write attempts were all 0. This satisfies the prior
  receipt-backed explanation path for why planning remains sparse and
  non-general. It does not prove confidence-bounded planning-regret benefit,
  non-identical repeated live Tau planning behavior, planning benefit under a
  larger/balanced corpus, new live Tau execution inside the audit, production
  retry machinery, live Memory recall in the sealed-test loop, complete live
  Phase 01-16 runtime execution, paid provider execution, or semantic dream
  quality. Next PCTOM-R work should run a broader/different planning
  intervention that changes action policy beyond the current sparse
  trust/commitment subset, or non-identical repeated live Tau behavior over a
  larger/balanced planning corpus. Service deployment remains supporting
  reliability scope, not the primary planning research artifact.
- 2026-07-21 (PCTOM-R FULL64 LIVE MEMORY FAULT SURFACE): full64 live
  Memory-in-loop fault evidence now exists at
  `/tmp/persona-dream-live-tau-full64-memory-fault-surface-20260721T122732Z/live_tau_full64_memory_fault_surface_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_FULL64_MEMORY_FAULT_SURFACE` while
  hash-binding the full64 live Tau statistical-confidence receipt, the live
  Memory revision-recall receipt, and the local HTTP service retry receipt.
  Counts: 8 fault trials, 8 fault families, 10 live Memory `/recall` probes,
  4 condition recall queries, 4 condition recall successes, 1 causal replay
  receipt, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect violations, and 0
  Memory/provider/Tau/canonical/identity/source-memory writes by this fault
  surface. Fault families covered: Memory unreachable, malformed Memory
  payload, collection visibility/stale recall, condition recall perturbation,
  duplicate/irrelevant source perturbation, schema drift, retry after uncertain
  completion, and untrusted tool text. Terminal outcomes were constrained to
  `RECOVERED_WITH_EQUIVALENT_END_STATE`, `BLOCKED_BEFORE_SIDE_EFFECT`, and
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE`. This is live Memory probe
  evidence over full64 live Tau-originated artifacts and the local service
  retry boundary; it does not prove new live Tau execution, new Memory writes,
  a permanently deployed external production service, paid provider execution,
  semantic dream quality, or complete Phase 01-16 runtime execution. Next
  PCTOM-R work should target a broader/different planning intervention or a
  permanently deployed external service boundary.
- 2026-07-21 (PCTOM-R LOCAL HTTP SERVICE RETRY BOUNDARY): local HTTP
  service-boundary retry evidence now exists at
  `/tmp/persona-dream-live-tau-sealed-test-service-retry-proof-20260721T121812Z/live_tau_sealed_test_service_retry_proof_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_SERVICE_RETRY_PROOF` while consuming the
  full64 live Tau sealed-test root
  `/tmp/persona-dream-live-tau-sealed-test-replication-full64-20260721T055039Z`.
  A separate service process accepted retry jobs over HTTP and wrote start/stop
  receipts. Counts: 5 HTTP job submissions, 4 unique service jobs, 1 duplicate
  submission detected, 2 completed jobs, 2 blocked jobs, 0 quarantined jobs,
  256 active predictions, 256 action decisions, 256 Gate 6 receipts, 8 child
  retry/fault trials, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect
  violations, 0 duplicate active predictions promoted, and 0 duplicate action
  decisions promoted. Checks show duplicate submission for the same job id was
  idempotent, exact retry and retry-after-uncertain-completion recovered
  equivalent active state, missing base root and interrupted persistence
  blocked before active-state promotion, and terminal outcomes stayed inside
  `RECOVERED_WITH_EQUIVALENT_END_STATE` or `BLOCKED_BEFORE_SIDE_EFFECT`.
  `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_originated_artifacts_consumed:true`, `live_tau_reexecuted:false`,
  and Memory/provider/canonical/identity/source-memory write attempts were all
  0. This closes a local HTTP service-boundary rung, not a permanently deployed
  external production service, new live Tau execution, live Memory service
  fault injection, paid provider execution, semantic dream quality, or complete
  Phase 01-16 runtime execution. Next PCTOM-R work should target live
  Memory-in-loop/fault evidence or a broader/different planning intervention.
- 2026-07-21 (PCTOM-R EXPANDED REPEATED LIVE TRUST/COMMIT SUMMARY):
  repeated expanded live Tau trust/commitment summary evidence now exists at
  `/tmp/persona-dream-live-tau-trust-commit-expanded-repeated-seed-summary-20260721T120650Z/live_tau_trust_commit_repeated_seed_receipt.v1.json`.
  It consumes two accepted expanded live Tau source receipts:
  `/tmp/persona-dream-live-tau-trust-commit-expanded-v17-24-20260721T110845Z/live_tau_trust_commit_replication_receipt.v1.json`
  and
  `/tmp/persona-dream-live-tau-trust-commit-expanded-v17-24-repeat2-20260721T114011Z/live_tau_trust_commit_replication_receipt.v1.json`.
  Status is `PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY` with
  `mocked:false`, `live:true`, `live_tau_receipts_consumed:true`,
  aggregate command `live_tau_reexecuted:false`, expected 24 episodes per
  family, expected trust episode limit 8, variants 17-24, 2 passed source
  receipts, 64 total live Tau calls consumed from those source receipts, 64
  sealed/scored cases, 16 planning rows, 2 action switches, 2 nonzero
  planning deltas, and oracle-match transitions `GAIN=2`, `UNCHANGED=14`.
  The aggregate CD-minus-baseline planning-regret mean is
  `-0.10625000000000001` with bootstrap CI `[-0.265625, 0.0]`, so planning
  benefit is still not confidence-bounded. The second expanded live Tau run
  reproduced the same row pattern as the first, so this is repeated live
  execution evidence but not non-identical seed-behavior evidence. The
  one-source negative receipt at
  `/tmp/persona-dream-live-tau-trust-commit-expanded-repeated-seed-summary-one-source-20260721T120712Z/live_tau_trust_commit_repeated_seed_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY` with
  error `requires_at_least_two_seed_receipts:1`, showing the aggregate summary
  fails closed when only one source receipt is supplied. Next PCTOM-R work
  should produce production retry-service proof, live Memory-in-loop/fault
  evidence, or a broader/different planning intervention; do not return to
  provider/video or subjective dream quality.
- 2026-07-21 (PCTOM-R LIVE EXPANDED TRUST/COMMIT COVERAGE): live Tau
  execution now covers the expanded trust/commitment variants 17-24. The
  accepted receipt at
  `/tmp/persona-dream-live-tau-trust-commit-expanded-v17-24-20260721T110845Z/live_tau_trust_commit_replication_receipt.v1.json`
  reports `PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION` with `mocked:false`,
  `live:true`, `live_tau_reexecuted:true`, 8 selected trust/commitment
  episodes (`sealedte-trust-commit-17` through `sealedte-trust-commit-24`),
  32 Tau calls, 32 sealed/scored cases, 8 action decisions per condition, all
  variant filter checks true, and zero Memory/provider/canonical/identity/
  source-memory writes. CD beat the strongest baseline on point estimates:
  belief Brier `-0.009062500000000029`, action Brier
  `-0.026050000000000018`, and planning regret `-0.10625000000000007`.
  Planning benefit is still not confidence-bounded because the bootstrap CI is
  `[-0.31875000000000003, 0.0]`. Only one action switch occurred
  (`sealedte-trust-commit-23`), producing one oracle-match gain and seven
  unchanged rows. The empty-filter negative receipt at
  `/tmp/persona-dream-live-tau-trust-commit-expanded-empty-filter-20260721T113450Z/live_tau_trust_commit_replication_receipt.v1.json`
  reports `BLOCKED_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION`, 0 cases, 0 Tau
  calls, and no writes, so the expanded live runner fails closed when no
  variants match. Next PCTOM-R work should produce repeated expanded live Tau
  seeds, live Memory-in-loop/fault evidence, or production retry-service proof
  instead of returning to provider/video or subjective dream quality.
- 2026-07-21 (PCTOM-R EXPANDED DETERMINISTIC TRUST/COMMIT COVERAGE):
  deterministic trust/commitment coverage has been expanded before another
  live Tau retry. The corpus generator now supports 24 episodes per family,
  and the fresh corpus check receipt at
  `/tmp/persona-dream-expanded-corpus-20260721T110141Z/social_episode_corpus_check_receipt.json`
  reports `PASS_SOCIAL_EPISODE_CORPUS` with `mocked:false`, `live:false`,
  `fixture_backed:true`, 96 total episodes, 24 episodes per family, 96
  first-order labels, 96 second-order labels, deterministic policies, and no
  LLM judge. The filtered trust/commitment heldout receipt at
  `/tmp/persona-dream-expanded-trust-heldout-20260721T110148Z/heldout_condition_benefit_receipt.v1.json`
  reports `PASS_PCTOM_HELDOUT_CONDITION_BENEFIT` with `mocked:false`,
  `live:false`, 8 selected trust/commitment episodes
  (`explicit-trust-commit-17` through `explicit-trust-commit-24`), 32 M/R/D/CD
  cases, 8 sealed commitments, deterministic scores, action decisions, and
  planning-regret scores per condition, and all scenario-family/variant filter
  checks true. CD beats the strongest baseline on mean belief Brier
  (`-0.07979999999999995`) but ties the strongest baseline on mean planning
  regret (`0.0`). An empty-filter negative receipt at
  `/tmp/persona-dream-expanded-trust-heldout-empty-filter-20260721T110157Z/heldout_condition_benefit_receipt.v1.json`
  reports `BLOCKED_PCTOM_HELDOUT_CONDITION_BENEFIT`, 0 cases, 0 action
  decisions, missing CD delta, and no writes/calls, so the filtered heldout
  boundary fails closed instead of accepting an empty comparison. This is
  deterministic simulator evidence, not live Tau heldout execution, live
  Memory recall, production retry machinery, paid provider execution,
  semantic dream quality, or complete Phase 01-16 runtime evidence. Next
  PCTOM-R work should run live Tau over the expanded trust/commitment variants
  or prove the production retry service boundary.
- 2026-07-21 (PCTOM-R REPEATED-SEED TRUST/COMMIT SUMMARY): repeated-seed
  trust/commitment planning evidence now exists at
  `/tmp/persona-dream-live-tau-trust-commit-repeated-seed-summary-20260721T105120Z/live_tau_trust_commit_repeated_seed_receipt.v1.json`.
  It consumes two accepted floor4 live Tau receipts:
  `/tmp/persona-dream-live-tau-trust-commit-replication-floor4-20260721T101929Z/live_tau_trust_commit_replication_receipt.v1.json`
  and
  `/tmp/persona-dream-live-tau-trust-commit-replication-floor4-repeat2-20260721T103729Z/live_tau_trust_commit_replication_receipt.v1.json`.
  Status is `PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPEATED_SEED_SUMMARY`;
  `mocked:false`, `live:true`, `live_tau_receipts_consumed:true`,
  aggregate command `live_tau_reexecuted:false`, 2 passed seed receipts, 32
  total Tau calls consumed, 32 sealed/scored cases, and 8 planning rows. The
  aggregate CD-minus-baseline planning-regret mean is `-0.15000000000000002`,
  with 4 action switches, 2 oracle-match gains, 2 oracle-match losses, and 4
  unchanged rows. The aggregate planning-regret CI is
  `[-0.42500000000000004, 0.125]`, so planning benefit is still not
  confidence-bounded. The second floor4 run reproduced the same action-row
  pattern as the first, so next planning work should expand the deterministic
  trust/commitment corpus or obtain non-identical repeated live Tau behavior
  before upgrading planning claims. Production retry-service proof also remains
  open. Provider/video and semantic dream quality remain outside the current
  critical path.
- 2026-07-21 (PCTOM-R FLOOR4 TRUST/COMMIT LIVE TAU REPLICATION): focused
  trust/commitment live Tau replication evidence now exists at
  `/tmp/persona-dream-live-tau-trust-commit-replication-floor4-20260721T101929Z/live_tau_trust_commit_replication_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION` with
  `mocked:false`, `live:true`, `live_tau_reexecuted:true`, 4 trust/commitment
  episodes, 16 M/R/D/CD Tau calls, 16 sealed/scored cases, and 16 constrained
  action decisions. The run reached the existing action-selection floor that
  blocked the one-episode smoke attempt. CD had a negative planning-regret
  point estimate versus the strongest baseline (`-0.15000000000000002`) with 2
  action switches, 1 oracle-match gain, 1 oracle-match loss, and 2 unchanged
  rows, but the bootstrap planning-regret CI
  `[-0.6375000000000001, 0.1875]` crosses zero. This is accepted floor
  evidence, not confidence-bounded planning-benefit proof. Next PCTOM-R work
  should add repeated live Tau seeds, expand the deterministic
  trust/commitment corpus beyond the current variants, or prove production
  retry-service behavior. Do not reactivate provider/video or semantic dream
  quality as the critical path.
- 2026-07-21 (PCTOM-R FULL64 LIVE TAU ACTION-POLICY SENSITIVITY): live Tau
  full64 action-policy sensitivity evidence now exists at
  `/tmp/persona-dream-live-tau-full64-action-policy-sensitivity-20260721T094805Z/live_tau_full64_action_policy_sensitivity_receipt.v1.json`.
  It consumes the accepted full64 live Tau sealed-test root and full64 planning
  diagnostic receipt without reexecuting Tau and reports
  `PASS_LIVE_TAU_PCTOM_FULL64_ACTION_POLICY_SENSITIVITY`. Counts: 64 episodes,
  4 action switches, 4 nonzero planning-regret deltas, all 4 nonzero deltas in
  `trust-commit`, 3 oracle-match gains, 1 oracle-match loss, and net oracle
  match gain 2. The sensitivity conclusion is
  `REALIZED_ACTION_SWITCH_EXPLAINS_SPARSE_PLANNING_SIGNAL`: CD changed action
  only on the four nonzero trust/commitment cases, selecting
  `ASK_CLARIFYING_QUESTION` instead of the baseline `SET_BOUNDARY`; three
  switches matched the simulator oracle and one did not. Per-action
  deterministic utility surfaces were present for the compared selected and
  oracle actions. `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_reexecuted:false`, `human_content_judgment_required:false`, and
  Tau/Memory/provider/canonical/identity/source-memory write or call attempts
  were all 0. This explains the sparse planning point estimate at the action
  policy level, but it still does not prove confidence-bounded planning-regret
  benefit, repeated-seed planning benefit, production retry machinery, live
  Memory recall inside the sealed-test loop, paid provider execution, semantic
  dream quality, or complete Phase 01-16 runtime execution. The next planning
  evidence should repeat or expand trust/commitment episodes before upgrading
  planning benefit.
- 2026-07-21 (PCTOM-R FULL64 LIVE TAU PLANNING DIAGNOSTIC): live Tau full64
  planning diagnostic evidence now exists at
  `/tmp/persona-dream-live-tau-full64-planning-diagnostic-20260721T093504Z/live_tau_full64_planning_diagnostic_receipt.v1.json`.
  It consumes the accepted full64 live Tau sealed-test root and full64
  statistical-confidence receipt without reexecuting Tau and reports
  `PASS_LIVE_TAU_PCTOM_FULL64_PLANNING_DIAGNOSTIC`. Counts: 64 planning rows,
  60 ties, 3 beneficial deltas, 1 harmful delta, and 4 nonzero deltas. The
  planning-regret CI is `[-0.08515625000000002, 0.00390625]`, so it crosses
  zero. The diagnostic conclusion is `SPARSE_FAMILY_CONCENTRATED_SIGNAL`: all
  nonzero deltas are in the `trust-commit` family. Three `trust-commit`
  episodes improved when CD selected `ASK_CLARIFYING_QUESTION` instead of the
  baseline `SET_BOUNDARY`; one `trust-commit` episode was worse for that same
  CD action. `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_reexecuted:false`, `human_content_judgment_required:false`, and
  Tau/Memory/provider/canonical/identity/source-memory write or call attempts
  were all 0. This explains why the full64 planning point estimate cannot be
  upgraded to a planning-benefit claim: the signal is sparse and
  family-concentrated. The later action-policy sensitivity receipt explains
  the sparse action-switch mechanism; the next planning evidence would need
  repeated seeds or more trust/commitment episodes.
- 2026-07-21 (PCTOM-R FULL64 LIVE TAU STATISTICAL CONFIDENCE): live Tau
  full64 statistical-confidence evidence now exists at
  `/tmp/persona-dream-live-tau-full64-statistical-confidence-20260721T092609Z/live_tau_full64_statistical_confidence_receipt.v1.json`.
  It consumes the accepted full64 live Tau sealed-test replication root without
  reexecuting Tau and reports
  `PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE`. Counts: 64 episodes,
  256 cases, 64 paired deltas each for belief Brier, action Brier, and
  planning regret, and 10,000 bootstrap samples. The preregistered belief
  Brier CD-minus-strongest-baseline mean is `-0.018301562500000004` with
  95% bootstrap CI `[-0.029314882812500002, -0.008604609375000004]`, so
  `primary_benefit_with_confidence:true`. Action Brier and planning regret do
  not have confidence-bounded benefit: `action_benefit_with_confidence:false`
  and `planning_benefit_with_confidence:false` because their CI uppers cross
  zero. `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_reexecuted:false`, `human_content_judgment_required:false`, and
  Tau/Memory/provider/canonical/identity/source-memory write or call attempts
  were all 0. This proves the live Tau full64 primary ToM prediction benefit
  on belief Brier, not planning-regret benefit, production retry machinery,
  live Memory recall in the sealed-test loop, paid provider execution,
  semantic dream quality, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R FULL64 LIVE TAU RETRY PROOF): bounded retry/fault
  evidence over the full64 live Tau sealed-test root now exists at
  `/tmp/persona-dream-live-tau-full64-sealed-test-retry-proof-20260721T092754Z/live_tau_sealed_test_retry_proof_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF` while consuming the
  full64 replication receipt without reexecuting Tau. Counts: 256 active
  predictions, 256 action decisions, 256 Gate 6 receipts, 8 retry/fault trials,
  3 recovered trials, 3 blocked-before-side-effect trials, 2 quarantined
  trials, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect violations, 2
  duplicate active-prediction attempts detected and rejected, and 0 duplicate
  action decisions promoted. Checks show `base_is_full64_live_tau:true`,
  `commitment_hashes_recomputed:true`, `active_predictions_unique:true`,
  `action_decisions_unique:true`, `predictions_have_actions:true`, and
  `causal_replay_written:true`. `mocked:false`, `live:true`,
  `fixture_backed:false`, `live_tau_reexecuted:false`,
  `human_content_judgment_required:false`, and Tau/Memory/provider/canonical/
  identity/source-memory write or call attempts were all 0. This proves bounded
  retry/idempotence over full64 live-originated sealed-test artifacts. It does
  not prove deployed production orchestrator retry machinery, new live Tau
  execution, live Memory service fault injection, paid provider execution,
  semantic dream quality, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R FULL64 LIVE TAU SEALED-TEST REPLICATION): full
  64-episode live Tau sealed-test replication evidence now exists at
  `/tmp/persona-dream-live-tau-sealed-test-replication-full64-20260721T055039Z/live_tau_sealed_test_replication_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION` on split
  `sealed_test` with `full_64_episode_replication:true`, 4 scenario families,
  64 episodes, 256 condition cases, 256 Tau call attempts, and 256 live Tau
  calls. Counts per condition are
  `tau_authored_prediction_payloads_per_condition: M=64, R=64, D=64, CD=64`,
  `sealed_commitments_per_condition: M=64, R=64, D=64, CD=64`,
  `deterministic_scores_per_condition: M=64, R=64, D=64, CD=64`,
  `action_decisions_per_condition: M=64, R=64, D=64, CD=64`, and
  `planning_regret_scores_per_condition: M=64, R=64, D=64, CD=64`.
  CD improved the strongest baseline in the full64 point estimates:
  belief Brier `-0.01830156249999998`, action Brier
  `-0.0008531250000000101`, and planning regret
  `-0.03593750000000001`. `mocked:false`, `live:true`,
  `fixture_backed:false`, `llm_judge_used:false`,
  `human_content_judgment_required:false`, and Memory/provider/canonical/
  identity/source-memory write attempts were all 0. This proves full64 live
  Tau sealed-test execution through sealed commitments, deterministic scoring,
  and constrained action selection. It does not prove statistical confidence
  for the live Tau CD benefit point estimates, production retry machinery over
  the full64 root, live Memory service fault injection in the same loop, paid
  provider execution, semantic dream quality, or complete Phase 01-16 runtime
  execution. The next critical path is a receipt-backed statistical-confidence
  analysis over this full64 live Tau root or retry/fault proof consuming this
  root, not another provider/video run or vague GitHub status update.
- 2026-07-21 (PCTOM-R BOUNDED QUEUE-WORKER RETRY PROOF): bounded local
  queue-worker retry/fault evidence now exists at
  `/tmp/persona-dream-live-tau-sealed-test-queue-worker-retry-proof-20260721T054051Z/live_tau_sealed_test_queue_worker_retry_proof_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_QUEUE_WORKER_RETRY_PROOF` while starting a
  separate worker process over a filesystem queue. Counts: 4 queued jobs, 4
  job results, 1 worker process, worker exit code 0, 2 completed jobs, 2
  blocked jobs, 0 quarantined jobs, 16 active predictions, 16 action decisions,
  16 Gate 6 receipts, 8 child retry/fault trials, 1 retry-after-uncertain-
  completion trial, 1 interrupted-persistence trial, 1 conflicting-active-
  pointer trial, 1 causal replay receipt, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0
  side-effect violations, and 0 promoted duplicate active predictions/actions.
  The worker recovered equivalent active state for exact retry and uncertain-
  completion retry jobs, blocked missing-base-root and interrupted-persistence
  jobs, and preserved the recovered/blocked terminal-outcome discipline of the
  sealed-test retry proof. `mocked:false`, `live:true`,
  `fixture_backed:false`, `always_on_external_service:false`,
  `live_tau_reexecuted:false`, `human_content_judgment_required:false`, and
  Memory/provider/canonical/identity/source-memory write attempts were all 0.
  This proves a bounded local queue-worker process over live-originated
  sealed-test artifacts. It does not prove a permanently deployed always-on
  production service, full 64-episode live Tau sealed-test replication, new
  live Tau execution, live Memory service fault injection, paid provider
  execution, semantic dream quality, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R RUN.SH ORCHESTRATION RETRY PROOF): local command-dispatch
  retry/fault evidence now exists at
  `/tmp/persona-dream-live-tau-sealed-test-runsh-orchestration-retry-proof-20260721T053400Z/live_tau_sealed_test_runsh_orchestration_retry_proof_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_RUNSH_ORCHESTRATION_RETRY_PROOF` while
  exercising `skills/persona-dream/run.sh` as the orchestration boundary.
  Counts: 4 run.sh invocations, 2 successful invocations, 2 blocked
  invocations, 16 active predictions, 16 action decisions, 16 Gate 6 receipts,
  8 child retry/fault trials, 1 retry-after-uncertain-completion trial, 1
  interrupted-persistence trial, 1 conflicting-active-pointer trial, 1 causal
  replay receipt, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect violations,
  0 duplicate active predictions promoted, and 0 duplicate action decisions
  promoted. The exact retry and retry-after-uncertain-completion run.sh
  invocations recovered equivalent active state; missing base root returned a
  fail-closed blocked child receipt; output-root-as-file interrupted persistence
  exited nonzero before active-state promotion. `mocked:false`, `live:true`,
  `fixture_backed:false`, `live_tau_reexecuted:false`,
  `human_content_judgment_required:false`, and Memory/provider/canonical/
  identity/source-memory write attempts were all 0. This proves local run.sh
  command-dispatch retry discipline over live-originated sealed-test artifacts.
  It does not prove an always-on external production service or queue worker,
  full 64-episode live Tau sealed-test replication, new live Tau execution,
  live Memory service fault injection, paid provider execution, semantic dream
  quality, or complete Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R BOUNDED LIVE TAU SEALED-TEST RETRY PROOF): bounded
  retry/idempotence evidence over live Tau-originated sealed-test artifacts now
  exists at
  `/tmp/persona-dream-live-tau-sealed-test-retry-proof-20260721T052430Z/live_tau_sealed_test_retry_proof_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_SEALED_TEST_RETRY_PROOF` while consuming the
  bounded live Tau sealed-test replication receipt
  (`sha256:c066eabd3d5a1a08f4a426cdd7347f91e969998795872d4d2e7e773b84f94087`).
  Counts: 16 active predictions, 16 action decisions, 16 Gate 6 receipts, 8
  retry/fault trials, 3 recovered trials, 3 blocked-before-side-effect trials,
  2 quarantined trials, 0 `CONTINUED_WITH_UNKNOWN_STATE`, 0 side-effect
  violations, 2 duplicate active-prediction attempts detected and rejected, and
  0 duplicate action decisions promoted. The runner recomputes prediction
  payload, model receipt, and evidence bundle hashes before indexing active
  state, proves exact retry and retry-after-uncertain-completion recover to an
  equivalent state, blocks/quarantines partial Tau output, stale scoring,
  interrupted action selection, and conflicting active pointers, and writes one
  causal replay for the conflicting active-prediction pointer boundary.
  `mocked:false`, `live:true`, `fixture_backed:false`,
  `live_tau_originated_artifacts_consumed:true`,
  `live_tau_reexecuted:false`, `controlled_retry_faults_used:true`,
  `human_content_judgment_required:false`, and Memory/provider/canonical/
  identity/source-memory write attempts were all 0. This proves bounded
  retry/idempotence over live-originated sealed-test artifacts. It does not
  prove deployed production orchestrator retry machinery, full 64-episode live
  Tau sealed-test replication, new live Tau execution, live Memory service
  fault injection, paid provider execution, semantic dream quality, or complete
  Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R BOUNDED LIVE TAU SEALED-TEST REPLICATION): bounded live
  Tau sealed-test replication evidence now exists at
  `/tmp/persona-dream-live-tau-sealed-test-replication-20260721T045807Z/live_tau_sealed_test_replication_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION` on split
  `sealed_test` with 4 episodes, 4 scenario families, 16 Tau calls, and 16
  live Tau calls. Counts per condition are
  `tau_authored_prediction_payloads_per_condition: M=4, R=4, D=4, CD=4`,
  `sealed_commitments_per_condition: M=4, R=4, D=4, CD=4`,
  `deterministic_scores_per_condition: M=4, R=4, D=4, CD=4`,
  `action_decisions_per_condition: M=4, R=4, D=4, CD=4`, and
  `planning_regret_scores_per_condition: M=4, R=4, D=4, CD=4`. The run used
  live Tau-authored prediction payloads, sealed them before deterministic
  reveal, scored them with Gate 5, and fed them into constrained Gate 6 action
  selection. It produced a null benefit signal: CD-minus-strongest-baseline was
  `0.0` for belief Brier, action Brier, and planning regret. `mocked:false`,
  `live:true`, `fixture_backed:false`, `llm_judge_used:false`,
  `human_content_judgment_required:false`, and Memory/provider/canonical/
  identity/source-memory write attempts were all 0. This proves bounded live
  Tau sealed-test plumbing and scoring, not full 64-episode live Tau
  replication, statistical confidence for live Tau CD benefit, production
  retry machinery, full Phase 01-16 runtime, paid provider execution, or
  semantic dream quality.
- 2026-07-21 (PCTOM-R LIVE FAULT-INJECTION SURFACE): broader fault-containment
  evidence now exists at
  `/tmp/persona-dream-live-fault-injection-surface-20260721T044950Z/live_fault_injection_surface_receipt.v1.json`.
  It reports `PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE` while consuming the
  deterministic sealed-test statistical-confidence receipt and the live Memory
  revision-recall receipt. Counts: 8 fault families, 8 fault trials, 4 live
  Memory fault probes, and 1 causal replay receipt. The fault families are
  `memory_timeout_or_unreachable`, `memory_malformed_payload`,
  `memory_collection_visibility_or_stale_recall`,
  `model_malformed_structured_output`, `schema_drift`,
  `interrupted_persistence`, `retry_after_uncertain_completion`, and
  `untrusted_tool_text`. Terminal outcomes were constrained to
  `BLOCKED_BEFORE_SIDE_EFFECT`,
  `QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE`, or
  `RECOVERED_WITH_EQUIVALENT_END_STATE`; `continued_with_unknown_state: 0`,
  `side_effect_violations: 0`, and canonical/source/identity/provider/Tau
  write or call attempts were all 0. This proves live Memory /recall fault
  probes plus controlled local model/tool/schema/persistence/retry fault
  containment over hash-bound PCTOM-R predecessor receipts. It does not prove
  live Tau sealed-test execution, production retry machinery inside a deployed
  orchestrator, paid provider execution, video/audio quality, semantic dream
  quality, or complete live Phase 01-16 runtime execution.
- 2026-07-21 (PCTOM-R HELD-OUT CONDITION BENEFIT): frozen held-out
  condition-benefit evidence now exists at
  `/tmp/persona-dream-heldout-condition-benefit-final-20260721T041000Z/heldout_condition_benefit_receipt.v1.json`.
  It reports `PASS_PCTOM_HELDOUT_CONDITION_BENEFIT` on split
  `explicitly_frozen_heldout` with `generated_at: 2026-07-21T00:00:00Z`.
  The run consumed 24 deterministic simulator episodes across 4 families and
  wrote 96 condition cases. Counts per condition are
  `sealed_commitments_per_condition: M=24, R=24, D=24, CD=24`,
  `deterministic_scores_per_condition: M=24, R=24, D=24, CD=24`, and
  `action_decisions_per_condition: M=24, R=24, D=24, CD=24`. The
  preregistered primary proper score is `mean_belief_brier`; CD scored
  `0.14000000000000004` versus strongest baseline D at `0.2198`, so
  `cd_minus_strongest_baseline=-0.07979999999999995` and
  `benefit_observed: true` for this deterministic held-out ToM score. Planning
  regret did not improve over the strongest baseline: CD tied D with
  `cd_minus_strongest_baseline=0.0`. The oracle policy source is
  `deterministic_simulator_policy.v1`; `llm_judge_used:false`,
  `human_content_judgment_required:false`, `mocked:false`, `live:false`,
  `fixture_backed:false`, and Tau/Memory/provider/canonical/identity/
  source-memory attempts are all 0. This proves a deterministic frozen
  held-out artifact with sealed commitments, deterministic scores, and action
  decisions; it does not prove live Tau held-out execution, live Memory recall
  after revision, real external service fault injection, production retry
  machinery, 64-episode statistical confidence intervals, planning-regret
  benefit, complete Phase 01-16 runtime, paid provider execution, video
  quality, or semantic dream quality.
- 2026-07-21 (PCTOM-R REVISION RECALL): action-linked revision artifacts now
  have deterministic longitudinal recall/use evidence with receipt
  `/tmp/persona-dream-live-tau-revision-recall-20260721T035640Z/live_tau_revision_recall_receipt.v1.json`.
  It consumes the live Tau action-linked revision receipt
  `/tmp/persona-dream-live-tau-action-linked-revision-20260721T034916Z/live_tau_action_linked_revision_receipt.v1.json`
  (`sha256:2f642fe5cb41a23f762a870356bea62b8eb7c3d37d9f3d47e05c9dbbe4166ebe`),
  builds 16 deterministic recall documents, runs 4 condition-scoped recall
  queries, and returns 16 hits. It reports `prior_and_posterior_distinguished:
  true`, `synthetic_literal_boundary_preserved: true`, and `write_violations:
  0`, with Tau/Memory/provider/canonical/identity/source-memory attempts all
  0. This is deterministic artifact recall over live-originated revision
  artifacts, not live Memory recall after revision. It also does not prove
  held-out statistical benefit, planning benefit over the strongest baseline,
  real external fault injection, production retry proof, complete Phase 01-16
  runtime, paid provider execution, video quality, or semantic dream quality.
- 2026-07-21 (PCTOM-R ACTION-LINKED REVISION): live-originated Gate 6 action
  decisions now feed strict Gate 7 non-destructive belief revisions with
  receipt
  `/tmp/persona-dream-live-tau-action-linked-revision-20260721T034916Z/live_tau_action_linked_revision_receipt.v1.json`.
  It consumes the live Tau condition action-selection receipt
  `/tmp/persona-dream-live-tau-condition-action-selection-20260721T034126Z/live_tau_condition_action_selection_receipt.v1.json`
  (`sha256:95521d5fa8171e96b0466df8015ddf9f7154144d1e959eb490322ad1d479861e`),
  writes 16 strict `tom_belief_revision.v1` records, and reports 16
  `PASS_TOM_BELIEF_REVISION` checks. Counts per condition are
  `prior_action_hypotheses_per_condition: M=4, R=4, D=4, CD=4` and
  `posterior_action_revisions_per_condition: M=4, R=4, D=4, CD=4`.
  The strict revision records keep action linkage outside the revision schema,
  preserve the sealed prior as auditable, update current-use posterior
  distributions from deterministic outcome evidence, mutate no evidence, and
  attempt zero Tau/Memory/provider/canonical/identity/source-memory writes.
  This is action-linked Gate 7 instrumentation over live-originated artifacts;
  it is not longitudinal recall after revision, held-out statistical benefit,
  real external fault injection, production retry proof, complete Phase 01-16
  runtime, paid provider execution, video quality, or semantic dream quality.
- 2026-07-21 (PCTOM-R CONDITION ACTION SELECTION): repeated live Tau condition
  outputs now feed Gate 6 constrained action selection with receipt
  `/tmp/persona-dream-live-tau-condition-action-selection-20260721T034126Z/live_tau_condition_action_selection_receipt.v1.json`.
  It consumes the repeated live Tau M/R/D/CD comparison receipt
  `/tmp/persona-dream-live-tau-condition-comparison-20260721T030825Z/live_tau_condition_comparison_receipt.v1.json`
  (`sha256:15254b5b5cd47c89d6c0ca538a838dee754a438256f743d1e27a62645dae9168`),
  writes 16 Gate 6 action cases, and reports 4 action decisions plus 4
  deterministic reward/regret scores for each condition (`M`, `R`, `D`, `CD`).
  The action vocabulary is the constrained PCTOM-R set:
  `ASK_CLARIFYING_QUESTION`, `WAIT`, `DISCLOSE_INFORMATION`,
  `OFFER_COOPERATION`, `SET_BOUNDARY`, `ACT_INDEPENDENTLY`, and `ABSTAIN`.
  The oracle policy source is deterministic simulator policy, `llm_judge_used:
  false`, `human_content_judgment_required: false`, and Tau/Memory/provider/
  canonical/identity/source-memory attempts are all 0 for the bridge itself.
  Mean planning regret is 0.0 for all four conditions in this bounded
  calibration subset because each Tau top action mapped to the deterministic
  oracle action. This is Gate 6 live-originated planning instrumentation, not a
  held-out planning-benefit claim, real external fault injection, production
  retry proof, longitudinal recall, complete Phase 01-16 runtime, paid provider
  execution, video quality, or semantic dream quality.
- 2026-07-21 (PCTOM-R CONDITION RELIABILITY): controlled Gate 8/9 reliability
  over repeated live condition artifacts now has receipt
  `/tmp/persona-dream-live-tau-condition-reliability-20260721T032659Z/live_tau_condition_reliability_bridge_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE`, consumes base
  receipt `/tmp/persona-dream-live-tau-condition-comparison-20260721T030825Z/live_tau_condition_comparison_receipt.v1.json`
  (`sha256:15254b5b5cd47c89d6c0ca538a838dee754a438256f743d1e27a62645dae9168`),
  covers fault families `stale_artifact`, `missing_graph_edge`,
  `malformed_structured_output`, and `interrupted_persistence_or_retry`, and
  has `continued_with_unknown_state: 0`. Gate 8 accepted 7 trials with
  `fault_containment_rate: 1.0`; Gate 9 localized a stale-artifact divergence
  with one replacement tool return. No Tau, Memory, provider, canonical,
  identity, or source-memory writes were attempted. This is controlled local
  artifact fault evidence over live-originated artifacts, not real external
  service fault injection or production retry machinery. Next critical path is
  planning-relevant action selection/regret over Tau-authored condition outputs.
- 2026-07-21 (PCTOM-R REPEATED LIVE TAU CONDITION COMPARISON): the next
  repeated live condition artifact is
  `/tmp/persona-dream-live-tau-condition-comparison-20260721T030825Z/live_tau_condition_comparison_receipt.v1.json`.
  It reports `PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON`, 16 Tau call attempts,
  16 live Tau calls, 4 calibration episodes consumed across 4 scenario families,
  4 sealed commitments and 4 deterministic Gate 5 scores per condition, and
  zero Memory/provider/canonical/identity/source-memory writes. Gate counts:
  16 PASS each for Gate 2, Gate 3, Gate 4, and Gate 5. The bounded calibration
  subset had CD mean action Brier 0.61265 versus strongest baseline M
  0.6534 (`cd_minus_strongest_baseline=-0.04075`), but this is not a held-out
  statistical claim. Next critical path is condition-runner reliability:
  controlled artifact faults, retry boundaries, and causal replay over the live
  condition artifacts with no `CONTINUED_WITH_UNKNOWN_STATE`.
- 2026-07-21 (PCTOM-R LIVE TAU CONDITION COMPARISON): the text-first
  condition lane now has a live Tau-authored M/R/D/CD comparison receipt:
  `/tmp/persona-dream-live-tau-condition-comparison-20260721T030038Z/live_tau_condition_comparison_receipt.v1.json`
  reports `PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON`, 4 Tau call attempts, 4
  live Tau calls, 1 sealed commitment and 1 deterministic Gate 5 score per
  condition, and zero Memory/provider/canonical/identity/source-memory writes.
  This proves bounded live condition instrumentation only; it does not prove
  held-out benefit, statistical calibration, action regret, production retry,
  longitudinal recall, Phase 01-16, paid provider, video, or semantic dream
  quality. First-run repair lesson:
  `/tmp/persona-dream-live-tau-condition-comparison-20260721T025653Z/live_tau_condition_comparison_receipt.v1.json`
  correctly failed because the reveal timestamp equaled `sealed_at` and one
  Tau R output put a `synthetic_counterfactual` ref in branch source refs /
  prediction evidence refs. The runner now sets reveal time to `sealed_at + 1s`
  and the prompt contract forbids synthetic refs in visible-ref fields.
- 2026-07-19 (WEEKS-1-2 INTEGRITY FIXES, accepted external re-review — 6 defects
  closed): cognitive-loop correctness + lineage hardening. (1) The interpretation
  guard no longer self-compares — `run_cognitive_loop` binds the INDEPENDENTLY
  computed observation-packet file hash (`p13.file_sha`), so a tampered
  `observation_packet_sha256` field fails and the genuine chain passes. (2)
  freeze-old/namespace-new: dream-004's 26 raw-key canonical records are FROZEN
  (`reports/pipeline-complete/.persona-dream/legacy_key_format_receipt.v1.json`
  names them all); NEW canonical writes use `dream:<persona_id>:<dream_id>[:watch|
  :interpretation|:tom]:<id>`. (3) phase14 emits distinct ToM statuses
  (LIVE / DETERMINISTIC_PROJECTION / DEGRADED_TOM_LIVE_ROUTE_FALLBACK); the guard
  accepts the PASS forms and needs an explicit waiver for the degraded fallback.
  (4) phase15 materializes `persona_dream_interpretations` vertices + the
  observation→interpretation→tom ladder, preserving dream-level edges. (5) all
  embry/kai/surf strings live in one cognition contract fixture
  (`fixtures/persona_dream_cognition_contract.embry_kai_surf.v1.json`, schema
  `contracts/persona_dream_cognition_contract.v1.schema.json`); phase 13/14/16 are
  grep-clean. (6) every NEW write-set record carries the causal-family lineage
  fields (`root_event_ids`/`causal_family_id`/`synthetic_depth`/`derivation_depth`/
  `independent_evidence_count`/`commit_id`/`visibility_state=pending`) shared with
  the GMO agent. Proof: `./run.sh test-suite` 403 passed (x2); live dry-run
  reached PASS_SELF_INTERPRETATION + PASS_TOM_VALIDATION_LIVE + DRY_RUN plan with
  namespaced keys; governance `persona_dream_governance_weeks12_integrity_20260719`
  reread-exact.
- 2026-07-19 (P1 TAU-ROUTING TEMPORARY_DEBT PAID, 23 → 0): the "only /tau may
  reach /scillm" boundary is fully clean. `check_tau_routing_boundary.py --strict`
  exits 0 and `sanity.sh` now runs it in `--strict` mode (the ratchet is the gate).
  8 callers migrated to the sanctioned Tau adapters (text →
  `tau_text_reasoning_adapter`, which is JSON-object-only so free-text callers wrap
  as `{"...": "..."}`; image/VLM → `tau_vlm_review_adapter`, and multi-image
  identity/continuity reviews via the new persona-dream-side glue
  `scripts/tau_vlm_composite_review.py` that composites frame + reference sheets
  into ONE labeled montage for the single-image Tau panel node — NOT a new Tau node,
  since work is scoped to agent-skills-main). watch's `qra._scillm_chat_completion`
  routes text+image through Tau; its Whisper transcription is already local (no
  scillm audio). 2 diagnostics permanently allowlisted (health probe, loopback
  transport-contract proof); 11 rung-ladder transport experiments retired (receipt
  `reports/pipeline-complete/.persona-dream/rung_ladder_retirement_receipt.v1.json`).
  Live-proven: 4 Tau routes at HTTP-200 (no paid provider),
  `reports/pipeline-complete/.persona-dream/tau_live_receipts/`. Suites: persona-dream
  388 passed, watch 45 passed. Governance: `persona_dream_governance/tau_routing_debt_paydown_20260719`.
- 2026-07-19 (P0 OBSERVATION PACKET v2 — ONE PACKET, ONE AUTHORITY): the two
  incompatible phase-12 observation notions (scene-driven
  `watch_gauntlet_observation_packet.v1` vs fixed-lane
  `dream_observation_packet.v1`) are unified by an evidence-only successor schema
  `schemas/dream_observation_packet.v2.schema.json`: typed independently-optional
  modules, **no silent-video assumption, no fixed frame count, psychological
  interpretation FORBIDDEN** (const-false flag + a deterministic psychology
  filter that strips inferred emotion/mood/intent from VLM text and records what
  it removed). `scripts/build_observation_packet_v2.py` assembled the single
  **ACCEPTED** successor packet
  (`watch_gauntlet/59b9ff3155d6/dream_observation_packet.v2.json`, supersedes the
  DEGRADED v1 by hash `sha256:5229c664…`, v1 retained + marked superseded by a
  sidecar): **live** per-frame visible entities over 12/12 frames via the
  sanctioned Tau **panel-reviewer VLM** route (`tau_vlm_review_adapter.py`, 12
  receipts all HTTP 200, no direct scillm), a **full-clip local Whisper
  large-v3-turbo** transcript (exact Kai line recognized), and the authoritative
  ArcFace + step-36/37/38 adjudications folded by reference+hash. **Durable
  lessons:** (1) *the sanctioned Tau panel-reviewer VLM function already carries a
  per-frame image + free-text prompt* — the "frame-shaped Tau VLM node still to be
  added" was not needed for evidence-only per-frame description. (2) *enrichment is
  not a rewrite* — all 7 read-only `persona_dream_watch_evidence` vertices remain
  representable (`CONSISTENT_WITH_ADDITIVE_ENRICHMENT`); the delta where v2 now
  carries evidence a vertex marked "unavailable" is recorded additively, never by
  editing the canonical vertex. Governance:
  `persona_dream_governance/persona_dream_observation_packet_v2_20260719` (exact
  reread PASS). 12 deterministic tests + the live run (fixture-only is not
  acceptance).

- 2026-07-19 (P1 TAU-ONLY MODEL-ROUTING BOUNDARY — enforced): the operator rule
  *only /tau may reach /scillm* is now a **deterministic static gate**
  (`scripts/check_tau_routing_boundary.py`), not a convention. It scans
  `skills/persona-dream` + `skills/watch` for direct scillm proxy calls and fails
  on any un-sanctioned one; it is wired into `run.sh check-tau-routing-boundary`,
  `sanity.sh`, and `run.sh test-suite` (via `tests/test_tau_routing_boundary.py`).
  **Durable lesson:** *a routing rule that isn't statically checked is not enforced*
  — 23 pre-existing direct-scillm callers existed despite the standing rule; they
  are now enrolled as `TEMPORARY_DEBT` (the authoritative migration backlog) so no
  NEW violation can land silently. Sanctioned routes: text/QRA →
  `tau_text_reasoning_adapter.py` (verified live, HTTP 200, no paid call); image/VLM
  → `persona_dream_panel_agent` panel-reviewer or a frame-shaped Tau VLM node still
  to be added (the text node cannot carry images or free-text). Migrating watch
  VLM/QRA + lane_c image review is deferred pending that VLM node.

- 2026-07-19 (P0 CORRECTNESS BUNDLE — Sol Pro review, closed): three verified
  cognitive-loop defects fixed. **Lessons (durable):** (1) *presence of a proof
  object is not proof* — `canonical_dream_memory_written = bool(canonical_write_proof)`
  certified nothing; it now requires staging AND publish AND commit-manifest to all
  reread-match, else `BLOCKED_CANONICAL_PERSISTENCE_INCOMPLETE` + nonzero exit.
  (2) *edges are not vertices* — the committed "14/14 traversal" proved 14 EDGES
  resolved, not that the 7 Watch-observation VERTICES existed (they didn't); phase16
  traversal is now STRICT (every edge target, including `persona_dream_watch_evidence`
  vertices, must resolve or traversal FAILS) and the old claim is corrected via
  `corrected_traversal_receipt.v1.json` (old kept, marked superseded). (3) *loops
  need typed transitions* — `scripts/cognitive_loop_transitions.py` is a 5-state
  machine (`ACCEPTED_OBSERVATION→PASS_INTERPRETATION→PASS_TOM_VALIDATION→
  STAGED_PERSISTENCE_VERIFIED→CANONICAL_COMMIT`) that hash-binds each predecessor
  (phase14 binds exact phase13; commit binds exact 13+14) and hard-stops the loop on
  any structural blocker before the next side effect; the aggregate no longer accepts
  a bare `DEGRADED*` status. phase15 is now transactional (idempotency key → stage →
  verify → publish → verify → commit manifest as the single source of canonical
  visibility; retain-and-mark since the `$memory` API has no delete primitive;
  detect-and-quarantine on rerun). Watch-evidence vertices are materialized
  (`synthetic_origin=true`, `psychological_interpretation_performed=false`). The live
  dream `dream_dream_successor_943b01ecd9a3` (19 records) was reconciled ADDITIVELY —
  7/7 Watch vertices materialized, retroactive commit manifest written, strict
  traversal re-run PASS — with the 19 pre-existing records re-read live but NEVER
  rewritten. A 4th lesson: a lossless daemon numeric round-trip (`0.0→0`) is not
  corruption — normalize numbers in the reread-fidelity hash only, never in the
  artifact-binding hash. Governance:
  `persona_dream_governance/persona_dream_p0_correctness_governance_20260719`
  (exact reread PASS). 54/54 lane tests green.

- 2026-07-19 (GREEN_CANONICAL_LANE — CI contract reconciliation): the default test
  suite went from 29 failed / 313 passed to **0 failed / 342 passed / 0 skipped**,
  stable across two runs, reproducible via the new `./run.sh test-suite` (also wired
  into `sanity.sh` as a CI guard). The root cause was **incomplete vendoring** of the
  b68bf3d1 (2026-07-11) one-scene dry-run pipeline harness into `skills/persona-dream/`
  — not obsolete-lane bit-rot — so the decision was **RESTORE, not retire** (no
  retirement receipt). Three restores + one expectation fix: (1) authored the
  never-committed `schemas/kling_scene_packet.schema.json` (Draft 2020-12, faithful to
  the one-scene fixture; value gates stay in the Python validators, not const-pinned);
  (2) recreated the omitted fixture PNG `fixtures/one_scene_kling_dry_run/artifacts/panel_001_reference.png`
  and re-locked its sha256 in two receipts; (3) fixed the work-order writers' relocated
  agent-contract path (`REPO = ROOT.parents[1]` → skill-owned `agents/`) and created
  five real subagent contracts (dreamer, memory, panel-repair-gate, panel-creator,
  panel-reviewer); (4) updated `test_run_sh_read` to the current PROJECT_KNOWLEDGE
  header. `MANIFEST.json` is a SHA-256 patch-bundle manifest (34 files, 8 schemas)
  verified by `scripts/verify_manifest.py` — resynced deterministically (only the kling
  schema entry drifted, 4704→4108 bytes; now passes). `kling.scene_packet.v1` has no
  phase-11 successor (`phase11_live_request.v1` never references `scene_packet`), and
  the affected test files are partially-live, so retirement would have suppressed green
  coverage. No revision/rung/qualification gate weakened; no assertion deleted. Receipt:
  `reports/pipeline-complete/.persona-dream/state/green_canonical_lane_reconciliation_receipt.v1.json`;
  memory `persona_dream:pipeline-complete:green_canonical_lane_ci_contract_reconciliation`
  (`persona_dream_governance`, exact reread PASS).

- 2026-07-18 (Phase 16 — Recall and Behavior Evaluation, the completion boundary):
  the founding experiment's machine-decidable acceptance boundary is now CLOSED.
  `scripts/phase16_behavior_evaluation.py` returns `overall_status: PASS` for all five
  probes against the canonical dream `persona_memory/dream_dream_successor_943b01ecd9a3`,
  routing every LLM probe through the Tau text node (no direct scillm), with deterministic
  code post-checks. Receipt: `.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json`.
  (a) Semantic recall returns the dream from 3 differently-worded queries (ranks 1/3/7;
  dense 0.593/0.432/0.736) while an `orbital telemetry` negative control excludes it — proof
  that recall is discriminating, not returning everything. (b) Multi-hop traversal resolves all
  14 canonical edges live to 3 source memories + 7 Watch observations + 4 ToM nodes (actual
  vertex/edge keys recorded). (c) With context assembled ONLY from live `/recall`, the persona
  uses the dream and marks it as a dream. (d) It denies literal occurrence and the
  `synthetic_origin=true`/`literal_historical_event=false` flags reread exactly. (e) Identity is
  stable: the dream loop's canonical write-set is dream+edges+ToM only (it never wrote/updated an
  identity or source record), source anchors reread literal/unchanged, and a Tau values Q&A stays
  Kai-centered/value-stable — labeled the honest slice since no standalone Embry persona-definition
  file or runnable create-persona identity suite exists. DECISIVE LESSON: the natural "trouble at
  the water" question correctly pulls the persona to the LITERAL sick-day memory, not the dream —
  a grounded-USE-of-dream probe must ask about the dream's UNIQUE psychological content (accepting
  Kai's correction without losing autonomy), which the literal memories do not encode; otherwise
  correct persona behavior reads as a probe failure. What remains is NOT machine-decidable:
  Chatterbox voice expression (acceptance item 10) and the human's subjective acceptance of the
  rendered dream video.
- 2026-07-19 (phases 13-15 routed through Tau; FIRST canonical dream-memory write):
  the DEFERRED phase-13/14 text-reasoning blocker is resolved. At Tau commit `416edc5a`
  no general text-completion node existed (panel-reviewer is image-bound; `scillm_subagent_gate`
  is a validator; `dream_packet_agent` does no in-Tau LLM; the script-writer/reviewer command
  specs are dead pointers to unsupported roles — verified by reading their contracts). A minimal
  text-only node was added to the Tau repo (commit `09e64a44`,
  `tau_coding.persona_dream_text_reasoning_agent`, branch `issue-74-ready-queue-condition-block`):
  it carries a caller **hash-recorded prompt** + **caller-defined JSON output contract**, reuses
  panel-reviewer's scillm-key resolution (`api_key_source docker:scillm-proxy`), and emits a
  `tau.persona_dream.scillm_text_reasoning_receipt.v1` receipt (prompt/contract shas, model,
  http_status, raw output). Persona-dream's `scripts/tau_text_reasoning_adapter.py` dispatches
  phase 13/14 prompts to it by subprocess into the Tau repo — **NO direct scillm from
  persona-dream**; the deterministic citation/grounding gates are UNCHANGED (the LLM only drafts,
  code decides). **Live on the ACCEPTED successor return** (`watch_gauntlet/59b9ff3155d6/cognitive_loop/`):
  phase 13 PASS (4 interpretations, all citing Watch observation ids + source-memory ids; live
  `$memory` recall confirmed, one residue id matched), phase 14 PASS (4 ToM candidates accepted,
  subset-grounded), phase 15 `LIVE_CANONICAL_PERSISTENCE`. Phase 15 now permits a canonical write
  only when a **binding agent-level acceptance receipt** (`ACCEPTED_AGENT_LEVEL`, matching return
  video sha256 + return id, step_36 & step_38 PASS) overrides the DEGRADED observation status —
  and NEVER a historical origin, renderer DEFECT verdict, or superseded id (hard blocks, 8
  fail-closed tests). **19 canonical records** written through the `$memory` API with **exact
  reread-by-key**: the synthetic dream node `persona_memory/dream_dream_successor_943b01ecd9a3`
  (`synthetic_origin:true, literal_historical_event:false`), 4 `tom_candidates` nodes, and 3
  `derived_from` + 7 `observed_in_scene` + 4 `supports_interpretation` edges. Governance record
  (`persona_dream_governance/...:cognitive_loop_canonical_write`) + phase 13/14/15 step records
  (`persona_dream_pipeline_steps`, now `Live-Proven-On-Accepted-Return`) all exact reread. Loop
  receipt `PASS_COGNITIVE_LOOP`, `canonical_dream_memory_written: true`. Boundary: Phase 16
  (Qdrant semantic recall + downstream behavior change + human subjective acceptance) remains.

- 2026-07-19 (Stage B post-return gauntlet RE-RUN — VLM routed through Tau, ACCEPTED
  at agent level; canonical loop still DRY-RUN, fail-closed): the three v1 blockers were
  all downstream of the missing VLM layer. Per the standing directive "only /tau has access
  to /scillm", every VLM call was routed through the Tau panel-reviewer node
  (`tau_coding.persona_dream_panel_agent --role panel-reviewer`, Tau commit `416edc5a`,
  custom hash-recorded `visual_review_prompt`, `api_key_source docker:scillm-proxy`) — NOT
  direct scillm from Stage B drivers. **Step 36 PASS (v2):** ArcFace whole-clip metric still
  fails (5/12 sub-threshold) but VLM adjudication classifies all 5 low-cosine frames
  `POSE_OCCLUSION` consistent with beat intent, zero substituted persons; scene/wardrobe/
  action continuity PASS; Kai scored via the recovered face-bearing reference
  `02-kai_character_sheet.png` (not contradicted). **Steps 37-38 PASS (v2):** the successor's
  authoritative line equals the frozen predecessor's rendered line (whisper
  `recognized==canonical`); re-mixing the hash-bound isolated line WAV (`c240e201`) + same bed
  (`8d5e0d3e`) reproduced a bit-identical mix (`33edae9a`), muxed onto the silent return;
  whisper `large-v3-turbo` forced alignment in-window; lip-sync `INAPPLICABLE_BY_COMPOSITION`.
  **Acceptance ACCEPTED_AGENT_LEVEL** (both fail-closed gates pass); human subjective acceptance
  still the human's. **Canonical loop still dry-run, `canonical_dream_memory_written: false`** —
  phases 13/14 text reasoning has no Tau node at 416edc5a (panel-reviewer is image-bound) and
  direct scillm is forbidden; `run_cognitive_loop.py` also hardcodes `allow_canonical_write=False`.
  Fail-closed: canonical persistence DEFERRED. Receipts under `…/rev_successor_943b01ecd9a3/…/97688ec5…/`:
  `post_kling_continuity_review_receipt.v2.json`, `step37_38_audio_final_assembly_receipt.v2.json`,
  `post_return_acceptance_receipt.v2.json`, `tau_vlm_route_verification_receipt.v1.json`,
  `tau_step36_adjudication/`, `step37_38_successor_mux/`; loop outcome
  `stageb_cognitive_loop_outcome.v1.json`. Memory: `persona_dream_pipeline_steps` +
  `persona_dream_governance` written with exact reread match=true. LESSON: the VLM was never a
  scillm-auth problem to "chase" in the drivers — it was a ROUTING problem; Tau's panel-reviewer
  already holds sanctioned scillm access and takes one composite image + a hash-recorded prompt.

- 2026-07-18 (Stage B post-return gauntlet on the LIVE successor return — ACCEPTANCE
  BLOCKED, fail-closed; canonical cognitive loop NOT run): the successor Kling return
  (`sha256:59b9ff31…`, 10.041667s, one submit, request `sha256:97688ec5…`, silent) was
  received (commit `a47fc595`) and put through the post-return gauntlet on THIS return.
  Results: Step 35 frame contact sheet PASS (12 uniform frames, single-shot clip);
  Watch gauntlet DEGRADED (per-frame VLM + transcript unavailable — scillm gpt-5.5 chat
  auth ROTATED; silent pre-mux video); Step 36 post-Kling continuity FAIL — the live
  deterministic ArcFace read (buffalo_l, CPU, threshold 0.421) vs `embry_contact_sheet_v3`
  shows the identity-source fix matching STRONGLY in the opening identity window (cos
  0.60-0.61, an improvement over the prior `EMBRY_IDENTITY_DRIFT_00_03`) but clearing only
  7/12 frames overall (mean 0.378), with the final third at cos 0.02-0.15; ArcFace alone
  cannot separate drift from pose and the VLM adjudication layer is down, so identity is
  NOT certifiable; Kai reference sheet has no detectable face (unscoreable). Steps 37-38
  audio+assembly BLOCKED (the exact Kai line was never rendered; no chatterbox engine; no
  paid authorization; VLM lip-sync unavailable). Acceptance BLOCKED; canonical cognitive
  loop NOT run — dry-run only, `canonical_dream_memory_written: false`. LESSON: two
  independent hard dependencies gate this stage in the current environment — a live VLM
  (scillm gpt-5.5 chat, auth rotated) for continuity adjudication + phases 13/14, and a
  voice render engine (chatterbox_turbo, absent) for the never-rendered exact line — and
  the fail-closed contract correctly refused to fake acceptance or write a canonical dream.
  The deterministic ArcFace identity lane DID run live and gave a genuine, mixed verdict:
  the v3 identity source helps materially where Embry is clearly the foreground subject but
  does not clear the whole-clip metric gate. Receipts under
  `.../rev_successor_943b01ecd9a3/` (`post_return_acceptance_receipt.v1.json`,
  `watch_gauntlet/59b9ff3155d6/step35_frame_contact_sheet_receipt.v1.json` +
  `step36_arcface_identity_summary.json` + `step36_embry_presence_refine.json` +
  `cognitive_loop_dryrun/`, and `phase_11_submit_return/provider_return/…97688ec5…/`
  `post_kling_continuity_review_receipt.v1.json` + `step37_38_audio_final_assembly_receipt.v1.json`).

- 2026-07-18 (qualification gate scoping — DECISIVE LESSON: exact-match gates must
  select by record TYPE, not keyspace): the step-38 requalification blocker was NOT
  record pollution — it was gate OVER-MATCH. `prepare_revision_qualification` listed
  `project_knowledge` by `(run_id, revision_id)` and required the space to hold
  EXACTLY the 27 qualification records, so 15 governance/audit records that
  legitimately share that keyspace were counted as `unexpected_keys` and blocked the
  gate. The governance records were never qualification records; the gate's intent
  was "exactly the 27 qualification records exist and reread exactly." Fix
  (`scope_qualification_documents()`, commit 1d454819): select the exact-match set by
  record IDENTITY — qualification schema AND `record_type` AND stable-key prefix must
  all agree; governance records (matching none) are readable but never counted; a
  malformed qualification claim or duplicate key fails closed; the gate is provably as
  strict as before for the 27 records (tests/test_qualification_gate_scoping.py, 8
  pass; full suite 21 pass). LESSON: an exact-match/exclusive-ownership gate that
  selects rows by keyspace membership is permanently brittle on a DELETION-FREE store
  — any other sanctioned writer that shares the keyspace makes it over-match forever,
  and you cannot "clean up" past the mismatch because nothing can be deleted. Select
  by the record's own type/schema, and route unrelated writers to their own
  collection (future governance writes now go to `persona_dream_governance`; the ten
  governance persisters were repointed; historical records stay untouched in
  `project_knowledge`). With the gate scoped, the full chain completed live: rebuild
  index (promote the accepted lane C waiver frame `sha256:9f8fb8c9`, retain phase_c as
  superseded via an invalidation ledger) → `revision_supersession`
  PASS_REQUALIFICATION_SUPERSEDED → prepare/verify/activate `--supersede`
  PASS_ACTIVE_CONSISTENT → `acceptance_rung_receipt.v5.json` = PASS_ACCEPTANCE_RUNG
  (supersedes v4). `does_not_prove` keeps Kling readiness, provider media publication,
  publication authorization, paid authorization, provider return, lip-sync-on-return.
  No paid call made or authorized.

- 2026-07-18 (Lane C step 38 fix — EXECUTED LIVE, BLOCKED by a gate conflict): the
  primary lane C plan (regenerate ONLY sb_003_end_frame so Kai's mouth is not
  camera-readable during 5.0-7.7s, keeping sb_003_start as the identity anchor) was
  run live through a new bounded driver (scripts/lane_c_regenerate_sb_003_end_frame.py)
  on the same Phase C GPT Image 2 lane (codex-oauth; embry_contact_sheet_v3 + Kai
  character sheet as reference inputs), max 5 attempts, failure-aware repair. It did
  NOT converge: FAILED_LANE_C_ATTEMPTS_EXHAUSTED. The DECISIVE LESSON is a real,
  documented tension between two unweakened gates — the hardened full-frame identity
  reviewer is FAIL-CLOSED and needs Kai's lower face (nose/mouth/chin/jaw) visible to
  ground specific-identity features, which directly conflicts with the composition
  requirement that his mouth NOT be camera-readable. Attempt 1 hid the mouth by arm
  occlusion → composition PASS but identity FAIL; attempts 2-5 kept a verifiable face
  → identity PASS (embeddings 0.64-0.81; att4-att5 also both continuity pairs PASS)
  but the mouth stayed readable → composition FAIL. GPT Image 2 could not hit the
  narrow overlap in 5 tries (att4/att5 near misses), so this is a generation-
  controllability gap, not a strict impossibility. It also exposes a design tension:
  the delta says the end-frame face is NOT required (identity anchored by the start
  frame), but acceptance criterion (a) verifies the face on the end frame for both
  characters — reconciling that is a gate-design decision reserved for a human. Per
  the fail-closed contract, the frozen revision and its canonical sb_003_end_frame are
  untouched, requalification + rung restoration were NOT attempted, and the acceptance
  rung REMAINS at v4 (not restored). Blocker + full attempt table:
  step38_lane_c_blocker_receipt.v1.json. Memory (exact reread PASS): keys
  ...:38:lane_c_sb_003_end_regen and ...:38:lane_c_blocker. No paid call.

- 2026-07-18 (embedding identity subgate — DECISIVE LESSON): identity verification
  was moved from VLM judgment to a deterministic ArcFace cosine distance, and it
  resolved the v3 impasse cleanly. VLMs (gpt-5.5 vision) are NOT metric identity
  verifiers: the run-to-run instability on known_bad_sb_001 was the model unable to
  place a face that is genuinely a near-look-alike. The fix is the standard 1:1
  verification method — InsightFace buffalo_l (w600k_r50, 512-d L2-normalized):
  detect -> 5-pt align -> embed -> cosine similarity vs a calibrated threshold
  (scripts/identity_face_embedding_subgate.py; deterministic; mockable Embedder
  interface; 11 unit tests). Wired into
  phase07_storyboard_tau_node._run_identity_continuity_review as the IDENTITY VERDICT
  AUTHORITY (full-frame VLM keeps scene/wardrobe/composition + face visibility; VLM
  face-crop demoted to advisory; code FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH records
  the score; fail-closed — no InsightFace means FAIL, never a silent VLM fallback).
  Calibration v4 (reviewer_calibration_receipt.v4.json, live CPU onnxruntime) =
  REVIEWER_CALIBRATION_PASS. Measured distributions: genuine same-person (reference-
  cell pairwise) floor 0.4991; known-bad/tamper offending ceiling 0.3430; cross-person
  (Embry-vs-Kai) 0.095..0.331. Threshold 0.421 (margin midpoint), margin 0.1561.
  known_bad_sb_001 Embry cosine 0.323 -> metrically a DIFFERENT face (the adjudication
  answer, by measurement: different identity; no reclassification). positive_control_
  sb_002, over-rejected by v3's VLM crop, PASSes (Kai 0.526). All 8 accepted successor
  frames PASS the embedding subgate (0.525..0.815). Live node integration confirmed
  end-to-end: known_bad_sb_001 full-frame VLM still PASSes but the node FAILs via the
  embedding subgate. Threshold recipe for the next agent: recompute genuine (positive +
  reference-cell pairwise) and known-bad distributions and set the threshold in the
  margin; re-derive if the reference sheet changes. Install pinned insightface==0.7.3
  + onnxruntime==1.19.2 (pyproject [identity] extra; insightface_install_receipt.v1.json).

- 2026-07-18 (face-crop identity subgate — SUPERSEDED by embedding subgate above): A zoomed-in face-crop subgate DID close
  the full-frame dilution blind spot — but only for non-marginal mismatches, and it
  did NOT fully calibrate. Mechanism (scripts/identity_face_crop_subgate.py, wired
  into phase07_storyboard_tau_node._run_identity_continuity_review, additive +
  fail-closed + provenance-free): ask gpt-5.5 for face bboxes, PIL-crop the candidate
  face plus up to 3 pose-matched reference views (frontal/3-4/profile), upscale, and
  run a feature-level face-to-face comparison; full-frame AND subgate must both PASS
  (code FAIL_FACE_CROP_IDENTITY_MISMATCH). Under a strict first prompt the subgate
  correctly FAILED the residual known_bad_sb_001 that full-frame review missed —
  proving the zoom surfaces the divergence. But calibration v3 (3 subgate-prompt
  revisions, the cap) = REVIEWER_CALIBRATION_FAILED: known-bad 2/3 FAIL, tamper 1/1,
  positives 1/2 (unstable). Hard lesson: known_bad_sb_001 is a genuine NEAR-LOOK-ALIKE
  — at face-crop scale gpt-5.5 cannot separably discriminate it from the genuine
  positives, and its verdicts on borderline crops are UNSTABLE run-to-run (the same
  two crops returned SAME, then DIFFERENT, then an empty verdict across runs). Any
  prompt strict enough to fail it also over-rejected real matches on surface
  warmth/pose; any prompt lenient enough to pass real matches also passed it. This is
  a discrimination-boundary case that belongs to human adjudication, not more prompt
  fiddling. Actionable for the next agent: (1) borderline face-crop comparisons need
  best-of-N agreement or a second independent reviewer before a FAIL/PASS is trusted —
  a single call is too noisy; (2) higher-resolution crops or a dedicated face-embedding
  distance metric may separate near-look-alikes better than a VLM prose comparison;
  (3) a packaged bundle (reviewer_calibration_v3/human_adjudication_bundle) with
  side-by-side candidate vs pose-matched reference crops + one-page questions is the
  right artifact when the model sits at its discrimination limit. Restoration stayed
  WITHHELD (acceptance_rung_receipt.v3 = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION);
  a factual blocked outcome with an adjudication bundle beats a forced pass.
- 2026-07-18 (state-clearing audit + supersession): Re-qualifying an immutable
  revision after its artifact index is rebuilt (same revision id, changed index)
  needed a sanctioned path; in Phase D it was done ad hoc by hand-deleting the
  Memory active-pointer document, the immutable queue terminal event, and the
  three qualification receipts. That deletion is now audited with verdict
  `AUDIT_PASS_NO_EVIDENCE_LOST`: every cleared item's pre-deletion content is
  recoverable — the four files byte-for-byte from git commit `a97c734e` (old
  hashes reverified: prepare `040308e2`, verify `0fc97ae5`, activation
  `86e32aec`, terminal event `f7c182a8`), and the single-slot CAS pointer by
  deterministic re-derivation from the committed old activation receipt.
  Contrary to the worst-case hypothesis, the deleted receipts were the
  git-tracked revision-tree receipts, not the gitignored `state/` ones, so git
  recovery exists. Lesson: immutable-revision re-qualification of a rebuilt index
  must never depend on that luck. Codified fix: `scripts/revision_supersession.py`
  + `activate_revision_qualification.py --supersede` replace deletion with
  retain-and-mark supersession (archive predecessors under `superseded/`,
  snapshot the old pointer as `SUPERSEDED` in Memory, append an old→new
  artifact-index entry to an append-only ledger); every other pointer mismatch
  stays fail-closed. Audit receipt
  `.../revisions/rev_successor_943b01ecd9a3/state_clearing_audit_receipt.v1.json`;
  tests `tests/test_revision_requalification_supersession.py` (3/3).
- 2026-07-17 (afternoon, persistence audit): An external agent audit of
  `rev_idea_f3f9c48d5cc2` was reconciled with receipts
  (`scripts/audit_revision_persistence.py`, receipts under
  `.persona-dream/state/revision_persistence_audit_*.json`). Confirmed real:
  the frozen Phase 01-10 index never covers post-qualification Phase 11-13
  evidence (122 request-scoped files in the old revision, now hash-bound by a
  generated request-evidence index); dead absolute-path references exist in
  frozen receipts (38 unique missing paths inside the old revision, mostly
  dead /tmp worktrees); pointer `revisionRoot` values are non-portable
  absolute paths (cosmetic: all tooling derives roots from
  run_root + revisionId). Refuted with evidence: "Memory has zero Phase 11/12
  records" is false - the step collection holds 42 records for the old
  revision including steps 21-36 with request-scoped hashes, plus
  `pd_phase11_*` boundary records; "validation.json incorrectly says provider
  submission never ran" is a misread - the run-root validation describes the
  ACTIVE revision (new request, zero calls, coherent with its unused ledger),
  not the frozen revision's consumed request. The systemic fix is the new
  post-step audit gate; the active revision `rev_upstream_bf3b05d47fb8` passes
  it with zero unexpected unindexed files and full memory reread (27 + 42 +
  boundary record for request `ca90ba9f...`).
- 2026-07-17 (afternoon): The upstream-contract reconstruction gate is done.
  `rev_upstream_bf3b05d47fb8` (source `rev_idea_f3f9c48d5cc2`) was created,
  qualified, and activated in one bounded transaction
  (`scripts/reconstruct_upstream_contract_revision.py`): the seven canonical
  files for steps 05/11/12/15 exist and validate, the step-41 invalidation
  ledger covers steps 06-42, Memory prepare/verify/activation passed
  (339/339 hashes, `activation-1662abf63c5270c9d7ca17b46ef34c76`), and 42/42
  revision-bound step records were exactly reread. Steps 06-20 were then
  hash-revalidated (9/9 consistency checks). Key lesson: stage every artifact,
  ledger, and the deterministic step-record bundle inside the revision BEFORE
  computing the index/manifest; write all post-activation receipts under
  `.persona-dream/state/` so the frozen artifact set is never mutated.
- 2026-07-17 (afternoon): The repaired SB_004 request is compiled and fixed at
  `sha256:ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`
  with an unused attempt ledger (`PREFLIGHT_READY`, zero calls, zero submit
  intents). The repair lives in `PANEL_CONCISE_ACTIONS["sb_004"]`
  (`scripts/phase11_payload_binding.py`): Embry-only forward commit through
  the safe channel, Kai held outside, lava-reef boundary sharply readable,
  432 chars. Preflight chain: binding bootstrap at publication commit
  `8b12d4c8c5af3fff6f0de2aa1a545b502ca71ed2`, reconcile upstream validation,
  live provider snapshot, live public media probes (6 assets), canonical
  compile, adapter preflight all PASS with zero technical blockers. Gate:
  `BLOCKED_AWAITING_HUMAN_APPROVAL` for five hash-bound approvals (template at
  `phase11_authorization_packet.v1.pending.json`; max spend $0.84). No paid
  call was made.
- 2026-07-17: The corrected Phase 11 request
  `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`
  made one live provider submission, polled 43 times, and returned an
  18,520,578-byte H.264 1280x720 24 fps MP4 lasting 10.041667 seconds. The MP4
  SHA-256 is
  `sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`.
  Twelve Watch frames were assembled into a 4x3 contact sheet and inspected.
  Post-Kling continuity is `FAIL`: identity, wardrobe, boards, setting, and
  Kai's hand signal remain coherent, but SB_004 does not visibly show Embry's
  safe-channel commit or a readable lava-reef boundary. Memory exact reread is
  42/42 with 42 semantic syncs and 42 Qdrant pointers. Final acceptance remains
  blocked on steps 05, 11, 12, 15, 36, 40, and 42. Do not resubmit: the paid
  authorization was consumed and a repaired hash requires separate authority.
- 2026-07-15: `rev_repair_a8b93ffeca8f` is a semantic-mix counterexample: its
  Phase 01 request belongs to the Tau issue-41 fixture while Phase 03-10 belong
  to the Embry/Kai surfing idea. It must not be reported `ACTIVE_CONSISTENT`.
  The repair implementation creates a new immutable revision from an explicit
  human idea, writes ten hash-chained phase bindings, verifies Memory exact and
  dense recall, and only then activates. Code presence is not migration proof.
- 2026-07-15: The live semantic-mix repair activated
  `rev_idea_f3f9c48d5cc2` for run `pipeline-complete`. The explicit human idea
  is bound through 10/10 phase lineage records. Memory exact-reread verified 27
  synchronized documents (1 revision, 10 phases, 16 required artifacts), and
  the run-scoped active pointer and terminal event
  `repair-454b255245a1a162/000001-completed.json` agree with the activation
  receipt. Live run-detail reports all ten phases `accepted_current` and
  `ACTIVE_CONSISTENT`. That qualification remains scoped to Phases 01-10 and
  does not inherit any Phase 11 provider result.
- 2026-07-16: The canonical Phase 11 pre-Kling boundary for
  `rev_idea_f3f9c48d5cc2` is now live-validated and Memory-persisted. The exact
  Standard/audio-off request body hash is
  `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`.
  Its four prompts are 247, 268, 362, and 271 characters; SB_003 is silent,
  `multi_prompt` is present, `end_image_url` is absent, and the adapter
  preflight passed with a request-scoped submit-once fence.
  Memory `/upsert` wrote request-scoped key
  `pd_phase11_eb5dbe1257f6152103d1ce1e2700f9582d8ef6e5fb87e90e`, `/list`
  exactly reread it and the active pointer, semantic sync is `synced`, and
  question-shaped recall returned the same identity with dense score
  `0.7866844`. Current gate: `BLOCKED_AWAITING_HUMAN_APPROVAL` for five new
  hash-bound receipts: publication authorization, visual/media acceptance,
  exact-request acceptance, cost acceptance, and paid-call authorization.
  `actual_provider_call_attempts=0`, `provider_ready=false`,
  `live_submit_ready=false`, and no provider return or Watch observation exists.
- 2026-07-16: The separately authorized request
  `sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16`
  consumed exactly one attempt, request ID
  `019f6b89-e69a-7371-9b98-313a96f5f020`, and failed with HTTP 422 because
  fal does not support `end_image_url` with `multi_prompt`. Its ledger is
  `FAILED`, `submit_intent_count=1`, `actual_provider_call_attempts=1`, and
  `automatic_resubmit_allowed=false`. The failure is Memory-persisted with
  exact reread, semantic sync, and dense recall. The compiler now preserves
  `sb_004.end_frame` as continuity-only evidence instead of a provider input.
- 2026-07-16: Graham explicitly authorized all five Phase 11 decisions for
  request body
  `sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71`
  with a maximum spend of `$0.84` and exactly one generation attempt. The
  adapter submitted once and received request ID
  `019f6acb-853c-7552-bc73-ff8a6548afb1`. fal queue status reached
  `Completed`, but result retrieval returned HTTP 422 with four errors: every
  `multi_prompt[*].prompt` exceeded the provider's 512-character maximum. The
  durable attempt ledger now records `state=FAILED`,
  `actual_provider_call_attempts=1`, `submit_intent_count=1`, and
  `automatic_resubmit_allowed=false`. No MP4 was returned and Watch was not
  invoked. The compiler also exposed a false-count defect by reporting zero
  attempts while blocking on the failed ledger. A corrected request requires a
  new request hash, new hash-bound approvals, and new explicit paid-call
  authorization; the consumed authorization must not be reused.
- 2026-07-16: Phase 11 Memory identities are now request-scoped. The failed
  request is separately persisted at
  `pd_phase11_ab56b1cf2875c1c9c35871073006bdc779397deae2777732` with one
  attempt, semantic sync, and dense recall `0.75495136`; the corrected request
  uses the distinct key above with zero attempts. The old run/revision-only key
  remains backward-readable history and is no longer a write target.
- Project initialized, knowledge tracking started
- Agent is persona-dream pipeline that generates cinematic Kling Omni sequences from persona memory. Purpose: test whether an AI agent can autonomously dream about events from memory like a real person. The pipeline must be treated as a no-omission serial gate loop from request intake through final report. The full pipeline order is: Request / Idea Intake → Dreaming Persona Selection → Memory Recall → Residue Grounding → Dream Packet → Story / Video Plan → Producer Persona Selection → Producer selects Director → Producer selects Script Writer → Creative Authority Receipts → Look Lock → Script DNA → Storyboard Prompt Composition → Storyboard Panel Receipts → Panel Continuity And Repair Ledger → Panel Generation Loop → Panel Visual Review Loop → Surgical Panel Repair → Panel Repair Gate → Panel Source Receipt → Provider Media Publication Work Order → Local Provider Media Staging → Publication Preflight → Publication Authorization → Public URL Probe → Provider Media Handoff → Provider Media Lock → Kling Scene Packet → Provider Final Gate → Paid Call Authorization → Kling Submit → Kling Poll / Callback → Output Retrieval → FFprobe / Technical Validation → Frame Contact Sheet → Post-Kling Continuity Review → Voice / Audio Handoff Lane when voiced → Final Assembly / Movie Lane → Report Generation → Gate Validation Loop → Upstream Revision Invalidation → Final Acceptance Boundary.
- 2026-06-30: **Do not omit the creative authority layer.** Producer Persona Selection, Director Selection, Script Writer Selection, and Creative Authority Receipts are mandatory upstream gates. Producer owns creative arbitration and run-level decisions. Director owns camera, lens, blocking, lighting, color grade, pacing, and visual continuity. Script Writer owns dialogue, story pressure, beat logic, scene tension, reveal structure, and Script DNA. Changes to producer/director/script-writer selections invalidate Look Lock, Script DNA, storyboard, panels, provider packets, reports, and downstream receipts unless a migration receipt proves derivation from the current upstream revision.
- 2026-06-30: Multi-scene hardening should reuse the same per-scene serial loop, but must namespace every scene/panel artifact. Do not use singleton paths such as `receipts/kling_scene_packet.json`, `receipts/panel_source_receipt.json`, or `receipts/panel_repair_gate_receipt.json` as mutable shared state for multi-scene runs. Use per-scene directories such as `scenes/scene_001/receipts/...`, aggregate only from immutable per-scene receipts, and fail the aggregate gate if any scene is blocked or stale. This prevents the observed class of regression where a later packet-install step copied an older singleton panel repair receipt back into the run root.
- 2026-06-30: Historical one-scene proof/report state used the Tau issue-41 fixture. Its old `15/15` report claim is superseded and is not evidence for the current Embry/Kai revision. The checked-in validation later reported only `12/15`, so neither report may be used as Phase 11 readiness proof.
- 2026-06-30: Multi-scene live image smoke now has real Scillm/Codex OAuth evidence, not fake workers. Command: `./run.sh multiscene-live-smoke --run-root /tmp/persona-dream-multiscene-live-20260630T020933Z --scene-count 2 --max-workers 2 --auth codex-oauth --model gpt-image-2 --quality high --image-timeout-s 900 --json`. Receipt: `/tmp/persona-dream-multiscene-live-20260630T020933Z/receipts/multiscene_live_smoke_receipt.json`; validation: `/tmp/persona-dream-multiscene-live-20260630T020933Z/receipts/multiscene_live_smoke_validation.json`; status `PASS`, `mocked:false`, `live:true`, `scene_count:2`, `max_workers:2`, `forbidden_singleton_receipts:[]`, `kling_called:false`, `paid_call_authorized:false`. Scene 001 contact sheet SHA `6834a68f2486be56accde3b5265deb28948ad7d2778fdfcfc5d97bb6394a7ae0`, panel SHA `eee1bb993e70b400f048e04908ed4da2832245ef8a3085f867411416c1211413`; Scene 002 contact sheet SHA `22ef9ba1a241321ebbf6e44637d40fe75b7c991708d965f0b228579acff80cab`, panel SHA `e3341e3029435f60c67caef77bb49b149300500adc970b034c397818da33fef6`.
- 2026-06-30: Live bug fixes found while hardening multi-scene: (1) Scillm project-agent doctor used stale shell `SCILLM_PROXY_KEY=sk-dev-proxy-123` while the running Docker proxy had a different local master key; fixed `scripts/sanity_project_agent_scillm_calls.py` to resolve the running proxy key and propagate it to child proof scripts. (2) `scripts/generate_image.py --auth codex-oauth` falsely reported Codex OAuth unavailable when called outside the Scillm import environment; fixed it to inspect `CODEX_HOME/auth.json`. (3) `generate_image.py` could hang after Codex had already written the requested PNG and receipt; fixed it to treat matching output+receipt as terminal evidence and terminate the child process. These were Scillm wrapper/runtime bugs, not Tau bugs, so no Tau ticket was filed.
- 2026-06-30: Multi-scene report artifact: `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/multiscene-live-smoke/report.html`, generated from the live multi-scene receipt and validation. Served at `http://127.0.0.1:8898/report.html` during verification. CDP screenshot: `/tmp/codex-ui-verification/agent-skills/persona-dream-multiscene-live-report/20260630T021733Z.png`; marker/read JSON: `/tmp/codex-ui-verification/agent-skills/persona-dream-multiscene-live-report/20260630T021733Z.read.json`. Visual inspection confirmed the report shows real scene images and summary fields.
- 2026-06-30: The report generator caught a false-green regression from stale singleton receipts: `write-one-scene-kling-review-packet` reinstalled an older `panel_repair_gate_receipt.json`, causing provider eligibility to revert to false and the public probe URL to become missing. The repair was deterministic: copy the passing live probe receipt back to `receipts/provider_media_probe_receipt.json`, run `apply-provider-media-public-probe`, rewrite `panel_source_receipt.json`, reinstall the blocked Kling packet, and rerun the complete pipeline report. This lesson reinforces that timeouts, empty outputs, stale receipts, and overwritten singleton receipts must fail gates, not be summarized as accepted.
- 2026-06-19: patch_pipeline_report_ui design pass adds gate summary banner, section pass/fail badges, provisional downstream sections after blocked gates, 5-column panel storyboard table, deduped panel breakdown, collapsed contact-sheet provenance.

- 2026-06-23: **Harness phase repair accepted locally** (pending WebGPT phase review). Do **not** rewrite `medium_loop_dag_smoke.py` unless a live rung fails preflight. Keep it as the local serial proof ladder. Broken piece was viewer + artifact sync + overclaiming, not core Python rungs. Viewer now uses `TransportReactFlowDagWorkspace` via `personaDreamDagEvidenceAdapter.ts` (~247-line shell). Install fresh artifacts with `scripts/install_dag_harness_artifacts.py`. Route: `http://localhost:3002/#scillm/dag-harness`. Live PASS on 2026-06-23 for `scillm-one`, `scillm-two-concurrent`, `real-gates`.
- 2026-06-23: **Stop and ask human** when blocked or confused — codified in `.cursor/rules/stop-and-ask-human.mdc` and `~/.codex/AGENTS.md`. Do not spiral; wait for human scope/acceptance choices.
- 2026-06-23: **Agent anti-spiral rules** codified in `.cursor/rules/proof-ladder-scope-lock.mdc` and `~/.codex/AGENTS.md` (Proof Ladder And Harness Scope Lock). Key rule: if the next command does not produce an inspectable artifact answering the exact question, do not run it.
- 2026-06-22: The recent DAG/harness work must be treated as a failed/drifted implementation attempt, not proof of readiness. `scripts/medium_loop_dag_smoke.py` currently proves only a narrowed local serial gate smoke for real persona-dream Phase 2, Phase 5, and Phase 6 commands on the correct run root, plus an opt-in one-node `$scillm` HTTP probe. It does not import or execute `ScillmDagHarness`, does not prove deterministic model generation, does not prove a bounded semantic self-improvement loop, and does not prove no-paid/no-live enforcement.
- 2026-06-22: The first non-mocked `$scillm` HTTP/service call node now exists: `--include-scillm-probe --stop-after-scillm-probe` generates `scillm_oneshot_probe.py`, calls `POST http://localhost:4001/v1/chat/completions` via `httpx.AsyncClient`, and validates exact JSON. Last observed receipt: `/tmp/persona-dream-real-dag-i_7ogn11/repo/.loop/context/scillm-oneshot-probe-receipt.json` with HTTP 200, `ok: true`, model `gpt-5.5`, and parsed content `{"ok": true, "answer": "persona-dream-scillm-probe"}`. Do not add panels, WebGPT, voice, React Flow, Kling, provider packets, or multi-agent orchestration until the next rung, two concurrent `$scillm` calls, passes.
- 2026-06-22: The canonical human/project-agent review surface is `http://127.0.0.1:8892/full-report.html`, backed by `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict`. Do not use stale `r13` run roots for Phase 5/6 proof.
- 2026-06-29: One downstream persona-dream slice now has local proof from real Scillm panel image generation through Scillm VLM review into the Tau serial creator/reviewer/repair-gate harness, ending at a dry-run one-scene Kling request. Evidence root: /tmp/persona-dream-scillm-panel-proof-20260629T1536. Scillm doctor receipt /home/graham/workspace/experiments/scillm/.scillm/proofs/project_agent_sanity/20260629T153621Z/receipt.json reports PASS for 13/13 lanes. Image receipt /tmp/persona-dream-scillm-panel-proof-20260629T1536/artifacts/images/panel_001_receipt.json reports ok=true, 1672x941, sha256=5d2456775e28b649bc82ce898751dd5e124366536282b8fb5d46f7ba9fe16366. VLM receipt /tmp/persona-dream-scillm-panel-proof-20260629T1536/receipts/live_scillm_vlm_visual_review_receipt.json reports status=PASS over Scillm gpt-5.5 image_url. Tau proof /tmp/persona-dream-scillm-panel-proof-20260629T1536/tau-proof-final/manifest.json reports mocked=false, live=true, selected agents panel-creator -> panel-reviewer -> persona-dream-panel-repair-gate, command_exit_codes=[0,0,0], first_blocker=null, and dry_run_one_scene_kling_request populated. This does not prove the full dream packet/story/contact-sheet/panel-prompt upstream, multi-panel while loop, public media publication, or live Kling call.
- 2026-06-29: The next backward-working Tau integration proof used real panel 01 upstream source `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/storyboard/panel_repair_gate/first_batch_work_orders_20260614T044000Z/panel_01_work_order.json` as the prompt source for `tau persona-dream-panel-proof --scillm-live-panel`. Evidence root: `/tmp/persona-dream-panel01-live-tau-upstream-proof-20260629T1745`. Tau generated `/tmp/persona-dream-panel01-live-tau-upstream-proof-20260629T1745/scillm-panel/panel_001.png`, VLM review receipt reports `status:PASS`, and Tau manifest reports `mocked:false`, `live:true`, `scillm_originated_inside_tau:true`, `command_exit_codes:[0,0,0]`, `first_blocker:null`, and dry-run `one_scene_kling_request.json`. The serial persona-dream pipeline still blocks because Tau's terminal repair receipt is not the canonical persona-dream repair-gate/source contract: `write-panel-source` exits `1` with `repair_gate_schema_not_persona_dream_panel_repair_gate_receipt_v1`, missing subgate statuses, `generated_image_path_missing`, and `claimed_media_hash_missing`; `pipeline-loop-run ... --max-iterations 1` exits `1` at `missing_panel_source_receipt_path`. Tracked in Tau issue https://github.com/grahama1970/tau/issues/33. No public upload or live Kling call was performed.
- 2026-06-29: After Tau issue #33 was resolved at Tau commit `b0131c1`, the canonical issue-33 proof root `/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/issue-33-live-persona-dream-20260629T180606Z` advances through canonical Kling packet, local provider media lock, publication work order, and local provider-media staging. `pipeline-loop-run --max-iterations 1` wrote `storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_001_local_staging_receipt.json` with `status:PASS_PROVIDER_MEDIA_LOCAL_STAGING`, staged bytes at `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/provider_media/issue-33-live-persona-dream-20260629T180606Z/panel_001.png`, and locked SHA-256 `sha256:3ef0ab7722d6742adf0c4e2b19a325f3e0cdaa761f8459e49329b2737a5d99fa`. The current first blocker is now `provider_media_publication_authorization`: missing `receipts/provider_media_publication_preflight.json`, requiring explicit authorization for public upload/git push or equivalent public asset publication. No public upload, live URL probe, live Kling call, or paid provider call was performed.
- 2026-07-03: Phase 04 Contact Sheets is live-wired but not complete. Tau ran the contact-sheet creator/reviewer/build/reviewer loop with live:true and mocked:false. A real Codex OAuth image generation created and indexed the Embry surfboard contact sheet at /mnt/storage12tb/skills/persona-dream/outputs/embry-kai-surf-phase04-contact-sheets-20260702/artifacts/images/contact_sheet_embry_surfboard.png with receipt /mnt/storage12tb/skills/persona-dream/outputs/embry-kai-surf-phase04-contact-sheets-20260702/artifacts/images/contact_sheet_embry_surfboard_receipt.json and sha256 d4052937952bb14e5be77c25b262e30d92822068f5af26dd6cb69d7f03240216. It was inserted into memory collection persona_dream_visual_assets and Qdrant collection persona_dream_visual_assets_v1. The Tau builder originally missed persisted contact sheets because semantic /recall is insufficient for exact visual-asset gates and _compact_memory_recall_item dropped image_path/asset_id. Tau was patched at /home/graham/workspace/experiments/tau/src/tau_coding/persona_dream_dream_packet_agent.py to exact-query persona_dream_visual_assets via /list filters entity_id and asset_id before semantic recall, and to preserve asset_id, entity_id, entity_type, title, image_path, url, and source in compacted recall items. Targeted Tau test /home/graham/workspace/experiments/tau/tests/test_persona_dream_dream_packet_agent.py passes with 7 passed. Post-patch build receipt /home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/pipeline-complete/phase_04_contact_sheets/contact_sheet_build_receipt.json remains BLOCKED_CONTACT_SHEET_BUILD with attached_asset_count 1 and blocked_asset_count 4. Remaining required sheets are Kai surfboard, June Swell, Lava Reef, and Kona Coast. Do not mark Phase 04 READY until those required assets are generated, indexed, attached, and the contact-sheet artifact gate passes.
- 2026-07-04: Phase 06 Script has a deterministic Tau script-writer/script-reviewer contract path wired into ux-lab, but it is not yet the full GPT-5.5/Kimi live creator-reviewer loop. Changed files include tau/src/tau_coding/persona_dream_dream_packet_agent.py, tau agent-command-specs/script-writer and script-reviewer, pi-mono/packages/ux-lab/server/index.ts, and skills/persona-dream/ui/src/DreamWorkspace.tsx. Current API evidence: GET http://127.0.0.1:3001/api/tau/dream/script-draft/latest returns ok=true, status=PASS_SCRIPT_CONTRACT, script length 2114 chars, 7 interaction-matrix coverage rows, and 15 asset-usage rows. Current artifact: /home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/persona-dream-script-ui-dispatch/script-ui-20260703T230200Z/run/script_contract.json. CDP marker: /tmp/codex-ui-verification/agent-skills/dream-script-phase06-hydrated-script-after-vite-restart/20260703T232408Z.read.json. Remaining known UI issue: right sidebar may still show stale MISSING_EVIDENCE copy even when the central Script pane hydrates the PASS_SCRIPT_CONTRACT artifact.
- 2026-07-04 correction: A fresh status poll of GET http://127.0.0.1:3001/api/tau/dream/script-draft/latest after the Phase 06 knowledge update returned ok=true, status=PASS_SCRIPT_CONTRACT, script_chars=2114, coverage=7, assets=14. Treat 14 asset-usage rows as the current observed API count unless a newer script_contract.json receipt proves otherwise.
- 2026-07-06: Phase 07 storyboard failure mode: the multi-day blocker was not primarily a card/layout problem. The panel prompt and reviewer gate let character identity become secondary to wide establishing-shot composition, reef/location beauty, and crowd/lineup context. For identity-critical storyboard panels, priority must be: required character identity match > faces visible and reference-verifiable > character-readable composition > location/reef/cinematic details. Use medium-wide foreground two-shots when Embry/Kai are required, and pass Embry/Kai reference sheets as actual image inputs/attachments, not only local path text.
- 2026-07-06: If the human shows a visual counterexample for a persona-dream panel, stop UI/status-copy work and inspect the generated prompt, reference attachment route, reviewer schema, and acceptance gate. Do not spend further cycles styling around bad imagery. The next artifact must be a corrected Tau creator/reviewer run receipt or a precise blocker proving why regeneration cannot proceed.
- 2026-07-13: Historical qualification of `rev_repair_a8b93ffeca8f` is superseded by the July 15 semantic-lineage validator. That revision is a rejected semantic-mix counterexample, not the current active authority.
- 2026-07-15: The earlier Phase 11 receipt-only state at commit `972d1a2c` was
  not Memory-persisted or live-submittable. It is retained as the regression
  baseline and is superseded by the 2026-07-16 canonical compiler, adapter
  preflight, fail-closed validation, and Memory persistence evidence above.
- 2026-07-17: Phase 11 boundary restore exists as task commit `8ed796cb2 persona-dream: finish phase11 boundary restore`, but it is not on `origin/main` (`git merge-base --is-ancestor 8ed796cb2 origin/main` returned exit 1). A clean `origin/main` worktree cherry-pick attempt proved the commit is superseded, not simply missing: main already has newer Phase 11 lineage commits including `2638b7c persona-dream: add canonical phase 11 boundary`, `c53d68a persona-dream: make phase 11 artifacts portable`, `5214240 persona-dream: clear phase 11 technical blockers`, `5a30f24 persona-dream: add phase 11 canary adapter`, `bbc1c4c fix(persona-dream): bind revisions to explicit human idea`, `a4c9ca6 feat(persona-dream): bind and persist Phase 11 preflight`, `54aa25a fix(persona-dream): scope Phase 11 requests and memory evidence`, and `d249e36 fix(persona-dream): reject multi-prompt end image`. Do not cherry-pick `8ed796cb2` to main. The required main action is to push this knowledge correction after proving the current main Phase 11 path; this is not full pipeline progress, Dreamer readiness, or provider readiness.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-16 | Initialize project knowledge | Enable shared human/agent context |
| 2026-06-16 | Panel beats must include explicit prop motion cues | Foreground prop behavior gate requires visible motion for tea steam, paper lift, screen reflections, sky-eye blink, umbrella ripple, Tyranid movement. Vague beats like 'Horus speaks' fail the gate. |
| 2026-06-16 | Combined creature/environment reference sheets accepted as PASS | Tyranids and void-world are visually inseparable. Single combined sheet serves visual continuity better than two disconnected sheets. Update validate_phase_05_contact_sheet_gate.py PARTIAL_IDS set when accepting combined sheets. |
| 2026-06-16 | Voice clone submission should be automatic in autonomous mode | SKILL.md now has automated voice clone submission after voice-segment-selector produces a 30s WAV. Manual listen review is optional — the selector candidate WAV IS the acceptance. In autonomous (non-dry-run) mode, the agent submits the Kling voice clone API call automatically without waiting for human approval. |
| 2026-06-16 | Kling voice clone API discovered and working | API base: api-singapore.klingai.com. Auth: JWT with HS256, no auth endpoint. Voice name max 20 chars. voice_url must be public URL (no file upload). Tested: auth OK, name too long returns 400, multipart unsupported. WAV files are local and need public hosting before clone call can succeed. |
| 2026-06-16 | Kling voice clone succeeded — voice IDs obtained | Horus voice_id=895864972788502540, Embry voice_id=895864973321830413. Cost: /usr/bin/zsh.05 each. The SKILL.md voice automation now includes the actual voice_id values so the agent uses them directly in downstream panel generation (<<<voice_1>>>, <<<voice_2>>>). The blocker is fully resolved. |
| 2026-06-16 | Panel auto-repair loop requires 8 validations per iteration | Subagent loops generate → validate → fix → re-validate with 8 specific checks: characters, props, environment, creatures, effects, script/dialogue, scale, motion cues. Max 5 retries per panel. Surgical fix only — never regenerate from scratch. FAILED_HARD after max retries. |
| 2026-06-16 | Panel repair uses $loop skill — not manual loop simulation | The $loop skill (skills/loop/) is the proper bounded harness for panel generation iteration. It owns explorer → coder → checks → code-reviewer → repair. The subagent provides objective, target file, and check command per panel. $loop handles retry and receipt. Never simulate the loop manually. |
| 2026-06-16 | review-panel skill created as CI runner | skills/review-panel/ is the CI harness for storyboard panel review. It invokes the panel-reviewer subagent ONCE per panel — the subagent owns all repair iteration context internally (up to 5 surgical retries via $loop + create-image). The runner patches index.html diagnostic table and emits SubagentSnapshot progress for ux-lab/subagent-monitor. FAILED_HARD after max retries. Never implement review or repair logic in the runner. |
| 2026-06-16 | Panel image generation uses /create-image — not bespoke API calls | The /create-image skill handles all image generation with backend fallback (FLUX, Gemini, scillm).  handles iteration. /scillm handles LLM proxy. Never call image APIs directly — always route through /create-image for dimension validation and fallback. |
| 2026-06-20 | Upstream changes invalidate downstream dream artifacts | Any change to idea, memories, story, characters, producer, scriptwriter, director, camera, lighting, contact sheets, script, panel intent, voice plan, provider constraints, or gate policy marks affected downstream artifacts stale. The agent must regenerate impacted story/script/references/prompts/panels/text/camera/lighting/provider packet from the current upstream revision, not merely reconcile receipts. Completion requires `unresolved_panel_image_errors == 0`, `unresolved_panel_text_errors == 0`, and `all_downstream_artifacts_match_current_upstream_revision == true`; otherwise Kling/provider readiness remains blocked with explicit findings. |
| 2026-06-22 | `medium_loop_dag_smoke.py` default scope narrowed to cheap real gates only | Default run excludes panel repair and voice clone because those paths triggered expensive, slow, stale WebGPT/panel activity during a harness sanity check. Default gates are Phase 2, Phase 5, and Phase 6 only. Optional flags may include panel repair or voice clone, but those are not part of the minimal harness proof. |
| 2026-06-22 | Added opt-in real `$scillm` httpx one-shot probe | `--include-scillm-probe --stop-after-scillm-probe` runs only `scillm_oneshot_probe`, calls localhost `:4001` with `httpx.AsyncClient`, validates exact JSON, streams JSONL events, and writes `scillm-oneshot-probe-receipt.json`. This is a service-call proof only, not ScillmDagHarness or Dreamer proof. |
| 2026-06-22 | Do not cite the local serial runner as ScillmDagHarness evidence | A reviewer correctly identified the runner as a bespoke serial subprocess recipe interpreter. It ignores or does not prove many DAG semantics such as topological scheduling, cycle detection, real retry behavior, strict schema validation, unconditional aggregation on failure, process-tree cleanup, and provider/network isolation. |
| 2026-06-22 | Final panel repair must not use Nano Banana/Gemini final imagery | Final panels must be photorealistic and match the accepted contact/reference sheets. Use `$create-image` / `$scillm` GPT image path with receipts for final repair. Nano Banana/Gemini/non-photorealistic storyboard images must fail panel review rather than be accepted or patched around in the report. |
| 2026-06-22 | Report/UI edits require source backup and visual proof | Prior edits repeatedly removed or degraded sections: sticky header/lucide navigation, Producer, Voice/Orpheus-TTS controls, complete Script, panel text prompts, and panel intent details. Future edits must start from backup/source truth, preserve sections, and verify with rendered screenshot before making any green/ready claim. |
| 2026-06-30 | Full persona-dream pipeline steps must not be omitted | The canonical pipeline includes Request Intake, Dreaming Persona, Memory, Residue Grounding, Dream Packet, Story/Video Plan, Producer, Director, Script Writer, Creative Authority Receipts, Look Lock, Script DNA, Storyboard, Panel Ledger, Panel Generate/Review/Repair, Provider Media, Kling Packet, Provider Final Gate, Paid Authorization, Kling execution/poll/retrieval, ffprobe, frame contact sheet, continuity review, audio handoff, final assembly, report, gate loop, upstream invalidation, and final acceptance boundary. Future status/report answers must label implemented vs intended/missing behavior instead of silently compressing this list. |
| 2026-06-30 | Multi-scene is the same loop only after path namespacing and aggregation are hardened | Reuse the one-scene validators per scene, but store scene receipts under scene-scoped paths and aggregate from immutable scene manifests. Singleton root receipts may be used only as derived rollups, not as authoritative mutable per-scene state. |
| 2026-06-30 | Live Kling remains a separate paid-call boundary | A prepared `kling.scene_packet.v1` with provider media is not a live execution. Live Kling requires an explicit paid-call authorization receipt plus submit/poll/download/ffprobe/frame-contact-sheet/continuity-review receipts. |
| 2026-07-03 | Phase 05 voice selection may be autonomous only through a creator/reviewer contract | Agents may discover candidate public/provided/local/synthetic voice references, extract clean clips, render Chatterbox demos, and select defaults, but the phase must write `voice_candidate_bundle.json` and `voice_selection_receipt.json` with provenance, rights notes, live non-mocked demo receipts, tone metadata, and reviewer rationale. Silent final voice locking is not accepted. |
| 2026-07-06 | Phase 07 storyboard prompts must be identity-first for character panels | Wide establishing-shot prompts caused plausible surf/location frames with wrong or unverifiable Embry/Kai identities. Character panels must require foreground, reference-matched, face-visible Embry and Kai before surf composition, reef visibility, crowd pressure, or cinematic beauty. Avoid weak wording like 'for continuity only' for identity references. |
| 2026-07-06 | Failed identity review invalidates accepted storyboard frames | A generated storyboard frame cannot remain ACCEPTED_START_FRAME or ACCEPTED_END_FRAME when identity_continuity_review.status is FAIL. Reviewer failure must downgrade the frame, write a blocker, and force Tau creator/reviewer regeneration instead of letting the UI display or package the image as accepted. |
| 2026-07-14 | Phases 01-10 require an immutable ACTIVE_CONSISTENT revision before acceptance | Accepted-looking local files are insufficient. Qualification requires hash-bound local artifacts, exact Memory records, Qdrant semantic sync, a deterministic active pointer, and a terminal repair event. Provider submission remains a separate Phase 11 boundary. |
| 2026-07-15 | Phase 11 receipt edits are not provider lifecycle implementation | Do not call the Phase 11 preflight complete from credential, price, schema, or payload receipt fields alone. Readiness requires a corrected compiler with audio-consistent prompts, tests and `run.sh` integration, fail-closed report validation, Memory persistence, exact payload-bound approvals, and submit-once/poll/download receipts. |
| 2026-07-16 | Phase 11 may await humans only after technical validation and Memory proof | `BLOCKED_AWAITING_HUMAN_APPROVAL` is valid only when the active revision chain, exact request, media bindings, fresh provider evidence, adapter preflight, submit-once fence, Memory exact reread, semantic sync, and dense recall pass with zero provider attempts. |
| 2026-07-16 | A failed authorized canary consumes the one-attempt authorization | Request `444a5a27...` was submitted once and rejected by fal result validation because all four shot prompts exceeded 512 characters. Never reset or reuse its ledger; a repaired request must have a new hash and separate explicit authorization. |
| 2026-07-16 | Phase 11 Memory identity is exact-request scoped | Run/revision-only keys collide when a repaired payload is compiled. New Phase 11 writes include `request_body_sha256` in the deterministic key so failed and corrected requests coexist without merge residue. |
| 2026-07-16 | `multi_prompt` and `end_image_url` are incompatible on the selected fal endpoint | Live request `9966f6b6...` returned HTTP 422: `End Image Url is not supported with Multi Prompt`. Keep the accepted end frame as continuity-only evidence, omit it from the request body, and reject this field combination before submission. |
| 2026-07-17 | Do not cherry-pick obsolete Phase 11 restore commit to `main` | The active branch `battle-ux8-live-contract` is dirty and `ahead 80, behind 203` relative to `origin/main`, so direct push is unsafe. A clean main worktree proved `8ed796cb2` conflicts with newer Phase 11 files already on main; treat it as superseded and integrate only the knowledge correction after focused proof. |
| 2026-07-18 | An identity-first qualified reference produces first-attempt storyboard passes | Regenerating the eight Phase 07 frames of `rev_successor_943b01ecd9a3` against the qualified `embry_contact_sheet_v3` identity source (not the rejected montage) yielded 8/8 frames PASS actual-pixel identity review on the first attempt each, with 7/7 inter-frame continuity pairs PASS and zero repair loops. Qualifying the identity reference before generation is what removed the repair-loop churn; the storyboard reviewer only needed to confirm, not correct. |
| 2026-07-18 | DECISION (future phase, not implemented): two-wave concurrent frame generation | Once the pipeline is stable, switch storyboard frame generation to a two-wave concurrent scheme — 4 start frames generated in parallel, then 4 end frames in parallel, with reviews pipelined. Full parallelism is forbidden because the continuity chain (each end frame binds to its start, each next start to the prior end) requires ordering between waves. The multiscene live smoke already proved parallel Scillm generation with per-scene namespacing, so the concurrency primitive exists; this is a scheduling change to adopt in a later phase, not now. |
| 2026-07-18 | LESSON: gates must be checked pairwise for satisfiability on the same artifact — the delta already held the answer | The step-38 lane C ran five attempts against two gates that had no overlap on one frame: a fail-closed full-frame identity reviewer needs Kai's face groundable, while the composition contract needs his mouth non-readable. No generation can satisfy both, so the loop exhausted. The resolution was not a better prompt or a bigger budget — it was already written in `step38_sb_003_composition_delta_proposal.v1.json`: the end frame set Kai's `face_required=false`, anchored to the unchanged start frame. The prior acceptance criterion (a) re-imposed the face check the delta had removed, recreating the contradiction. Implementing the delta's design as a scoped, fail-closed anchored-identity waiver (`scripts/anchored_identity_waiver.py`, 12 unit tests) made lane C PASS on the first attempt. Before burning attempts on a gate conflict, check whether the two gates can both hold on the same artifact and whether a prior decision already resolved it. A second lesson surfaced in the same run: the Embry-only end-frame review must be scoped to Embry — the shared reviewer prompt hard-requires both faces, so it re-failed over the waived, deliberately-turned-away character until scoped. A third: a genuine, pre-existing blocker (governance/audit memory records collide with the qualification prepare gate's exclusive-ownership requirement, and the Memory daemon exposes no deletion primitive) blocks requalification/rung v5; it was recorded fail-closed rather than forced by deleting audit records or weakening the gate. |

## Open Questions

- [x] Which exact `$scillm` localhost HTTP endpoint/model should the first non-mocked one-shot proof use? `POST /v1/chat/completions`, model `gpt-5.5`, `X-Caller-Skill: persona-dream`.
- [x] Two concurrent `$scillm` client calls rung (`scillm-two-concurrent`) — live PASS 2026-06-23 with overlap receipt.
- [ ] Where should the real ScillmDagHarness-backed runner live after the one-node `$scillm` proof passes?
- [ ] What is the canonical schema for streamed node events and receipts before adding concurrency or `$loop`?
- [ ] Which report generator owns `full-report.html` section restoration so manual HTML edits stop deleting work?
- [ ] Should Phase 07 panel-reviewer require a structured per-identity JSON schema with visible, matches_reference, confidence, face_visible, failure_code, and visible_evidence fields before PASS?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |
| `scripts/medium_loop_dag_smoke.py` | Local serial proof ladder (fixture, scillm-one, scillm-two-concurrent, real-gates). Not ScillmDagHarness. |
| `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/pipeline_review_8892/full-report.html` | Human/project-agent report surface served at `http://127.0.0.1:8892/full-report.html`. |
| `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/pipeline_review_8892/panel_verdicts/summary.json` | Panel-review evidence summary; last known problematic repair run reported panel 06/08/09 blocked. |
| `local/HANDOFF.md` | Current handoff for the next model; overrides older stale handoff claims. |
| `scripts/install_dag_harness_artifacts.py` | Copy latest proof dirs into ux-lab `public/scillm-dag-runs/`. |
| `docs/DAG_SMOKE_AGENT_GUIDE.md` | Required claim language for each rung. |
| `pi-mono/.../personaDreamDagEvidenceAdapter.ts` | Artifact → TransportDagEvidence adapter for harness viewer. |
| `reports/pipeline-complete/report.html` | Historical one-scene report; its old 15/15 claim is superseded and must not be used as current Phase 11 readiness evidence. |
| `reports/pipeline-complete/status.json` | Machine-readable command evidence for the complete one-scene pipeline report. |
| `reports/pipeline-complete/validation.json` | Historical report validator output; checked-in state reports 12/15 and is not a current green boundary. |
| `scripts/run_multiscene_live_smoke.py` | Real Scillm/Codex OAuth multi-scene smoke. Generates scene-scoped contact sheets and panels, writes per-scene manifests, and refuses singleton receipt collisions. |
| `scripts/validate_multiscene_live_smoke.py` | Independent validator for multi-scene live smoke receipts, image hashes, scene manifests, and Kling boundary fields. |
| `scripts/write_multiscene_live_report.py` | Source-derived HTML report generator for multi-scene live smoke receipts. |
| `reports/multiscene-live-smoke/report.html` | Latest multi-scene live smoke report generated from `/tmp/persona-dream-multiscene-live-20260630T020933Z`. |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->

## Cognitive Loop 13-15 (appended 2026-07-18)

- 2026-07-18 (cognitive loop 13-15 implemented + live-slice proven on the
  historical return): persona-dream phases 13 (self-interpretation), 14 (ToM
  validation), and 15 (dream persistence) moved from Designed to Implemented.
  Interpretive drafting uses scillm gpt-5.5; grounding is enforced by
  DETERMINISTIC code, not the LLM. Phase 13 rejects any claim that does not cite
  at least one Watch observation id AND at least one source-memory id, and (the
  honesty rule) rejects any claim that reads a proven renderer defect (identity
  DRIFT) as psychological truth instead of favoring the renderer-defect
  explanation. Phase 14 lets the LLM propose bounded ToM candidates but rejects
  any whose citations are not a subset of their parent accepted interpretation.
  Phase 15 defaults to dry-run: it emits an exact canonical would-write plan
  (dream memory doc with `synthetic_origin:true, literal_historical_event:false`;
  `derived_from` / `observed_in_scene` / `supports_interpretation` edges; a Qdrant
  embedding note) with hashes and ZERO canonical writes.
- DECISIVE BOUNDARY: a canonical dream-memory write requires
  `--allow-canonical-write` AND a non-superseded return id, and HARD-FAILS
  (exit 1) on the historical `991c311f365f` return because it is a historical
  provider return, has a DEGRADED observation status, and carries an identity
  DRIFT verdict. The write path was instead proven by 16 exact-reread-matched
  documents in the non-canonical `persona_dream_loop_validation` collection.
  Enforcement is covered by `tests/test_cognitive_loop_phases.py`
  (`test_superseded_historical_return_is_blocked_even_with_allow_flag`).
- Live loop receipt: `run_cognitive_loop.py` -> `PASS_COGNITIVE_LOOP`; artifacts
  under `.persona-dream/revisions/rev_successor_943b01ecd9a3/cognitive_loop/991c311f365f/`.
  Governance persisted (write + exact reread) to `persona_dream_governance`.
  Note: `lessons` collection rejects writes without extractable taxonomy, so
  scoped governance uses a dedicated collection.
- NOT PROVEN: this is fixture-and-live-slice proof on a SUPERSEDED historical
  return. The closed-loop research claim (Acceptance items 4-8: canonical
  persistence, Qdrant recall, multi-hop traversal, later behavior) still requires
  a freshly authorized, non-superseded successor return.

- 2026-07-19 (transaction-correctness repair loop — CLOSED PASS after 5 webgpt
  rounds): the phase-15 canonical persistence layer survived five adversarial
  review rounds, each narrowing the gate: (1) volatile created_at made every
  identical replay quarantine the valid prior commit, and the manifest wrote
  active:true unconditionally; (2) fixing (1) introduced a K0/K1 identity
  split (records stamped pre-derivation, manifest keyed post-derivation);
  (3) the returned plan hashed pre-stamp payloads that were then mutated by
  reference; (4) resume trusted the prior manifest without validating its
  record index and phase bindings; (5) PASS. LESSONS: every fix to a
  transaction layer must re-derive ALL representations (records, plan, proof,
  manifest) from ONE immutable post-stamp snapshot; compensating and
  quarantining writes must themselves be reread-verified; publication must be
  conditional on commit ownership; and an external adversarial reviewer with
  fault-injection demands found four real defect classes that 400+ green
  self-authored tests did not. Receipts: commits 2e3d2837, 4511b4a0,
  c8a71b9c, 7c517c8e; ruling PASS in
  review-bundles/manifest_replay_validation_reassess_20260719-assess-response.md;
  governance record persona_dream_transaction_gate_closed_20260719 (exact
  reread PASS).

- 2026-07-19 (roadmap converged): 2-round webgpt iteration produced the
  controlling ROADMAP r2 (round 1 PLAN_REVISED: validity-first reordering,
  voice lane and authority convergence ahead of the pilot, clean-room
  envelope + intervention ledger ahead of repeatability, concurrency struck
  from first replication; round 2 PLAN_STABLE). Round 1 also caught a live
  authority contradiction: CURRENT_STATE pinned pilot protocol v1 while the
  pilot runs under v2 — fixed pre-run. LESSON: iterate plans, not just code,
  through the external reviewer; a plan draft carries defects the same way a
  transaction layer does.

- 2026-07-22 (PCTOM-R objective evidence audit): top-level research progress
  must be bound to the same current receipt bundle, not inferred from a
  Git commit or from older success/coverage receipts. The
  `check-pctom-objective-evidence` command now requires the expanded
  15-id goal coverage receipt and the success-criteria receipt to reference
  each other by exact path and receipt SHA-256. It also maps the active
  objective clauses to named coverage ids and fails closed on stale success
  receipts, stale coverage receipts, missing unsupported-evidence abstention
  coverage, or missing fail-closed negative coverage.

- 2026-07-22 (PCTOM-R provider/video critical-path audit): do not represent
  provider/video exclusion as a constant in a top-level audit. The
  `check-pctom-objective-evidence` command now recomputes that boundary from
  `does_not_prove` claims and recursive side-effect counter scans over the
  success receipt, goal-coverage receipt, and every child receipt referenced by
  goal coverage. A copied coverage receipt or copied child receipt with
  `actual_provider_call_attempts=1` makes the objective audit block with
  `provider_video_not_critical_path=false`.

- 2026-07-22 (PCTOM-R objective receipt-integrity audit): top-level receipts
  supplied to `check-pctom-objective-evidence` must self-hash under the stable
  JSON receipt convention. Child receipts are historical and some lack valid
  internal `receipt_sha256`, so the enforceable child invariant is the
  goal-coverage evidence row's `file_sha256`: the child file currently at that
  path must match the hash captured when goal coverage was built. Top-level
  receipt tamper and child-file tamper now both fail closed.

- 2026-07-22 (PCTOM-R autonomous judgment audit): do not treat the
  `autonomous_no_human_judgment` coverage id as sufficient by itself. The
  objective audit now recomputes the autonomous boundary from all coverage
  evidence rows: `human_content_judgment_required` must not be true,
  `llm_judge_used` must not be true, and `mocked` must be false on every row.
  Row-level tamper for either human judgment or LLM judge usage blocks the
  objective audit.

- 2026-07-22 (PCTOM-R fail-closed negative evidence audit): do not treat the
  aggregate negative count as sufficient by itself. The objective audit now
  recomputes the fail-closed boundary from the negative coverage evidence rows:
  each row must be `kind=negative`, have `BLOCKED_` status, be non-mocked, and
  avoid human content judgment and LLM judge usage. Changing negative rows to
  `PASS_` or `mocked=true` blocks the objective audit.

- 2026-07-22 (PCTOM-R objective clause evidence audit): do not treat coverage-id
  presence as enough to satisfy an active objective clause. The objective audit
  now derives clause truth from row-level positive/negative evidence counts:
  Gate 0/1/2/4/5/7 clauses require positive evidence, unsupported-evidence
  abstention requires both positive and negative evidence, and fail-closed
  reliability requires positive Gate 8/Gate 9/fail-closed coverage plus
  fail-closed negative rows. Tampering `gate4_sealed_prediction_commitments`
  to `positive_evidence=0` or `unsupported_evidence_abstention` to
  `negative_evidence=0` blocks the objective audit with clause-specific errors.

- 2026-07-22 (PCTOM-R expanded objective clauses): the objective audit now also
  exposes `counterfactual_branches_synthetic`, `action_selection_planning`,
  `cross_stage_hash_lineage`, and `memory_retention_and_recall` as named
  objective clauses instead of leaving them only as required coverage ids.
  Tampering `gate6_action_selection_planning` to `positive_evidence=0` blocks
  with `objective_clause_not_proven:action_selection_planning`.

- 2026-07-22 (PCTOM-R success-criteria input integrity): the success-criteria
  audit now requires every supplied input receipt to self-hash and recursively
  scans each input for provider/canonical-memory/identity/source-memory side
  effect counters. The sealed-test statistical-confidence producer now emits
  `receipt_sha256` so its prediction-benefit receipt can pass this boundary.
  A stale prediction self-hash blocks with
  `prediction_receipt_sha256_self_mismatch`; a nested
  `debug_nested_counter_fixture.provider_calls=1` blocks even when the tampered
  input receipt has a recomputed self-hash.

- 2026-07-22 (PCTOM-R goal-coverage evidence identity): the goal-coverage audit
  now requires every evidence receipt to be identity-bound by either a matching
  internal `receipt_sha256` or an explicit manifest `expected_file_sha256`
  matching the current file. Legacy child receipts with stale self-hashes are
  no longer accepted unless the manifest binds their file hash. The audit also
  recursively scans each evidence receipt for provider/canonical-memory/
  identity/source-memory side-effect counters; a nested `provider_calls=1`
  blocks even when the tampered file is hash-bound in the manifest.

- 2026-07-22 (PCTOM-R Gate 0 branch-to-prediction lineage): the Gate 0 checker
  now requires each sealed prediction evidence residue to be carried by at
  least one dream branch referenced by that same prediction. It no longer
  accepts a prediction that separately names a residue and separately names a
  branch when the named branch does not carry that residue. Gate 0 and live
  Gate 0 bridge receipts now emit `receipt_sha256`; the live bridge also
  records file hashes for its live-memory and Gate 0 child receipts.
