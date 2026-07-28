"""Fleet rotation and lane-busy refusal (#1084, #1083).

The crontab pins --project tau and tick() resolved exactly that project, so a
busy or idle tau stalled the whole fleet and no other project was ever serviced.
Separately, nothing stopped a tick from dispatching a second ticket while one
was still leased, which authors a repair against a tree the first is changing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from watchdog.registry import select_next_project  # noqa: E402

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


def _checker(busy: dict):
    def check(run_id, project):
        return busy.get(project["project_id"], [])

    return check


def test_busy_lane_is_skipped_and_next_project_is_served():
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served=None,
        busy_checker=_checker({"alpha": [{"number": 7}]}),
    )
    assert chosen["project_id"] == "beta"
    assert skipped[0]["project_id"] == "alpha"
    assert skipped[0]["reason"] == "lane_busy"
    assert skipped[0]["in_flight_issues"] == [7]


def test_rotation_starts_after_the_last_served_project():
    chosen, _ = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="alpha",
        busy_checker=_checker({}),
    )
    assert chosen["project_id"] == "beta"


def test_rotation_wraps_around():
    chosen, _ = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="beta",
        busy_checker=_checker({}),
    )
    assert chosen["project_id"] == "alpha"


def test_paused_projects_are_skipped_with_named_reason():
    # last_served=beta -> order is gamma, alpha, beta. gamma is paused and alpha
    # is busy, so beta must be busy too for the walk to exhaust.
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="beta",
        busy_checker=_checker({"alpha": [{"number": 1}], "beta": [{"number": 2}]}),
    )
    assert chosen is None
    reasons = {s["project_id"]: s["reason"] for s in skipped}
    assert reasons["gamma"] == "project_state_paused"
    assert reasons["alpha"] == "lane_busy"


def test_a_free_project_is_served_even_when_others_are_paused_or_busy():
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served="beta",
        busy_checker=_checker({"alpha": [{"number": 1}]}),
    )
    assert chosen["project_id"] == "beta"
    assert {s["project_id"] for s in skipped} == {"gamma", "alpha"}


def test_no_serviceable_project_returns_none_with_every_reason():
    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served=None,
        busy_checker=_checker({"alpha": [{"number": 1}], "beta": [{"number": 2}]}),
    )
    assert chosen is None
    assert len(skipped) == 3
    assert sorted(s["reason"] for s in skipped) == [
        "lane_busy", "lane_busy", "project_state_paused",
    ]


def test_a_failed_lease_scan_never_reads_as_idle():
    """Working ahead precisely when the current state is unknown is the worst case."""

    def exploding(run_id, project):
        raise RuntimeError("gh unavailable")

    chosen, skipped = select_next_project(
        run_id="t", projects=PROJECTS, state=ALL_ACTIVE, last_served=None,
        busy_checker=exploding,
    )
    assert chosen is None
    assert any(s["reason"].startswith("lease_scan_failed") for s in skipped)


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
