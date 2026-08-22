#!/usr/bin/env python3
"""Regression guard: LinkedIn top-applicant status must reach ranking.

Incident (2026-08-22): the nightly kept only the LinkedIn evidence file with the
most rows (advanced-search) and discarded the top-applicant file, so every
``top_candidate: True`` flag was thrown away -- Graham's top-applicant roles
never carried the boost and never ranked higher. (0 of 11 reached the pool.)

This guard exercises the REAL merge + emit path (`_merge_linkedin_top_candidate`
then `_linkedin_evidence_candidates`) on a two-stream fixture and fails (exit 1)
if a top-applicant role does not survive with ``top_candidate_evidence=True`` and
the intended fit boost.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.discovery import (  # noqa: E402
    _linkedin_evidence_candidates,
    _merge_linkedin_top_candidate,
)

# Advanced-search stream: many rows, no top-candidate signal.
BASE = {"source": "linkedin_advanced_search", "opportunities": [
    {"title": "Backend Engineer", "organization": "Acme", "location": "Remote"},
]}
# Top-applicant stream: the role Graham is a top applicant for.
TOP = {"source": "linkedin_top_applicant", "top_candidate": True, "opportunities": [
    {"title": "Staff AI Engineer", "organization": "Glint", "location": "Buffalo, NY", "top_candidate": True},
]}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.json"
        top = Path(tmp) / "top.json"
        base.write_text(json.dumps(BASE), encoding="utf-8")
        top.write_text(json.dumps(TOP), encoding="utf-8")

        _merge_linkedin_top_candidate(base, top)
        _receipt, candidates = _linkedin_evidence_candidates(base)

    top_candidates = [c for c in candidates if c.get("top_candidate_evidence")]
    if not top_candidates:
        print(
            "TOP_CANDIDATE_DROPPED: a LinkedIn top-applicant role did not survive into the "
            "ranked candidate pool with top_candidate_evidence=True. The nightly must MERGE "
            "the top-applicant stream, not discard it for a higher-row-count file.",
            file=sys.stderr,
        )
        return 1
    boosted = [c for c in top_candidates if float(c.get("fit_score") or 0) >= 0.93]
    if not boosted:
        print(
            "TOP_CANDIDATE_NO_BOOST: top-applicant roles survived but did not receive the "
            f"fit boost (got {[c.get('fit_score') for c in top_candidates]}, expected >= 0.93).",
            file=sys.stderr,
        )
        return 1

    print(f"TOP_CANDIDATE_OK: {len(boosted)} top-applicant role(s) ranked with fit>=0.93")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
