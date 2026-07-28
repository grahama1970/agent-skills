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
