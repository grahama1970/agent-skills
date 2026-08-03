# Persona Dream

![Persona Dream card](../../docs/assets/project-cards/persona-dream.webp)

Persona Dream gives a persistent multimodal voice persona — a long-lived agent
with durable memory, a stable character, and access to text, images, audio, and
video — a controlled way to turn experience into a synthetic dream and examine
what comes back.

> **Does letting an AI persona dream about what has happened to it actually help
> — more than plainly remembering or reflecting — and is it still recognizably
> itself afterwards?**
>
> "No" is a real answer, and finding it is success.

This is not a movie generator. The dream is an **inspectable intermediate
representation** whose every conclusion stays linked to the supporting memories
and media; a dream may influence later reasoning, but it may never silently
become literal history or rewrite identity.

## Start here

I use this README as the durable research map, not as a status log. Choose the
authoritative entry point for the question you have:

| You need | Go to |
|---|---|
| Run the smallest local workflow | [Quick Start](#quick-start) |
| Inspect the executable runtime contract | [`SKILL.md`](SKILL.md) |
| Check current machine state, blockers, and next step | [`CURRENT_STATUS.json`](CURRENT_STATUS.json) |
| Check what is and is not proven | [Current Proof Boundary](#current-proof-boundary) and [What this project does not claim](#what-this-project-does-not-claim) |
| Read the immutable goal and gate sequence | [`GOAL.md`](GOAL.md) |
| Resume operational work | [`local/HANDOFF.md`](local/HANDOFF.md) |
| Review forensic chronology or superseded findings | [`PROJECT_KNOWLEDGE.md`](PROJECT_KNOWLEDGE.md) |
| Inspect transfer decisions | [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md) |
| Inspect per-run evidence | revision-scoped receipts under `reports/` |

## How to read the evidence

- `#1127` did what it was built to do when it detected a stimulus confound; it
  was not a failed implementation.
- Measurement validity is not a PCTOM benefit result.
- The listener study's stimuli were rejected as technically confounded; the
  study is not merely waiting for raters.
- Read [Current Proof Boundary](#current-proof-boundary) before interpreting any
  reported number, and use [`CURRENT_STATUS.json`](CURRENT_STATUS.json) for the
  current checked state.

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

## The controlling hierarchy

The immutable goal is registered with `$goal-drift` (source `human_prompt`) and
read back with `skills/goal-drift/run.sh goal --project persona-dream`. That
registry, not this file, is the authority.

1. **Research goal** — determine, through preregistered, falsifiable,
   fail-closed experiments, whether provenance-bound synthetic dreaming adds
   measurable value over direct memory and structured reflection. **A loss, a
   tie, or a null result is a completed result.** The goal is to learn whether
   the mechanism earns its complexity, not to prove that it succeeds.
2. **Experimental subject** — Embry is the primary persistent-persona test case.
   "Build Embry" is deliberately *not* the top-level objective; that framing
   assumed the mechanism works and rewarded churn in pursuit of a predetermined
   success.
3. **Safety contract** — preserve identity, factual competence, answer content,
   and evidence classes. These are validity constraints, never conclusions. See
   the Persistent-Persona Safety Hypothesis in [`GOAL.md`](GOAL.md).
4. **Transfer contract** — move validated mechanisms and failure lessons into
   Graph Memory Operator, Tau, SPARTA, and Chatterbox. Recorded per experiment
   in [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md).
5. **Product decision** — adopt, constrain, simplify, or retire each mechanism
   on the evidence. A component that fails a controlled ablation is removed or
   constrained; deletion is a goal-serving action.

**PCTOM-R** (Prospective Counterfactual Theory of Mind) is the research
workstream under item 1: does imagining what did *not* happen improve
predictions about what another agent *will* do? Its apparatus was repaired
Issue #1131 tracks the measurement-validity repair that allows
the treatment to lose; that repair is not evidence of benefit. The held-out
result is tracked by #1008; use [`CURRENT_STATUS.json`](CURRENT_STATUS.json) and
the revision-scoped receipts under `reports/` to determine its current state.
**Kling, Watch, Memory, Chatterbox, and Tau** are supporting lanes. Their
transfer decisions live in [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md).

This project does not have to become a production product to be complete.

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
| Session mood | Deterministic mood bound before turn 1, stable across three turns, answer text preserved | Deployed production behavior beyond local live receipts |
| Chatterbox voice | Live `/synthesize-batch` render of the mood envelope, strict ASR WER 0.0, durable WAV snapshots | Perceived emotion, naturalness, human acceptance |
| Speaker recognition | Condition-scoped resemblyzer receipts only — joined live-chain three-turn renders (4.64-5.32s) separation 0.159977 (`reports/goal_v5/continuity/live_chain/voice_recognition/RECEIPT.json`); long 4.68-6.0s renders separation 0.208427 (`reports/goal_v5/continuity/session_mood_voice_recognition_long_identity/RECEIPT.json`); neither value is a universal threshold | Human listener recognition, perceived emotion, naturalness, cross-mood identity (#1130) |
| Joined live chain | One fresh cycle id, `live_chain_20260729t130950z`, joins accepted dream evidence -> Watch binding -> journal -> ledger delta -> pre-turn session mood -> three live Chatterbox turns -> Embry recognition, with 13/13 negative controls blocked | Perceived emotion; deployed production behavior beyond local live receipts |
| Session arc bias | `session_arc_bias.v1` publishes bounded deltas from the latest ledger arc, `intensity_delta=0.18`, `valence_delta=-0.18`, with no tone category; `sparta_arc_bias_handoff/SPARTA_CONSUMER_CONTRACT.json` binds the SPARTA consumer contract; `grahama1970/sparta@2fe1a67221da4b5f07d32b9136f4578f38d4e716` locally consumed that artifact before turn 1 and preserved answer text/tone category across three turns | Human-perceived emotion; deployed production behavior beyond the local live API receipt |
| Reliability pilot | Five fresh live-chain cycles passed in `reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json`: 5 attempted, 5 completed, 5 passed, duplicate accepted effects 0, Wilson 95% lower bound 0.565509 — a downstream P2 engineering pilot, not production or full Phase 01-16 pipeline reliability | Production reliability (no-restart soak, #1128); restart/recovery study (#1129) |
| Blinded listener study | V2 preregistration, counterbalanced rater surface, response validation, ASR verification, and neutral-repeat technical screen | Existing four stimuli rejected as `BLOCKED_STIMULUS_TECHNICAL_CONFOUND`; #1179 must re-render and pass the frozen screen before #1058 human collection. No perceptual emotion, identity, or naturalness result |
| Historical media loop | One accepted canonical dream persistence path and provider return | Repeatability; previous-video attachment causality |
| PCTOM-R | Measurement-validity-v2 passes on a non-degenerate corpus; mixed truth labels, episode-conditioned distributions, sealed commitments, and valid CD losses | No live held-out benefit result; #1008 must determine whether CD beats, ties, or loses to the strongest baseline |

The active voice gate is **#1179**: re-render all four listener-study
conditions under one identical normalization policy and rerun the frozen
technical-confound screen. Human collection must not begin unless that screen
passes. Cross-mood machine identity remains under #1130; perceived emotion,
identity, and naturalness remain under #1058.

```text
#1179 re-render all four conditions identically
-> rerun unchanged technical-confound screen
-> #1130 cross-mood machine identity
-> #1058 blinded human listener study
```

**#1131 is closed:** the PCTOM-R corpus and estimator now pass
measurement-validity-v2 and can produce treatment losses. This validates the
apparatus only. **#1008 owns the live held-out condition-benefit result**, which
does not yet exist; no evidence currently shows that counterfactual dreaming
helps.

SPARTA has a local live API receipt at
`grahama1970/sparta@2fe1a67221da4b5f07d32b9136f4578f38d4e716` showing the
current `session_arc_bias.v1` artifact was applied before turn 1, reused across
three turns, preserved answer text and tone category, and fell back to neutral
when no artifact was supplied.

<!-- BEGIN GENERATED CURRENT RESEARCH STATE -->

*Generated from `CURRENT_STATUS.json` by `scripts/generate_readme_research_state.py`;
run `./run.sh generate-readme-research-state`. Full claim dispositions live in
the JSON, not here.*

- **Phase:** `P2_LIVE_CONTINUITY_CHAIN`
- **Open claims:** #1008 (PCTOM-R held-out benefit), #1179 (Blinded listener study), #1128 (Continuity reliability soak), #1129 (Restart / recovery), #1059 (Previous-video causality)
- **Current blocker:** Blinded Chatterbox listener-study stimuli are present, ASR-verified, and available through a static blinded rater page; the analysis guard still blocks without enough valid human rows plus signed human interpretation, s…
- **Next step:** Collect the blinded Chatterbox listener-study responses and signed interpretation; do not substitute LLM/self-ratings. Defer PCTOM-R unless the operator reprioritizes the research workstream.

<!-- END GENERATED CURRENT RESEARCH STATE -->

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
- deployed production behavior beyond the local live SPARTA API receipt;
- perceived emotion, naturalness, or human acceptance of synthesized speech;
- that a human listener recognizes Embry;
- a confidence-bounded PCTOM-R planning advantage;
- that attaching a previous video causally improves continuity.

Claims here are retired only by a named receipt read back from disk.

---

## Research detail

The settled research goal and gate sequence live in [`GOAL.md`](GOAL.md).
Detailed hypotheses, protocols, and workstream descriptions live in
[`docs/research.md`](docs/research.md). For current checked state, use
[`CURRENT_STATUS.json`](CURRENT_STATUS.json).

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

## Pipeline detail

The numbered 01-16 stage contract, inputs, outputs, and operator notes live in
[`docs/pipeline.md`](docs/pipeline.md). Use [`SKILL.md`](SKILL.md) for the
executable runtime contract.

## Embry and Kai: Example workflow, not a benefit result

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

## Interface walkthrough

The full control-by-control interface walkthrough lives in
[`docs/interface-walkthrough.md`](docs/interface-walkthrough.md).

## Technical architecture

The detailed component and data-flow design lives in
[`docs/architecture.md`](docs/architecture.md). The bounded-loop section above
is the README-level architecture.

## Verification detail

Commands, expected outputs, artifact schemas, and acceptance procedures live in
[`docs/verification.md`](docs/verification.md). The current claim boundary
remains in [Current Proof Boundary](#current-proof-boundary), and per-run
evidence remains under `reports/`.

## References

- [`SKILL.md`](SKILL.md) - current operational contract
- [`create-persona`](../create-persona/SKILL.md) - persona authority and identity-consistency validation
- [`memory`](../memory/SKILL.md) - Memory First, multimodal recall, ToM, and persistence contract
- [`watch`](../watch/SKILL.md) - evidence-first dream-media perception
- [`create-movie`](../create-movie/SKILL.md) - downstream polished media lane
- [Graph Memory Operator](https://github.com/grahama1970/graph-memory-operator) - graph, retrieval, and persistence implementation
- Nested creative helpers live under `skills/persona-dream/skills/`.
