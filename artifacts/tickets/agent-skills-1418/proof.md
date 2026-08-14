# Issue 1418 Proof

Issue: `project-watchdog: persisted tick receipt omits excluded issue reasons from dry-run scan`

## Result

Persisted tick receipts now include first-class machine-readable issue exclusion fields:

- `issue_scans`: per-project scan summaries with scanned count, excluded counts, excluded issue numbers, and repo-qualified issue refs.
- `excluded_counts`: aggregate exclusion counts by reason.
- `excluded_issues`: aggregate issue numbers by reason.
- `excluded_issue_refs`: aggregate repo-qualified issue refs by reason.

The registry scan still logs `issues_excluded_from_dispatch`, but the receipt is now enough to explain skipped issues without reading the log.

## Commits

- repair commit pushed to `origin/main`: `8b173d7a250b49b61546da32eea4d37fc9c9c09a`
- remote ref proof: `git ls-remote origin refs/heads/main` returned `8b173d7a250b49b61546da32eea4d37fc9c9c09a refs/heads/main`

## Deterministic Checks

Focused regression tests:

```text
uv run --project skills/project-watchdog pytest -q \
  skills/project-watchdog/tests/test_project_rotation.py::test_stale_lease_skip_reason_is_machine_readable \
  skills/project-watchdog/tests/test_project_rotation.py::test_tick_receipt_copies_excluded_issues_from_selected_scan \
  skills/project-watchdog/tests/test_project_rotation.py::test_strict_project_tick_does_not_fall_through_to_another_project \
  skills/project-watchdog/tests/test_project_rotation.py::test_all_project_tick_is_the_explicit_fleet_fallback

4 passed in 0.11s
```

Full project-watchdog tests:

```text
uv run --project skills/project-watchdog pytest -q skills/project-watchdog/tests

169 passed in 3.02s
```

Skill sanity:

```text
skills/project-watchdog/sanity.sh

project-watchdog sanity: 45 passed, 0 failed
unit tests: 169 passed in 2.85s
```

Mock evidence claim checker:

```text
python3 scripts/check_mock_evidence_claims.py

OK: checked 647 test file(s); no mock+proof claim violations
```

## Live Dry-Run Receipt

Receipt: `artifacts/tickets/agent-skills-1418/live-target-busy-receipt.json`

The receipt exercised a real project-watchdog dry-run tick against live GitHub issue listing for `grahama1970/agent-skills`, then read back the receipt JSON.

Live assertion output:

```json
{
  "has_first_class_excluded_counts": true,
  "has_first_class_excluded_issues": true,
  "receipt_parsed": true,
  "scan_names_agent_skills": true,
  "target_busy_count_positive": true,
  "target_busy_names_1411": true
}
```

Receipt readback summary:

```json
{
  "status": "COMPLETED",
  "ok": true,
  "excluded_counts": {
    "blocked": 31,
    "human_hold": 7,
    "leased": 3,
    "target_busy": 1
  },
  "excluded_issues": {
    "target_busy": [1411]
  }
}
```

The live proof did not scrape the log; it asserted the excluded issue from the receipt artifact.

## Worktree Audit

The ticket close worktree audit was run:

```text
skills/best-practices-github-ticket/scripts/audit-worktrees.sh \
  --repo /home/graham/workspace/experiments/agent-skills-worktrees/watchdog-excluded-receipts-1418 \
  --json
```

It exited non-zero because of retained worktree debt outside this task:

```json
{
  "ok": false,
  "total": 185,
  "tmp": 1,
  "detached": 56,
  "prunable": 0,
  "dirty_secondary": 50
}
```

The task worktree itself was clean after the repair commit. Closure therefore uses `GH_TICKET_SKIP_WORKTREE_AUDIT=1` with this proof artifact as justification.

## Evidence Boundary

- mocked: yes, unit tests use monkeypatch/fake project data and sanity uses a GitHub shim for mutation-safety checks.
- live: yes, the dry-run CLI receipt used the real project-watchdog runtime and live GitHub issue listing.
- actually exercised: registry exclusion reasons, receipt propagation, strict/fleet regressions, full deterministic watchdog tests, and live receipt readback naming `target_busy` issue `#1411`.
- remains unverified: applied global cron dispatch after resume and full `monitor-opportunities` 2am cron readiness.

Immutable Goal: NOT_MET
