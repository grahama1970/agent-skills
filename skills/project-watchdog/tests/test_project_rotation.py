"""Fleet rotation and per-target collision (#1084, #1083).

The crontab pins --project tau and tick() resolved exactly that project, so an
idle tau stalled the whole fleet and no other project was ever serviced.

Collision is a property of the TARGET, not the repository. agent-skills holds
364 skills; two tickets against different ones share no files. Scheduling on the
repository blocked 363 skills to protect 1, which is why a single lease on tau
left the fleet dispatching nothing.
"""
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog import commands, registry  # noqa: E402
from watchdog.registry import (  # noqa: E402
    UNKNOWN_TARGET,
    busy_targets,
    issue_targets,
    select_next_project,
    targets_are_blocked,
)

PROJECTS = {
    "projects": [
        {"project_id": "alpha", "repo": "o/alpha"},
        {"project_id": "beta", "repo": "o/beta"},
        {"project_id": "gamma", "repo": "o/gamma"},
    ]
}
ALL_ACTIVE = {
    "projects": {
        "alpha": {"state": "active"},
        "beta": {"state": "active"},
        "gamma": {"state": "paused"},
    }
}


def _issue(num, target):
    body = f"type: bug\ntarget: {target}\nroute: backend_python_or_skill_runtime\n"
    return {"number": num, "body": body, "labels": [{"name": "agent-work"}]}


def test_rotation_serves_the_first_active_project():
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served=None)
    assert chosen["project_id"] == "alpha"
    assert skipped == []


def test_rotation_starts_after_the_last_served_project():
    chosen, _ = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="alpha")
    assert chosen["project_id"] == "beta"


def test_rotation_wraps_around():
    """With last_served=beta the walk is gamma, alpha, beta; gamma is paused."""
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="beta")
    assert chosen["project_id"] == "alpha"
    assert [s["reason"] for s in skipped] == ["project_state_paused"]


def test_paused_projects_are_skipped_with_named_reason():
    state = {"projects": {k: {"state": "paused"} for k in ("alpha", "beta", "gamma")}}
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=state, last_served=None)
    assert chosen is None
    assert [s["reason"] for s in skipped] == ["project_state_paused"] * 3


def test_missing_runtime_state_uses_project_default_state():
    state = {"projects": {}}
    active_project = {"project_id": "battle", "state_policy": {"default_state": "active"}}
    paused_project = {"project_id": "new", "state_policy": {"default_state": "paused"}}
    unconfigured_project = {"project_id": "old"}

    assert commands._project_runtime_state(active_project, state) == "active"
    assert commands._project_runtime_state(paused_project, state) == "paused"
    assert commands._project_runtime_state(unconfigured_project, state) is None


def test_a_lease_no_longer_removes_its_project_from_rotation():
    """One leased ticket used to withhold every other target in the repo."""
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served=None)
    assert chosen["project_id"] == "alpha", "a busy project is still serviceable"
    assert not any(s.get("reason") == "lane_busy" for s in skipped)


def test_a_ticket_is_blocked_only_by_its_own_target():
    busy = busy_targets([_issue(1, "skills/ask")])
    assert busy == {"skills/ask"}
    assert targets_are_blocked({"skills/ask"}, busy) is True
    assert targets_are_blocked({"skills/ticket"}, busy) is False


def test_target_is_read_from_the_line_ticket_writes():
    assert issue_targets(_issue(1, "skills/project-watchdog")) == {"skills/project-watchdog"}
    assert issue_targets(_issue(2, "skills/ticket/")) == {"skills/ticket"}


def test_markdown_target_paths_override_orientation_skill_mentions():
    body = """## Type

feature

## Target paths

- skills/battle/sanity.sh, skills/battle qualification scripts

## Orientation for a stateless agent

Use `skills/memory/run.sh recall`, `skills/project-state/run.sh --json`,
`skills/dogpile/run.sh`, `skills/brave-search/run.sh`, `skills/test/run.sh`,
and `skills/treesitter/run.sh`.
"""
    assert issue_targets({"body": body}) == {"skills/battle/sanity.sh"}


def test_markdown_target_paths_accept_coarse_exact_skill_path():
    body = """## Target paths

- skills/battle, project-watchdog/Tau repair lane

## Required skills

- `battle`
- `ticket`
"""
    assert issue_targets({"body": body}) == {"skills/battle"}


def test_a_legacy_ticket_falls_back_to_the_skills_it_mentions():
    """7 of the 8 leases open on agent-skills predate the target: line."""
    body = "Fix `skills/ask` compete when `skills/surf` returns a stale tab."
    assert issue_targets({"body": body}) == {"skills/ask", "skills/surf"}


def test_skill_scoped_project_ignores_unrelated_agent_skills_tickets(monkeypatch):
    """A Battle project tick must not take Ask/Surf tickets from the shared repo."""
    ask_issue = _issue(1507, "skills/ask")
    battle_issue = _issue(1510, "skills/battle")

    def run_cmd(cmd, timeout_s=None):
        import json as _json

        assert cmd[1:3] == ["issue", "list"]
        return {
            "exit_code": 0,
            "stdout": _json.dumps([ask_issue, battle_issue]),
            "stderr": "",
        }

    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    routable = registry.list_routable_issues(
        "t",
        {
            "project_id": "battle",
            "repo": "o/agent-skills",
            "worktree": "/tmp/wt",
            "issue_target_prefixes": ["skills/battle"],
        },
    )

    assert [i["number"] for i in routable] == [1510]
    assert routable[0]["watchdog_targets"] == ["skills/battle"]
    assert registry.LAST_SCAN["excluded_issues"]["project_scope_mismatch"] == [1507]


