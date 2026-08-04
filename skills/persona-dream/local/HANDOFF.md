# Handoff Report: Persona Dream

**Timestamp:** 2026-07-29T18:25:00Z
**Active Agent:** Codex
**Repository:** `grahama1970/agent-skills`
**Target Branch:** `main`
**Worktree Used:** `/home/graham/workspace/experiments/agent-skills-issue1117-persona-dream-main`
**Base Commit Before This Slice:** `cdf8f91425e29ecfb92806ab47ef3fb40a361cc7`
**Immutable Goal:** `NOT_MET`

## 1. Project Overview

- **Ecosystem:** Python skill in `agent-skills`, with receipt-backed continuity,
  Memory/Tau/Watch/Kling historical lanes, and Chatterbox voice integration.
- **Core Purpose:** Build and verify Embry as a persistent persona whose
  explicitly synthetic dreams produce bounded, provenance-linked changes in
  self-narrative, arc state, session mood, and voice while preserving identity,
  factual competence, answer content, and synthetic-versus-literal boundaries.
- **Current Phase:** `P2_LIVE_CONTINUITY_CHAIN`.
- **Current Truth:** `skills/persona-dream/CURRENT_STATUS.json`.

## 2. Current State (Doc-Code Alignment)

- **P2.1-P2.3:** Continuity ledger hardening, deterministic session-mood
  binding, and live Chatterbox mood rendering are implemented and receipted.
- **P2.4 backend preflight:** Passed under the Chatterbox voice-lane interpreter
  with `resemblyzer` available.
- **P2.4 recognition scoring:** Passed after rendering longer 4.68-6.0s
  session-mood turns. The earlier short 1.76-2.16s renders remain useful
  historical evidence, but they were too short for the identity gate.
- **P2 joined live-chain receipt:** Passed for cycle
  `live_chain_20260729t130950z` at
  `reports/goal_v5/continuity/live_chain/RECEIPT.json`. Issue #1117 repaired
  its presentation fields so `selected_before_first_turn` is sequence-derived
  (`mood_bound_seq=0`, `first_turn_seq=1`) while equal second-granularity
  timestamps are recorded separately as inconclusive.
- **Session arc-bias artifact:** Passed under the re-scoped #1057 Persona
  Dream ownership boundary at
  `reports/goal_v5/continuity/session_arc_bias/RECEIPT.json`. Persona Dream
  publishes numeric deltas only; SPARTA owns production conversation-service
  consumption.
- **SPARTA arc-bias handoff contract:** Passed at
  `reports/goal_v5/continuity/sparta_arc_bias_handoff/RECEIPT.json`. This
  publishes the machine-checkable SPARTA consumer target and binds the exact
  `session_arc_bias.v1` source hash.
- **SPARTA local live arc-bias consumption:** Passed in the SPARTA repository at
  `grahama1970/sparta@2fe1a67221da4b5f07d32b9136f4578f38d4e716`, receipt
  `artifacts/persona_dream_arc_bias_consumer/20260729T180334Z/RECEIPT.json`,
  SHA-256
  `sha256:ca05bb17feb508e5996a9bd46123b8cffebbeb44a39465a1a09e9a64faf30813`.
  The receipt is `mocked=false`, `live=true`, and shows the local live SPARTA
  API consumed the current Persona Dream `session_arc_bias.v1` artifact before
  turn 1, kept the same artifact across three turns, preserved canonical answer
  text, preserved tone category, and used neutral fallback when no artifact was
  supplied.
- **Five-cycle reliability pilot:** Passed under #1041 at
  `reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json` with 5
  attempted, 5 completed, 5 passed, 0 blocked, 0 errored, 0 duplicate accepted
  effects, and Wilson 95% lower bound 0.565509.
> **STOP — do not collect human ratings.** The four stimuli below were later
> found technically confounded by
> `reports/goal_v5/continuity/blinded_listener_study/TECHNICAL_SCREEN_RECEIPT.json`,
> which BLOCKS them. #1179 owns the re-render under one identical
> loudness-normalization policy. Collecting responses against the current
> stimuli produces data that cannot be interpreted, and the readiness bullets
> below describe the state BEFORE that screen. They are retained as history, not
> as an instruction.

