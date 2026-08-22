# Handoff Report: persona-dream

**Timestamp**: 2026-08-22T00:00:00Z
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

- **Research phase**: `P2_LIVE_CONTINUITY_CHAIN` (`CURRENT_STATUS.json`,
  authoritative). Proven: N=5 live-chain reliability pilot (engineering
  feasibility only). Not proven: the research benefit itself.
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
- **Single full-cycle receipts** exist: e.g. run
  `/mnt/storage12tb/skills/persona-dream/outputs/eval-full-cycle-20260820T143356Z`
  (all 7 stages, `carried:6`) and the journal run `embry-journal-20260820`
  (spoken journal WER 0.104, two carried conversations).

## 4. What is Currently Broken / Open

- **End-to-end reliability is the open frontier**: `full-cycle-live` eval
  measured 1/3 trials passing on 2026-08-20. The two blocks were the
  pipeline's own fail-closed research gates, not infrastructure:
  1. recall-instrument gates — `negative_control_absent_top10: false` (the
     negative-control query semantically leaked into memory top-10; word-level
     avoidance was fixed in `autonomous_dream_cycle.py`, semantic leakage
     remains possible) and an unranked recall probe;
  2. ArcFace identity gate — a storyboard frame's generation failed
     (`sb_003: generation failed rc=1`).
  This matches successor issue #1128 (reliability soak). Suite verdict
  NOT_READY is honest; do not weaken oracles to green it.
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

1. Raise full-cycle reliability: fix identity-gate frame regeneration (retry
   or reroll on `generation failed rc=1`) and decide the semantic
   negative-control policy (embedding-distance check at draft time?), then
   rerun `full-cycle-live` until READY. This is #1128's evidence.
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