def test_broad_agent_skills_project_can_exclude_battle_tickets(monkeypatch):
    """Fleet rotation must not let generic agent-skills consume Battle tickets."""
    battle_issue = _issue(1510, "skills/battle")
    ticket_issue = _issue(1511, "skills/ticket")

    def run_cmd(cmd, timeout_s=None):
        import json as _json

        assert cmd[1:3] == ["issue", "list"]
        return {
            "exit_code": 0,
            "stdout": _json.dumps([battle_issue, ticket_issue]),
            "stderr": "",
        }

    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    routable = registry.list_routable_issues(
        "t",
        {
            "project_id": "agent-skills",
            "repo": "o/agent-skills",
            "worktree": "/tmp/wt",
            "issue_target_exclude_prefixes": ["skills/battle"],
        },
    )

    assert [i["number"] for i in routable] == [1511]
    assert routable[0]["watchdog_targets"] == ["skills/ticket"]
    assert registry.LAST_SCAN["excluded_issues"]["project_scope_mismatch"] == [1510]


def test_an_unreadable_target_is_its_own_namespace():
    """It collides with other unreadable tickets, not with the whole fleet.

    Blocking everything sounds safer and is not: one legacy ticket with no
    target then holds the entire fleet, which is the stall this replaces.
    """
    assert issue_targets({"body": "no paths at all"}) == {UNKNOWN_TARGET}
    assert targets_are_blocked({"skills/ticket"}, {UNKNOWN_TARGET}) is False
    assert targets_are_blocked({UNKNOWN_TARGET}, {UNKNOWN_TARGET}) is True
    assert targets_are_blocked({UNKNOWN_TARGET}, set()) is False


def test_a_multi_skill_ticket_blocks_on_any_overlap():
    assert targets_are_blocked({"skills/ask", "skills/loop"}, {"skills/loop"}) is True
    assert targets_are_blocked({"skills/ask", "skills/loop"}, {"skills/hum"}) is False


# --- lease vocabulary (#1088) -------------------------------------------------
#
# lane_busy_issues scanned only `agent-active`, but `skills/ticket/run.sh lease`
# applies `maintainer-active`. A ticket leased through the documented command
# therefore read as idle and the watchdog dispatched alongside it -- the exact
# work-ahead cascade #1083 closed, reachable through the supported path. There
# was no coverage of this function at all, which is how it shipped.

from watchdog import commands, config, registry  # noqa: E402


def _fake_gh(by_label: dict[str, list[dict]], fail_on: str | None = None):
    """Stand in for `gh issue list`, which ANDs repeated --label flags."""
    calls: list[str] = []

    def run_cmd(cmd, timeout_s=None):
        label = cmd[cmd.index("--label") + 1]
        calls.append(label)
        if label == fail_on:
            return {"exit_code": 1, "stdout": "", "stderr": "gh unavailable"}
        import json as _json
        return {"exit_code": 0, "stdout": _json.dumps(by_label.get(label, [])), "stderr": ""}

    return run_cmd, calls


def test_maintainer_held_lease_counts_as_in_flight(monkeypatch):
    run_cmd, calls = _fake_gh({"maintainer-active": [{"number": 1088, "labels": []}]})
    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    busy = registry.lane_busy_issues("t", {"repo": "o/agent-skills"})

    assert [i["number"] for i in busy] == [1088]
    assert sorted(calls) == sorted(config.LEASE_LABELS), "every lease label must be scanned"


def test_lease_scan_covers_the_same_vocabulary_classify_issue_refuses(monkeypatch):
    """One scan per label: a single call with both --labels matches neither."""
    run_cmd, calls = _fake_gh({
        "agent-active": [{"number": 10, "labels": []}],
        "maintainer-active": [{"number": 20, "labels": []}, {"number": 10, "labels": []}],
    })
    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    busy = registry.lane_busy_issues("t", {"repo": "o/agent-skills"})

    assert [i["number"] for i in busy] == [10, 20], "deduplicated and ordered"
    assert len(calls) == len(config.LEASE_LABELS)


def test_one_failed_label_scan_fails_the_whole_scan(monkeypatch):
    """A partial view must never be reported as the full in-flight set."""
    run_cmd, _ = _fake_gh({"agent-active": []}, fail_on="maintainer-active")
    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    try:
        registry.lane_busy_issues("t", {"repo": "o/agent-skills"})
    except RuntimeError as exc:
        assert "maintainer-active" in str(exc)
    else:
        raise AssertionError("a failed label scan must raise, not return a partial list")


def _lease_scan_fake(issue: dict, acquired_at: str | None):
    """Return live-shaped issue-list and label-event responses."""
    def run_cmd(cmd, timeout_s=None):
        if cmd[1] == "issue":
            label = cmd[cmd.index("--label") + 1]
            names = {entry["name"] for entry in issue["labels"]}
            rows = [issue] if label in names else []
            import json as _json
            return {"exit_code": 0, "stdout": _json.dumps(rows), "stderr": ""}
        assert cmd[1] == "api"
        events = []
        if acquired_at is not None:
            events.append({
                "event": "labeled",
                "created_at": acquired_at,
                "label": {"name": "maintainer-active"},
            })
        import json as _json
        return {"exit_code": 0, "stdout": _json.dumps([events]), "stderr": ""}
    return run_cmd


def _live_shaped_lease(number: int = 7) -> dict:
    return {
        "number": number,
        "title": "leased",
        "body": "target: skills/project-watchdog\n",
        "labels": [{"name": "maintainer-active"}],
        "url": f"https://github.test/issues/{number}",
        "updatedAt": "2026-07-28T00:00:00Z",
    }