- **Blinded listener-study readiness:** Four preregistered Chatterbox stimuli
  are restored under `reports/goal_v5/continuity/blinded_listener_study/stimuli/`
  and validated by
  `reports/goal_v5/continuity/blinded_listener_study/STIMULUS_VALIDATION_RECEIPT.json`.
  All four hashes match the preregistration, live ASR returns WER 0.0 for all
  four, the rater response schema/instructions are present, empty/malformed
  rater rows are rejected, and the remaining failed gate is
  `human_responses_complete`.
- **Blinded listener-study rater page:** A static collection surface now exists
  at `reports/goal_v5/continuity/blinded_listener_study/rater_page.html`, with
  receipt
  `reports/goal_v5/continuity/blinded_listener_study/RATER_PAGE_RECEIPT.json`
  and SHA-256
  `sha256:8026000a080add6f63df81cf90c9b8522bed442c0f28b91647555ca2bed67bce`.
  It copies the four WAVs into `blinded_stimuli/S01.wav` through `S04.wav`,
  avoids condition-labelled audio paths in the HTML, and emits
  schema-compatible JSONL for `responses.jsonl`. This is a Persona Dream
  evaluation-collection artifact, not SPARTA production UX and not perceptual
  proof.
- **Blinded listener-study analysis guard:** The analysis receipt at
  `reports/goal_v5/continuity/blinded_listener_study/RECEIPT.json` now fails
  closed with `BLOCKED_BLINDED_LISTENER_STUDY_ANALYSIS` until
  `human_responses_complete` and `signed_human_interpretation_missing` are
  cleared. Receipt SHA-256:
  `sha256:e052a9ccc250ce31f6d72fe31004f42b3fa97f6e3deadfb036b1fdd1212f5f89`.
- **Status boundary:** P2.4 recognition proof and the SPARTA local live receipt
  do not prove perceived emotion, naturalness, human listener recognition,
  deployed SPARTA production behavior beyond the local live API receipt,
  production reliability beyond an N=5 pilot, or PCTOM-R benefit.
- **Issue #1117 durability repair:** `CURRENT_STATUS.json` no longer cites `/tmp`
  evidence paths for the agentic-eval fixture output or rater-page screenshot;
  durable copies live under
  `reports/goal_v5/continuity/sanity_evidence/`.

## 3. What is Working Well

- `./run.sh check-current-state-consistency --strict` returned
  `PASS_CURRENT_STATE_CONSISTENT` before this slice.
- Longer live Chatterbox render receipt:
  `reports/goal_v5/continuity/session_mood_chatterbox_live_long_identity/RECEIPT.json`
  with `live=true`, `mocked=false`, three `chatterbox_base` turns, WER `0.0`,
  and durations `4.68`, `4.8`, and `6.0` seconds.
- Recognition receipt:
  `reports/goal_v5/continuity/session_mood_voice_recognition_long_identity/RECEIPT.json`
  with `status=PASS_SESSION_MOOD_VOICE_RECOGNITION`, `engine=resemblyzer`,
  failed gates `[]`, Embry similarities `0.872906`, `0.841573`, `0.842233`,
  and impostor separation `0.208427`.
- Joined live-chain receipt:
  `reports/goal_v5/continuity/live_chain/RECEIPT.json` with
  `status=PASS_PERSONA_DREAM_LIVE_CHAIN`, `mocked=false`, `live=true`, receipt
  SHA-256 `sha256:e414712551e43d727996b065ca250b2221bbbf60824d6fbbeae3a177e144e2fd`,
  side-effect counters `{accepted dream writes: 1, journal writes: 1, ledger arc
  deltas: 1, live Chatterbox turns: 3}`, and 13/13 negative controls blocked.
- Live-chain Chatterbox leg:
  `reports/goal_v5/continuity/live_chain/chatterbox_live/RECEIPT.json` with
  `chatterbox_base`, WER `0.0`, `0.0`, `0.0`, and durations `5.32`, `5.24`,
  `4.64` seconds.
- Live-chain recognition leg:
  `reports/goal_v5/continuity/live_chain/voice_recognition/RECEIPT.json` with
  `PASS_SESSION_MOOD_VOICE_RECOGNITION`, failed gates `[]`, Embry similarities
  `0.850468`, `0.872958`, `0.793123`, and separation `0.159977`.
