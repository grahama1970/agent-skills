# HANDOFF — live-evidence (2026-08-27, DriveWealth interview prep)

## Addendum — 2026-08-27 evening session (GLM, pre-handoff)

- **Prep-pack lane LANDED LOCALLY, not on origin.** The previously uncommitted
  prep-pack work (validate_prep_pack.py, validate_precomputed_oracles.py,
  compile_drivewealth_oracle_pack.py, prep_pack_drivewealth.json, route_plan
  fixture blocks, 4 agentic-eval cases, run.sh/SKILL.md wiring) was reviewed,
  validated, and committed as `cfda4a9bab` on local main. Gates proven:
  eval-prep-pack PASS, eval-precomputed-oracles PASS, dry compile PASS
  (10 interviews / 90 questions / 808 docs), memory write HTTP 200 + 3/3
  recall probes, 12/12 touched tests.
- **Push is blocked by pre-existing repo divergence, not by this skill.**
  Local main: ahead 186 / behind 126. `git merge origin/main` refuses on 14
  dirty files owned by unidentified lanes (incl. substantive monitor-
  opportunities policy edits — the auto-submit standing-authorization removal).
  Do NOT stash or reset them; incoming commit a686cb0263 also touches this
  skill's SKILL.md, so expect a merge conflict there when integration happens.
- **HUD verified working end-to-end, live.** Serve :8799 serves the current
  dist (byte-identical, rebuilt 16:11, post-9bd753c0fd). Pumped DW-AI-01's 9
  turns through POST /api/transcript → 3 cards published, all `supported` →
  HUD rendered live: SAY ALOUD banner, answer-key card, lane badges. An idle
  HUD (no listener, stale session) LOOKS broken — that is the "trash fire"
  report explained. The listener was NOT running; interview day still needs:
  `./run.sh listen --mode pipewire --backend-url http://127.0.0.1:8799 --device
  cpu --consent-confirmed`. As of the default-port fix, CLI defaults now point
  at 8799; older notes about a 8765 default are stale.
- **DEFECT (unfixed): replay clobbers the active session.** `live_evidence
  replay` (and any bare `POST /api/session/start {"consent_confirmed": false}`)
  silently resets a live session: LISTENING·MEETING → ARMED·CONSENT NEEDED,
  visible cards wiped, no warning. Suggested fix: 409 on active session
  without explicit reset flag, or replay attaches to the active session.
- **HUD session state right now is synthetic** (my replay turns + 3 demo
  cards). Stop → Start clears it before a real session.
- **ask skill CLI drift:** SKILL.md documents `./run.sh ask --handler <seat>
  --execute --json`, but the installed CLI has no `--handler` option (error:
  "No such option: --handler. Did you mean --chain?"). Reconcile docs or CLI
  before the next consult attempt.
- **Untouched next increment:** solver JSON deck schema — solver emits
  {title, trigger} points; replace browser markdown parsing in
  scannablePoints() (ui/src/components/SolutionStage.tsx:73) and
  parseSolutionSections(). Scoped, zero code written.


For the next agent. Everything below is receipt-backed; commands named were
run and read back in the sessions of 2026-08-26/27. Do not trust this file
over live state — verify with the named commands.

## Resume Here

- **Objective**: live-evidence is the interview copilot for the DriveWealth
  AI Engineer technical assessment (two 45-min principal sessions). It must
  listen to call audio, identify questions, and glance-serve answer cards
  from the curated KB. Interview-day bring-up is ONE command:
  `scripts/interview_day.sh` (fail-closed probes: scillm, memory daemon, KB
  recall, doctor, pack load, session, listener, HUD).
- **Exact next action**: nothing is blocking interview use. Highest-value
  remaining increments, in order: (1) solver-side JSON deck schema
  ({title, trigger} points instead of markdown prose parsed in the browser
  — see ui/src/components/SolutionStage.tsx scannablePoints comment);
  (2) clean full-suite eval rerun on a quiet box (last full run
  USABLE_WITH_GAPS 41/47, all 6 failures individually re-proven or
  root-caused after fixes — receipts below); (3) the 19-item defect ledger
  at scratchpad tickets_to_file.md (session-local; re-derive from this file
  if gone).

## What works (verified live)

- Physical audio chain: chatterbox voice -> speaker/null-sink -> PipeWire
  monitor capture -> CPU whisper -> stage-1 -> cards. Attended run 7/9
  matches with all 9 questions carded; batch-2 campaign 38/45 at realistic
  pacing. CPU whisper is LOAD-SENSITIVE: identical wav scored 0/9 at load
  80 and 8/9 at load 30. Keep the box quiet during use; the CUDA/torch
  driver mismatch (warning in listener log) forces CPU STT.
- Blind question extraction: all 10 webgpt-authored interviews pass
  (77/90+), fixture fixtures/mock_interviews_drivewealth.json (status:
  final, webgpt coverage-approval receipt embedded).