def test_stale_lease_is_reclaimed_from_the_in_flight_set(monkeypatch):
    issue = _live_shaped_lease()
    monkeypatch.setattr(
        registry, "run_cmd", _lease_scan_fake(issue, "2026-07-26T00:00:00Z")
    )
    monkeypatch.setattr(registry, "_now_utc", lambda: datetime(2026, 7, 28, tzinfo=UTC))
    monkeypatch.setattr(config, "LEASE_STALE_SECONDS", 86_400)

    busy = registry.lane_busy_issues("t", {"repo": "o/agent-skills"})

    assert busy == []
    stale = registry.LAST_LEASE_SCAN["stale"]
    assert stale[0]["issue_number"] == 7
    assert stale[0]["labels"] == ["maintainer-active"]
    assert stale[0]["leases"][0]["reason"] == "lease_expired"
    assert stale[0]["leases"][0]["acquired_at"] == "2026-07-26T00:00:00Z"


def test_fresh_lease_remains_in_flight(monkeypatch):
    issue = _live_shaped_lease()
    monkeypatch.setattr(
        registry, "run_cmd", _lease_scan_fake(issue, "2026-07-27T23:30:00Z")
    )
    monkeypatch.setattr(registry, "_now_utc", lambda: datetime(2026, 7, 28, tzinfo=UTC))
    monkeypatch.setattr(config, "LEASE_STALE_SECONDS", 86_400)

    busy = registry.lane_busy_issues("t", {"repo": "o/agent-skills"})

    assert [row["number"] for row in busy] == [7]
    assert registry.LAST_LEASE_SCAN["stale"] == []
    assert registry.LAST_LEASE_SCAN["active"][0]["leases"][0]["reason"] == "lease_active"


def test_unknown_acquisition_time_fails_closed_as_in_flight(monkeypatch):
    issue = _live_shaped_lease()
    monkeypatch.setattr(registry, "run_cmd", _lease_scan_fake(issue, None))
    monkeypatch.setattr(registry, "_now_utc", lambda: datetime(2026, 7, 28, tzinfo=UTC))

    busy = registry.lane_busy_issues("t", {"repo": "o/agent-skills"})

    assert [row["number"] for row in busy] == [7]
    assert registry.LAST_LEASE_SCAN["unknown_acquisition_time"] == [
        {"issue_number": 7, "label": "maintainer-active"}
    ]


def test_reclaim_removes_only_the_expired_lease_label(monkeypatch):
    calls = []

    def issue_edit(repo, issue_number, *, add=None, remove=None):
        calls.append({"repo": repo, "issue": issue_number, "add": add, "remove": remove})
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    monkeypatch.setattr(commands.github, "issue_edit", issue_edit)
    stale = [{
        "issue_number": 7,
        "labels": ["maintainer-active"],
        "leases": [{"reason": "lease_expired"}],
        "reason": "lease_expired",
    }]

    reclaimed, failures = commands._reclaim_stale_leases(
        "o/agent-skills", stale, apply=True
    )

    assert failures == []
    assert reclaimed[0]["status"] == "reclaimed"
    assert calls == [{
        "repo": "o/agent-skills",
        "issue": 7,
        "add": None,
        "remove": ["maintainer-active"],
    }]


def test_reclaimed_issue_is_not_redispatched_in_the_same_tick(monkeypatch):
    issue = _live_shaped_lease()
    issue["labels"] = [{"name": "agent-work"}]

    def run_cmd(cmd, timeout_s=None):
        import json as _json
        return {"exit_code": 0, "stdout": _json.dumps([issue]), "stderr": ""}

    monkeypatch.setattr(registry, "run_cmd", run_cmd)
    routable = registry.list_routable_issues(
        "t",
        {"repo": "o/agent-skills", "worktree": "/tmp/worktree"},
        skip_issue_numbers={7},
    )

    assert routable == []
    assert registry.LAST_SCAN["excluded_issues"]["lease_reclaimed_this_tick"] == [7]


def test_targeted_issue_does_not_let_earlier_issue_claim_its_target(monkeypatch):
    first = _issue(32, "scripts/pdf_lab")
    second = _issue(31, "scripts/pdf_lab")

    def run_cmd(cmd, timeout_s=None):
        import json as _json
        return {"exit_code": 0, "stdout": _json.dumps([first, second]), "stderr": ""}

    monkeypatch.setattr(registry, "run_cmd", run_cmd)

    routable = registry.list_routable_issues(
        "t",
        {"repo": "o/r", "worktree": "/tmp/wt"},
        only_issue=31,
    )

    assert [i["number"] for i in routable] == [31]
    assert registry.LAST_SCAN["excluded_issues"]["not_targeted_issue"] == [32]
    assert "target_busy" not in registry.LAST_SCAN["excluded"]


def test_stale_lease_skip_reason_is_machine_readable(monkeypatch):
    issue = _live_shaped_lease()
    issue["labels"] = [{"name": "agent-work"}, {"name": "maintainer-active"}]

    def run_cmd(cmd, timeout_s=None):
        import json as _json
        return {"exit_code": 0, "stdout": _json.dumps([issue]), "stderr": ""}

    monkeypatch.setattr(registry, "run_cmd", run_cmd)
    routable = registry.list_routable_issues(
        "t",
        {"repo": "o/agent-skills", "worktree": "/tmp/worktree"},
        skip_issue_numbers={7},
        skip_issue_reasons={7: "stale_lease"},
    )

    assert routable == []
    assert registry.LAST_SCAN["excluded"]["stale_lease"] == 1
    assert registry.LAST_SCAN["excluded_issues"]["stale_lease"] == [7]


# --- cross-repo dependency routing -------------------------------------------
#
# `$ticket` writes `depends_on` / `blocked-by` so watchdog can hold downstream
# tickets until upstream tickets have shipped. The first implementation only
# rendered the marker; dispatch ignored it.


