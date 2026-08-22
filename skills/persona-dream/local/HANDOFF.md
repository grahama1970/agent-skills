# Handoff Report: persona-dream

**Timestamp**: 2026-08-22T22:39:07Z
**Active Agent**: Claude Fable 5 (Claude Code)
**Prior file note**: supersedes the 2026-07-29 Codex handoff (issue #1117
slice, P2.1-P2.3 receipts) — recoverable at
`git show 675e9334ed:skills/persona-dream/local/HANDOFF.md`.

## 1. Project Overview

- **Ecosystem**: Python 3.12 (uv, Typer, run.sh CLI) + React/Vite UX surfaces;
  Tau executes the dream spine as a receipt-gated DAG; Chatterbox (docker,
  :8018) renders voice; whisper container does ASR; memory daemon behind the
  sparta explorer API (:3001).
- **Core Purpose**: determine, through preregistered fail-closed experiments,
  whether provenance-bound synthetic dreaming adds measurable value over direct
  memory/reflection while preserving identity. "No" is a valid answer. See
  `GOAL.md` (immutable) and `CURRENT_STATUS.json` (machine-readable state).

## 2. Current State (Doc-Code Alignment)

- **Research phase**: `P2_CORRECTED_GOAL_PAIR_PROOF` (`CURRENT_STATUS.json`,
  authoritative). Proven: one corrected-goal paired proof and a 3-trial live
  full-cycle eval after #1495/#1496. Not proven: the research benefit itself,
  human-perceived emotional value, 35-cycle no-restart reliability, or separate
  mediation by dream versus journal.
- **The loop is complete and runnable**: as of 2026-08-20 the full cycle has
  run live end to end — day ingest → Tau dream spine (select / frozen
  instruments / frames / VLM observe / phase-13 interpret / phase-14 ToM /
  persist with exact re-read / dream journal) → tone-annotated day journal →
  ASR-verified spoken `journal.wav` → memory write + artifact store →
  multi-turn fully audible dynamic Horus/Embry conversation → carry-back.
- **Conversation contract**: `horus` is a first-class voiced role
  (`scripts/append_conversation.py` refuses embry OR horus turns without tone
  + rendered audio; sha256-bound in `conversation.jsonl`). Dialogue is
  generated per turn (`scripts/dynamic_conversation.py`, `run.sh
  converse-dynamic`): Horus drafts via Tau conditioned on her journal + live
  transcript, speaks with `horus_v2_agent_ref_6s.wav`; Embry replies through
  the gated `speak_reply` path.
- **UI**: pipeline workspace (11 phases) mounts at `http://127.0.0.1:5173/#dream`
  (`ux/app`, `npm run dev` + `npm run dev:dream-api` for the :8791 API host;
  vite proxies `/api/projects/dream`→8791, `/api/memory`→3001, `/api`→8790
  journal FastAPI via `uv run --extra ux python ux/server.py`). Residue board
  draws a seeded stratified image/video/audio/text sample from live memory.

## 3. What is Working Well

- **Eval suite** (`fixtures/agentic_eval.json`, 12 cases; run with
  `~/.claude/skills/agentic-evals/run.sh run fixtures/agentic_eval.json`):
  five critical capability claims, all live-path, dead services report
  BLOCKED not FAIL. Four claims PROVEN as of 2026-08-20: workspace renders
  (SSR guard + fail-before-fix proof in `fixtures/regressions.json`, verified
  non-vacuous via `regressions verify`), pipeline API serves runs + path
  policy 403s, board media stratification (live), dynamic audible
  conversation (live).
