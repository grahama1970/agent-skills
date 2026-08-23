#!/usr/bin/env python3
"""Regression guard: WNY LinkedIn-located roles must not be buried.

Incident (2026-08-23, run-20260823T060000Z): 6 eligible WNY_ONSITE roles
(Roswell Park, Coforge, Fleet AI, ...) were discovered via LinkedIn Jobs, then
quarantined as source_intel `LOCATOR_ONLY` / `action_worthy: False` with no
promotion path. Because Buffalo/WNY roles surface almost entirely via LinkedIn,
the hard-constraint geography was structurally absent from the ranked shortlist
every run. The primary-source readback (readback.py) is the missing half of the
research-first architecture.

This guard exercises the real functions and fails (exit 1) if:
  - a WNY LinkedIn locator whose employer HAS a same-run primary ATS posting is
    NOT promoted into the rankable opportunity pool; or
  - a WNY LinkedIn locator with NO primary corroboration is buried
    (action_worthy False / decision LOCATOR_ONLY) instead of surfaced as
    PENDING_PRIMARY_VERIFICATION; or
  - a non-WNY LinkedIn locator is wrongly promoted or made action-worthy.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities import pipeline  # noqa: E402
from monitor_opportunities.ranking import _run_local_ats_probe, _is_source_intel_candidate  # noqa: E402
from monitor_opportunities.readback import (  # noqa: E402
    live_ats_probe,
    promote_linkedin_locators,
    slug_variants,
)


def _locator(cid, org, title, geo):
    return {
        "candidate_id": cid, "lane": "A", "organization": org, "title": title,
        "workplace_type": geo, "source_provider": "human_supplied_linkedin",
        "primary_evidence_url": f"https://www.linkedin.com/jobs/view/{cid}",
        "source_receipt_id": "src:a:linkedin:test",
    }


def _primary(org, title, geo="WNY_ONSITE"):
    return {
        "candidate_id": f"candidate:a:greenhouse:{org[:6]}", "lane": "A", "organization": org,
        "title": title, "workplace_type": geo, "source_provider": "greenhouse",
        "primary_evidence_url": f"https://boards.greenhouse.io/{org[:6].lower()}/jobs/1",
        "source_receipt_id": "src:a:greenhouse:test",
    }


def main() -> int:
    failures: list[str] = []

    corroborated = _locator("wny-hit", "Roswell Park Comprehensive Cancer Center", "Computational Scientist", "WNY_ONSITE")
    uncorroborated = _locator("wny-miss", "Coforge", "AI Engineering Lead", "WNY_ONSITE")
    remote_locator = _locator("remote-loc", "SomeCo", "Backend Engineer", "REMOTE")
    primary = _primary("Roswell Park Comprehensive Cancer Center", "Senior Computational Scientist")

    candidates = [corroborated, uncorroborated, remote_locator, primary]
    probe = _run_local_ats_probe(candidates)
    out, receipts = promote_linkedin_locators(candidates, probe)

    by_locator = {c.get("locator_candidate_id"): c for c in out if c.get("located_via") == "linkedin"}
    # 1. corroborated WNY locator promoted into the opportunity pool
    promoted = by_locator.get("wny-hit")
    if promoted is None:
        failures.append("WNY_PROMOTION_MISSING: a WNY locator with a same-run primary ATS source was not promoted")
    else:
        if _is_source_intel_candidate(promoted):
            failures.append("WNY_PROMOTION_NOT_RANKABLE: promoted candidate still classifies as source_intel")
        if promoted.get("source_provider") == "human_supplied_linkedin":
            failures.append("WNY_PROMOTION_STILL_LOCATOR: promoted candidate keeps the LinkedIn source_provider")

    # 2. uncorroborated WNY locator surfaced (pending), not buried
    miss = next((c for c in out if c.get("candidate_id") == "wny-miss"), None)
    if not (miss and miss.get("pending_primary_verification")):
        failures.append("WNY_MISS_NOT_SURFACED: uncorroborated WNY locator was not flagged pending_primary_verification")
    else:
        si = pipeline._source_intel(miss)
        if not (si and si.get("action_worthy") and si.get("decision") == "PENDING_PRIMARY_VERIFICATION"):
            failures.append(f"WNY_MISS_BURIED: uncorroborated WNY locator not action-worthy pending (got {si and si.get('decision')}, action_worthy={si and si.get('action_worthy')})")

    # 3. non-WNY locator untouched (still a plain, non-actionable locator)
    remote = next((c for c in out if c.get("candidate_id") == "remote-loc"), None)
    if remote is None or remote.get("pending_primary_verification") or remote.get("located_via"):
        failures.append("REMOTE_LOCATOR_MUTATED: a non-WNY locator was promoted or made pending")
    else:
        si = pipeline._source_intel(remote)
        if si and (si.get("action_worthy") or si.get("decision") != "LOCATOR_ONLY"):
            failures.append("REMOTE_LOCATOR_ACTIONABLE: a non-WNY locator was wrongly made action-worthy")

    # 4. LIVE resolver: an employer whose ATS board is fetchable (no same-run
    #    primary) is still promoted by actively resolving its board.
    if "roswellpark" not in slug_variants("Roswell Park Comprehensive Cancer Center"):
        failures.append("SLUG_DERIVATION_WEAK: expected 'roswellpark' among derived slugs")

    def _stub_board(client, target):
        if target["slug"] == "roswellpark":
            return ({"result_status": "MATCHES"}, [{
                "source_provider": "greenhouse", "organization": target["name"],
                "title": "Computational Scientist", "workplace_type": "WNY_ONSITE",
                "primary_evidence_url": "https://boards.greenhouse.io/roswellpark/jobs/9",
                "posting_url": "https://boards.greenhouse.io/roswellpark/jobs/9",
            }])
        return ({"result_status": "INVALID_REQUEST"}, [])

    live_only = _locator("live", "Roswell Park Comprehensive Cancer Center", "Computational Scientist", "WNY_ONSITE")
    live_out, live_rec = promote_linkedin_locators([live_only], live_ats_probe(None, adapters=[_stub_board]))
    live_promoted = [c for c in live_out if c.get("located_via") == "linkedin"]
    if not live_promoted:
        failures.append("LIVE_RESOLVER_NO_PROMOTE: live ATS fetch failed to promote a resolvable WNY locator")
    elif live_promoted[0].get("source_provider") == "human_supplied_linkedin":
        failures.append("LIVE_RESOLVER_STILL_LOCATOR: live-promoted candidate kept the LinkedIn provider")
    elif live_rec[0].get("status") != "PRIMARY_CONFIRMED":
        failures.append(f"LIVE_RESOLVER_BAD_RECEIPT: expected PRIMARY_CONFIRMED, got {live_rec[0].get('status')}")

    # 5. Slug-collision safety: a fetched board belonging to a DIFFERENT employer
    #    must never promote, even with an identical title.
    def _collision_board(client, target):
        return ({"result_status": "MATCHES"}, [{
            "source_provider": "greenhouse", "organization": "Fleet Financial Group",
            "title": "Computational Scientist", "workplace_type": "REMOTE",
            "primary_evidence_url": "https://boards.greenhouse.io/fleet/jobs/1",
        }])
    collide = _locator("collide", "Fleet AI, Inc.", "Computational Scientist", "WNY_ONSITE")
    c_out, _ = promote_linkedin_locators([collide], live_ats_probe(None, adapters=[_collision_board]))
    if any(c.get("located_via") == "linkedin" for c in c_out):
        failures.append("SLUG_COLLISION_FALSE_PROMOTE: a different employer's posting was promoted on a title match")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print(f"WNY_LINKEDIN_READBACK_OK: cross-ref + live-fetch promote WNY locators, "
          f"surfaced-pending otherwise, non-WNY untouched ({len(receipts)} readback attempts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