def _dependency_issue(num=31, labels=None, body=None):
    return {
        "number": num,
        "title": "dependent",
        "body": body if body is not None else "target: skills/project-watchdog\n",
        "labels": [{"name": name} for name in (labels or ["agent-work"])],
        "url": f"https://github.test/issues/{num}",
    }


def _fake_dependency_scan(issue: dict, *, upstream_state="OPEN", comments=None, fail_ref=False):
    def run_cmd(cmd, timeout_s=None):
        import json as _json

        if cmd[1:3] == ["issue", "list"]:
            return {"exit_code": 0, "stdout": _json.dumps([issue]), "stderr": ""}
        if cmd[1:3] == ["issue", "view"] and cmd[-1] == "comments":
            payload = {"comments": [{"body": body} for body in (comments or [])]}
            return {"exit_code": 0, "stdout": _json.dumps(payload), "stderr": ""}
        if cmd[1:3] == ["issue", "view"] and "state,stateReason" in cmd:
            if fail_ref:
                return {"exit_code": 1, "stdout": "", "stderr": "not found"}
            payload = {"state": upstream_state, "stateReason": "COMPLETED"}
            return {"exit_code": 0, "stdout": _json.dumps(payload), "stderr": ""}
        raise AssertionError(cmd)

    return run_cmd


def test_open_dependency_blocks_dispatch(monkeypatch):
    issue = _dependency_issue(
        body="""target: skills/project-watchdog

## Dependencies

- blocked-by: grahama1970/pdf_oxide#31
depends_on: grahama1970/pdf_oxide#31
"""
    )
    monkeypatch.setattr(registry, "run_cmd", _fake_dependency_scan(issue, upstream_state="OPEN"))

    routable = registry.list_routable_issues(
        "t", {"repo": "o/agent-skills", "worktree": "/tmp/wt"}
    )

    assert routable == []
    assert registry.LAST_SCAN["excluded"]["dependency_open"] == 1
    assert registry.LAST_SCAN["excluded_issues"]["dependency_open"] == [31]


def test_closed_dependency_apply_clears_hold_labels_without_same_tick_dispatch(monkeypatch):
    issue = _dependency_issue(
        labels=["agent-work", "blocked:upstream", "maintainer-blocked", "needs-human"],
    )
    monkeypatch.setattr(
        registry,
        "run_cmd",
        _fake_dependency_scan(
            issue,
            upstream_state="CLOSED",
            comments=["blocked-by: grahama1970/pdf_oxide#31"],
        ),
    )
    calls = []

    def issue_edit(repo, issue_number, *, add=None, remove=None):
        calls.append({"repo": repo, "issue": issue_number, "add": add, "remove": remove})
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(registry.github, "issue_edit", issue_edit)

    routable = registry.list_routable_issues(
        "t", {"repo": "o/agent-skills", "worktree": "/tmp/wt"}, apply=True
    )

    assert routable == []
    assert registry.LAST_SCAN["excluded"]["dependency_unblocked_this_tick"] == 1
    assert registry.LAST_SCAN["dependency_unblocks"][0]["status"] == "unblocked"
    assert calls == [{
        "repo": "o/agent-skills",
        "issue": 31,
        "add": None,
        "remove": ["blocked:upstream", "maintainer-blocked", "needs-human"],
    }]


def test_closed_dependency_dry_run_still_reports_downstream_routable(monkeypatch):
    issue = _dependency_issue(
        labels=["agent-work", "blocked:upstream", "maintainer-blocked", "needs-human"],
    )
    monkeypatch.setattr(
        registry,
        "run_cmd",
        _fake_dependency_scan(
            issue,
            upstream_state="CLOSED",
            comments=["blocked-by: grahama1970/pdf_oxide#31"],
        ),
    )

    routable = registry.list_routable_issues(
        "t", {"repo": "o/agent-skills", "worktree": "/tmp/wt"}, apply=False
    )

    assert [row["number"] for row in routable] == [31]
    assert routable[0]["watchdog_dependencies"]["status"] == "resolved"


def test_unreadable_dependency_fails_closed(monkeypatch):
    issue = _dependency_issue(body="target: skills/project-watchdog\ndepends_on: no/ref#1\n")
    monkeypatch.setattr(registry, "run_cmd", _fake_dependency_scan(issue, fail_ref=True))

    routable = registry.list_routable_issues(
        "t", {"repo": "o/agent-skills", "worktree": "/tmp/wt"}
    )

    assert routable == []
    assert registry.LAST_SCAN["excluded"]["dependency_unreadable"] == 1


# --- a silent no-op tick is the failure this watchdog exists to prevent -------
#
# Both no-project-serviceable paths reported ok:True / exit 0, so a fleet where
# every project was paused looked identical to a quiet minute. Measured live on
# 2026-07-28: 5 registered projects, 4 paused, tau holding one lease, and the
# tick reported success while dispatching nothing.

from watchdog.commands import _record_fleet_stall  # noqa: E402


def test_a_stall_that_cannot_clear_itself_needs_attention():
    receipt = {"ok": True, "status": "SKIPPED"}
    _record_fleet_stall(receipt, [
        {"project_id": "tau", "reason": "lane_busy"},
        {"project_id": "scillm", "reason": "project_state_paused"},
        {"project_id": "pi-mono", "reason": "project_state_paused"},
    ])
    assert receipt["ok"] is False
    assert receipt["status"] == "NEEDS_ATTENTION"
    assert receipt["fleet_stall"]["needs_human"] == ["project_state_paused"]
    assert receipt["fleet_stall"]["self_clearing"] is False
    assert "dispatch nothing" in receipt["summary"]


