#!/usr/bin/env python3
"""Validate the SPARTA exposure skill contract.

This script is intentionally a contract guard, not a production classifier.
Production grounding belongs to /extract-entities and /create-evidence-case.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"

REQUIRED_MARKERS = {
    "scope_sparta_f36": "The v1 scope is SPARTA/F-36 only.",
    "memory_intent": "/memory` owns intent routing",
    "extract_grounding": "/extract-entities` owns entity grounding",
    "evidence_case": "/create-evidence-case` owns crosswalk chains",
    "monitor_freshness": "/monitor-sparta` owns pipeline health",
    "coverage_page": "Coverage page",
    "supply_chain_page": "Supply Chain page",
    "data_qid_boundary": "`data-qid` values only as navigation",
    "bare_exposure_clarify": "`what is our exposure?` | `clarify_missing_target`",
    "ac3_exposure_evidence": "`what is our exposure for AC-3?` | `extract_entities_then_create_evidence_case`",
    "relationship_evidence": "`what is our exposure from CM0001 to DE-0009.05?` | `relationship_evidence_case`",
    "supplier_read_model": "`show supplier exposure for vendor X` | `supply_chain_read_model_then_evidence_case_if_grounded`",
    "ham_sandwich_unsupported": "`how does AC-3 relate to ham sandwiches?` | `clarify_unsupported_premise`",
    "flying_saucers_not_grounded": "must never be preserved as grounded vocabulary",
    "draft_signoff": "Recorded human signoff before promotion",
    "fail_closed": "Do not present stale `/monitor-sparta` output as live operational exposure.",
    "no_regex": "Do not use regex, keyword lists, or exposure phrase lists for intent routing.",
}

SCENARIOS = {
    "bare_exposure": "clarify_missing_target",
    "grounded_control_exposure": "extract_entities_then_create_evidence_case",
    "relationship_exposure": "relationship_evidence_case",
    "supplier_exposure": "supply_chain_read_model_then_evidence_case_if_grounded",
    "unsupported_premise": "clarify_unsupported_premise",
    "ungrounded_term": "clarify_or_deflect_ungrounded_term",
}


def load_contract() -> str:
    if not SKILL_MD.exists():
        raise AssertionError(f"missing {SKILL_MD}")
    return SKILL_MD.read_text(encoding="utf-8")


def validate_markers(text: str) -> list[str]:
    missing = []
    for name, marker in REQUIRED_MARKERS.items():
        if marker not in text:
            missing.append(name)
    return missing


def validate_scenario(text: str, scenario: str) -> str:
    if scenario not in SCENARIOS:
        raise AssertionError(f"unknown scenario {scenario!r}")
    expected_route = SCENARIOS[scenario]
    if expected_route not in text:
        raise AssertionError(f"scenario {scenario!r} missing route {expected_route!r}")
    return expected_route


def sampled_guard(text: str, samples: int, seed: int | None) -> list[str]:
    if samples <= 0:
        return []
    if samples < 50:
        raise AssertionError("--samples must be >= 50 for compliance contract sweeps")
    rng = random.Random(seed)
    names = list(SCENARIOS)
    observed = []
    for _ in range(samples):
        name = rng.choice(names)
        observed.append(validate_scenario(text, name))
    return observed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--samples", type=int, default=0)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args(argv)

    try:
        text = load_contract()
        missing = validate_markers(text)
        if missing:
            raise AssertionError("missing required markers: " + ", ".join(missing))
        route = validate_scenario(text, args.scenario) if args.scenario else None
        sampled = sampled_guard(text, args.samples, args.seed)
    except AssertionError as exc:
        payload = {
            "schema": "sparta_exposure.contract_check.v1",
            "status": "FAIL",
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"SPARTA_EXPOSURE_CONTRACT_FAIL: {exc}")
        return 1

    payload = {
        "schema": "sparta_exposure.contract_check.v1",
        "status": "PASS",
        "sentinel": "SPARTA_EXPOSURE_CONTRACT_OK",
        "skill": "sparta-exposure",
        "scenario": args.scenario,
        "scenario_route": route,
        "sampled_cases": len(sampled),
        "sampled_unique_routes": sorted(set(sampled)),
        "mocked": False,
        "live_memory_arango_monitor_explorer": False,
        "what_was_exercised": "local skill contract text and required routing examples",
        "what_remains_unverified": "live Memory intent routing, extract-entities service output, create-evidence-case output, monitor-sparta freshness reads, and Sparta Explorer read-model integration",
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print("SPARTA_EXPOSURE_CONTRACT_OK")
        if route:
            print(f"scenario_route={route}")
        if args.samples:
            print(f"sampled_cases={len(sampled)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
