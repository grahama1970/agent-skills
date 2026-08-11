#!/usr/bin/env python3
"""Exhaustively prove fixed-seat sequential stopping equivalence."""

from __future__ import annotations

import argparse
import itertools
import json
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes-required", type=int, required=True)
    parser.add_argument("--seat-cap", type=int, required=True)
    return parser.parse_args()


def final_decision(votes: tuple[bool, ...], yes_required: int) -> str:
    return "PASS" if sum(votes) >= yes_required else "FAIL"


def sequential_decision(votes: tuple[bool, ...], yes_required: int) -> tuple[str, int]:
    seat_cap = len(votes)
    yes = 0
    no = 0
    for index, vote in enumerate(votes, start=1):
        if vote:
            yes += 1
        else:
            no += 1
        if yes >= yes_required:
            return "PASS", index
        if no > seat_cap - yes_required:
            return "FAIL", index
    return final_decision(votes, yes_required), seat_cap


def main() -> int:
    args = parse_args()
    if args.yes_required < 1 or args.yes_required > args.seat_cap:
        print(json.dumps({"status": "FAIL", "error": "invalid threshold"}, indent=2))
        return 1
    mismatches = []
    early_pass = 0
    early_fail = 0
    cases = 0
    for votes in itertools.product((False, True), repeat=args.seat_cap):
        cases += 1
        expected = final_decision(votes, args.yes_required)
        observed, stopped_after = sequential_decision(votes, args.yes_required)
        if observed != expected:
            mismatches.append({"votes": votes, "expected": expected, "observed": observed})
        if stopped_after < args.seat_cap and observed == "PASS":
            early_pass += 1
        if stopped_after < args.seat_cap and observed == "FAIL":
            early_fail += 1
    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "yes_required": args.yes_required,
        "seat_cap": args.seat_cap,
        "exhaustive_cases": cases,
        "early_pass_cases": early_pass,
        "early_fail_cases": early_fail,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
    print(json.dumps(result, indent=2))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
