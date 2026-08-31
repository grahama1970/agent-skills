# Handoff Report: persona-dream

**Timestamp**: 2026-08-28T12:20:17Z
**Active Agent**: Codex GPT-5
**Immutable Goal**: NOT_MET
**Prior file note**: supersedes the 2026-08-22 handoff; that version is still
recoverable from git history.

## 1. Project Overview

- **Ecosystem**: Python 3.12, `uv`, Typer-style `run.sh` commands, Tau DAG
  execution, Graph Memory/Arango/Qdrant persistence, Chatterbox voice, Whisper
  ASR, and React/Vite inspection surfaces.
- **Core purpose**: determine through preregistered, falsifiable, fail-closed
  experiments whether provenance-bound synthetic dreaming adds measurable value
  over direct memory and structured reflection, while preserving identity,
  factual competence, answer content, and the synthetic-versus-literal boundary.
- **Amended operational goal**: in a paired Horus/Embry run, test whether a
  synthetic dream plus Embry's journal/reflection about that dream can introduce
  one bounded emotional conflict and measurable Chatterbox delivery changes
  during a dynamic conversation, while the factual answer body and protected
  identity/provenance boundaries remain unchanged relative to a
  structured-reflection control.

## 2. Current State

- **Research phase**: `P2_CORRECTED_GOAL_PAIR_PROOF`.
- **Plain-language boundary**: The loop is complete and runnable for the
  corrected paired technical proof. Not proven: the research benefit itself,
  human-perceived emotional value, human listener identity, or production-scale
  reliability.
- `GOAL.md` is the controlling goal text. It explicitly says the project is not
  merely a Kling/video project, dashboard project, GitHub-status project, or a
  goal to prove dreaming works.
- `CURRENT_STATUS.json` reports `current_phase:
  P2_CORRECTED_GOAL_PAIR_PROOF`.
- `./run.sh check-current-state-consistency --strict` on 2026-08-28 returned:
  `PASS_CURRENT_STATE_CONSISTENT`, `9 stages checked`, `0 mismatches`.
- The strongest current technical proof is:
  `skills/persona-dream/local/proofs/pd-corrected-goal-v1/live-pair-20260822T170000Z/corrected_goal_receipt.json`
  with status `PASS_CORRECTED_GOAL_PAIRED_PROOF`, `mocked=false`,
  `live=true`, and gates:
  `PASS_ANSWER_INVARIANCE`, `PASS_EMOTION_LINEAGE`,
  `PASS_CHATTERBOX_DELIVERY`.
- The strongest full-cycle harness proof is:
  `skills/persona-dream/local/proofs/pd-corrected-goal-v1/full-cycle-live-20260822T223907Z/agentic_eval_report.json`.
  `CURRENT_STATUS.json` records `readiness=READY`, `case_count=1`,
  `trial_count=3`, `passed_trials=3`, and each trial stdout contained
  `FULL_CYCLE_OK stages=7` and `conversation:3_pairs_all_voiced`.
- Proof boundary from the status file: the 3-trial full-cycle harness supports
  the local pipeline claim after #1495/#1496. It does not prove 35-cycle
  no-restart reliability, human-perceived emotional value, human listener
  identity, separate mediation by dream versus journal, or production
  readiness.

## 3. Implemented Versus Missing

1. **Implemented**: paired corrected-goal live proof exists for answer
   invariance, emotion lineage, and Chatterbox delivery movement.
2. **Implemented**: `fixtures/agentic_eval.json` contains 37 cases, including
   `full-cycle-live`, `corrected-goal-live-pair-gate-readback`,
   `horus-embry-audible-conversation-live`, and spoken-journal spine checks.
3. **Implemented**: Horus and Embry are both treated as first-person live
   Chatterbox voices in the dynamic-conversation path; Embry-only output is not
   the intended conversation proof.
4. **Implemented**: `unlazy` now has a receipt-boundary validator and schemas on
   `origin/main` in commit `44f563f4d720d76e1a1a261d073420fcd7130cb8`.
5. **Missing**: `unlazy` is not yet wired into `project-watchdog`,
   `monitor-herdr`, `ops-herdr`, Tau, or persona-dream goal closure. It is a
   usable skill, not yet an enforced closure gate for this project.
