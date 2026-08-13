"""Locator evidence cannot independently admit opportunities."""

from __future__ import annotations

from pathlib import Path

from monitor_opportunities.discovery import _linkedin_evidence_candidates
from monitor_opportunities.pipeline import _is_report_opportunity, _source_intel


def test_linkedin_only_candidate_is_source_intel_not_opportunity() -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "ops-linkedin-jobs-capture.json"
    receipt, candidates = _linkedin_evidence_candidates(fixture)
    assert receipt["required_source_id"] == "linkedin_top_applicant"
    assert candidates
    assert all(not _is_report_opportunity(candidate) for candidate in candidates)
    intel = [_source_intel(candidate) for candidate in candidates]
    assert all(item and item["signal_type"] == "LINKEDIN_LOCATOR" for item in intel)
    assert all(item and item["decision"] == "LOCATOR_ONLY" for item in intel)
