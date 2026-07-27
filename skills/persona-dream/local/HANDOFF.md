# Handoff Report: Persona Dream

**Timestamp:** 2026-07-27T15:09:48-04:00 / 20260727T190948Z
**Active Agent:** Codex
**Repository:** `grahama1970/agent-skills`
**Target Branch:** `main`
**Worktree Used:** `/home/graham/workspace/experiments/agent-skills-persona-dream-main-push`
**Base Commit Before Handoff Update:** `ed84b3106b11fd9d4003c86f3132509ee12168c0`
**Immutable Goal:** `NOT_MET`

## 1. Project Overview

- **Ecosystem:** Python skill in `agent-skills`, with local receipt trees,
  pytest/uv validation, Memory/Tau/Watch/Kling historical lanes, and
  Chatterbox voice integration receipts.
- **Core Purpose:** Build and verify Embry as a persistent persona whose
  explicitly synthetic dreams produce bounded, provenance-linked changes in
  self-narrative, arc state, session mood, and voice while preserving identity,
  factual competence, answer content, and synthetic-versus-literal boundaries.
- **Current Phase:** `P2_LIVE_CONTINUITY_CHAIN`.
- **Source of Current Truth:** `skills/persona-dream/CURRENT_STATUS.json`.

## 2. Current State (Doc-Code Alignment)

- **Documented hierarchy:** `GOAL.md`, `README.md`, `PROJECT_KNOWLEDGE.md`, and
  `SKILL.md` now describe Embry persistent-persona continuity as the controlling
  goal. PCTOM-R is a research workstream under that goal. Kling, Watch, Memory,
  Chatterbox, and Tau are supporting lanes with separate proof boundaries.
- **Implemented reality:** P2.1 continuity-ledger hardening, P2.2 deterministic
  session-mood binding, and P2.3 live Chatterbox session-mood rendering are
  implemented and receipted. P2.4 voice-recognition preflight is implemented,
  but it blocks because no real speaker-recognition backend is importable in the
  checked runtimes.
- **Live Chatterbox status:** The system can render three session-mood-derived
  utterances through `POST http://127.0.0.1:8018/synthesize-batch` using
  `chatterbox_base`; strict ASR reports WER `0.0` for all three turns and the
  WAV snapshots are copied into the report tree.
- **Remaining alignment risk:** The full accepted-dream-to-production-session
  receipt does not exist. Do not treat pushed commits, green sanity, WebGPT
  review, or Chatterbox ASR as completion of the immutable goal.

## 3. What is Working Well

- **Repository health:** `skills/persona-dream/sanity.sh` is recorded in
  `CURRENT_STATUS.json` as `PASS` with `513 passed, 9 subtests passed`.
- **Tau boundary:** Strict Tau-only routing checks report
  `hard_violations=0`, `temporary_debt=0`, and `stale_allow_entries=0`.
- **Ledger hardening:** `scripts/continuity_ledger.py` validates ledgers on
  read, normalizes Embry's legacy shape, uses atomic append writes, checks
  expected epochs, rejects duplicate dream-cycle replay, recomputes
  identity-core hashes, and blocks deltas that try to smuggle identity-core or
  arc-state fields.
- **Session mood binding:** `scripts/session_mood_binding.py` binds one
  deterministic `session_mood_id` before turn 1, asserts that same ID across
  three turns, preserves answer text exactly, and emits a
  Chatterbox-base-ready `voice_delivery` envelope.
- **Voice actuator path:** `session_mood_chatterbox_live/RECEIPT.json` is
  `mocked: false`, `live: true`, uses `chatterbox_base`, preserves durable
  WAVs, and passes strict ASR WER `0.0`.
- **PCTOM-R custody:** The previously fragile `/tmp` PCTOM-R proof roots have
  durable local custody under `skills/persona-dream/research/prospective-tom/`.

## 4. What is Currently Broken

- **P2.4 speaker recognition:** Active blocker. The receipt
  `reports/goal_v5/continuity/session_mood_voice_recognition_preflight/RECEIPT.json`
  is `BLOCKED_SPEAKER_RECOGNITION_PREFLIGHT`; `resemblyzer=false` and
  `speechbrain_ecapa=false`. Do not substitute waveform hashes, loudness, MFCC,
  or spectral similarity as Embry recognition proof.