- Session arc-bias receipt:
  `reports/goal_v5/continuity/session_arc_bias/RECEIPT.json` with
  `PASS_SESSION_ARC_BIAS_RECEIPT`, artifact SHA-256
  `sha256:a978509c4e3fc54501c43f67f08afd7a506734ad1955d54db99325056ecc8152`,
  source dream `live_chain_20260729t130950z`, ledger epoch `2`,
  arc delta `arc_1_55a79f6ef25f`, `intensity_delta=0.18`,
  `valence_delta=-0.18`, `emits_tone=false`, and 7/7 negative controls blocked.
- SPARTA arc-bias handoff receipt:
  `reports/goal_v5/continuity/sparta_arc_bias_handoff/RECEIPT.json` with
  `PASS_SPARTA_ARC_BIAS_HANDOFF_RECEIPT`, receipt SHA-256
  `sha256:722c0b605c39611df553b354593fb0867275aa4780e1d0b04dc9c6404ea6530c`,
  contract
  `reports/goal_v5/continuity/sparta_arc_bias_handoff/SPARTA_CONSUMER_CONTRACT.json`,
  contract SHA-256
  `sha256:38eff20c657188c0d16cb6cbe74e78d97e4ba4c2ec87312f32d11679e69042df`,
  and 7/7 negative controls blocked.
- SPARTA local live arc-bias consumption receipt:
  `grahama1970/sparta@2fe1a67221da4b5f07d32b9136f4578f38d4e716`
  `artifacts/persona_dream_arc_bias_consumer/20260729T180334Z/RECEIPT.json`
  with `PASS_SPARTA_PERSONA_DREAM_ARC_BIAS_CONSUMED`, receipt SHA-256
  `sha256:ca05bb17feb508e5996a9bd46123b8cffebbeb44a39465a1a09e9a64faf30813`,
  `mocked=false`, `live=true`, current Persona Dream session-arc-bias artifact
  SHA-256
  `sha256:a978509c4e3fc54501c43f67f08afd7a506734ad1955d54db99325056ecc8152`,
  contract SHA-256
  `sha256:38eff20c657188c0d16cb6cbe74e78d97e4ba4c2ec87312f32d11679e69042df`,
  `arc_bias_applied_before_first_turn=true`,
  `same_arc_bias_artifact_all_turns=true`,
  `answer_text_unchanged=true`,
  `tone_category_unchanged_by_arc_bias=true`, `neutral_fallback_checked=true`,
  and failures `[]`. This proves local live API consumption only; it does not
  prove human perception or deployed production behavior beyond the local API.
- Reliability aggregate receipt:
  `reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json` with
  `PASS_LIVE_CHAIN_RELIABILITY_PILOT`, SHA-256
  `sha256:9ca2bc211fc12cb6033d45b4f7c7b1e2b9c1ba9ec4bc8cb0dd64784c0228ce2f`,
  campaign id `live_chain_reliability_20260729t133501z`, 5/5 cycle receipts
  passed, duplicate accepted effects `0`, and Wilson 95% lower bound `0.565509`.
- Blinded listener-study validation receipt:
  `reports/goal_v5/continuity/blinded_listener_study/STIMULUS_VALIDATION_RECEIPT.json`
  with `PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS`, SHA-256
  `sha256:c5d6c01e4f4db0fb7f1a4a5c1535c316d666665c541753b6c4f8db46f162e7fa`,
  stimulus hashes matched `4/4`, live ASR WER `0.0/0.0/0.0/0.0`, and human
  responses `0/20 valid`. `RESPONSE_SCHEMA.json` is
  `sha256:21e51f2392ab9a9c4d6bfb8d15907fa36eb292f443cbc2861c61be2d4650850e`;
  `RATER_INSTRUCTIONS.md` is
  `sha256:cf830dcd68338ca37e0e2a0d0778c18031cf7a4fa767a06921bce417a9ddf6e5`.
- `session_mood_chatterbox_live.py` now sends Chatterbox the service-visible
  `/data/embry_ref.wav` path while the receipt records the host-side authorized
  reference path and SHA-256. This avoids the `reference_audio_outside_allowed_roots`
  failure seen from fresh worktrees.
