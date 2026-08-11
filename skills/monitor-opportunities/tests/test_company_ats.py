"""Company->ATS resolution: correct boards, no wrong-company false positives."""

from __future__ import annotations

import monitor_opportunities.company_ats as ca


def test_classify_apply_type() -> None:
    assert ca.classify_apply_type("https://jobs.ashbyhq.com/drata/abc") == "direct_ats"
    assert ca.classify_apply_type("https://boards.greenhouse.io/x/jobs/1") == "direct_ats"
    assert ca.classify_apply_type("https://www.linkedin.com/jobs/view/123") == "linkedin"
    assert ca.classify_apply_type("https://example.com/careers") == "unknown"


def test_resolve_matches_real_board(monkeypatch) -> None:
    monkeypatch.setattr(ca, "_brave_web", lambda q, count=6: "Careers at Drata https://jobs.ashbyhq.com/drata/uuid apply now")
    r = ca.resolve_company_ats("Drata")
    assert r is not None and r["provider"] == "ashby" and r["slug"] == "drata"


def test_rejects_wrong_company_on_generic_token(monkeypatch) -> None:
    # "Primitive Labs" must NOT match "periodic-labs" on the shared word "labs".
    monkeypatch.setattr(ca, "_brave_web", lambda q, count=6: "Periodic Labs jobs https://jobs.ashbyhq.com/periodic-labs")
    assert ca.resolve_company_ats("Primitive Labs") is None


def test_rejects_substring_company(monkeypatch) -> None:
    # "Glint" must NOT match "glints" (a different company).
    monkeypatch.setattr(ca, "_brave_web", lambda q, count=6: "Glints careers https://jobs.lever.co/glints")
    assert ca.resolve_company_ats("Glint Tech Solutions") is None


def test_not_found_when_no_ats(monkeypatch) -> None:
    monkeypatch.setattr(ca, "_brave_web", lambda q, count=6: "no ats boards here, just a homepage")
    assert ca.resolve_company_ats("Qualis1 Inc.") is None
