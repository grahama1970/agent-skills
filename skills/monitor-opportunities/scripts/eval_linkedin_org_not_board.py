#!/usr/bin/env python3
"""Regression guard: LinkedIn top-applicant organization must be an employer,
not a job-board / aggregator name.

Follow-up to #1484: the field-recovery fix restored real employers for most
rows, but one row still yields organization "Find Data Science Jobs" — a job
board, not the hiring company. A board name is not an employer and must not be
surfaced as the organization.

Runs the real parser over the committed fixture and fails (exit 1) if any
top-applicant candidate's organization matches a job-board pattern.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.discovery import _linkedin_evidence_candidates  # noqa: E402

FIXTURE = SKILL_DIR / "tests" / "fixtures" / "linkedin" / "top_applicant_misparse.json"

# A job board / aggregator, not an employer.
_BOARD_PATTERN = re.compile(r"\b(jobs?|careers?|hiring|listings?|openings?)\b", re.IGNORECASE)


def _is_board(org: str) -> bool:
    return bool(_BOARD_PATTERN.search(org or ""))


def main() -> int:
    _receipt, candidates = _linkedin_evidence_candidates(FIXTURE)
    bad = [(c["title"], c["organization"]) for c in candidates
           if _is_board(str(c.get("organization", "")))]
    if bad:
        print(
            f"LINKEDIN_ORG_IS_BOARD: {len(bad)} top-applicant row(s) have a job-board name as the "
            "organization instead of the employer. Examples: "
            + "; ".join(f"{t[:26]!r} -> {o[:30]!r}" for t, o in bad[:4]),
            file=sys.stderr,
        )
        return 1
    print(f"LINKEDIN_ORG_NOT_BOARD_OK: {len(candidates)} top-applicant orgs are employers, not boards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
