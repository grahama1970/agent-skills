"""Work done beside a blocker, instead of on it.

The failure: an agent hits a wall, does not say "blocked", and produces
defensible deterministic work next to it. goal-drift grades that SERVES_GOAL,
because it does serve the goal -- it is the hard half being routed around.

These tests encode what must NOT be flagged as hard as what must.
"""

from __future__ import annotations

import pytest

from ask import avoidance_drift as ad
from ask import blocker_ledger


@pytest.fixture(autouse=True)
def _ledger(tmp_path, monkeypatch):
    monkeypatch.setenv(blocker_ledger.LEDGER_ENV, str(tmp_path / "blockers.jsonl"))


def _block(target="skills/ask", code="upstream_missing"):
    return blocker_ledger.record(target=target, failure_code=code)


# --- the ledger -----------------------------------------------------------

def test_a_blocker_survives_the_run_that_hit_it() -> None:
    """Before this, blockers evaporated at run end and nothing could compare."""
    _block()
    assert [b["failure_code"] for b in blocker_ledger.open_blockers()] == ["upstream_missing"]


def test_the_same_wall_hit_twice_is_one_blocker() -> None:
    _block(); _block()
    open_ones = blocker_ledger.open_blockers()
    assert len(open_ones) == 1
    assert open_ones[0]["observations"] == 2


def test_clearing_a_blocker_requires_live_proof() -> None:
    """'It should work now' is what an avoiding agent also says."""
    _block()
    with pytest.raises(ValueError, match="requires live proof"):
        blocker_ledger.clear(target="skills/ask", failure_code="upstream_missing", live_proof="")


def test_a_cleared_blocker_leaves_the_open_set() -> None:
    _block()
    blocker_ledger.clear(
        target="skills/ask", failure_code="upstream_missing",
        live_proof="ran the live DAG; read back execution-status.json PASS",
    )
    assert blocker_ledger.open_blockers() == []


def test_re_observing_reopens_a_cleared_blocker() -> None:
    """The wall is demonstrably still there, whatever an earlier clear claimed."""
    _block()
    blocker_ledger.clear(target="skills/ask", failure_code="upstream_missing", live_proof="live run")
    _block()
    assert len(blocker_ledger.open_blockers()) == 1


def test_acknowledging_does_not_clear() -> None:
    """Saying 'blocked' is the honest exit, but the wall is still there."""
    _block()
    blocker_ledger.acknowledge(target="skills/ask", failure_code="upstream_missing")
    open_ones = blocker_ledger.open_blockers()
    assert len(open_ones) == 1 and open_ones[0]["acknowledged"] is True


def test_a_blocked_execution_is_recorded_without_being_asked() -> None:
    """The agent this detects would not have filed the report."""
    entry = blocker_ledger.record_from_execution(
        {"status": "BLOCKED", "blocked_reason": "browser_tab_lifecycle_failed", "ok": False},
        target="skills/ask",
    )
    assert entry is not None
    assert blocker_ledger.open_blockers()[0]["failure_code"] == "browser_tab_lifecycle_failed"


def test_a_passing_execution_records_nothing() -> None:
    assert blocker_ledger.record_from_execution({"status": "PASS", "ok": True}) is None
    assert blocker_ledger.open_blockers() == []


# --- the detector ---------------------------------------------------------

def test_work_with_no_live_path_beside_an_open_blocker_is_drift() -> None:
    """The case this was built for, in the words the agent itself writes."""
    _block()
    verdict = ad.assess_target(
        "skills/ask",
        ["Added contracts and 37 tests. Proof boundary: test-backed only, blocked upstream in Tau."],
    )
    assert verdict["verdict"] == ad.AVOIDANCE_DRIFT
    assert "blocked" in verdict["next_action"].casefold()


def test_attempting_the_live_path_and_failing_is_not_avoidance() -> None:
    """Failing at the wall is the honest case and must never be flagged."""
    _block()
    verdict = ad.assess_target(
        "skills/ask",
        ["Attempted the live run against the real provider; it failed with a 502."],
    )
    assert verdict["verdict"] == ad.BLOCKED_DECLARED