def test_a_stall_held_open_only_by_leases_stays_ok():
    """A lease ends when its holder finishes; that is a quiet tick, not a fault."""
    receipt = {"ok": True, "status": "SKIPPED"}
    _record_fleet_stall(receipt, [
        {"project_id": "tau", "reason": "lane_busy"},
        {"project_id": "alpha", "reason": "lane_busy"},
    ])
    assert receipt["ok"] is True
    assert receipt["status"] == "SKIPPED"
    assert receipt["fleet_stall"]["self_clearing"] is True
    assert receipt["fleet_stall"]["needs_human"] == []


def test_a_failed_lease_scan_is_not_treated_as_self_clearing():
    receipt = {"ok": True, "status": "SKIPPED"}
    _record_fleet_stall(receipt, [
        {"project_id": "tau", "reason": "lease_scan_failed: gh unavailable"},
    ])
    assert receipt["ok"] is False
    assert receipt["fleet_stall"]["self_clearing"] is False


def test_exclusions_are_reported_by_distinct_reason():
    """blocked, leased and human-held need different remedies, so they are separate."""
    def issue(num, *labels):
        return {"number": num, "labels": [{"name": n} for n in ("agent-work", *labels)]}

    cases = {
        "leased": issue(1, "maintainer-active"),
        "blocked": issue(2, "agent-blocked"),
        "human_hold": issue(3, "needs-human"),
    }
    for expected, iss in cases.items():
        action, reason = registry.classify_issue_with_reason(iss)
        assert action is None and reason == expected, f"{expected}: got {reason}"

    action, reason = registry.classify_issue_with_reason(issue(4))
    assert action == "ticket_repair" and reason is None


# --- the tick must not stop at the first active project ----------------------


def test_rotation_order_leads_with_the_requested_project():
    order = registry.rotation_order(PROJECTS, ALL_ACTIVE, requested="beta")
    assert [str(e["project_id"]) for e in order][0] == "beta"


def test_rotation_order_starts_after_the_last_served():
    state = dict(ALL_ACTIVE, last_served_project="alpha")
    order = registry.rotation_order(PROJECTS, state)
    assert [str(e["project_id"]) for e in order] == ["beta", "gamma", "alpha"]


def test_rotation_order_covers_every_project_exactly_once():
    """A project skipped this tick must still be tried before the tick ends."""
    order = registry.rotation_order(PROJECTS, ALL_ACTIVE, requested="gamma")
    ids = [str(e["project_id"]) for e in order]
    assert sorted(ids) == ["alpha", "beta", "gamma"]
    assert len(ids) == len(set(ids))


def test_strict_project_tick_does_not_fall_through_to_another_project(tmp_path, monkeypatch):
    """`--project tau` must not dispatch agent-skills while claiming tau was requested."""
    import json as _json

    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    projects_path.write_text(_json.dumps({
        "projects": [
            {"project_id": "tau", "repo": "o/tau"},
            {"project_id": "agent-skills", "repo": "o/agent-skills"},
        ]
    }))
    state_path.write_text(_json.dumps({
        "global": {"state": "active"},
        "projects": {"tau": {"state": "active"}, "agent-skills": {"state": "active"}},
    }))
    scanned: list[str] = []
    captured: dict = {}

    class FakeStreak:
        escalated = False
        should_persist_receipt = False
        idle_seconds = 0.0
        consecutive_ticks = 1

        def as_receipt_block(self):
            return {"project_id": "tau", "consecutive_ticks": 1}

    def fake_list(
        run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None,
        only_issue=None, apply=False,
    ):
        scanned.append(str(candidate["project_id"]))
        registry.LAST_SCAN.clear()
        registry.LAST_SCAN.update({
            "scanned": 0,
            "excluded": {},
            "excluded_issues": {},
            "unroutable_no_repair_lane": 0,
        })
        if candidate["project_id"] == "agent-skills":
            return [_issue(99, "skills/project-watchdog")]
        return []

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "_audit_one_closure", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_attest_completion", lambda *a, **k: None)
    monkeypatch.setattr(commands.streaks, "record_idle", lambda project_id: FakeStreak())
    monkeypatch.setattr(
        commands,
        "finish",
        lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code)
        or code,
    )

    commands._tick_locked("run", tmp_path / "receipt", apply=False, project_id="tau",
                          max_tickets=1)

    assert scanned == ["tau"]
    assert captured["receipt"]["rotation"]["mode"] == "strict"
    assert captured["receipt"]["rotation"]["selected"] is None


def test_all_project_tick_is_the_explicit_fleet_fallback(tmp_path, monkeypatch):
    import json as _json

    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    projects_path.write_text(_json.dumps({
        "projects": [
            {"project_id": "tau", "repo": "o/tau"},
            {"project_id": "agent-skills", "repo": "o/agent-skills"},
        ]
    }))
    state_path.write_text(_json.dumps({
        "global": {"state": "active"},
        "projects": {"tau": {"state": "active"}, "agent-skills": {"state": "active"}},
    }))
    scanned: list[str] = []
    captured: dict = {}

    def fake_list(
        run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None,
        only_issue=None, apply=False,
    ):
        scanned.append(str(candidate["project_id"]))
        registry.LAST_SCAN.clear()
        registry.LAST_SCAN.update({
            "scanned": 0,
            "excluded": {},
            "excluded_issues": {},
            "unroutable_no_repair_lane": 0,
        })
        if candidate["project_id"] == "agent-skills":
            issue = _issue(99, "skills/project-watchdog")
            issue["watchdog_action"] = "ticket_repair"
            issue["watchdog_targets"] = ["skills/project-watchdog"]
            return [issue]
        return []

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "handle_issue",
                        lambda *a, **k: {"ok": True, "status": "DRY_RUN"})
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_persist_tick_state", lambda state: None)
    monkeypatch.setattr(
        commands,
        "finish",
        lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code)
        or code,
    )

    commands._tick_locked("run", tmp_path / "receipt", apply=False, project_id="all",
                          max_tickets=1)

    assert scanned == ["tau", "agent-skills"]
    assert captured["receipt"]["rotation"]["mode"] == "fleet"
    assert captured["receipt"]["rotation"]["selected"] == "agent-skills"


