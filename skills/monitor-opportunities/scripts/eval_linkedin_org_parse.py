#!/usr/bin/env python3
"""Regression guard: LinkedIn top-applicant organization must not be the title.

Incident (#1483): top-applicant rows come out of the parser with organization
equal to a fragment of the role title (e.g. "AI Principal Engineer" ->
"AI Principal Engineer with verification"), because the captured fields are
misaligned — the real employer is often elsewhere in the row. A resume/report
that shows "Manager, AI Engineer @ Manager, AI Engineer" is wrong.

This guard runs the REAL parser (_linkedin_evidence_candidates) over a committed
fixture of misaligned rows and fails (exit 1) if any emitted top-applicant
candidate's organization is a fragment of its title or carries the
"with verification" artifact.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.discovery import _linkedin_evidence_candidates  # noqa: E402

FIXTURE = SKILL_DIR / "tests" / "fixtures" / "linkedin" / "top_applicant_misparse.json"


def _is_misparsed(title: str, org: str) -> bool:
    t, o = title.strip().lower(), org.strip().lower()
    if not o:
        return True
    if "with verification" in o:
        return True
    # organization is a leading fragment of the title (the title leaked in)
    return o[:15] and o[:15] in t


def main() -> int:
    _receipt, candidates = _linkedin_evidence_candidates(FIXTURE)
    bad = [(c["title"], c["organization"]) for c in candidates
           if _is_misparsed(str(c.get("title", "")), str(c.get("organization", "")))]
    if bad:
        print(
            f"LINKEDIN_ORG_MISPARSE: {len(bad)} top-applicant row(s) have organization == title "
            "fragment or a 'with verification' artifact. The parser must recover the real employer "
            "from the row instead of echoing the title. Examples: "
            + "; ".join(f"{t[:28]!r} -> {o[:28]!r}" for t, o in bad[:4]),
            file=sys.stderr,
        )
        return 1
    print(f"LINKEDIN_ORG_PARSE_OK: {len(candidates)} top-applicant rows have a distinct employer organization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
