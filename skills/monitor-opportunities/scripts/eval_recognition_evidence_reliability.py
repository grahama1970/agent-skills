#!/usr/bin/env python3
"""Guard recognition evidence routing across the current shortlisted set.

This is not the final live Brave/Search plus Ask proof. It is a retained
multi-sample guard over the production ``route_opportunity`` path using the
latest report-visible shortlist as input and a recorded extraction oracle as
the evidence boundary. The receipt labels that boundary explicitly so this case
cannot be mistaken for live provider reliability.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.recognition_routes import route_opportunity  # noqa: E402

PROFILE = {
    "schools": ["University at Buffalo", "SUNY at Buffalo", "Trinity University"],
    "networks": ["DARPA ARCOS", "defense/aerospace", "AFRL"],
}

KNOWN_ROUTE_BY_ORG = {
    "unstructured": "FOUNDER_DIRECT",
    "moog inc.": "DEFENSE_NETWORK",
    "moog": "DEFENSE_NETWORK",
}

FALLBACK_SHORTLIST = [
    {
        "candidate_id": "fixture:recognition:unstructured",
        "organization": "Unstructured",
        "title": "Forward Deployed Engineer",
    },
    {
        "candidate_id": "fixture:recognition:moog",
        "organization": "Moog Inc.",
        "title": "Senior AI Engineer",
    },
    {
        "candidate_id": "fixture:recognition:vanta",
        "organization": "Vanta",
        "title": "Software Engineer, AI Platform",
    },
    {
        "candidate_id": "fixture:recognition:acv",
        "organization": "ACV Auctions",
        "title": "Machine Learning Engineer IV, Data",
    },
    {
        "candidate_id": "fixture:recognition:coforge",
        "organization": "Coforge",
        "title": "AI Engineering Lead",
    },
    {
        "candidate_id": "fixture:recognition:primitive",
        "organization": "Primitive Labs",
        "title": "Member of Technical Staff, Founding Engineer",
    },
    {
        "candidate_id": "fixture:recognition:clay",
        "organization": "Clay",
        "title": "Software Engineer, Data Products and Platform",
    },
    {
        "candidate_id": "fixture:recognition:cognition",
        "organization": "Cognition",
        "title": "Forward Deployed Engineer",
    },
]


def _load_shortlist(run_dir: Path) -> list[dict[str, Any]]:
    for rel in ("ranking-live/shortlist.json", "ranking/shortlist.json"):
        path = run_dir / rel
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("items", "opportunities", "shortlist"):
                    value = data.get(key)
                    if isinstance(value, list):
                        return value
    return []


def _expected_route(opp: dict[str, Any]) -> str:
    org = str(opp.get("organization") or "").strip().lower()
    return KNOWN_ROUTE_BY_ORG.get(org, "COLD_APPLY_LONGSHOT")


def _search_rows(opp: dict[str, Any], sample_index: int, query: str) -> list[dict[str, Any]]:
    org = str(opp.get("organization") or "").strip().lower()
    title = str(opp.get("title") or "")
    suffix = f"sample={sample_index} query={query[:80]}"
    if org == "unstructured":
        return [
            {
                "title": f"Unstructured founder Brian Raymond {suffix}",
                "description": "Brian Raymond founded Unstructured and works on AI data infrastructure.",
            },
            {
                "title": f"Unstructured role {title}",
                "description": "Engineering work around document AI, data processing, and public sector use cases.",
            },
        ]
    if org in {"moog inc.", "moog"}:
        return [
            {
                "title": f"Moog aerospace defense digital thread {suffix}",
                "description": "Moog is an aerospace and defense manufacturer with digital engineering programs.",
            },
            {
                "title": f"Moog role {title}",
                "description": "Senior AI engineering role tied to agentic solutions and digital thread.",
            },
        ]
    return [
        {
            "title": f"{opp.get('organization')} company profile {suffix}",
            "description": "Public company and job description snippets without a named founder, defense bridge, "
            "or hiring manager for this specific role.",
        },
        {
            "title": f"{opp.get('organization')} role {title}",
            "description": "Generic hiring page content. No supported warm recognition route is present.",
        },
    ]


def _extract_from_recorded_prompt(prompt: str) -> str:
    lower = prompt.lower()
    if "employer: unstructured" in lower:
        return json.dumps(
            {
                "is_founder_led_startup": True,
                "founder_name": "Brian Raymond",
                "founder_domain_aware": True,
                "is_defense_aerospace": False,
                "hiring_manager_name": None,
            },
            sort_keys=True,
        )
    if "employer: moog inc." in lower or "employer: moog" in lower:
        return json.dumps(
            {
                "is_founder_led_startup": False,
                "founder_name": "Moog Inc",
                "founder_domain_aware": False,
                "is_defense_aerospace": True,
                "hiring_manager_name": None,
            },
            sort_keys=True,
        )
    return json.dumps(
        {
            "is_founder_led_startup": False,
            "founder_name": None,
            "founder_domain_aware": False,
            "is_defense_aerospace": False,
            "hiring_manager_name": None,
        },
        sort_keys=True,
    )


def _run_samples(shortlist: list[dict[str, Any]], samples: int) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for opp in shortlist:
        expected = _expected_route(opp)
        routes: list[str] = []
        for sample_index in range(samples):
            def search_fn(query: str, *, _opp: dict[str, Any] = opp, _sample: int = sample_index) -> list[dict[str, Any]]:
                return _search_rows(_opp, _sample, query)

            routed = route_opportunity(opp, PROFILE, search_fn, _extract_from_recorded_prompt)
            got = routed["recognition_route"]["route_type"]
            routes.append(got)
            if got != expected:
                failures.append(
                    "RECOGNITION_EVIDENCE_ROUTE_MISMATCH: "
                    f"{opp.get('candidate_id')} {opp.get('organization')} expected {expected}, got {got}"
                )
            if expected == "COLD_APPLY_LONGSHOT" and got != "COLD_APPLY_LONGSHOT":
                failures.append(
                    "RECOGNITION_EVIDENCE_INVENTED_ROUTE: "
                    f"{opp.get('candidate_id')} {opp.get('organization')} got unsupported {got}"
                )
        histogram = dict(sorted(Counter(routes).items()))
        results.append(
            {
                "candidate_id": opp.get("candidate_id"),
                "organization": opp.get("organization"),
                "title": opp.get("title"),
                "expected_route": expected,
                "route_histogram": histogram,
                "samples": samples,
                "pass": all(route == expected for route in routes),
            }
        )
    return results, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=SKILL_DIR / "local/nightly/latest")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--out", type=Path, default=SKILL_DIR / "local/evals/recognition-evidence-reliability.json")
    args = parser.parse_args()

    run_dir = args.run.resolve()
    samples = max(1, args.samples)
    shortlist = _load_shortlist(run_dir)
    failures: list[str] = []
    if not shortlist:
        shortlist = FALLBACK_SHORTLIST

    results, sample_failures = _run_samples(shortlist, samples) if shortlist else ([], [])
    failures.extend(sample_failures)
    opportunity_count = len(results)
    passed = sum(1 for item in results if item["pass"])
    expected_warm = sum(1 for item in results if item["expected_route"] != "COLD_APPLY_LONGSHOT")
    invented_warm = sum(
        count
        for item in results
        if item["expected_route"] == "COLD_APPLY_LONGSHOT"
        for route, count in item["route_histogram"].items()
        if route != "COLD_APPLY_LONGSHOT"
    )
    pass_rate = round(passed / opportunity_count, 4) if opportunity_count else 0.0

    receipt = {
        "schema": "monitor_opportunities.recognition_evidence_reliability.v1",
        "status": "PASS" if not failures else "FAIL",
        "mocked": True,
        "live": False,
        "external_live": False,
        "proof_boundary": "production route_opportunity over latest shortlisted opportunities with recorded search/extraction oracle",
        "does_not_prove": [
            "live Brave result quality",
            "live Ask or model extraction quality",
            "nightly report integration",
        ],
        "run_dir": str(run_dir),
        "samples_per_opportunity": samples,
        "opportunity_count": opportunity_count,
        "expected_warm_route_count": expected_warm,
        "invented_warm_route_count": invented_warm,
        "route_pass_rate": pass_rate,
        "failures": failures,
        "opportunities": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"RECOGNITION_EVIDENCE_RELIABILITY_FAIL receipt={args.out}", file=sys.stderr)
        return 1
    print(
        "RECOGNITION_EVIDENCE_RELIABILITY_OK "
        f"opportunities={opportunity_count} samples={samples} pass_rate={pass_rate:.4f} "
        f"invented_warm_routes={invented_warm} mocked=yes live=no receipt={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
