#!/usr/bin/env python3
"""Regression guard: LinkedIn top-applicant rows must not be silently dropped.

A role Graham is a top applicant for must reach ranking even when its employer
cannot be parsed. The parser currently drops such a row (title present but
organization unresolved), silently losing a high-value opportunity. It should
instead surface the row with organization marked unknown, not discard it.

Runs the real parser over the committed fixture and fails (exit 1) if fewer
candidates are emitted than input rows that carry a title.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))
from monitor_opportunities.discovery import _linkedin_evidence_candidates  # noqa: E402
FIXTURE = SKILL_DIR / "tests" / "fixtures" / "linkedin" / "top_applicant_misparse.json"

def main() -> int:
    fix = json.loads(FIXTURE.read_text())
    titled = [o for o in fix.get("opportunities", []) if (o.get("title") or o.get("role"))]
    _r, cands = _linkedin_evidence_candidates(FIXTURE)
    dropped = len(titled) - len(cands)
    if dropped > 0:
        print(f"LINKEDIN_SILENT_DROP: {dropped} top-applicant row(s) with a title were dropped "
              f"({len(titled)} in, {len(cands)} out). A top-applicant role must be surfaced even "
              "when its employer cannot be parsed (organization=unknown), not discarded.",
              file=sys.stderr)
        return 1
    print(f"LINKEDIN_NO_SILENT_DROP_OK: all {len(titled)} titled top-applicant rows reached ranking")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