- **Full-cycle live eval currently passes the focused harness**: receipt
  `skills/persona-dream/local/proofs/pd-corrected-goal-v1/full-cycle-live-20260822T223907Z/agentic_eval_report.json`
  (`sha256:24e3fc0f481ae8a2cf1e38104ef7e4179801f8073c913782e5ae212188bb76e0`)
  reports
  `readiness=READY`, `case_count=1`, `trial_count=3`, `passed_trials=3/3`,
  `live_qualified=true`, `mocked=false`, `fixture_backed=true`. The three runs
  were `eval-full-cycle-20260822T220339Z`,
  `eval-full-cycle-20260822T221510Z`, and
  `eval-full-cycle-20260822T222750Z`; each reported `FULL_CYCLE_OK stages=7`,
  a Tau dream spine pass, ASR-verified spoken journal, memory/artifact write,
  `conversation:3_pairs_all_voiced`, and `carried:6`.

## 4. What is Currently Broken / Open

- **End-to-end reliability remains the open frontier**: `full-cycle-live` now
  has a 3/3 live harness pass on 2026-08-22 after #1495 exposed
  `run.sh converse-dynamic` and #1496 made recall-instrument outcomes
  auditable. This is not #1128's 35-cycle no-restart reliability evidence.
  #1128 remains open because its acceptance bar is 35 immutable terminal rows,
  stable process identity, Wilson lower bound recomputation, and fail-closed
  negative controls.
- **`/api/tau/dream/*`** (story/script draft endpoints the workspace calls)
  has no server implementation anywhere; those UI actions fail.
- **Blinded listener study**: stimuli must be re-rendered under one identical
  normalization (#1179) before any human collection (#1058). Ordered next
  steps live in `CURRENT_STATUS.json.next_step`.
- **Environment traps** (each cost real time on 2026-08-19/20):
  - `uv sync --extra ux` prunes the other extra — reinstall identity deps with
    `uv pip install insightface==0.7.3 onnxruntime==1.19.2` (NOT `-e .[identity]`);
    `./run.sh doctor` catches this.
  - The `whisper` docker container silently exiting makes Chatterbox reject
    every ASR candidate with an in-container DNS error; symptom is
    `BLOCKED_JOURNAL_AUDIO` / `asr_transcript_missing…`. `docker start whisper`.
  - `~/node_modules` symlinks to pi-mono and leaks a second React into
    anything without its own copy (eval bundlers pin aliases for this).
  - `ui/src` is `@ts-nocheck`: tsc catches nothing there; the SSR render eval
    is the guard. Concurrent lanes share this checkout's git index — stage
    narrowly and verify what landed.

## 5. Next Steps

1. Decide the next reliability ticket action under `project-watchdog`: #1128
   needs 35 no-restart cycles and depends on cross-mood identity policy (#1130),
   while #1130 is still agent-blocked and needs a frozen 36-render matrix.
2. #1179 listener-stimuli re-render under one normalization; rerun the frozen
   technical screen unchanged; then #1130, #1058.
3. Optional UX: implement or stub `/api/tau/dream/*` server-side; commit the
   ux-lab registry surface entry if still uncommitted.

## 6. Project Context for Success

- **Key files**: `run.sh` (every entrypoint; `dream`, `converse-dynamic`,
  `speak-journal`, `doctor`), `scripts/autonomous_dream_cycle.py`,
  `scripts/dynamic_conversation.py`, `scripts/speak_reply.py`,
  `scripts/append_conversation.py`, `scripts/eval_full_cycle.py`,
  `ui/src/DreamWorkspace.tsx` (+ `ux/app`), `fixtures/agentic_eval.json`,
  `fixtures/regressions.json`, `PROJECT_KNOWLEDGE.md` (2026-08-19 entry has
  the full incident forensics), `CURRENT_STATUS.json`, `GOAL.md`.
- **Recent commits** (all on origin/main): `675e9334ed` full-cycle eval,
  `774bf570ac` dynamic first-class-voiced conversation, `9ad1843f89` audible
  conversation eval + instruments fix, `9a8d8bd388` workspace eval guards,
  `6f8ef3028b` workspace mount + blank-page fixes + stratified board.
- **Discipline**: every claim needs a named receipt read back from disk;
  stage receipts over exit codes; BLOCKED is not FAIL; never assert from a
  tool's own success response.