def test_declaring_the_blocker_is_not_drift_however_much_work_follows() -> None:
    _block()
    blocker_ledger.acknowledge(target="skills/ask", failure_code="upstream_missing")
    verdict = ad.assess_target("skills/ask", ["More fixture-backed contract work, test-backed only."])
    assert verdict["verdict"] == ad.BLOCKED_DECLARED


def test_a_target_with_no_blocker_is_clean() -> None:
    verdict = ad.assess_target("skills/other", ["test-backed only"])
    assert verdict["verdict"] == ad.CLEAN


def test_a_cleared_target_is_not_drift() -> None:
    _block()
    blocker_ledger.clear(target="skills/ask", failure_code="upstream_missing", live_proof="live run, read back")
    verdict = ad.assess_target("skills/ask", ["test-backed only"])
    assert verdict["verdict"] == ad.CLEARED


def test_ordinary_work_that_claims_nothing_is_not_accused() -> None:
    """Silence about proof is not a confession; only an explicit gap counts."""
    _block()
    verdict = ad.assess_target("skills/ask", ["Renamed a helper and updated its docstring."])
    assert verdict["verdict"] == ad.CLEAN


def test_an_open_blocker_with_no_work_at_all_is_not_drift() -> None:
    """Stopping is the desired behaviour; it must not be punished."""
    _block()
    assert ad.assess_target("skills/ask", [])["verdict"] == ad.BLOCKED_DECLARED


def test_a_live_attempt_outweighs_a_fixture_caveat_in_the_same_batch() -> None:
    _block()
    verdict = ad.assess_target(
        "skills/ask",
        ["Contract work, fixture-backed.", "Then ran it end-to-end against the real service."],
    )
    assert verdict["verdict"] == ad.BLOCKED_DECLARED


def test_work_items_may_be_dicts_from_a_receipt() -> None:
    _block()
    verdict = ad.assess_target(
        "skills/ask", [{"title": "add contracts", "proof_boundary": "unit tests only"}]
    )
    assert verdict["verdict"] == ad.AVOIDANCE_DRIFT


def test_the_scan_names_every_drifting_target() -> None:
    _block("skills/ask")
    _block("skills/surf")
    blocker_ledger.acknowledge(target="skills/surf", failure_code="upstream_missing")
    scan = ad.scan({
        "skills/ask": ["test-backed only"],
        "skills/surf": ["test-backed only"],
    })
    assert scan["drifting_targets"] == ["skills/ask"]
    assert scan["clean"] is False


def test_a_scan_with_nothing_recorded_is_clean() -> None:
    assert ad.scan({})["clean"] is True


# --- defects found by the first live run ----------------------------------

def test_the_lane_failure_code_beats_the_generic_run_status(tmp_path) -> None:
    """A run ending NEEDS_ATTENTION says nothing about which wall was hit.

    Observed live: four distinct lane failures all collapsed into one useless
    key, `unknown::NEEDS_ATTENTION`.
    """
    node = tmp_path / "node-artifacts" / "handler-webgpt"
    node.mkdir(parents=True)
    (node / "node-receipt.json").write_text(
        '{"failure_code": "browser_submit_not_accepted", "status": "NEEDS_ATTENTION"}',
        encoding="utf-8",
    )
    entry = blocker_ledger.record_from_execution(
        {"status": "NEEDS_ATTENTION", "ok": False}, target="t", run_dir=str(tmp_path)
    )
    assert entry["failure_code"] == "browser_submit_not_accepted"


def test_the_target_is_read_from_where_ask_actually_puts_it() -> None:
    """It lives at dag.target.target; the top-level lookup recorded 'unknown'."""
    bundle = {"dag": {"target": {"repo": "local/agent-skills", "target": "unblock-x"},
                      "dag_id": "ask-tau-…"}}
    assert blocker_ledger.target_of_bundle(bundle) == "unblock-x"


def test_a_bundle_without_a_target_falls_back_to_the_dag_id() -> None:
    assert blocker_ledger.target_of_bundle({"dag": {"dag_id": "ask-tau-abc"}}) == "ask-tau-abc"


def test_an_unreadable_run_dir_does_not_raise() -> None:
    assert blocker_ledger.most_specific_failure_code("/nonexistent/path") == ""