6. **Missing**: no `project_watchdog.goal_completion.v1` receipt exists that
   closes persona-dream's immutable goal.
7. **Missing**: blinded human listener evidence. `CURRENT_STATUS.json` says
   `human_perceived_emotion_and_identity` is
   `AWAITING_HUMAN_LISTENER_COLLECTION`, with `valid_human_responses: 0/20`,
   and missing `SIGNED_INTERPRETATION.json`.
8. **Missing**: held-out PCTOM-R benefit comparison. `pctom_heldout_benefit`
   is `UNPROVEN` with `sample_count: 0`.
9. **Missing**: 35+ consecutive no-restart continuity soak. The current status
   says `p2_continuity_reliability_soak` is `PLANNED_NOT_RUN`,
   `sample_count: 0`.
10. **Missing unless explicitly reactivated**: Kling/provider video execution.
    `GOAL.md` says current completion does not require more Kling videos, but
    the human has also said that every pipeline step, including journal
    post-dream creation with Kling, is nonoptional. Treat this as an alignment
    hazard: before any closure claim, the active acceptance ledger must say
    whether Kling/media is a hard gate for the current run.

## 4. What Is Working Well

- The current-state surfaces agree with receipts under
  `check-current-state-consistency --strict`.
- The corrected-goal proof does test the thing the human corrected: dream plus
  journal creates bounded conflict/emotion while preserving the answer body.
- The full-cycle live agentic eval recorded three live trials through day
  ingest, Tau dream spine, journal render, spoken journal, memory/artifact
  write, dynamic Horus/Embry conversation, and carry-back.
- The agentic eval fixture includes adversarial guards against common bypasses:
  missing crew casting, missing live artifacts, and journal/audio spine drift.
- The Chatterbox constraint is now written in `SKILL.md`: dream emotion can only
  reliably travel through intensity and tempo on the current base affect path;
  invented inline tags must not be added because base speaks them literally.

## 5. What Is Broken, Blocked, Or Unproven

- **Human perception is not proven**: there are no 20 valid listener rows and no
  signed interpretation.
- **Research benefit is not proven**: the repaired PCTOM apparatus can measure,
  but held-out benefit has not been run.
- **Reliability is not proven at production scale**: three full-cycle trials and
  the older N=5 pilot are not the 35+ no-restart campaign.
- **Goal closure is not receipt-gated**: `unlazy` can validate receipt shape, but
  persona-dream has not been wired to require it through watchdog/Herdr/Tau.
- **Ask/WebGPT evidence is incomplete**: a one-shot review bundle was prepared
  at `/tmp/persona-dream-unlazy-one-shot-context-20260827.md`, and Claude Fable
  returned a live answer, but the WebGPT lane did not submit. The ask wrapper
  also reported both lanes as failed despite the Claude node receipt showing
  `status=PASS`, `live=true`, and `provider_live=true`. That is an `$ask`
  aggregation/reporting defect, not persona-dream proof.
- **Provider/Kling path remains hazardous**: panel/Kling work must pass
  `PASS_PANEL_REVIEWED`, provider-media eligibility, public media URL, voice ID,
  callback/polling, cost/entitlement, and approval gates before paid live
  submission. Local files alone are not provider-ready media.
- **UI story/script draft endpoints are still absent**:
  `/api/tau/dream/*` has no server implementation according to the previous
  handoff; do not treat the workspace buttons as operational until this is
  rechecked and repaired.

## 6. Remaining Steps To Achieve The Immutable Goal

1. **Re-anchor the acceptance ledger**: create or update a machine-readable
   persona-dream goal ledger that encodes the amended operational chain:
   dream residue, dream packet, Embry journal/reflection, bounded conflict,
   bounded session mood/arc delta, live Horus voice, live Embry voice,
   unchanged answer body, Chatterbox delivery movement, synthetic provenance,
   and closure receipt path.
2. **Add the unlazy/watchdog gate**: require `skills/unlazy/run.sh
   receipt-check` before any watchdog closure of persona-dream. The acceptance
   reference must name exact persona-dream receipts, expected statuses, mocked
   flags, live flags, and forbidden closure-from-prose conditions.
3. **Run the current persona-dream agentic eval case set that maps to the
   amended goal**: at minimum `corrected-goal-live-pair-gate-readback`,
   `horus-embry-audible-conversation-live`, spoken-journal spine checks, and
   `full-cycle-live` if the services are available. Record the report path.