- KB: 856+ units in /memory scope drivewealth incl. a 90-question answer
  key (knowledge/answer-key/ in the dw-openapi repo). Recall verified with
  interviewer-phrased probes via daemon POST :8601/recall. KNOWN: CLI
  `memory recall --scope` returns found:false while the daemon path works
  (memory-repo bug); `memory learn` 422s on agent-written lessons
  ("no extractable taxonomy").
- HUD (rebuilt 2026-08-27 through four external design-review rounds):
  teleprompter single column (root cause of earlier crushed layout:
  .app-layout reserved the rail grid track), 2x2 CardDeckMatrix with 1-4
  hotkeys and focus dimming, trigger-length bullets, diagnostics hidden via
  .answer-provenance (data stays in DOM), TTS earcons policy-gated on
  voice_output (silent in meeting purpose BY DESIGN — do not "fix").
  Serve on PORT 8799 — 8765 is owned by task-monitor on this machine.
- Trigger pipeline fixes this week (committed): imperative-clause detection
  and interviewer-statement fallthrough in question_window.py — principal
  phrasing ("Design X", "We need Y") now reaches stage-1; candidate-channel
  suppression regression-proven (eval-interview-loop 6/6 PASS, latest run
  2026-08-27). Publication: INSUFFICIENT cards are held, observable at
  GET /api/cards/publications (causal assertions in eval_interview_loop.py).

## Known-broken / unfinished

- Full 47-case suite: no clean READY receipt exists. Last full run 41/47;
  the 6 fails were: stray .venv (removed, then RESTORED deliberately — a
  concurrent skill-maintainer workflow uses it; contract conflict
  unresolved), chatterbox CUDA-OOM crash + scillm restart (environmental,
  cases re-proven individually), fast-solver latency (a concurrent
  workflow was mid-fix; final state unknown), interview-loop (fixed:
  publication-hold migration). Background eval runs on this box get killed
  by concurrent workflows (exit 144) — run long suites foreground/chunked.
- STT jargon mishears: "immutable"->"a mutable" observed, self-corrected by
  revision fencing. Hotword biasing for RealtimeSTT is the standard fix
  (unimplemented).
- Compound questions on the '?' path canonicalize the tail clause only
  (imperative path keeps full turn). DW-AI-02 T05 forensics.
- ANOTHER AGENT has uncommitted work in this skill right now (SKILL.md,
  run.sh, fixtures, scripts/compile_drivewealth_oracle_pack.py,
  prep_pack_drivewealth.json, validate_prep_pack.py) — the prep-pack lane.
  Coordinate before committing over it.

## Key artifacts

- fixtures/: briefing_drivewealth.json (18 points + diagram sources),
  mock_interviews_drivewealth.json (10 interviews, final),
  drivewealth_bridge.md, tuesday_runbook.md, metrics_cold.md,
  debugger_walkthrough.md (4 breakpoint seams incl. exact file:line),
  diagrams/ (authority-stack + 3 architecture charts, phart + SVG).
- Rehearsal audio: /mnt/storage12tb/skills/live-evidence/synthetic-interviews/
  DW-AI-01..10.wav (~11-13 min each) + timecoded .transcript.txt.
- Blind grader: run.sh eval-synthetic-interviews [--interview ID] [--gap N]
  (dual tail|head stems — both canonicalization styles count).
- .vscode/launch.json (repo root, gitignored): debugger demo configs.

## Environment gotchas (each cost real time)

- LIVE_EVIDENCE_REPOS is COLON-separated; 5 repos incl.
  ~/workspace/experiments/dw-openapi.
- SciLLM key: export LIVE_EVIDENCE_SCILLM_KEY from the container
  (docker exec docker-scillm-proxy-1 printenv SCILLM_MASTER_KEY); ambient
  SCILLM_PROXY_KEY is drifted and 401s.
- Older builds needed --backend-url because the default was 8765 (wrong
  service, 404 in listener log). Current builds default to 8799, but keep
  explicit --backend-url in runbooks for copy-paste clarity.
- GPU: chatterbox TTS + CUDA whisper cannot run concurrently (OOM crash
  receipt 2026-08-26). Do not run TTS during live capture.
- pkill patterns containing "live_evidence" match your own shell (exit 144).

## Last verified commands (2026-08-27)

- eval-interview-loop: 6/6 PASS
- eval-synthetic-interviews per interview: 01..10 all ok:true (dual-stem)
- HUD screenshot after teleprompter commit 9bd753c0fd: matrix deck renders,
  hotkeys work, diagnostics hidden (commits 6473c4e358, 4ae2d62d76,
  9bd753c0fd)

## Proof boundary

mocked: no for everything labeled verified above; live: yes. Unverified:
full-suite READY, fast-solver final state, Qdrant vectors + graph edges for
the drivewealth scope (BM25 carries recall today), authenticated HCP token
lane (ops-terraform hcp-status PASS path needs a real TFE_TOKEN).