- `session_mood_voice_recognition.py` now records repo-contained artifacts with
  repo-relative paths instead of temporary worktree absolute paths.
- #1117 focused proof in this slice:
  - `uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_live_chain_receipt.py -q`
    -> `9 passed`
  - `./skills/persona-dream/run.sh check-current-state-consistency --strict --json`
    -> `PASS_CURRENT_STATE_CONSISTENT`, `mismatch_count=0`

## 4. What is Currently Broken

- **Deployed production service not proven beyond local live receipt:** Session
  mood is proven in the deterministic receipt runner, Persona Dream publishes
  the arc-bias artifact and SPARTA consumer handoff contract, and SPARTA has a
  local live API consumption receipt. There is still no deployed-production
  claim beyond that local receipt.
- **Perception not proven:** The listener-study stimuli are ready, but
  `responses.jsonl` has 0/20 valid human responses and there is no signed human
  interpretation record. The analysis receipt now enforces that boundary.
- **PCTOM-R benefit unproven:** The machinery remains strong, but no
  confidence-bounded counterfactual-dreaming planning advantage has been shown.
- **Reliability boundary:** The five-cycle engineering pilot passed, but this is
  not production reliability and does not cover a larger campaign or restart
  recovery.

## 5. Next Steps

1. Collect the 20 human responses for the blinded Chatterbox listener study,
   append them to `responses.jsonl`, and add `SIGNED_INTERPRETATION.json`; do
   not substitute an LLM/self-rating.
2. Rerun `./run.sh analyze-blinded-listener-study --json` and require it to
   clear `human_responses_complete` and
   `signed_human_interpretation_missing`.
3. Return to PCTOM-R condition-benefit work such as issue `#1008` only after an
   explicit operator reprioritization or after the voice/perception gate is
   receipted.

## 6. Project Context for Success

- **Primary status file:** `skills/persona-dream/CURRENT_STATUS.json`
- **Goal contract:** `skills/persona-dream/GOAL.md`
- **Research log:** `skills/persona-dream/PROJECT_KNOWLEDGE.md`
- **Skill contract:** `skills/persona-dream/SKILL.md`
- **Current-state gate:** `skills/persona-dream/scripts/check_current_state_consistency.py`
- **Live render script:** `skills/persona-dream/scripts/session_mood_chatterbox_live.py`
- **Recognition script:** `skills/persona-dream/scripts/session_mood_voice_recognition.py`
- **Long render receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_mood_chatterbox_live_long_identity/RECEIPT.json`
- **Long recognition receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_mood_voice_recognition_long_identity/RECEIPT.json`
- **Joined live-chain receipt:** `skills/persona-dream/reports/goal_v5/continuity/live_chain/RECEIPT.json`
- **Session arc-bias receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_arc_bias/RECEIPT.json`
- **SPARTA arc-bias handoff receipt:** `skills/persona-dream/reports/goal_v5/continuity/sparta_arc_bias_handoff/RECEIPT.json`
- **SPARTA local live arc-bias consumption receipt:** `grahama1970/sparta@2fe1a67221da4b5f07d32b9136f4578f38d4e716:artifacts/persona_dream_arc_bias_consumer/20260729T180334Z/RECEIPT.json`
- **Reliability aggregate receipt:** `skills/persona-dream/reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json`
- **Listener-study readiness receipt:** `skills/persona-dream/reports/goal_v5/continuity/blinded_listener_study/STIMULUS_VALIDATION_RECEIPT.json`
- **Listener-study analysis receipt:** `skills/persona-dream/reports/goal_v5/continuity/blinded_listener_study/RECEIPT.json`

Use this claim boundary:

```text
Persona Dream remains in P2_LIVE_CONTINUITY_CHAIN. The joined
accepted-dream-to-live-chain receipt passes, Persona Dream publishes a
session_arc_bias artifact and SPARTA consumer handoff contract, SPARTA has a
local live API receipt consuming that artifact, and an N=5 live-chain
reliability pilot passes. The immutable Embry continuity goal remains NOT_MET
until human perceptual emotion/identity evidence is receipted; deployed
production behavior beyond the local live API, production reliability, and
PCTOM-R benefit remain explicitly unproven.
```
