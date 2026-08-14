# Issue 1417 Proof

Issue: `project-watchdog: global cron used --project tau but dispatched agent-skills repairs every minute`

## Result

Implemented strict project selection for `project-watchdog tick`:

- `--project <id>` now scans only the named project.
- fleet rotation is explicit via `--project all`.
- generated global cron lines now use `--project all`.
- tick receipts now include `rotation.mode` as `strict` or `fleet`.
- closure audit and completion attestation use the same strict/fleet candidate set as ticket repair dispatch.

The production cron line remains disabled. This proof does not claim the global cron has been resumed.

## Commits

- repair commit pushed to `origin/main`: `60225efb9511c9c38942e00f49d108febe5cc246`
- remote ref proof: `git ls-remote origin refs/heads/main` returned `60225efb9511c9c38942e00f49d108febe5cc246 refs/heads/main`

## Deterministic Checks

Focused regression tests:

```text
uv run --project skills/project-watchdog pytest -q \
  skills/project-watchdog/tests/test_project_rotation.py::test_strict_project_tick_does_not_fall_through_to_another_project \
  skills/project-watchdog/tests/test_project_rotation.py::test_all_project_tick_is_the_explicit_fleet_fallback \
  skills/project-watchdog/tests/test_project_watchdog.py::test_the_cron_line_sources_a_shell_init_file

3 passed in 0.22s
```

Full project-watchdog tests:

```text
uv run --project skills/project-watchdog pytest -q skills/project-watchdog/tests

167 passed in 2.88s
```

Skill sanity:

```text
skills/project-watchdog/sanity.sh

project-watchdog sanity: 45 passed, 0 failed
unit tests: 167 passed in 2.88s
```

Mock evidence claim checker:

```text
python3 scripts/check_mock_evidence_claims.py

OK: checked 647 test file(s); no mock+proof claim violations
```

## Live Dry-Run Receipt

Receipt: `artifacts/tickets/agent-skills-1417/live-strict-project-proof.json`

The receipt exercised:

- real `skills/project-watchdog/run.sh install-cron --minute */17` dry-run rendering.
- real `skills/project-watchdog/run.sh tick --project tau --max-tickets 1` dry-run against the operator state root.
- no cron installation or GitHub mutation.

Receipt assertions:

```json
{
  "cron_line_uses_all": true,
  "install_dry_run_succeeded": true,
  "strict_tick_did_not_select_agent_skills": true,
  "strict_tick_mode": true,
  "strict_tick_names_tau": true,
  "strict_tick_reports_tau_paused": true,
  "strict_tick_selected_no_project": true
}
```

## Worktree Audit

The ticket close worktree audit was run:

```text
skills/best-practices-github-ticket/scripts/audit-worktrees.sh \
  --repo /home/graham/workspace/experiments/agent-skills-worktrees/watchdog-strict-project-1417 \
  --json
```

It exited non-zero because of retained worktree debt outside this task:

```json
{
  "ok": false,
  "total": 184,
  "tmp": 1,
  "detached": 56,
  "prunable": 0,
  "dirty_secondary": 50
}
```

The failing audit paths are pre-existing retained worktrees and do not include this task's dirty unstaged work. Closure therefore uses `GH_TICKET_SKIP_WORKTREE_AUDIT=1` with this proof artifact as justification.

## Evidence Boundary

- mocked: yes, unit tests use monkeypatch/fake project data and sanity uses a GitHub shim for mutation-safety checks.
- live: yes, the dry-run CLI receipt used the real project-watchdog runtime and operator state root.
- actually exercised: strict project selection, explicit fleet selection, cron line rendering, full deterministic watchdog tests, and live dry-run behavior for `--project tau`.
- remains unverified: applied global cron dispatch after resume, `#1418` receipt-exclusion repair, and full `monitor-opportunities` 2am cron readiness.

Immutable Goal: NOT_MET