def test_tick_receipt_copies_excluded_issues_from_selected_scan(tmp_path, monkeypatch):
    import json as _json

    projects_path = tmp_path / "projects.json"
    state_path = tmp_path / "state.json"
    projects_path.write_text(_json.dumps({
        "projects": [{"project_id": "agent-skills", "repo": "o/agent-skills"}]
    }))
    state_path.write_text(_json.dumps({
        "global": {"state": "active"},
        "projects": {"agent-skills": {"state": "active"}},
    }))
    captured: dict = {}

    def fake_list(
        run_id, candidate, busy, *, skip_issue_numbers=None, skip_issue_reasons=None,
        only_issue=None, apply=False,
    ):
        registry.LAST_SCAN.clear()
        registry.LAST_SCAN.update({
            "scanned": 5,
            "excluded": {
                "blocked": 1,
                "human_hold": 1,
                "leased": 1,
                "stale_lease": 1,
                "target_busy": 1,
            },
            "excluded_issues": {
                "blocked": [1402],
                "human_hold": [1403],
                "leased": [1404],
                "stale_lease": [1405],
                "target_busy": [1411],
            },
            "unroutable_no_repair_lane": 0,
        })
        issue = _issue(1418, "skills/project-watchdog")
        issue["watchdog_action"] = "ticket_repair"
        issue["watchdog_targets"] = ["skills/project-watchdog"]
        return [issue]

    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "handle_issue",
                        lambda *a, **k: {"ok": True, "status": "DRY_RUN"})
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)
    monkeypatch.setattr(commands, "_persist_tick_state", lambda state: None)
    monkeypatch.setattr(
        commands,
        "finish",
        lambda run_id, d, receipt, code, **k: captured.update(receipt=receipt, code=code)
        or code,
    )

    commands._tick_locked(
        "run", tmp_path / "receipt", apply=False, project_id="agent-skills",
        max_tickets=1
    )

    receipt = captured["receipt"]
    assert receipt["excluded_counts"]["target_busy"] == 1
    assert receipt["excluded_issues"]["target_busy"] == [1411]
    assert receipt["excluded_issues"]["blocked"] == [1402]
    assert receipt["excluded_issues"]["human_hold"] == [1403]
    assert receipt["excluded_issues"]["leased"] == [1404]
    assert receipt["excluded_issues"]["stale_lease"] == [1405]
    assert receipt["excluded_issue_refs"]["target_busy"] == ["o/agent-skills#1411"]
    assert receipt["issue_scans"][0]["project_id"] == "agent-skills"
    assert receipt["issue_scans"][0]["excluded_issues"]["target_busy"] == [1411]


def test_scheduler_short_lock_allows_unrelated_target_tick(tmp_path, monkeypatch):
    import json as _json
    from itertools import count
    from watchdog import commands, config  # noqa: PLC0415

    root = tmp_path / "state-root"
    projects_path = tmp_path / "projects.json"
    state_path = root / "state.json"
    root.mkdir(parents=True)
    projects_path.write_text(_json.dumps({
        "projects": [{"project_id": "agent-skills", "repo": "o/agent-skills"}]
    }))
    state_path.write_text(_json.dumps({
        "global": {"state": "active"},
        "projects": {"agent-skills": {"state": "active"}},
    }))
    issue_one = _issue(1, "skills/ask")
    issue_one["watchdog_action"] = "ticket_repair"
    issue_one["watchdog_targets"] = ["skills/ask"]
    issue_two = _issue(2, "skills/ticket")
    issue_two["watchdog_action"] = "ticket_repair"
    issue_two["watchdog_targets"] = ["skills/ticket"]
    handled: list[int] = []
    nested_rcs: list[int] = []
    seq = count(1)

    def fake_list(run_id, candidate, busy, *, skip_issue_numbers=None, only_issue=None, apply=False):
        commands.registry.LAST_SCAN.clear()
        commands.registry.LAST_SCAN.update({
            "scanned": 1,
            "excluded": {},
            "excluded_issues": {},
            "dependency_unblocks": [],
        })
        return [issue_two if only_issue == 2 else issue_one]

    def fake_handle(run_id, receipt_dir, project, issue, *, apply):
        handled.append(int(issue["number"]))
        assert not config.lock_dir().exists(), "scheduler lock must be released before dispatch"
        if int(issue["number"]) == 1:
            nested_rcs.append(commands.tick(
                apply=True, project_id="agent-skills", max_tickets=1, only_issue=2
            ))
        return {"ok": True, "status": "COMPLETED", "issue_number": int(issue["number"])}

    monkeypatch.setattr(config, "state_root", lambda: root)
    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(config, "tick_would_enter_quiet_hours", lambda: False)
    monkeypatch.setattr(commands, "timestamp", lambda: f"20260823T1752{next(seq):02d}Z")
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "handle_issue", fake_handle)
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)

    rc = commands.tick(apply=True, project_id="agent-skills", max_tickets=1, only_issue=1)

    assert rc == 0
    assert nested_rcs == [0]
    assert handled == [1, 2]