- **No live-chain receipt:** The target
  `reports/goal_v5/continuity/live_chain/RECEIPT.json` has not been produced.
- **No recognizability proof:** ASR proves content survived synthesis. It does
  not prove perceived emotion, naturalness, speaker similarity, adversarial
  Embry recognition, or stable identity across moods.
- **No fresh accepted-dream chain:** Current slices do not prove a fresh
  accepted dream -> Watch observations -> grounded journal -> bounded arc delta
  -> authoritative ledger -> production conversation session -> stable
  dream-derived mood -> recognizable Embry speech.
- **Repeated reliability unproven:** The accepted media dream loop remains
  historical N=1. There is no five-cycle reliability campaign.
- **PCTOM-R benefit unproven:** PCTOM-R machinery is strong, but it has not
  shown a confidence-bounded planning advantage for counterfactual dreaming.
- **Kling continuation unproven:** Previous-video attachment A/B was not run.
  Existing continuity evidence is image-stage and intra-clip adjudication, not
  causal proof that a previous video improved continuity.

## 5. Next Steps

1. Resolve the P2.4 speaker-recognition backend blocker with an approved real
   backend such as `resemblyzer` or `speechbrain_ecapa`, or route the existing
   WAV artifacts to a dedicated voice/audio evaluation lane that already has a
   real speaker backend.
2. Add speaker-similarity and adversarial Embry-recognition gates for the three
   live session-mood Chatterbox renders in
   `reports/goal_v5/continuity/session_mood_chatterbox_live/`.
3. Produce
   `skills/persona-dream/reports/goal_v5/continuity/live_chain/RECEIPT.json`
   from one fresh accepted-dream chain, including the positive path and the
   required negative controls.
4. After the live-chain receipt exists, run the five-cycle engineering
   reliability campaign and then return to PCTOM-R condition-benefit work such
   as issue `#1008` if the operator keeps that research priority.
5. Defer Kling previous-video/last-frame anchoring A/B until after the live
   continuity chain, because provider/video is not the current critical path.

## 6. Project Context for Success

- **Primary status file:** `skills/persona-dream/CURRENT_STATUS.json`
- **Goal contract:** `skills/persona-dream/GOAL.md`
- **Research log:** `skills/persona-dream/PROJECT_KNOWLEDGE.md`
- **Skill contract:** `skills/persona-dream/SKILL.md`
- **Sanity gate:** `skills/persona-dream/sanity.sh`
- **Ledger code:** `skills/persona-dream/scripts/continuity_ledger.py`
- **Journal append path:** `skills/persona-dream/scripts/write_dream_journal.py`
- **Session mood consumer:** `skills/persona-dream/scripts/session_mood_binding.py`
- **P2.1 receipt:** `skills/persona-dream/reports/goal_v5/continuity/ledger_hardening/RECEIPT.json`
- **P2.2 receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_mood_binding/RECEIPT.json`
- **P2.3 receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_mood_chatterbox_live/RECEIPT.json`
- **P2.4 blocker receipt:** `skills/persona-dream/reports/goal_v5/continuity/session_mood_voice_recognition_preflight/RECEIPT.json`
- **PCTOM durable archive:** `skills/persona-dream/research/prospective-tom/`

Recent Persona Dream commits at this handoff:

- `91c6f657b` - `persona-dream: preflight voice recognition gate`
- `d90e12156` - `persona-dream: preserve session mood audio receipts`
- `f5c457a9c` - `persona-dream: record p2 recognition next step`
- `1cc0dcf8e` - `persona-dream: correct chatterbox merge handoff`
- `44672cf8a` - `persona-dream: archive pctom stop-condition evidence`

Use this claim boundary for the next agent:

```text
Persona Dream is in P2_LIVE_CONTINUITY_CHAIN. P2.1-P2.3 are real implementation
slices with receipts. P2.4 is blocked on a real speaker-recognition backend.
The immutable Embry continuity goal remains NOT_MET until a fresh accepted dream
is carried through Watch, journal, ledger, pre-turn session mood, multi-turn
Chatterbox rendering, and Embry recognition into
reports/goal_v5/continuity/live_chain/RECEIPT.json.
```
