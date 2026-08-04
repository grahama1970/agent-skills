# Persona Dream — evidence and proof boundary

This is the audit surface for [Persona Dream](../README.md): what has been
proven, what has not, and which receipt earns each claim. It is deliberately
separate from the README, which is for people trying to understand what the
project is.

Machine state lives in [`../CURRENT_STATUS.json`](../CURRENT_STATUS.json), which
is the authority; the current-state block below is generated from it.

## How to read the evidence

- `#1127` did what it was built to do when it detected a stimulus confound; it
  was not a failed implementation.
- Measurement validity is not a PCTOM benefit result.
- The listener study's stimuli were rejected as technically confounded; the
  study is not merely waiting for raters.
- Read [Current Proof Boundary](#current-proof-boundary) before interpreting any
  reported number, and use [`CURRENT_STATUS.json`](CURRENT_STATUS.json) for the
  current checked state.

## Current state

Phase **P2_LIVE_CONTINUITY_CHAIN**. The digest below is generated from
`CURRENT_STATUS.json`, which holds the authoritative blockers, next step, and
every figure. `./run.sh check-current-state-consistency --strict` fails if this
file drifts from it.

| Lane | Implemented and receipted | Not proven |
|---|---|---|
| Continuity ledger | Atomic writes, epoch compare-and-set, cycle idempotency, identity-core guard | Runtime authority across real sessions |
| Session mood | Deterministic mood bound before turn 1, stable across three turns, answer text preserved | Behavior beyond local live receipts |
| Chatterbox voice | Live render at ASR WER 0.0 with durable snapshots; Embry reads her own journal aloud (#1208) | That the requested tone is audible at all — measured below the renderer's own noise floor (#1209). Perceived emotion, naturalness, human acceptance |
| Speaker recognition | Machine separation under two named render conditions; neither value is a universal threshold | Human recognition; cross-mood identity (#1130) |
| Joined live chain | One fresh cycle joins dream evidence through to recognition, 13/13 negative controls blocked | Perceived emotion; behavior beyond local receipts |
| Session arc bias | Bounded deltas published under a hash-bound consumer contract, consumed live by SPARTA before turn 1 | Human-perceived emotion; deployed production behavior |
| Reliability pilot | Five live cycles passed, zero duplicate accepted effects — a feasibility pilot | Production reliability (#1128); restart/recovery (#1129) |
| Blinded listener study | V2 preregistration, counterbalanced raters, and a neutral-repeat technical screen | Stimuli rejected as technically confounded; #1179 must re-render before #1058 |
| PCTOM-R | Measurement validity passes on a non-degenerate corpus; the treatment can lose | No held-out benefit result (#1008) |
| Historical media loop | One accepted dream persistence path and provider return | Repeatability; previous-video causality |

Figures, receipt paths, and revision ids are in
[`CURRENT_STATUS.json`](CURRENT_STATUS.json) and
[`docs/verification.md`](docs/verification.md).


<!-- BEGIN GENERATED CURRENT RESEARCH STATE -->

*Generated from `CURRENT_STATUS.json` by `scripts/generate_readme_research_state.py`;
run `./run.sh generate-readme-research-state`. Full claim dispositions live in
the JSON, not here.*

- **Phase:** `P2_LIVE_CONTINUITY_CHAIN`
- **Open claims:** #1008 (PCTOM-R held-out benefit), #1179 (Blinded listener study), #1128 (Continuity reliability soak), #1129 (Restart / recovery), #1212 (daily_event_ingestion)
- **Current blocker:** Listener-study stimuli are rejected as technically confounded (BLOCKED_STIMULUS_TECHNICAL_CONFOUND, #1127); #1179 must re-render all four conditions…
- **Next step:** Re-render the four listener-study conditions under one identical normalization (#1179) and rerun the frozen technical screen unchanged.

<!-- END GENERATED CURRENT RESEARCH STATE -->

## Current Proof Boundary

This is a research prototype. Nothing below is a product claim, and the
vocabulary is deliberately narrow: **implemented** means code exists,
**fixture-proven** means deterministic checks pass with no live behavior implied,
**live slice proven** means a real external operation ran and was inspected, and
**blocked** means a named prerequisite is missing.

| Boundary | State | Where the evidence lives |
|---|---|---|
| Grounded dream packets | Implemented | `reports/` run receipts |
| Image and storyboard production | Live slice proven | `reports/` panel and review receipts |
| Phases 01-10, qualified revision | Qualified revision | [`docs/verification.md`](docs/verification.md) |
| Phase 11, submit and return | Live return accepted at agent level; human acceptance open | [`docs/verification.md`](docs/verification.md) |
| Phase 12, Watch observation | Live slice proven on historical return; packet degraded on successor | [`docs/verification.md`](docs/verification.md) |
| Phases 13-15, interpretation to persistence | Live slice proven on the accepted return | [`docs/verification.md`](docs/verification.md) |
| Phase 16, recall and later behavior | Machine-decidable slice live-proven | [`docs/verification.md`](docs/verification.md) |
| Chatterbox voice expression | Blocked: stimuli rejected as technically confounded | [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md), #1179 |
| Readable journal artifact | Implemented and hash-bound | `reports/goal_v5/journal/JOURNAL_RENDER_RECEIPT.json` |
| Spoken journal | Live slice proven | `reports/goal_v5/journal/JOURNAL_AUDIO_RECEIPT.json` |
| Requested tone to measurable acoustic effect | **Disproven**: below the renderer's own stochastic spread | `reports/goal_v5/journal/TONE_EFFECT_RECEIPT.json`, #1209 |
| Journal page | Live slice proven: rendered in Chrome at 1440x900, footnotes resolve, audio loads | `reports/goal_v5/journal_ux/BROWSER_PROOF_RECEIPT.json` |
| Interactive dream discussion | Append-only writer live-proven; return into memory blocked upstream | `reports/goal_v5/conversation/CONVERSATION_APPEND_RECEIPT.json` |
| Day events to a later dream | Not established; blocked upstream on memory-service recall | #1212 |
| PCTOM-R held-out benefit | Not run | [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md), #1008 |

Revision ids, request hashes, receipt paths, and the per-phase narrative are in
[`docs/verification.md`](docs/verification.md). Current machine state is in
[`CURRENT_STATUS.json`](CURRENT_STATUS.json).

## Next workflow steps

Not in Quick Start because they are not finished. Each is one open join in the
journal loop:

| Step | Command | Blocked on |
|---|---|---|
| Write the day into memory | `./run.sh ingest-day --date <d> --from-commits` | #1212 — recall discards `scope`, and stored documents are not retrievable |
| Keep the discussion | *(no writer yet)* | #1210 |
| Verify the page in a browser | *(no capture yet)* | #1213 |

## PCTOM-R, and why its numbers are not a result

PCTOM-R asks whether counterfactual dreaming improves *prospective* Theory of
Mind — predicting what another agent will do — beyond what direct memory gives.

The machinery is strong and the receipt counts are large. Neither fact is a
finding. Receipt volume measures the reliability of the experiment apparatus
within its text-first scope; it does not measure benefit. Until a preregistered
proper-scoring or planning-regret metric separates CD from the strongest M/R/D
baseline on a held-out slice, PCTOM-R has no result to report.

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
- Claims here are retired only by a named receipt read back from disk.

## Ownership boundaries

Persona Dream owns the dream packet, continuity ledger, session-mood binding,
and the receipts that join them. It does **not** own: Graph Memory (persistence
and recall), Watch (observation and adjudication), Tau (model routing and
creator/reviewer loops), Kling and other providers (media generation),
Chatterbox (speech synthesis), or the voice-evaluation lane (speaker backends).
Each has its own proof boundary; Persona Dream may cite their receipts but may
not restate their guarantees. See [Technical Architecture](#technical-architecture).

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
2. **Experimental subject** — Embry is the test case, not the objective.
   "Build Embry" would assume the mechanism works.
3. **Safety contract** — preserve identity, factual competence, answer content,
   and evidence classes. These are validity constraints, never conclusions. See
   the Persistent-Persona Safety Hypothesis in [`GOAL.md`](GOAL.md).
4. **Transfer contract** — move validated mechanisms and failure lessons into
   Graph Memory Operator, Tau, SPARTA, and Chatterbox. Recorded per experiment
   in [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md).
5. **Product decision** — adopt, constrain, simplify, or retire each mechanism
   on the evidence. Deletion is a goal-serving action here.

**PCTOM-R** (Prospective Counterfactual Theory of Mind) is the research
workstream under item 1: does imagining what did *not* happen improve
predictions about what another agent *will* do? Issue #1131 tracks the
measurement-validity repair that lets the treatment lose; that repair is not
evidence of benefit. The held-out result is tracked by #1008. Current state is
in [`CURRENT_STATUS.json`](CURRENT_STATUS.json).

**Kling, Watch, Memory, Chatterbox, and Tau** are supporting lanes. Their
transfer decisions live in [`TRANSFER_LEDGER.md`](TRANSFER_LEDGER.md). This
project does not have to become a production product to be complete.

