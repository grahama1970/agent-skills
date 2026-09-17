# Handoff Report: Persona Dream

**Timestamp**: 2026-09-16
**Active Agent**: pi (agent-skills session)
**Scope**: this session's work — the closed experience→state loop and the
chatterbox-speak / embry-voice-control safety wiring + deployment. Older
revision-qualification / Kling / video-plan state is unchanged and still lives
in `CURRENT_STATUS.json` and `PROJECT_KNOWLEDGE.md`.

## 1. Project Overview

- **Ecosystem**: Python (uv per-skill), Docker compose voice stack.
- **Core research goal (unchanged)**: does synthetic dreaming add measurable
  value over direct memory and structured reflection? Persistent continuity is
  a *safety constraint* under that goal, not the objective.
- **This session's thread**: prove the bounded closed loop
  `experience → recalled emotional trigger → deterministic admission →
  durable persona_state_delta → independent fold → later behavior/speech`,
  and make the chatterbox-speak render path safe and self-contained enough to
  serve it live.

## 2. Current State (what landed on origin/main this session)

All commits verified as ancestors of `origin/main`, byte-matched at land time.

| Commit | What |
|---|---|
| earlier `ba567ca` | memory-recall emotional-trigger bridge (pre-session baseline) |
| `0e72a662` | **C0/C1 matched-experiment machinery**: `admit_persona_state_delta.py`, `fold_persona_state.py`, `c0c1_frozen.py`, `seed_c0c1_eval_memory.py`, frozen contract + baseline capsule, 19-case live eval (READY) |
| `bf2b95e7` | **C0/C1 experiment executed**: `run_c0c1_experiment.py` + retained `EXPERIMENT_RECEIPT.json` (result PASS) |
| `1ae62979` | **chatterbox-speak core extraction**: `speak_core.py` (typed VoiceDeliveryPlan → gated render → hashed receipt), CLI thinned, 13-case live eval |
| `16a92c70` | **embry-voice-control wired through the core**: digest-verified loader, `/readiness` core parity, `render_evidence` in turn receipts, `check_no_direct_chatterbox_posts.py` |
| `15bf4958` | **voice-stack cutover executed**: `speak_core` resolves host WAVs across layouts; `CUTOVER_RUNBOOK.md` addendum + sanitized override template |

Reference doc `18674b0d` (`skills/ask/references/strategy-to-workflow.md`) also
landed: the ask-one-shot → lane-specs → workflowScript recipe used to drive all
of the above.

## 3. What is Working Well (verified this session)

- **Deterministic admission gate** (`admit-persona-state-delta`): recomputes
  every trigger fact from the hash-verified source reread (packets cannot forge
  identity/valence/intensity/derived-status), canonical-only distinct-event
  counting, cumulative clamped admission from folded state, per-cycle + baseline
  clamps, idempotency, and pre/post `/list` zero-write proof on every rejection.
- **Fold** (`fold-persona-state`): validates and **blocks** on any invalid
  accepted delta (never repairs), explicit cross-arm isolation.
- **C0/C1 experiment result** (`EXPERIMENT_RECEIPT.json`, sha256:5712314…):
  c0 REJECTED insufficient_distinct_events, fold == baseline 0.20;
  c1 one bounded +0.10 delta, fold 0.20→0.30, 1 cited delta;
  c1_null REJECTED unknown_intensity_scale; c1_inert per amendment v1.1.
  c1/c1_inert dispositions are honest `replay_persisted` (content-addressed
  idempotency; fresh-accept evidence is the 19-case eval, cited by hash).
- **chatterbox-speak / embry-voice-control**: live Embry render path now passes
  the backend-aware fail-closed tag gate; a static scan
  (`check_no_direct_chatterbox_posts.py`) keeps any direct `/synthesize` POST
  from reappearing outside the gate; every turn receipt carries `render_evidence`
  (plan/request/route/core/audio hashes).
- **Voice stack is live under compose** (`embry-voice` project): voice-control
  :8019 (healthy, `/readiness` digest_match:true), realtime-stt :8020 (ready,
  wake sha256 verified), chatterbox :8018 (model_loaded). Old ad-hoc container
  retired-renamed; rollback = `start_agent_server_docker.sh` (one command).

## 4. What is Currently Broken / Open

- **The research question itself is NOT answered.** The loop is proven
  *bounded and causal for a single axis (warmth) on one eval persona
  (embry-eval)*. It does **not** yet show dreaming beats direct memory /
  structured reflection, nor felt/perceived emotion, nor longitudinal benefit.
  Claim boundary is frozen: "deterministic evolution from declared,
  provenance-bound emotional signals."
- **C1-inert is an accepted amendment, not a passed content-control.** A
  deterministic gate reading only emotional signals can't distinguish records
  differing solely in a non-emotional attribute; content-pathway discrimination
  is carried by C1-null + contradiction, not C1-inert (contract §Amendment v1.1).
