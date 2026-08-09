#!/usr/bin/env python3
"""Measures whether a NON-EXPERT operator can answer security questions using
the SPARTA corpus alone, and -- more importantly -- whether the corpus tells
them when it cannot answer.

Three question classes, because they fail in different ways:

  resolve   real identifier in a dense slice -> must RESOLVE with the right name.
            Measures retrieval coverage.

  reject    fabricated identifier in a dense slice -> must return NOT_IN_CORPUS.
            Measures confabulation resistance.

  abstain   REAL identifier absent from a sparse slice -> must return
            UNVERIFIED_LOCALLY, never NOT_IN_CORPUS. Measures whether the tool
            protects its operator from asserting a false negative.

The `abstain` class is the one that decides whether this is safe in a
non-expert's hands. Log4Shell, Heartbleed, and the xz backdoor are all real and
all absent from the local NVD slice. A tool that answers "not found" for those
hands its operator a confidently wrong answer -- precisely the failure this
corpus exists to prevent. An abstain miscall is therefore scored CRITICAL and
fails the run regardless of overall accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyst_probe import resolve, search  # noqa: E402

QUESTION_BANK = [
    # --- resolve: retrieval coverage across the taxonomies the assessment names
    {"class": "resolve", "id": "T1003", "expect_name_contains": "Credential Dumping",
     "why": "ATT&CK technique attribution -- threat analysis"},
    {"class": "resolve", "id": "CWE-1004", "expect_name_contains": "HttpOnly",
     "why": "weakness class -- vulnerability assessment"},
    {"class": "resolve", "id": "CAPEC-1", "expect_name_contains": "ACL",
     "why": "attack pattern -- offensive technique"},
    {"class": "resolve", "id": "D3-ACA", "expect_name_contains": "Certificate",
     "why": "countermeasure -- detection engineering"},
    {"class": "resolve", "id": "CVE-1999-0073", "expect_name_contains": "CVE-1999-0073",
     "why": "CVE present in the local slice"},

    # --- reject: fabricated identifiers a model might hallucinate
    {"class": "reject", "id": "CWE-999999",
     "why": "fabricated weakness id -- must not be dignified with an answer"},
    {"class": "reject", "id": "CAPEC-999999",
     "why": "fabricated attack pattern id"},
    {"class": "reject", "id": "T9999",
     "why": "fabricated ATT&CK technique id"},

    # --- abstain: REAL and famous, but absent locally. Must not read as fake.
    {"class": "abstain", "id": "CVE-2021-44228",
     "why": "Log4Shell -- real, absent locally; false 'not found' would be a wrong answer"},
    {"class": "abstain", "id": "CVE-2014-0160",
     "why": "Heartbleed -- real, absent locally"},
    {"class": "abstain", "id": "CVE-2024-3094",
     "why": "xz-utils backdoor -- real, absent locally"},
]

# Description-to-weakness questions in the shape the assessment reportedly uses.
SEARCH_BANK = [
    {"text": "cookie storing sensitive information without the HttpOnly flag",
     "expect_id": "CWE-1004", "framework": "CWE"},
    {"text": "adversaries dump credentials from the operating system to obtain login material",
     "expect_id": "T1003", "framework": "ATT_CK_Enterprise"},
]


def run_bank() -> dict:
    results, critical = [], []
    for question in QUESTION_BANK:
        got = resolve(question["id"])
        status = got["status"]
        if question["class"] == "resolve":
            ok = status == "RESOLVED" and question["expect_name_contains"].lower() in str(got.get("name") or "").lower()
        elif question["class"] == "reject":
            ok = status == "NOT_IN_CORPUS"
        else:  # abstain
            ok = status == "UNVERIFIED_LOCALLY"
            if status == "NOT_IN_CORPUS":
                critical.append({
                    "id": question["id"],
                    "failure": "false_negative_would_mislead_operator",
                    "detail": "a real identifier was reported as absent from a complete index",
                })
        results.append({
            "class": question["class"], "id": question["id"], "why": question["why"],
            "status": status, "name": got.get("name"), "ok": ok,
        })

    search_results = []
    for question in SEARCH_BANK:
        got = search(question["text"], limit=5, framework=question["framework"])
        ids = [c["control_id"] for c in got["candidates"]]
        search_results.append({
            "query": question["text"][:60], "expect": question["expect_id"],
            "top5": ids, "ok": question["expect_id"] in ids,
            "rank": (ids.index(question["expect_id"]) + 1) if question["expect_id"] in ids else None,
        })

    by_class = {}
    for cls in ("resolve", "reject", "abstain"):
        subset = [r for r in results if r["class"] == cls]
        by_class[cls] = {"passed": sum(1 for r in subset if r["ok"]), "total": len(subset)}
    search_passed = sum(1 for r in search_results if r["ok"])

    total_passed = sum(1 for r in results if r["ok"]) + search_passed
    total = len(results) + len(search_results)
    verdict = "PASS" if (total_passed == total and not critical) else "FAIL"

    return {
        "schema": "sparta.analyst_bench.v1",
        "verdict": verdict,
        "operator_profile": "non_cybersecurity_expert",
        "by_class": by_class,
        "search": {"passed": search_passed, "total": len(search_results)},
        "total_passed": total_passed, "total": total,
        "critical_failures": critical,
        "results": results,
        "search_results": search_results,
        "claims": {
            "proves": (
                "identifier-level retrieval coverage and, decisively, that the corpus "
                "abstains rather than emitting a false negative on real-but-absent ids"
            ),
            "does_not_prove": (
                "plausibility judgment -- whether an exploitation narrative is realistic, "
                "whether a detection rule would false-positive, or whether an AI's threat "
                "analysis is operationally sound. Those need a practitioner."
            ),
        },
        "mocked": False, "live": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = run_bank()
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=1))
    if args.quiet:
        print(f"VERDICT: {report['verdict']} ({report['total_passed']}/{report['total']})")
    else:
        print(json.dumps(report, indent=1))
    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
