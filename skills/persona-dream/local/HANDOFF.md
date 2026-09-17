# Handoff Report: Persona Dream

**Timestamp**: 2026-09-17 (updated after the later-turn-effect milestone)
**Active Agent**: pi (agent-skills session)
**Scope**: this session's work — the closed experience→state loop, the
chatterbox-speak / embry-voice-control safety wiring + deployment, and the
later-turn delivery effect (the loop's back half). Older
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

## 2. Current State (Doc-Code Alignment)

**Documented features** (README "Where it stands" / SKILL.md): journal loop,
recall-grounded dreaming, spoken journal, attributed discussion carried back
into memory, calibrated tone delivery, honest "dreaming helps?" non-claim.

**Implemented reality** now ALSO includes the C0/C1 thread, none of which is
in the README yet: emotional-trigger recall → deterministic admission →
folded persona state → later-turn framing + applied delivery.

**Drift / misalignments** (found via `$handoff` fact pass 2026-09-17):

- `README.md` "Where it stands" predates the entire C0/C1 thread — no mention
  of admission/fold, the frozen matched experiment, or the later-turn effect.
- `CURRENT_STATUS.json`, `PROJECT_KNOWLEDGE.md`, `CURRENT_STATE.md` contain
  zero `c0c1`/`later_turn` references (verified by grep this session); they
  still describe the pre-2026-09-15 state.
- This `local/HANDOFF.md` is the ONLY current doc; treat it as authoritative
  until README/EVIDENCE are refreshed.

**What landed on origin/main** (all commits verified as ancestors of
`origin/main`, byte-matched at land time):

| Commit | What |
|---|---|
| earlier `ba567ca` | memory-recall emotional-trigger bridge (pre-session baseline) |
| `0e72a662` | **C0/C1 matched-experiment machinery**: `admit_persona_state_delta.py`, `fold_persona_state.py`, `c0c1_frozen.py`, `seed_c0c1_eval_memory.py`, frozen contract + baseline capsule, 19-case live eval (READY) |
| `bf2b95e7` | **C0/C1 experiment executed**: `run_c0c1_experiment.py` + retained `EXPERIMENT_RECEIPT.json` (result PASS) |
| `1ae62979` | **chatterbox-speak core extraction**: `speak_core.py` (typed VoiceDeliveryPlan → gated render → hashed receipt), CLI thinned, 13-case live eval |
| `16a92c70` | **embry-voice-control wired through the core**: digest-verified loader, `/readiness` core parity, `render_evidence` in turn receipts, `check_no_direct_chatterbox_posts.py` |
| `15bf4958` | **voice-stack cutover executed**: `speak_core` resolves host WAVs across layouts; `CUTOVER_RUNBOOK.md` addendum + sanitized override template |
| `1fee9593` | **later-turn delivery effect (loop's back half)**: `run_later_turn_effect.py` + `run.sh later-turn-effect`, `render_via_chatterbox_speak` gained `--intensity` passthrough + persisted core receipts, retained eval `fixtures/agentic_eval.later_turn_effect.json` (readiness READY, critical claim proven live). Retained proof: `local/proofs/later-turn-effect-20260917T140812Z/` (PASS: c0 warmth 0.20→RESERVED, c1 0.30→WARMER; answer byte-identical + invariance gate PASS; affect applied=true, exaggeration 0.57 vs 1.11; durations 12.38s slow vs 11.11s brisk; zero memory writes) |

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
- **Later-turn effect proven live** (contract §"Later-turn effect"): both arms
  answer the frozen protected question from the independently reread folded
  state with a byte-identical capsule body (validator PASS, tamper case fails
  closed), framing differs by arm via a FROZEN CATEGORICAL mapping
  (warmth>baseline → WARMER else RESERVED), and Chatterbox delivery differs
  with paired `affect_effect applied=true` receipts (explicit low 0.3 vs high
  0.9 → exaggeration 0.57 vs 1.11 on chatterbox_base_affect; pace slow/brisk;
  temperature held identical). `persona_state_delta` key set unchanged across
  the run — the turn is never reinforcement evidence.

## 4. What is Currently Broken / Open

- **The research question itself is NOT answered.** The loop is now proven
  *bounded, causal, and carried through to later-turn behavior/delivery for a
  single axis (warmth) on one eval persona (embry-eval)* — but it does **not**
  yet show dreaming beats direct memory / structured reflection, nor
  felt/perceived emotion, nor longitudinal benefit. Claim boundary is frozen:
  "deterministic evolution from declared, provenance-bound emotional signals,
  deterministically mapped to later framing and applied delivery."
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
- **Doc drift (from the $handoff alignment pass)**: `README.md` "Where it
  stands", `docs/EVIDENCE.md`, `CURRENT_STATUS.json`, `PROJECT_KNOWLEDGE.md`,
  and `CURRENT_STATE.md` predate the C0/C1 thread (zero mentions — verified by
  grep). Until refreshed, this `local/HANDOFF.md` plus
  `contracts/c0c1_matched_experiment.v1.md` are the authoritative current state.
- **Worker teardown artifacts**: several `pi-subagents` worker runs reported
  `failed` on already-completed work (fork-context thinking sanitization abort).
  Always verify child artifacts on disk before trusting either status.

## 5. Next Steps

1. **Answer the actual research question**: replicate C0/C1 across more axes and
   independent scenarios, then run the preregistered comparison against direct
   memory (M) and structured reflection (R) — the M/R/D arm. A null result is a
   valid, publishable finding. Do not treat the proven mechanism as the answer.
2. **Harden the deploy**: fold the non-secret override gaps into
   `deploy/compose.yaml`; keep `WHISPER_API_KEY` in a gitignored `.env`. Decide
   whether to retire the generic whisper :9000 and journal :8032 drift after a
   soak period (currently left up on purpose).
3. **Optional self-healing** (open design question from the user, not yet built):
   map each `BLOCKED_*`/`REJECTED_*` disposition to `triage-error` catalog
   entries with `next_command`; add bounded *deterministic* self-repair only for
   the recoverable subset (reseed-arm is idempotent by design). Keep `$jev` in
   shadow/measure-only mode — the pipeline emits closed-set typed codes, so there
   is little ambiguous signal for a classifier to decide yet.
4. **Later-turn follow-ups (optional)**: linear (non-categorical) warmth→delivery
   mapping is future work — the renderer's response curve says small deltas are
   inaudible, so the categorical profile is the honest frozen choice; a
   perceptual/audibility claim needs the listener-study machinery, not this
   receipt.

## 6. Project Context for Success

- **Frozen contract**: `contracts/c0c1_matched_experiment.v1.md` (+ v1.1
  amendments: C1-inert scope, fold arm-scoping, replay semantics) and
  `contracts/c0c1_baseline.json` (sha256:d6cae5f4…, warmth=0.20,
  MIN_DISTINCT_EVENTS=2, canonical-only counting).
- **Experiment entrypoint**: `scripts/run_c0c1_experiment.py --out-dir <dir>`;
  seed arms with `run.sh seed-c0c1-eval-memory --arm {c0,c1,c1_null,c1_inert,full} --reset`.
- **Admission/fold**: `scripts/admit_persona_state_delta.py`,
  `scripts/fold_persona_state.py`, shared frozen digest in `scripts/c0c1_frozen.py`.
- **Later-turn effect**: `run.sh later-turn-effect --out-dir <dir>` →
  `scripts/run_later_turn_effect.py` (folds both arms live, composes the turn
  from the frozen mapping, renders through the chatterbox-speak front door,
  gates answer invariance / applied affect / zero writes, writes
  `LATER_TURN_RECEIPT.json`).
- **Evals** (the acceptance authority, not unit tests):
  `fixtures/agentic_eval.persona_state_admission.json` (19 cases),
  `fixtures/agentic_eval.memory_recall_emotional_triggers.json` (8),
  `fixtures/c0c1_eval_memory_seed.json`, `agentic_eval.c0c1_seeding.json`,
  `fixtures/agentic_eval.later_turn_effect.json` (2 cases: live e2e + tamper
  negative; readiness READY).
  Run with `skills/agentic-evals/run.sh run <fixture> --output <report>`.
- **Voice**: chatterbox-speak core is `skills/chatterbox-speak/scripts/speak_core.py`;
  the gateway seam is `skills/embry-voice-control/src/embry_voice_control/chatterbox_gate.py`;
  stack is `skills/embry-voice-control/deploy/compose.yaml` +
  `CUTOVER_RUNBOOK.md`.
- **Retained proof for this session**:
  `local/proofs/c0c1-experiment-20260916T025216Z/EXPERIMENT_RECEIPT.json` and
  `local/proofs/later-turn-effect-20260917T140812Z/LATER_TURN_RECEIPT.json`
  (+ `agentic_eval_report.json`).
- **Gotcha**: local `run.sh` flaps between old-HEAD and origin content because
  background cron lanes rewrite tracked files mid-session; re-align to
  `git show origin/main:skills/persona-dream/run.sh` if a subcommand goes
  "Unknown command". Agentic-eval case commands importing skill code must use
  `uv run --project .. python -` (bare `python3` under the runner lacks httpx).
