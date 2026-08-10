#!/usr/bin/env python3
"""Pin the two-stage matching policy: rough at scale, expensive filter on few.

Stage one (Flashtext trie) is cheap and carries the whole dictionary. Stage two
(RapidFuzz) is expensive and must only ever see stage one's shortlist.

The cases that matter are the ones where being helpful is wrong. An edit on an
identifier yields a different real entity, so a "close" identifier match is a
silent substitution -- CWE-19 scores 83 against CWE-79, and they are Data
Processing Errors and Cross-site Scripting respectively. Accepting that is worse
than returning nothing, because the caller cannot tell it happened.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from entity_match_policy import (  # noqa: E402
    CandidateSetTooLarge,
    MAX_CANDIDATES,
    filter_candidates,
    is_fragment_of_larger_token,
    looks_like_identifier,
    normalise_identifier,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results, failures = [], []

    def check(name: str, ok: bool, detail: str) -> None:
        results.append({"case": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    # --- longest match: a hit inside a longer identifier is not a hit.
    # Flashtext returns the longest keyword IN THE DICTIONARY, not the longest
    # token in the TEXT, so an absent compound id grounds an inner component:
    # "F36B-M08-S02" yields M08, a different control taken from a substring of
    # the one actually named.
    fragment_cases = [
        ("F36B-M08-S02", 5, 8, True, "inner component of a compound id"),
        ("the M08 sensor", 4, 7, False, "standalone"),
        ("CWE-895", 0, 6, True, "CWE-89 inside CWE-895"),
        ("T1003.001", 0, 5, True, "T1003 inside its sub-technique"),
        ("AC-2(1)", 0, 4, True, "AC-2 inside an enhancement"),
        ("see CWE-89.", 4, 10, False, "sentence-final period is punctuation"),
        ("uses AC-2 (see note)", 5, 9, False, "spaced parenthetical"),
    ]
    wrong_fragments = [why for text, s0, e0, expected, why in fragment_cases
                       if is_fragment_of_larger_token(text, s0, e0) != expected]
    check("longest_match_fragments_rejected", not wrong_fragments,
          f"misjudged: {wrong_fragments or 'none'}")

    # --- identifiers: formatting may vary, alphanumerics may not.
    # This is the case the whole policy exists for. CWE-23 and CWE-32 are
    # Relative Path Traversal and Improper Symbolic Link Resolution.
    transposed = filter_candidates("CWE-23", [("CWE-32", 90.0), ("CWE-23", 100.0)])
    check("transposed_digits_never_match_wrong_entity",
          transposed.accepted and transposed.keyword == "CWE-23",
          f"CWE-23 picked {transposed.keyword} not CWE-32 -> {transposed.reason}")

    only_wrong = filter_candidates("CWE-23", [("CWE-32", 90.0)])
    check("transposed_digits_rejected_when_only_option", not only_wrong.accepted,
          f"CWE-23 vs CWE-32 at 90 -> {only_wrong.reason}")

    for written, canonical in (("CWE23", "CWE-23"), ("cwe 23", "CWE-23"), ("Cwe-23", "CWE-23"),
                               ("CVE 2021 44228", "CVE-2021-44228"), ("t1003", "T1003")):
        got = filter_candidates(written, [(canonical, 88.0)])
        # The REASON matters: accepting via the name path means the token was not
        # recognised as an identifier, so a wrong entity could be accepted for it.
        check(f"formatting_variant::{written}",
              got.accepted and got.keyword == canonical
              and got.reason == "identifier_formatting_normalised",
              f"{written!r} -> {got.reason}")

    # and the same variants must still refuse a different entity
    for written in ("CWE23", "cwe 23"):
        wrong = filter_candidates(written, [("CWE-32", 95.0)])
        check(f"formatting_variant_still_refuses_wrong::{written}", not wrong.accepted,
              f"{written!r} vs CWE-32 -> {wrong.reason}")

    check("normalisation_keeps_alphanumerics",
          normalise_identifier("CWE-23") == normalise_identifier("cwe 23") == "cwe23"
          and normalise_identifier("CWE-32") == "cwe32",
          "CWE-23/cwe 23 -> cwe23; CWE-32 -> cwe32")

    # --- identifiers: a near miss is a DIFFERENT entity, never a typo
    near = filter_candidates("CWE-19", [("CWE-79", 83.0), ("CWE-89", 83.0)])
    check("identifier_near_miss_rejected", not near.accepted,
          f"CWE-19 vs CWE-79 at 83 -> {near.reason}")

    exact = filter_candidates("CWE-89", [("CWE-89", 100.0), ("CWE-79", 83.0)])
    check("identifier_exact_accepted", exact.accepted and exact.keyword == "CWE-89",
          f"exact identifier -> {exact.reason}")

    tech = filter_candidates("T1004", [("T1003", 80.0)])
    check("technique_near_miss_rejected", not tech.accepted,
          f"T1004 vs T1003 at 80 -> {tech.reason}")

    # --- names: a misspelling IS the same entity
    typo = filter_candidates("OS Credentail Dumping",
                             [("OS Credential Dumping", 95.0), ("Credential Access", 60.0)])
    check("name_typo_accepted", typo.accepted,
          f"name typo at 95 with clear margin -> {typo.reason}")

    weak = filter_candidates("something unrelated entirely", [("Access Control", 62.0)])
    check("weak_name_rejected", not weak.accepted, f"62 is below cutoff -> {weak.reason}")

    # --- ambiguity is evidence against a match, not a ranking problem
    tie = filter_candidates("Access Controls",
                            [("Access Control", 96.0), ("Access Controller", 95.0)])
    check("ambiguous_name_rejected", not tie.accepted,
          f"96 vs 95 within tie margin -> {tie.reason}")

    # --- identifier shape detection drives which rule applies
    shapes = {"CWE-89": True, "CVE-2021-44228": True, "T1003": True, "AML.T0051": True,
              "CAPEC-66": True, "D3-ACA": True, "TID-320": True,
              # formatting variants must classify as identifiers too, or they
              # silently take the NAME path where fuzzy matching is allowed
              "CWE23": True, "cwe 23": True, "d3 aca": True,
              "Access Control": False, "credential dumping": False,
              "Data Encrypted for Impact": False}
    wrong = [k for k, expected in shapes.items() if looks_like_identifier(k) != expected]
    check("identifier_shape_detection", not wrong, f"misclassified: {wrong or 'none'}")

    # --- the cost guard: stage two must never be handed the dictionary
    try:
        filter_candidates("anything", [(f"kw{i}", 90.0) for i in range(MAX_CANDIDATES + 1)])
        check("cost_guard_rejects_dictionary_sized_input", False, "no exception raised")
    except CandidateSetTooLarge as exc:
        check("cost_guard_rejects_dictionary_sized_input", True, str(exc)[:80])

    started = time.time()
    for _ in range(10_000):
        filter_candidates("CWE-19", [("CWE-79", 83.0), ("CWE-89", 83.0)])
    per_call_us = (time.time() - started) / 10_000 * 1e6
    check("filter_is_cheap_per_mention", per_call_us < 100,
          f"{per_call_us:.1f}us per decision over a shortlist")

    report = {
        "schema": "extract_entities.match_policy_bench.v1",
        "verdict": "PASS" if not failures else "FAIL",
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "failures": failures,
        "results": results,
        "policy": {
            "stage1": "Flashtext trie, O(text), carries the full dictionary",
            "stage2": "RapidFuzz, O(candidates), shortlist only, capped at "
                      f"{MAX_CANDIDATES}",
            "identifiers": "exact only -- one edit is a different entity",
            "names": "fuzzy with a cutoff and a tie margin",
        },
        "mocked": False, "live": False,
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for row in results:
            print(f"  {'ok  ' if row['ok'] else 'FAIL'} {row['case']:42s} {row['detail']}")
        print(f"VERDICT: {report['verdict']} ({report['passed']}/{report['total']})")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
