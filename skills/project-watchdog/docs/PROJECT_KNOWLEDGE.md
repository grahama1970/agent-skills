# project-watchdog — Project Knowledge

Curated current state. This is context, not proof. Claims here must be backed by
`sanity.sh` gates, receipts, or logs before they count as evidence.

Last synced: 2026-07-27 (second pass: escalation + Herdr pane dispatch)

## What this skill is

The single cron-driven control plane that scans registered GitHub repos for
routable issues and runs **one** bounded dispatch per tick. It exists so each
project does not grow its own cron loop.

It is *not* a repair engine. It selects, leases, invokes one bounded project
command, records a receipt, and stops.

## Current readiness

| Area | State | Evidence |
|---|---|---|
| CLI surface | READY | `sanity.sh` gate 1 |
| Fail-closed state gates | READY | gates 5, 6 |
| Dry-run safety boundary | READY | gate 4 — zero mutations observed via recording `gh` shim |
| Receipt retention policy | READY | gate 7 |
| Locking incl. stale reclaim | READY | unit tests `test_stale_lock_is_reclaimed`, `test_fresh_lock_is_not_reclaimed` |
| Path resolution | READY | gate 9 AST guard + `test_config_paths_are_absolute_and_expanded` |
| **Live dispatch** | **NOT_ESTABLISHED** | No dispatch has run since the path fix. See below. |
| Readiness report (`report.json`) | NOT_ESTABLISHED | Not implemented |
| Idle escalation | READY | `sanity.sh` gate 11 — real CLI, 2s threshold |
| Herdr pane dispatch | READY | gate 12 — real panes, exit 0 and exit 7 |
| monitor-herdr coverage of hung panes | READY | hung command → `timeout` exit 124 → pane reports `blocked` → monitor flags `w82:p9` `blocked_or_unknown_observe_only` |

**Live dispatch is unproven.** Both handlers were repaired on 2026-07-27 but
have not executed end to end since. The last verified live dispatch predates the
`${HOME}` bug being introduced. Treat `handle_tau_handoff_dispatch` and
`handle_tau_coder_spec` as untested against a real issue until a receipt says
otherwise.

## Known gaps and active blockers

1. **Label vocabulary mismatch — the reason the watchdog is idle.**
   Routing requires `agent-work` + `executor:local` + a body marker. Tickets
   filed by `/ticket` carry `type:*` / `route:*` / `maintainer-blocked` /
   `needs-human`. As of 2026-07-27, `gh issue list --repo grahama1970/tau
   --label agent-work` returns 0 and the cron had logged **41,607** consecutive
   `NOOP / no_routable_issues` ticks since 2026-06-28. Nothing is wrong with the
   scan; the two halves of the system speak different label vocabularies.
   Reconciling them is tracked separately and is not fixed by this skill alone.

2. **Dispatch is synchronous, in both backends.** The tick blocks on a
   bounded wait so lease and closure semantics are unchanged. Fire-and-forget
   pane dispatch needs a reconciliation path for leased-but-unfinished
   issues, which does not exist.

3. **No cross-repo dependency edge.** When a project is blocked on another
   project's work there is no machine-readable `blocked-by` field and no
   unblock poll. The dependency lives only in prose in the issue body.

4. **No readiness report.** `best-practices-skills` recommends
   `report.json` + `index.html` for orchestrator skills. Not built.

5. **`runtime_self_improvement: basic`.** Declared honestly: the skill has
   `sanity.sh` but no `./run.sh verify` command and no maintainer-ticket loop.
   Do not raise the tier without building those.

## Repairs applied 2026-07-27

| Defect | Impact | Fix |
|---|---|---|
| `Path("${HOME}/...")` in 4 constants | Python never expands `${HOME}`; all four were relative paths that did not exist, so **any** dispatch would have failed | `config.py` resolvers + AST guard in `sanity.sh` |
| `grahama1970/tau` hardcoded in every `gh` wrapper | A non-Tau dispatch would have commented on, relabelled, and closed an unrelated Tau issue | `github.py` takes `repo` with no default |
| Silent `except` in `release_lock` | Lock-release failures invisible in production | logs at ERROR |
| No stale-lock reclaim | One SIGKILL leaves the watchdog permanently `BLOCKED` | 900s reclaim, logged at WARNING |
| Uneventful receipts persisted | 41,682 dirs / 329 MB | `NOOP`/`SKIPPED` not persisted |
| `git push grahama1970 main` hardcoded | Wrong remote and branch for any other project | `git push origin HEAD` |
| No symlink containment on issue paths | A symlink inside the worktree could reach outside it; issue bodies are attacker-controlled | resolve-then-contain in `issue_fields` |

## Second pass, 2026-07-27

Three additions, each proven through the real path rather than unit tests alone.

**Idle escalation.** `streaks.py` counts consecutive idle ticks per project.
Past `NOOP_ESCALATION_SECONDS` (24h) a tick reports `NEEDS_ATTENTION` /
`idle_streak_exceeded` with a diagnosis, and persists a receipt at most once per
renotify window. The live tau streak began counting 2026-07-27; unless routing is
fixed first, tau escalates roughly 24h later.

**Herdr pane dispatch.** `herdr_space.py` runs a bounded dispatch as a named pane
in the `autoupdate` space. Three findings came out of building it, all from live
runs rather than from reading docs:

1. `herdr agent wait --status done` is rejected by Herdr itself — *"done is a UI
   attention state; use idle for CLI agent completion waits"*.
2. Waiting on `--status idle` then **also** fails for an arbitrary command:
   *"timed out waiting for agent status change"*, because agent status comes
   from provider integrations that a plain command does not have. Completion is
   therefore detected by a sentinel file, not by a UI state.
3. `$monitor-herdr` treats `done`/`idle`/`blocked`/`unknown` as stopped —
   **`working` is not in that set**. A hung pane would have sat in `working`
   forever, unflagged. The wrapper self-limits with `timeout` so a hang becomes a
   `blocked` pane, and holds a failed pane for 15 minutes so it does not vanish
   before the monitor's next tick.

End-to-end proof: a deliberately hung dispatch exited 124, the pane reported
`blocked`, and `monitor-herdr tick --space autoupdate --include-agent
watchdog-dispatch` flagged pane `w82:p9` as
`blocked_or_unknown_observe_only`. No changes to `monitor-herdr` were needed for
this; the composition works through its existing filter.

**Default is still `local`.** Pane dispatch is opt-in per project or via
`PROJECT_WATCHDOG_DISPATCH_BACKEND`, because the underlying dispatch handlers
remain unproven against a real routable issue.

## Companion assumptions

- `gh` is authenticated for every registered repo.
- `uv` resolves via `UV_BIN`, `~/.local/bin/uv`, or `PATH`.
- Tau exposes `handoff-command-loop` and
  `handoff-command-loop-github-transport`.
- Receipts and logs live under `~/.local/state/project-watchdog`, overridable
  with `PROJECT_WATCHDOG_STATE_ROOT`.
