# Handoff — /ask + /surf session, 2026-08-16

## State
- Primary checkout `~/workspace/experiments/agent-skills`, branch `main`, clean.
- All work landed on `origin/main` via plumbing. `git log origin/main..HEAD` is empty of today's work.
- Dirty tree + diverged local `main` are EXPECTED here (cron lanes write tracked files). See ops-worktrees SKILL.md "A dirty tree is not a finding".

## Environment fix that invalidates older test results
`~/.local/share/surf-cli/host-wrapper.sh` hardcoded
`agent-skills-font-integrate/.../host.cjs` (branch codex/best-practices-font-skill).
ALL browser automation ran that feature branch. Repointed to main.
Backup: /tmp/claude-1000/host-wrapper.sh.bak
The surf host caches modules at startup — after editing surf-cli/native, kill the
host PID (never `pkill -f`, it matches your own shell) and let Chrome respawn it.

## Proven live (receipts, re-runnable)
- webgpt, webkimi, webgemini, webgrok, webdeepseek: `run.sh prove-workflow <h>` -> WORKS 1/1
- webclaude: out of credits -> auto-falls back to claude-opus-5-high -> PASS
- claude-fable-low rate limited -> claude-opus-4-8-high, substitution recorded in receipt
- deepseek reads images: `deepseek.submit --mode Vision --attach-file lion.jpg` -> "Lion"
- handoff chain: `run.sh handoff` -> handler -> join -> human

## Fixed today (all with live evidence)
- `--stable-stall-ms` was sent to every provider; only webgpt.submit accepts it, so
  5 of 6 browser seats died on a CLI usage error before opening a page.
- `claude-fable-low` dispatched as nonexistent `claude-fable` — local seat never worked.
- Lanes declared browser_handler_timeout 3s after submit while answers arrived at 15s.
- Availability marked a whole PROVIDER limited from ambient tabs Ask never uses;
  one stale tab disabled webgpt for every run. Now scoped to the tab in use.
- Unbound browser runs now open a FRESH tab instead of inheriting ambient state.
- Seat windows released when their response is on disk (one pending lane held all).
- Preflight scanned JPEG bytes and rejected `~4`/`~5` as prose — blocked all images.
- handoff.json persisted; `run.sh handoff` added.

## Panel quorum raised to 3 (2026-08-17) — EDITED, NOT YET RUN
Roundtable quorum was 2 everywhere; a 2-seat panel that loses a seat is a single
opinion with clean receipts. Now 3 answering seats for a roundtable, 2 kept for
compete (a head-to-head at 2 is real). Both floors count seats that ANSWERED.

Changed: `src/ask/panel_compliance.py` (new `ROUNDTABLE_MIN_ANSWERING=3`,
`COMPETITION_MIN_ANSWERING=2`, new `check_roundtable_quorum` wired into
`audit(mode="roundtable")`); `scripts/prove_workflow.py` (imports both constants,
roster default 5 seats for roundtable, mode-aware 2400s timeout);
`scripts/live_roundtable_reliability.sh` (`MIN_DELIVERED` 2->3, handlers 3->5,
900/780s -> 1800/1620s); `best-practices-roundtable/SKILL.md` (new quorum
section — that file previously stated NO minimum at all); `ask/SKILL.md` panel
compliance table.

`fixtures/agentic_eval_live.json`: dropped the duplicate webgpt case (two cases
ran the identical `prove-workflow webgpt`), added three panel cases —
roundtable-reaches-quorum-and-passes-its-own-audit, roundtable-below-quorum-is-
not-reported-as-a-panel, competition-gets-two-isolated-candidates-answering.

NOTHING HERE IS VERIFIED. The session that wrote it could not execute — `run.sh`,
`python3`, and the agentic-evals runner were all refused by its permission mode.
The JSON has not been parsed, the new import has not been resolved, and no panel
has been run. Run before trusting any of it:
```
skills/agentic-evals/run.sh run skills/ask/fixtures/agentic_eval.json      # fast, catches import/syntax
skills/agentic-evals/run.sh run skills/ask/fixtures/agentic_eval_live.json # live panels, hours
```
Verified only by read-back: the pinned fixture run's join receipt is
`"status": "NEEDS_ATTENTION"` (`node-artifacts/join/node-receipt.json:228`), so
the new quorum check reads it as disclosed and the 8 pinned compliance cases do
not regress.

## Open
- No multi-seat panel has had ALL seats answer. `prove-workflow roundtable|compete` exist.
- The 8 pinned roundtable/competition compliance cases replay ONE captured run,
  `ask-tau-a-project-agent-is-stuck-on-one--f6d214e20595`, in which BOTH seats
  failed (webclaude `missing_sentinel` from the `--stable-stall-ms 0` bug fixed
  the same day; webgpt `browser_submit_not_accepted`). They prove the referee
  works, not that a panel runs. Re-capture from a post-fix run that reaches
  quorum.
- Measured before today: 60.3% BLOCKED across 1765 runs. Last 10h of real runs: 75% PASS (n=20, small).
- Decide whether the host-wrapper repoint should be permanent.

## Testing policy (operator, non-negotiable)
No unit tests for skills. /agentic-evals only, with real_world cases exercising live paths.
Fast suite: skills/ask/fixtures/agentic_eval.json (48 cases).
Live suite: skills/ask/fixtures/agentic_eval_live.json (18 cases, real providers).
