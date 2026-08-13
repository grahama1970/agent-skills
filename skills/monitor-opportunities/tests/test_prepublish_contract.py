"""Pre-publish truth contract: an untrustworthy digest must never be published."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitor_opportunities.prepublish_contract import validate

NOW = datetime(2026, 8, 13, tzinfo=UTC)


def _row(**over):
    base = {
        "candidate_id": "c1",
        "organization": "Acme",
        "title": "AI Architect",
        "eligibility_state": "ELIGIBLE_REMOTE",
        "published_at": (NOW - timedelta(days=2)).isoformat(),
        "posting_url": "https://www.linkedin.com/jobs/view/123/",
    }
    base.update(over)
    return base


def _entry(**over):
    base = {"candidate_id": "c1", "organization": "Acme", "title": "AI Architect",
            "response_score": 0.5}
    base.update(over)
    return base


def test_clean_digest_passes() -> None:
    ok, rep = validate({"top": [_entry()]}, [_row()], now=NOW)
    assert ok and rep["violations"] == []


def test_row_not_in_this_run_is_rejected() -> None:
    # A digest row with no shortlist backing is stale or invented.
    ok, rep = validate({"top": [_entry(candidate_id="ghost")]}, [_row()], now=NOW)
    assert not ok
    assert rep["violations"][0]["rule"] == "current-run"


def test_generic_search_url_is_rejected() -> None:
    # The 2026-08-13 defect: every digest row linked to the board search page.
    ok, rep = validate(
        {"top": [_entry()]},
        [_row(posting_url="https://www.linkedin.com/jobs/search/")],
        now=NOW,
    )
    assert not ok
    assert any(v["rule"] == "resolvable-url" for v in rep["violations"])


def test_premium_insights_without_per_job_url_is_rejected() -> None:
    # Per-job facts require a per-job source; this is the wrong-data-attribution bug.
    ok, rep = validate(
        {"top": [_entry(premium_insights={"applicants": 10})]},
        [_row(posting_url="https://www.linkedin.com/jobs/search/")],
        now=NOW,
    )
    assert not ok
    assert any(v["rule"] == "evidence-backed" for v in rep["violations"])


def test_nonzero_trigger_without_evidence_is_rejected() -> None:
    ok, rep = validate(
        {"top": [_entry(drivers={"trigger": 0.9})]}, [_row()], now=NOW
    )
    assert not ok
    assert any(v["rule"] == "evidence-backed" for v in rep["violations"])


def test_stale_posting_is_rejected() -> None:
    ok, rep = validate(
        {"top": [_entry()]},
        [_row(published_at=(NOW - timedelta(days=40)).isoformat())],
        now=NOW,
    )
    assert not ok
    assert any(v["rule"] == "fresh" for v in rep["violations"])


def test_missing_date_is_not_a_violation() -> None:
    # Many boards omit dates; dropping those rows would cost real opportunities.
    ok, _ = validate({"top": [_entry()]}, [_row(published_at=None)], now=NOW)
    assert ok


def test_ineligible_row_is_rejected() -> None:
    ok, rep = validate(
        {"top": [_entry()]}, [_row(eligibility_state="REJECT_LOCATION")], now=NOW
    )
    assert not ok
    assert any(v["rule"] == "eligible" for v in rep["violations"])


def test_duplicate_posting_is_rejected() -> None:
    rows = [_row(), _row(candidate_id="c2")]
    top = [_entry(), _entry(candidate_id="c2", response_score=0.4)]
    ok, rep = validate({"top": top}, rows, now=NOW)
    assert not ok
    assert any(v["rule"] == "unique-canonical" for v in rep["violations"])


def test_out_of_order_scores_are_rejected() -> None:
    rows = [_row(), _row(candidate_id="c2", organization="Beta", title="ML Eng")]
    top = [_entry(response_score=0.2),
           _entry(candidate_id="c2", organization="Beta", title="ML Eng", response_score=0.9)]
    ok, rep = validate({"top": top}, rows, now=NOW)
    assert not ok
    assert any(v["rule"] == "frozen-selection" for v in rep["violations"])


def test_fewer_than_max_rows_is_fine() -> None:
    # "never REQUIRE a full 8" — padding to a quota is itself a defect.
    ok, _ = validate({"top": [_entry()]}, [_row()], max_rows=8, now=NOW)
    assert ok


def test_unavailable_signal_must_not_read_as_observed() -> None:
    # webgpt P0 #05: unavailable must never be presented as an observed value.
    ok, rep = validate(
        {"top": [_entry()], "signals_wired": {"trigger": True}},
        [_row()],
        trigger_receipt={"orgs_searched": 0, "brave_search_available": False},
        now=NOW,
    )
    assert not ok
    assert any(v["rule"] == "typed-missingness" for v in rep["violations"])


def test_identical_insights_across_jobs_is_a_crossjoin_violation() -> None:
    # The 2026-08-13 defect: one page read 8x, its numbers attached to 8 jobs.
    rows = [_row(), _row(candidate_id="c2", organization="Beta", title="ML Eng")]
    same = {"applicants": 10, "salary": "$119K/yr - $154K/yr"}
    top = [
        _entry(premium_insights=same, response_score=0.9),
        _entry(candidate_id="c2", organization="Beta", title="ML Eng",
               premium_insights=same, response_score=0.8),
    ]
    ok, rep = validate({"top": top}, rows, now=NOW)
    assert not ok
    assert any(v["rule"] == "lineage-no-crossjoin" for v in rep["violations"])


def test_distinct_insights_across_jobs_pass() -> None:
    rows = [_row(), _row(candidate_id="c2", organization="Beta", title="ML Eng")]
    top = [
        _entry(premium_insights={"applicants": 9}, response_score=0.9),
        _entry(candidate_id="c2", organization="Beta", title="ML Eng",
               premium_insights={"applicants": 22}, response_score=0.8),
    ]
    ok, rep = validate({"top": top}, rows, now=NOW)
    assert ok, rep["violations"]


def test_conflicting_org_trigger_evidence_is_a_crossjoin_violation() -> None:
    # Trigger news is ORG-level: two rows of one org cannot disagree about it.
    rows = [_row(), _row(candidate_id="c2", title="ML Eng")]
    top = [
        _entry(trigger_evidence="raised $40M", drivers={"trigger": 0.9}, response_score=0.9),
        _entry(candidate_id="c2", title="ML Eng", trigger_evidence="awarded contract",
               drivers={"trigger": 0.9}, response_score=0.8),
    ]
    ok, rep = validate({"top": top}, rows, now=NOW)
    assert not ok
    assert any(v["rule"] == "lineage-no-crossjoin" for v in rep["violations"])


def test_source_receipt_from_another_run_is_rejected() -> None:
    ok, rep = validate(
        {"top": [_entry()]},
        [_row(source_receipt_id="src:from:another:run")],
        source_receipt_ids={"src:a:linkedin:thisrun"},
        now=NOW,
    )
    assert not ok
    assert any(v["rule"] == "lineage-traceable" for v in rep["violations"])
