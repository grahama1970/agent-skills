"""Fleet rotation and per-target collision (#1084, #1083).

The crontab pins --project tau and tick() resolved exactly that project, so an
idle tau stalled the whole fleet and no other project was ever serviced.

Collision is a property of the TARGET, not the repository. agent-skills holds
364 skills; two tickets against different ones share no files. Scheduling on the
repository blocked 363 skills to protect 1, which is why a single lease on tau
left the fleet dispatching nothing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

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


def test_a_legacy_ticket_falls_back_to_the_skills_it_mentions():
    """7 of the 8 leases open on agent-skills predate the target: line."""
    body = "Fix `skills/ask` compete when `skills/surf` returns a stale tab."
    assert issue_targets({"body": body}) == {"skills/ask", "skills/surf"}


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

from watchdog import config, registry  # noqa: E402


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
