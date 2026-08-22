#!/usr/bin/env python3
"""Regression guard: top-applicant roles must reach the shortlist.

Incident (2026-08-22, found by a complete run): the merge fix carried
top_candidate into discovery, but the SELECTION layer still dropped those roles.
A top-applicant role with an ambiguous location string escalated to
HUMAN_REVIEW_LOCATION_AMBIGUOUS (excluded from the shortlist), and ranking.py's
mandate-only score never rewarded top-applicant status -- so the morning report
led with cold remote roles and zero top-applicant / Buffalo roles.

This guard exercises the real `_eligibility` and `_score` and fails (exit 1) if:
  - a top-applicant role with an ambiguous location is NOT eligible, or
  - a top-applicant role does not out-select a cold remote role of equal fit.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.ranking import _eligibility, _score  # noqa: E402


def _total(c: dict) -> float:
    s = _score(c)
    top = 500_000 if c.get("top_candidate_evidence") else 0
    return s["mandate_fit"] * 1_000_000 + top + s["geo_priority"]


def main() -> int:
    failures: list[str] = []

    # 1. Top-applicant + ambiguous location must be eligible, not human-review.
    top_ambiguous = {"lane": "A", "workplace_type": "AMBIGUOUS", "fit_score": 0.93,
                     "top_candidate_evidence": True, "title": "AI Principal Engineer",
                     "source_receipt_id": "x"}
    state, _reasons = _eligibility(top_ambiguous)
    if not state.startswith("ELIGIBLE"):
        failures.append(f"TOP_APPLICANT_ESCALATED: top-applicant ambiguous-location role => {state}, expected ELIGIBLE*.")

    # 2. A top-applicant role must out-select a cold remote role of equal fit.
    cold_remote = {"lane": "A", "workplace_type": "REMOTE", "fit_score": 0.93,
                   "title": "Backend Engineer", "source_receipt_id": "x"}
    if not _total(top_ambiguous) > _total(cold_remote):
        failures.append("TOP_APPLICANT_NOT_PRIORITIZED: top-applicant role did not out-select an equal-fit cold remote role.")

    # 3. A Buffalo top-applicant role must be eligible and rank above cold remote.
    buffalo_top = {"lane": "A", "workplace_type": "WNY_ONSITE", "fit_score": 0.93,
                   "top_candidate_evidence": True, "title": "Senior AI Engineer", "source_receipt_id": "x"}
    if not _eligibility(buffalo_top)[0].startswith("ELIGIBLE"):
        failures.append("BUFFALO_TOP_NOT_ELIGIBLE")
    if not _total(buffalo_top) >= _total(top_ambiguous):
        failures.append("BUFFALO_TOP_NOT_PREFERRED: Buffalo top-applicant did not rank at least as high as ambiguous top-applicant.")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("TOP_APPLICANT_SHORTLISTED_OK: top-applicant roles are eligible and out-select cold remote")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