4. **Play/read back the produced Horus/Embry conversation artifacts**: locate
   the current full-cycle run directories from the eval report, confirm each
   conversation has both speakers, confirm audio files exist, and use local
   playback only after artifact checks pass.
5. **Resolve the Kling acceptance conflict**: if the current human requirement
   is that Kling media is mandatory for closure, update the goal ledger and
   run the provider path only through the existing provider gates. Do not hand
   compose panels, prompts, voice IDs, provider payloads, or callbacks.
6. **Collect or explicitly defer human listener evidence**: #1058 cannot be
   analyzed until `responses_v2.jsonl` has 20 valid human rows and
   `SIGNED_INTERPRETATION.json` exists. The agent cannot fabricate these.
7. **Run the held-out PCTOM-R benefit comparison**: #1008 remains the research
   benefit lane after measurement validity was repaired.
8. **Run the 35+ no-restart reliability campaign if production-level continuity
   reliability is part of closure**: do not upgrade 3/3 full-cycle or N=5 pilot
   results into this claim.
9. **Emit the final watchdog receipt only after all active gates pass or have an
   explicit falsifiable disposition**: closure should be a local
   `project_watchdog.goal_completion.v1` receipt, then checked by `unlazy`.

## 7. Where Agents Have Been Confused

1. **Confusing the goal with a positive outcome**: the immutable goal asks for
   an honest experimental disposition. It does not require proving dreams win.
2. **Confusing Embry continuity with the top-level objective**: Embry continuity
   is a safety constraint and test subject lane under the research goal.
3. **Confusing a working full-cycle proof with total closure**: the 3-trial
   full-cycle live eval is real evidence, but its own boundary excludes human
   perception, separate mediation, 35-cycle reliability, and production
   readiness.
4. **Confusing prose instructions with enforcement**: hooks, `AGENTS.md`, and
   `SKILL.md` help only if backed by harness checks. `unlazy` should become the
   machine gate that refuses closure claims lacking receipts.
5. **Confusing dynamic conversation with Embry monologue**: the required audible
   conversation is Horus and Embry, both first-person voices, discussing
   Embry's dream, mood, and feelings.
6. **Confusing Chatterbox tags with affect delivery**: Turbo handles the native
   tags, but base affect makes invented tags literal speech. Current dream mood
   proof should use intensity and tempo unless Chatterbox provides a new receipt.
7. **Confusing panel/Kling prep with provider eligibility**: accepted-looking
   images, work orders, or local paths do not satisfy provider readiness without
   the provider gate receipt.
8. **Confusing WebGPT/Claude review with local proof**: reviewer advice can
   guide ticket creation, but closure requires local receipt artifacts and
   command readbacks.

## 8. Project Context For The Next Agent

- Read first: `GOAL.md`, `CURRENT_STATUS.json`, `SKILL.md`,
  `fixtures/agentic_eval.json`, `PROJECT_KNOWLEDGE.md`, this handoff.
- Useful commands:
  - `cd skills/persona-dream && ./run.sh check-current-state-consistency --strict`
  - `jq '.latest_full_cycle_live_eval' skills/persona-dream/CURRENT_STATUS.json`
  - `jq '.corrected_goal_pair_proof' skills/persona-dream/CURRENT_STATUS.json`
  - `jq '.cases[] | select(.name=="full-cycle-live")' skills/persona-dream/fixtures/agentic_eval.json`
  - `skills/unlazy/run.sh receipt-check --help`
- Do not stop at a status report while an agent-owned next step remains. The
  next agent-owned step is to wire the goal ledger and unlazy/watchdog closure
  gate, then rerun the mapped persona-dream eval cases and preserve the receipt.

## 9. Current Stop Condition

- `mocked: no` for the status consistency readback and the existing recorded
  corrected-goal/full-cycle receipts.
- `live: yes` for the existing recorded corrected-goal/full-cycle receipts.
- `live: no` for this handoff edit itself; it is documentation and planning
  state, not pipeline execution.
- The immutable goal remains unmet until the active acceptance ledger is
  receipt-gated and either all required live gates pass or the project records a
  falsifiable negative/null disposition with local receipts.

Immutable Goal: NOT_MET
