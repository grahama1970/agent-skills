# Project Knowledge: project-watchdog

**Last updated:** 2026-07-27 08:52 by agent
**Status:** Active development

## Current Understanding

- project-watchdog is a cron that scans registered GitHub repos for issues labelled agent-work, leases one per tick, and hands the repair to Tau as a tau.dag_contract.v1 DAG. It does not orchestrate the repair itself.
- Live dispatch is UNPROVEN end to end. As of 2026-07-27 every persisted receipt sampled (3000/3000) is NOOP and zero issues have ever been handled to completion.
- The coder command spec at tau/experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json is a TRANSPORT STUB: it returns --result-status COMPLETED unconditionally. The repair DAG gates on required_evidence [changed_files, focused_tests] so the stub fails the gate instead of reporting a false PASS.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-07-27 | Repair goes through tau.dag_contract.v1, not tau self-fix tick | The /tau skill states creator/reviewer and repair loops must be DAG contracts. self-fix tick resolves specs from agent-skills/agents/, where only 3 of 92 agents have one; the DAG lane uses Tau's own spec root, where coder/reviewer/goal-guardian all exist. |
| 2026-07-27 | Repair DAG is acyclic; retry lives in coder.max_attempts | A reviewer->coder retry edge was rejected by real Tau with cycle_detected and unsupported_ready_queue_condition. Tau already owns retry policy, so the edge duplicated it. |
| 2026-07-27 | Removed herdr pane dispatch and cross-repo blocked-by | Neither was touched by the first live probe and neither had ever run outside self-authored tests. Runtime code dropped 2307 -> ~1750 lines. |
| 2026-07-27 | /ticket stamps agent-work at file time | The router selected on agent-work while /ticket emitted only type:*/route:*. The two halves shared no vocabulary, producing 41,607 consecutive no-work ticks over roughly a month. |

## Open Questions

- [ ] What fills the coder command spec? A real coder writes to the repo; code-runner returns a patch for review. Unresolved, and it is the last blocker to a completed loop.
- [ ] Should sanity.sh gain the live E2E gate that best-practices-skills requires for composite runtime skills? Its absence is why the missing-spec failure was found by a manual probe rather than by CI.
- [ ] core.py:254 still has one silent except handler flagged by correctness-no-silent-fallback.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/project_watchdog.py` | Typer CLI only; no business logic |
| `scripts/watchdog/commands.py` | tick / install-cron / set-state / status |
| `scripts/watchdog/registry.py` | project lookup and routable-issue selection |
| `scripts/watchdog/handlers.py` | compiles the repair DAG and calls `tau dag-run` |
| `scripts/watchdog/streaks.py` | idle-streak escalation |
| `scripts/watchdog/github.py` | gh wrappers; `repo` required, never defaulted |
| `scripts/check_path_literals.py` | AST guard against `Path("${VAR}/...")` |
| `registry/projects.json` | registered projects; `registry/state.json` is the operator gate |
| `sanity.sh` | 45 behavioural gates, zero mocks |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
