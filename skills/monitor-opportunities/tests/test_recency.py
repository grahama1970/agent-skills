"""Recency gate: only opportunities within the last 2 weeks are eligible."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitor_opportunities.ranking import _eligibility, _posting_age_days


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _base(**over: object) -> dict[str, object]:
    c = {"candidate_id": "c1", "lane": "A", "workplace_type": "REMOTE"}
    c.update(over)
    return c


def test_old_posting_rejected() -> None:
    state, reasons = _eligibility(_base(published_at=_iso(20)))
    assert state == "REJECT_STALE_AGE"
    assert "window" in reasons[0]


def test_recent_posting_eligible() -> None:
    state, _ = _eligibility(_base(published_at=_iso(3)))
    assert state == "ELIGIBLE_REMOTE"


def test_missing_date_not_rejected_on_age() -> None:
    # No date -> cannot prove staleness -> must NOT be dropped on recency.
    state, _ = _eligibility(_base())
    assert state == "ELIGIBLE_REMOTE"


def test_unparseable_date_not_rejected_on_age() -> None:
    state, _ = _eligibility(_base(published_at="not-a-date"))
    assert state == "ELIGIBLE_REMOTE"


def test_updated_at_used_when_no_published_at() -> None:
    assert _posting_age_days(_base(updated_at=_iso(30))) > 29
    state, _ = _eligibility(_base(updated_at=_iso(30)))
    assert state == "REJECT_STALE_AGE"


def test_env_override_widens_window(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_MAX_AGE_DAYS", "60")
    state, _ = _eligibility(_base(published_at=_iso(20)))
    assert state == "ELIGIBLE_REMOTE"
