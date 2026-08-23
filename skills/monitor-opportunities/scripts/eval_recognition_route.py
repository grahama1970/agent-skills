#!/usr/bin/env python3
"""Regression guard: recognition routing must beat cold apply for a rare expert.

Core mission (operator, 2026-08-23): the candidate is a DARPA ARCOS *prime*, not
a commodity applicant. A cold application is ~1/500 regardless of geography or
résumé polish; response odds come from reaching a human who RECOGNIZES the
pedigree. So per opportunity the product must emit the best get-past-the-algorithm
route (founder-direct, institutional bridge, defense-network, alumni, hiring
manager, or consulting/subcontract) and rank it above cold apply — with a true
cold long-shot flagged, never dressed up as a real shot.

Exercises the real classifier and fails (exit 1) if a recognition route is
misclassified, or if a cold long-shot is not flagged/ranked last.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.recognition_routes import (  # noqa: E402
    classify_route,
    rank_by_recognition,
    route_opportunity,
)

PROFILE = {
    "schools": ["University at Buffalo", "SUNY at Buffalo", "Trinity University"],
    "networks": ["DARPA ARCOS", "defense/aerospace", "AFRL"],
}


def _expect(opp, want_type, failures):
    got = classify_route(opp, PROFILE)["route_type"]
    if got != want_type:
        failures.append(f"ROUTE_MISCLASSIFIED: {opp.get('organization')} expected {want_type}, got {got}")


def main() -> int:
    failures: list[str] = []

    _expect({"organization": "Unstructured",
             "founder": {"name": "Brian Raymond", "reachable": True, "domain_aware": True}},
            "FOUNDER_DIRECT", failures)
    _expect({"organization": "Moog", "is_defense": True,
             "institutional_bridge": {"name": "UB CoE", "detail": "Moog-UB partnership"}},
            "INSTITUTIONAL_BRIDGE", failures)
    _expect({"organization": "DefensePrime", "is_defense": True},
            "DEFENSE_NETWORK", failures)
    _expect({"organization": "Vanta", "hiring_manager": {"name": "EM AI", "role": "Engineering Manager, AI"}},
            "HIRING_MANAGER_DIRECT", failures)
    _expect({"organization": "SAM.gov RFI", "lane": "federal_notice"},
            "CONSULTING_SUBCONTRACT", failures)
    _expect({"organization": "BigCo"},  # no signals
            "COLD_APPLY_LONGSHOT", failures)

    # A founder who is NOT domain-aware/reachable must not trigger FOUNDER_DIRECT.
    cold_founder = classify_route(
        {"organization": "X", "founder": {"name": "Y", "reachable": False, "domain_aware": False}}, PROFILE)
    if cold_founder["route_type"] == "FOUNDER_DIRECT":
        failures.append("FOUNDER_OVERREACH: an unreachable/non-domain founder wrongly gave FOUNDER_DIRECT")

    # Alumni only counts when the school matches the candidate's.
    _expect({"organization": "Z", "alumni": [{"name": "A", "school": "Some Other University"}]},
            "COLD_APPLY_LONGSHOT", failures)
    _expect({"organization": "Z2", "alumni": [{"name": "A", "school": "University at Buffalo"}]},
            "ALUMNI_REFERRAL", failures)

    # Ranking: cold long-shot must sink below every recognition route, and be flagged.
    ranked = rank_by_recognition([
        {"organization": "Cold"},
        {"organization": "Founder", "founder": {"name": "F", "reachable": True, "domain_aware": True}},
    ], PROFILE)
    if ranked[0]["organization"] != "Founder":
        failures.append("RANKING_WRONG: a recognition route did not outrank a cold long-shot")
    cold = next(o for o in ranked if o["organization"] == "Cold")
    if not cold["recognition_route"]["is_cold_longshot"]:
        failures.append("COLD_NOT_FLAGGED: a cold apply was not flagged as a long shot")

    # Automatic path: agentic extraction (stub returns the exact JSON gpt-5.5-high
    # produced live) must map to the right route, and NEVER invent a founder from
    # a public giant (the regex failure mode this replaced).
    def search_stub(_q):
        return [{"title": "x", "description": "y"}]

    def extract_startup(_p):
        return '{"is_founder_led_startup":true,"founder_name":"Brian Raymond","founder_domain_aware":true,"is_defense_aerospace":false,"hiring_manager_name":null}'

    r = route_opportunity({"organization": "Unstructured", "title": "Principal SWE"},
                          PROFILE, search_stub, extract_startup)["recognition_route"]
    if r["route_type"] != "FOUNDER_DIRECT" or "Raymond" not in r["target"]:
        failures.append(f"AGENTIC_FOUNDER_MISSED: expected FOUNDER_DIRECT/Raymond, got {r['route_type']}/{r['target']}")

    def extract_public_defense(_p):
        return '{"is_founder_led_startup":false,"founder_name":"Moog Inc","founder_domain_aware":false,"is_defense_aerospace":true,"hiring_manager_name":null}'

    r = route_opportunity({"organization": "Moog Inc.", "title": "AI Engineer"},
                          PROFILE, search_stub, extract_public_defense)["recognition_route"]
    if r["route_type"] == "FOUNDER_DIRECT":
        failures.append("AGENTIC_FOUNDER_OVERREACH: a non-startup public defense employer got FOUNDER_DIRECT")
    if r["route_type"] != "DEFENSE_NETWORK":
        failures.append(f"AGENTIC_DEFENSE_MISSED: expected DEFENSE_NETWORK, got {r['route_type']}")

    def extract_empty(_p):
        return "not json at all"

    r = route_opportunity({"organization": "BigCorp", "title": "SWE"},
                          PROFILE, search_stub, extract_empty)["recognition_route"]
    if not r["is_cold_longshot"]:
        failures.append("AGENTIC_BAD_EXTRACTION_NOT_COLD: unparseable extraction must fall to cold, not invent a route")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("RECOGNITION_ROUTE_OK: founder/bridge/defense/alumni/hiring-manager/consulting routes classified and "
          "ranked above cold apply; cold long-shots flagged and sunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