- **Live deploy env is override-carried, not in the tracked compose.** Three
  gaps live only in the untracked `/tmp/cutover-override.yaml` (+ sanitized
  `deploy/cutover-override.example.yaml`): ASR base URL (`http://172.17.0.1:9000`,
  NOT the `whisper` network name), `WHISPER_API_KEY` (secret), `/work` mount +
  widened `CHATTERBOX_REF_AUDIO_ROOTS`, host-visible artifacts bind, and the
  wake-model filename (`hey_embry_v1.onnx`, not `hey_embry.onnx`). Folding the
  non-secret ones into `deploy/compose.yaml` is unfinished follow-up.
- **Chatterbox affect is intensity/tempo only.** Valence is perceptually inert
  (~0.08 vs 0.96 for intensity); five of eight dream axes map inside the 0.5
  contrast noise floor and sound alike. Any "dream changes how Embry sounds"
  claim must travel through intensity/tempo with a `*_effect: applied:true`
  receipt, never a request echo.
- **Shame stop-hook was spiraling** earlier this session: the extension was
  disabled on disk (per operator 2026-09-14 directive) but a stale in-memory
  hook pointed at a moved module → fail-closed reject loop. Worked around by
  restoring the disabled-compat checker at the expected path. New sessions load
  nothing; per operator directive report normally, no `pi.agent_status.v1`
  footer required.
- **Worker teardown artifacts**: several `pi-subagents` worker runs reported
  `failed` on already-completed work (fork-context thinking sanitization abort).
  Always verify child artifacts on disk before trusting either status.

## 5. Next Steps

1. **Answer the actual research question**: replicate C0/C1 across more axes and
   independent scenarios, then run the preregistered comparison against direct
   memory (M) and structured reflection (R) — the M/R/D arm. A null result is a
   valid, publishable finding. Do not treat the proven mechanism as the answer.
2. **Later-turn delivery effect** (the loop's back half): exercise a later turn
   using the reread evolved state, prove the protected factual answer is
   byte-identical across arms while behavioral framing + Chatterbox delivery
   differ, with a paired `*_effect: applied:true` receipt.
3. **Harden the deploy**: fold the non-secret override gaps into
   `deploy/compose.yaml`; keep `WHISPER_API_KEY` in a gitignored `.env`. Decide
   whether to retire the generic whisper :9000 and journal :8032 drift after a
   soak period (currently left up on purpose).
4. **Optional self-healing** (open design question from the user, not yet built):
   map each `BLOCKED_*`/`REJECTED_*` disposition to `triage-error` catalog
   entries with `next_command`; add bounded *deterministic* self-repair only for
   the recoverable subset (reseed-arm is idempotent by design). Keep `$jev` in
   shadow/measure-only mode — the pipeline emits closed-set typed codes, so there
   is little ambiguous signal for a classifier to decide yet.

## 6. Project Context for Success

- **Frozen contract**: `contracts/c0c1_matched_experiment.v1.md` (+ v1.1
  amendments: C1-inert scope, fold arm-scoping, replay semantics) and
  `contracts/c0c1_baseline.json` (sha256:d6cae5f4…, warmth=0.20,
  MIN_DISTINCT_EVENTS=2, canonical-only counting).
- **Experiment entrypoint**: `scripts/run_c0c1_experiment.py --out-dir <dir>`;
  seed arms with `run.sh seed-c0c1-eval-memory --arm {c0,c1,c1_null,c1_inert,full} --reset`.
- **Admission/fold**: `scripts/admit_persona_state_delta.py`,
  `scripts/fold_persona_state.py`, shared frozen digest in `scripts/c0c1_frozen.py`.
- **Evals** (the acceptance authority, not unit tests):
  `fixtures/agentic_eval.persona_state_admission.json` (19 cases),
  `fixtures/agentic_eval.memory_recall_emotional_triggers.json` (8),
  `fixtures/c0c1_eval_memory_seed.json`, `agentic_eval.c0c1_seeding.json`.
  Run with `skills/agentic-evals/run.sh run <fixture> --output <report>`.
- **Voice**: chatterbox-speak core is `skills/chatterbox-speak/scripts/speak_core.py`;
  the gateway seam is `skills/embry-voice-control/src/embry_voice_control/chatterbox_gate.py`;
  stack is `skills/embry-voice-control/deploy/compose.yaml` +
  `CUTOVER_RUNBOOK.md`.
- **Retained proof for this session**:
  `local/proofs/c0c1-experiment-20260916T025216Z/EXPERIMENT_RECEIPT.json`.
- **Gotcha**: local `run.sh` flaps between old-HEAD and origin content because
  background cron lanes rewrite tracked files mid-session; re-align to
  `git show origin/main:skills/persona-dream/run.sh` if a subcommand goes
  "Unknown command". Agentic-eval case commands importing skill code must use
  `uv run --project .. python -` (bare `python3` under the runner lacks httpx).