def test_scheduler_execution_lock_blocks_overlapping_target_tick(tmp_path, monkeypatch):
    import json as _json
    from itertools import count
    from watchdog import commands, config  # noqa: PLC0415

    root = tmp_path / "state-root"
    projects_path = tmp_path / "projects.json"
    state_path = root / "state.json"
    root.mkdir(parents=True)
    projects_path.write_text(_json.dumps({
        "projects": [{"project_id": "agent-skills", "repo": "o/agent-skills"}]
    }))
    state_path.write_text(_json.dumps({
        "global": {"state": "active"},
        "projects": {"agent-skills": {"state": "active"}},
    }))
    issue_one = _issue(1, "skills/ask")
    issue_one["watchdog_action"] = "ticket_repair"
    issue_one["watchdog_targets"] = ["skills/ask"]
    issue_two = _issue(2, "skills/ask")
    issue_two["watchdog_action"] = "ticket_repair"
    issue_two["watchdog_targets"] = ["skills/ask"]
    handled: list[int] = []
    nested_rcs: list[int] = []
    seq = count(1)

    def fake_list(run_id, candidate, busy, *, skip_issue_numbers=None, only_issue=None, apply=False):
        commands.registry.LAST_SCAN.clear()
        commands.registry.LAST_SCAN.update({
            "scanned": 1,
            "excluded": {},
            "excluded_issues": {},
            "dependency_unblocks": [],
        })
        return [issue_two if only_issue == 2 else issue_one]

    def fake_handle(run_id, receipt_dir, project, issue, *, apply):
        handled.append(int(issue["number"]))
        assert not config.lock_dir().exists(), "scheduler lock must be released before dispatch"
        if int(issue["number"]) == 1:
            nested_rcs.append(commands.tick(
                apply=True, project_id="agent-skills", max_tickets=1, only_issue=2
            ))
        return {"ok": True, "status": "COMPLETED", "issue_number": int(issue["number"])}

    monkeypatch.setattr(config, "state_root", lambda: root)
    monkeypatch.setattr(config, "projects_path", lambda: projects_path)
    monkeypatch.setattr(config, "state_path", lambda: state_path)
    monkeypatch.setattr(config, "tick_would_enter_quiet_hours", lambda: False)
    monkeypatch.setattr(commands, "timestamp", lambda: f"20260823T1753{next(seq):02d}Z")
    monkeypatch.setattr(commands.registry, "lane_busy_issues", lambda *a, **k: [])
    monkeypatch.setattr(commands, "list_routable_issues", fake_list)
    monkeypatch.setattr(commands, "handle_issue", fake_handle)
    monkeypatch.setattr(commands.streaks, "clear_idle", lambda *a, **k: None)

    rc = commands.tick(apply=True, project_id="agent-skills", max_tickets=1, only_issue=1)

    assert rc == 0
    assert nested_rcs == [0]
    assert handled == [1]


# --- runtime state must not live in the repository ---------------------------


def test_state_is_written_outside_the_repository():
    """The tick writes state every run; inside the repo that dirties the skill.

    With readiness judged per target, a watchdog that dirties
    skills/project-watchdog makes every ticket against itself unrepairable.
    """
    from watchdog import config  # noqa: PLC0415

    live = config.state_path()
    assert config.SKILL_DIR not in live.parents, "state must not sit inside the skill"
    assert live.parent == config.state_root()


# --- an inconclusive audit must not be retried every minute ------------------


def test_an_unanswered_audit_cools_down_and_the_backlog_advances(tmp_path, monkeypatch):
    """A SciLLM auth failure made every audit inconclusive and the cron
    re-audited the SAME closure ten times in ten minutes, while 36 other
    closures waited."""
    from watchdog import commands, config  # noqa: PLC0415

    monkeypatch.setattr(config, "state_path", lambda: tmp_path / "state.json")
    project = {"project_id": "p", "repo": "o/r", "worktree": "/tmp/x"}
    projects = {"projects": [project]}
    state = {"projects": {"p": {"state": "active"}}}
    pending = [
        {"number": 10, "closedAt": "2026-07-01T00:00:00Z"},
        {"number": 11, "closedAt": "2026-07-02T00:00:00Z"},
    ]
    seen: list[int] = []

    def fake_audit(run_id, receipt_dir, proj, issue, *, apply):
        seen.append(int(issue["number"]))
        return {"ok": False, "status": "NEEDS_ATTENTION", "verdict": None,
                "project_id": "p"}

    monkeypatch.setattr(commands.registry, "list_closed_for_audit", lambda r, p: pending)
    monkeypatch.setattr(commands.registry, "rotation_order", lambda p, s, **k: [project])
    monkeypatch.setattr(commands, "handle_closure_audit", fake_audit)
    monkeypatch.setattr(commands, "load_json", lambda p: projects)

    receipt: dict = {}
    commands._audit_one_closure("r1", tmp_path, state, receipt, apply=True)
    commands._audit_one_closure("r2", tmp_path, state, receipt, apply=True)

    assert seen == [10, 11], "the second tick must move on, not re-audit #10"
    assert receipt["closure_audit"]["cooling_down"] == 1


def test_an_answered_audit_is_not_held_back(tmp_path, monkeypatch):
    from watchdog import commands, config  # noqa: PLC0415

    monkeypatch.setattr(config, "state_path", lambda: tmp_path / "state.json")
    project = {"project_id": "p", "repo": "o/r", "worktree": "/tmp/x"}
    state = {"projects": {"p": {"state": "active"}}}
    monkeypatch.setattr(
        commands.registry, "list_closed_for_audit",
        lambda r, p: [{"number": 10, "closedAt": "2026-07-01T00:00:00Z"}],
    )
    monkeypatch.setattr(commands.registry, "rotation_order", lambda p, s, **k: [project])
    monkeypatch.setattr(commands, "load_json", lambda p: {"projects": [project]})
    monkeypatch.setattr(
        commands, "handle_closure_audit",
        lambda *a, **k: {"ok": True, "status": "COMPLETED", "verdict": "PASS", "project_id": "p"},
    )
    commands._audit_one_closure("r1", tmp_path, state, {}, apply=True)
    assert state["closure_audit_attempts"] == {}, "an answered audit leaves no cooldown"


