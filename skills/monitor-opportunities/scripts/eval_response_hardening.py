#!/usr/bin/env python3
"""Regression guard: response-ranking must honor the four hardened signals.

Hardened 2026-08-22 so the morning report surfaces the roles that actually get
replies for Graham: LinkedIn top-applicant status, Buffalo/WNY presence, credible
remote, and Easy Apply. Before this, top_candidate and easy_apply had NO effect
on the score and geo was binary (WNY hybrid == onsite), so Buffalo top-applicant
roles ranked below cold remote roles.

This guard exercises the real `score_opportunity` and fails (exit 1) if any of
the ranking invariants regress.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.response_likelihood import score_opportunity  # noqa: E402


def _score(**opp) -> float:
    return score_opportunity(opp)["response_score"]


def main() -> int:
    failures: list[str] = []

    # 1. Top-applicant status must raise the score for an otherwise identical role.
    base = dict(fit=0.8, workplace_type="REMOTE")
    if not _score(**base, top_candidate_evidence=True) > _score(**base):
        failures.append("TOP_CANDIDATE_NO_EFFECT: top-applicant status did not raise the response score.")

    # 2. Easy Apply must give a positive nudge.
    if not _score(**base, easy_apply=True) > _score(**base):
        failures.append("EASY_APPLY_NO_EFFECT: Easy Apply did not raise the response score.")

    # 3. Graded geo: WNY hybrid > WNY onsite > remote, all else equal.
    hy = _score(fit=0.8, workplace_type="WNY_HYBRID")
    on = _score(fit=0.8, workplace_type="WNY_ONSITE")
    rem = _score(fit=0.8, workplace_type="REMOTE")
    if not (hy > on > rem):
        failures.append(f"GEO_ORDER_REGRESSION: expected WNY_HYBRID>WNY_ONSITE>REMOTE, got {hy:.3f},{on:.3f},{rem:.3f}.")

    # 4. A Buffalo top-applicant role must outrank a cold remote role of equal fit.
    buffalo_top = _score(fit=0.85, workplace_type="WNY_ONSITE", top_candidate_evidence=True)
    remote_cold = _score(fit=0.85, workplace_type="REMOTE")
    if not buffalo_top > remote_cold:
        failures.append(
            f"BUFFALO_TOP_BURIED: Buffalo top-applicant ({buffalo_top:.3f}) did not outrank "
            f"cold remote of equal fit ({remote_cold:.3f})."
        )

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("RESPONSE_HARDENING_OK: top-candidate, easy-apply, graded geo, and Buffalo priority all hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
