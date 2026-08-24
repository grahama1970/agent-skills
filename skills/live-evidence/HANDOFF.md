# Live Evidence Handoff

- schema: `tau.agent_handoff.v1`
- updated: `2026-08-24T13:11:49-04:00`
- project_dir: `/home/graham/workspace/experiments/agent-skills/skills/live-evidence`
- purpose: clear context safely before the next `$live-evidence` work

## Resume Here

- Objective: continue the `$live-evidence` v2 immutable goal: a consented live
  meeting copilot that surfaces research cards, memory-recall cards, code cards,
  briefing packs, and human-approved actions with source-bound evidence.
- Operational state: v1 technical-interview proof is achieved and is the
  regression floor. v2 is not complete until the documented field-campaign bar
  in `IMMUTABLE_GOAL.md` is met.
- Exact next action: rerun the code-family path against the Sparta/QRA meeting
  question and prove whether the recent code-card ranking fix now cites
  implementation source instead of commit messages, memory metadata, or design
  docs.
- Suggested command:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/live-evidence
./run.sh eval-transcript-meeting
```

- If the focused transcript meeting check passes, run the owning agentic eval:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/agentic-evals
./run.sh run ../live-evidence/fixtures/agentic_eval.json \
  --output /tmp/live-evidence-agentic-evals-latest.json
```

## What Exists

- `SKILL.md` defines the current product contract: local-first consented meeting
  copilot; default path is audio/STT to bounded trigger to Memory/GMO/code/ripgrep
  to `$ask` for code questions to source-bound evidence card.
- `IMMUTABLE_GOAL.md` defines the v2 completion bar: at least 20 real consented
  sessions, all three card families firing where warranted, usefulness labels,
  speech-start latency, blinded card-reading median under 3 seconds, and zero
  formal-assessment assistance/action/invented support.
- `PROJECT_STATE.md` records the last broad state table. It marks several lanes
  live-proven, but still lists open debts around live Ask in evals, diarization,
  model-lane rubric authorship, and editor bridge provisioning.
- `PROJECT_KNOWLEDGE.md` has newer 2026-08-22/2026-08-23 notes: transcript
  meeting eval, surface selection, STT segmentation fix, and code-family answer
  quality as the active open gap.
- `fixtures/agentic_eval.json` is the committed eval contract. It contains the
  real-world cases that should be updated when live-evidence behavior changes.

## What Works

- Local deterministic proof exists for the v1 interview loop through
  `./sanity.sh` according to `SKILL.md`. That proof starts a real local FastAPI
  server, posts a final interviewer turn over HTTP, runs real ripgrep against a
  temp repo, waits for a source-bound card, validates UI instrumentation, and
  writes a JSON receipt.
- The transcript-meeting harness exists:
  `scripts/eval_transcript_meeting.py`, `run.sh eval-transcript-meeting`, and
  `fixtures/transcript_meetings.json`.
- Surface selection exists in `src/live_evidence/surface_selector.py` and is
  documented as a direct SciLLM stage-1 exception for latency.
- A recent live-evidence commit exists for the active gap:
  `a5817f43a0 Fix live-evidence code card source ranking`. It touched
  `coordinator.py`, `retrieval/__init__.py`, `retrieval/ranker.py`,
  `retrieval/ripgrep.py`, and `tests/test_ripgrep.py`.

## What Is Broken Or Unproven

- v2 immutable goal is not met. Do not report it as complete from a commit,
  green unit tests, or a subset eval.
- The code-family lane is the active risk. The old handoff said it was broken;
  the newer commit says it was fixed. Treat the true current state as
  `recently patched, needs focused live/deterministic rerun`.
- `./sanity.sh` does not prove live mic, PipeWire, GPU STT, Graph Memory, Brave,
  Dogpile, or the 20-session field campaign unless those lanes are explicitly
  exercised.
- Any pytest with monkeypatching is wiring-only. It does not prove live meeting
  behavior or semantic card usefulness.
- Diarization/speaker identity is still not built according to
  `PROJECT_STATE.md`.
- Research-card live behavior is not complete unless a real research lane
  receipt shows Brave/Dogpile or governed fallback behavior for the target case.

## Active Files To Inspect First

- `src/live_evidence/coordinator.py`
- `src/live_evidence/retrieval/ripgrep.py`
- `src/live_evidence/retrieval/ranker.py`
- `src/live_evidence/retrieval/__init__.py`
- `src/live_evidence/surface_selector.py`
- `scripts/eval_transcript_meeting.py`
- `fixtures/transcript_meetings.json`
- `fixtures/agentic_eval.json`
- `IMMUTABLE_GOAL.md`
- `PROJECT_KNOWLEDGE.md`
- `PROJECT_STATE.md`

## Working Tree Notes

- Current branch at handoff creation: `main`, with local branch ahead and behind
  origin. Do not pull, rebase, clean, stash, or switch branches without first
  inventorying unrelated work.
- Unrelated root handoff file exists at `local/HANDOFF.md`; it points to
  ops-memory and should not be used as the live-evidence handoff.
- Untracked generated state exists at
  `skills/live-evidence/episodic-archiver_task_state.json`. Treat it as
  non-source runtime state unless a later task explicitly proves it belongs in
  the committed skill contract.
- For alpha+ projects, work on `main` only unless the human explicitly says
  otherwise. Do not create a random worktree for live-evidence work.

## Receipts Used For This Handoff

- `date -Iseconds` -> `2026-08-24T13:11:49-04:00`
- `git status --short --branch -- skills/live-evidence/HANDOFF.md skills/live-evidence/episodic-archiver_task_state.json local/HANDOFF.md`
- `git show --name-status --oneline --no-renames a5817f43a0 -- skills/live-evidence`
- File read-backs in this turn:
  - `skills/handoff/SKILL.md`
  - `skills/live-evidence/SKILL.md`
  - `skills/live-evidence/HANDOFF.md`
  - `skills/live-evidence/IMMUTABLE_GOAL.md`
  - `skills/live-evidence/PROJECT_STATE.md`
  - `skills/live-evidence/PROJECT_KNOWLEDGE.md`
  - `skills/live-evidence/fixtures/agentic_eval.json`
  - `skills/live-evidence/run.sh`

## Proof Boundary

- mocked: `no` for this handoff update; no mocked test result was used as proof.
- live: `no` for feature behavior in this turn; this handoff was produced from
  file read-backs and git inspection only.
- exercised: skill contracts, state docs, recent live-evidence git history, and
  the handoff file itself.
- unverified: current code-card behavior after `a5817f43a0`, full agentic eval
  readiness, live mic/STT path, research lane, Graph Memory lane, browser UI
  screenshots, and the 20-session field campaign.

## Blocker If You Resume And Stop

- If `./run.sh eval-transcript-meeting` fails, preserve the receipt and report
  the exact failing question, cited source path, expected source path, and card
  family. The likely next repair is the code retrieval/ranking path, not a new
  dashboard, summary, or commit-only status update.