# --- an attestation that never answered must be retried sooner ---------------


def _attest_state(tmp_path, monkeypatch, result, state):
    from watchdog import commands, config  # noqa: PLC0415

    project = {"project_id": "p", "repo": "o/r", "worktree": "/tmp/x"}
    monkeypatch.setattr(config, "state_path", lambda: tmp_path / "state.json")
    monkeypatch.setattr(commands, "load_json", lambda p: {"projects": [project]})
    monkeypatch.setattr(commands.registry, "rotation_order", lambda p, s, **k: [project])
    monkeypatch.setattr(
        commands.registry, "list_recently_closed",
        lambda r, p: [{"number": 1, "title": "t", "stateReason": "COMPLETED"}],
    )
    monkeypatch.setattr(commands, "handle_completion_attestation", lambda *a, **k: result)
    return commands._attest_completion("r", tmp_path, state, {}, apply=True)


def test_an_attestation_that_died_is_retried_within_the_hour(tmp_path, monkeypatch):
    """A webgpt attestation reached PASS on its handler node and the wrapper was
    killed before it could reopen the seven tickets it had named. Stamping the
    rate limit before the run lost the verdict AND blocked retry for a day."""
    from watchdog import config  # noqa: PLC0415

    state = {"projects": {"p": {"state": "active"}}}
    _attest_state(tmp_path, monkeypatch, {"verdict": None, "ok": False}, state)

    record = state["completion_attested_at"]["p"]
    assert record["answered"] is False
    # Just under the retry window it is still held back; just over, it runs again.
    state["completion_attested_at"]["p"]["at"] = (
        record["at"] - config.COMPLETION_ATTEST_RETRY_SECONDS + 60
    )
    assert _attest_state(tmp_path, monkeypatch, {"verdict": None}, state) is None
    state["completion_attested_at"]["p"]["at"] = (
        record["at"] - config.COMPLETION_ATTEST_RETRY_SECONDS - 60
    )
    assert _attest_state(tmp_path, monkeypatch, {"verdict": "PASS"}, state) is not None


def test_an_answered_attestation_holds_for_the_full_interval(tmp_path, monkeypatch):
    from watchdog import config  # noqa: PLC0415

    state = {"projects": {"p": {"state": "active"}}}
    _attest_state(tmp_path, monkeypatch, {"verdict": "PASS", "ok": True}, state)
    record = state["completion_attested_at"]["p"]
    assert record["answered"] is True

    record["at"] = record["at"] - config.COMPLETION_ATTEST_RETRY_SECONDS - 60
    assert _attest_state(tmp_path, monkeypatch, {"verdict": "PASS"}, state) is None, \
        "an answered attestation is not re-asked an hour later"


def test_agent_actionable_attention_does_not_make_the_tick_a_human_blocker():
    from watchdog import commands  # noqa: PLC0415

    result = {
        "ok": False,
        "status": "NEEDS_ATTENTION",
        "requires_human_input": False,
        "authorized_agent_next_steps": [{"kind": "inspect_artifact"}],
    }
    receipt = {}

    assert commands._handled_result_allows_agent_followup(result) is True
    assert commands._handled_tick_status(result, preview=False) == "COMPLETED"
    commands._record_agent_authorization(receipt, result)
    assert receipt["requires_human_input"] is False
    assert receipt["agent_action_required"] is True
    assert receipt["authorized_agent_next_steps"] == [{"kind": "inspect_artifact"}]


def test_a_bare_timestamp_from_older_state_still_works(tmp_path, monkeypatch):
    state = {"projects": {"p": {"state": "active"}}, "completion_attested_at": {"p": 0.0}}
    assert _attest_state(tmp_path, monkeypatch, {"verdict": "PASS"}, state) is not None


# --- a tick must not revert an operator's state change -----------------------


def test_a_tick_does_not_revert_a_concurrent_operator_change(tmp_path, monkeypatch):
    """`set-state project active --project watchdog-probe` reported UPDATED and
    the project was absent afterwards: a tick already in flight wrote its stale
    copy of the whole document over it, and the project never dispatched."""
    import json as _json

    from watchdog import commands, config  # noqa: PLC0415

    path = tmp_path / "state.json"
    monkeypatch.setattr(config, "state_path", lambda: path)
    path.write_text(_json.dumps({"projects": {"tau": {"state": "active"}}}))

    # A tick read state before the operator added a project.
    stale = {"projects": {"tau": {"state": "active"}}, "last_served_project": "tau"}

    # Operator registers a new project while that tick is still running.
    live = _json.loads(path.read_text())
    live["projects"]["watchdog-probe"] = {"state": "active"}
    path.write_text(_json.dumps(live))

    commands._persist_tick_state(stale)

    after = _json.loads(path.read_text())
    assert "watchdog-probe" in after["projects"], "the operator's change must survive"
    assert after["last_served_project"] == "tau", "the tick's own key is still written"


def test_an_operator_change_does_not_revert_tick_cooldowns(tmp_path, monkeypatch):
    import json as _json

    from watchdog import commands, config  # noqa: PLC0415

    path = tmp_path / "state.json"
    monkeypatch.setattr(config, "state_path", lambda: path)
    path.write_text(_json.dumps({
        "projects": {"tau": {"state": "active"}},
        "closure_audit_attempts": {"o/r#7": 123.0},
    }))
    monkeypatch.setattr(commands, "finish", lambda *a, **k: 0)
    commands.set_state("project", "paused", project_id="tau", reason="probe")

    after = _json.loads(path.read_text())
    assert after["projects"]["tau"]["state"] == "paused"
    assert after["closure_audit_attempts"] == {"o/r#7": 123.0}, "cooldowns survive"
