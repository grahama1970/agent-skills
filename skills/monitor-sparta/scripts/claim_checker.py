#!/usr/bin/env python3
"""Verify structured security claims against the SPARTA corpus.

Identifier lookup is the easy half. The task an AI-training assessment actually
sets is judging AI-generated security *content* -- and the errors models make
there are specific, repeatable, and checkable:

  wrong CWE mapping         "Log4Shell is a SQL injection flaw (CWE-89)"
  wrong technique           "EternalBlue is ATT&CK T1566, Phishing"
  fabricated identifier     "see CVE-2021-99999"
  taxonomy conflation       calling a CAPEC pattern a CVE, or a CWE a technique
  false exploitation claim  "the xz backdoor is CISA KEV-listed"
  false ransomware linkage  "Heartbleed was used in ransomware campaigns"
  wrong product             "Log4Shell affects OpenSSL"

Each returns VERIFIED, REFUTED, or UNVERIFIABLE with the record that decided it.
REFUTED requires positive contradicting evidence from the corpus -- absence
alone never refutes, because absence is not evidence in a sparse slice.

This is what lets an operator without practitioner recall evaluate model output:
not "I know this is wrong" but "the authoritative record says otherwise, here it
is." Claims the corpus cannot settle come back UNVERIFIABLE rather than guessed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyst_probe import classify_identifier, resolve  # noqa: E402

VERIFIED, REFUTED, UNVERIFIABLE = "VERIFIED", "REFUTED", "UNVERIFIABLE"


def _verdict(status: str, reason: str, evidence: dict | None = None) -> dict:
    return {"verdict": status, "reason": reason, "evidence": evidence}


def check_identifier_exists(identifier: str) -> dict:
    got = resolve(identifier)
    if got["status"] == "RESOLVED":
        return _verdict(VERIFIED, f"{identifier} is a real record in the corpus",
                        {"name": got.get("name"), "citation": got.get("citation")})
    if got["status"] == "NOT_IN_CORPUS":
        return _verdict(REFUTED,
                        f"{identifier} is absent from a near-complete {got['framework']} slice, "
                        "so the identifier is very likely invented", {"probe": got})
    return _verdict(UNVERIFIABLE,
                    f"{identifier} is absent from a sparse slice; absence is not evidence "
                    "either way. Verify upstream.", {"probe": got})


def check_cwe_mapping(cve: str, claimed_cwes: list[str]) -> dict:
    got = resolve(cve)
    if got["status"] != "RESOLVED":
        return _verdict(UNVERIFIABLE, f"{cve} is not resolvable locally", {"probe": got})
    actual = [c.upper() for c in ((got.get("kev") or {}).get("cwes") or [])]
    if not actual:
        return _verdict(UNVERIFIABLE, f"{cve} resolves but carries no CWE mapping locally")
    claimed = [c.upper() for c in claimed_cwes]
    overlap = [c for c in claimed if c in actual]
    if overlap:
        return _verdict(VERIFIED, f"{cve} maps to {overlap} in the authoritative record",
                        {"actual_cwes": actual, "citation": got.get("citation")})
    return _verdict(REFUTED,
                    f"{cve} maps to {actual}, not {claimed}",
                    {"actual_cwes": actual, "claimed_cwes": claimed, "citation": got.get("citation")})


def check_known_exploited(cve: str, claimed: bool) -> dict:
    got = resolve(cve)
    if got["status"] == "RESOLVED" and got.get("known_exploited"):
        if claimed:
            return _verdict(VERIFIED, f"{cve} is in the CISA KEV catalog",
                            {"date_added": (got.get("kev") or {}).get("date_added")})
        return _verdict(REFUTED, f"{cve} IS KEV-listed; the claim that it is not is wrong",
                        {"citation": got.get("citation")})
    # Not KEV-listed. KEV is complete locally, so this negative is meaningful.
    if claimed:
        return _verdict(REFUTED,
                        f"{cve} is not in the CISA KEV catalog, which is complete locally, "
                        "so it is not a known-exploited vulnerability",
                        {"probe_status": got["status"]})
    return _verdict(VERIFIED, f"{cve} is correctly described as not KEV-listed",
                    {"probe_status": got["status"]})


def check_ransomware_linked(cve: str, claimed: bool) -> dict:
    got = resolve(cve)
    if got["status"] != "RESOLVED" or not got.get("known_exploited"):
        return _verdict(UNVERIFIABLE, f"{cve} carries no KEV record to settle ransomware linkage")
    actual = bool((got.get("kev") or {}).get("known_ransomware_campaign_use"))
    if actual == claimed:
        return _verdict(VERIFIED, f"CISA records ransomware linkage for {cve} as {actual}",
                        {"citation": got.get("citation")})
    return _verdict(REFUTED, f"CISA records ransomware linkage for {cve} as {actual}, not {claimed}",
                    {"citation": got.get("citation")})


def check_taxonomy_class(identifier: str, claimed_class: str) -> dict:
    """Catches conflation: calling a CAPEC pattern a CVE, a CWE a technique, etc."""
    syntactic = classify_identifier(identifier)
    got = resolve(identifier)
    actual = got.get("framework") if got["status"] == "RESOLVED" else syntactic
    if actual is None:
        return _verdict(UNVERIFIABLE, f"cannot determine the taxonomy of {identifier}")
    normalized = {
        "CWE": "weakness", "CAPEC": "attack_pattern", "NVD": "vulnerability",
        "CISA_KEV": "vulnerability", "D3FEND": "countermeasure",
        "ATT_CK_Enterprise": "technique", "ATT_CK_Mobile": "technique",
        "ATT_CK_ICS": "technique", "attack": "technique",
    }.get(actual)
    if normalized is None:
        return _verdict(UNVERIFIABLE, f"{identifier} belongs to {actual}, which has no class mapping")
    if normalized == claimed_class:
        return _verdict(VERIFIED, f"{identifier} is a {normalized}", {"framework": actual})
    return _verdict(REFUTED,
                    f"{identifier} is a {normalized} ({actual}), not a {claimed_class}",
                    {"framework": actual})


def check_product_affected(cve: str, claimed_product: str) -> dict:
    got = resolve(cve)
    if got["status"] != "RESOLVED":
        return _verdict(UNVERIFIABLE, f"{cve} is not resolvable locally")
    kev = got.get("kev") or {}
    haystack = " ".join(str(x) for x in
                        (kev.get("vendor_project"), kev.get("product"), got.get("name"),
                         got.get("description"))).lower()
    if claimed_product.lower() in haystack:
        return _verdict(VERIFIED, f"{claimed_product} appears in the authoritative record for {cve}",
                        {"vendor": kev.get("vendor_project"), "product": kev.get("product")})
    return _verdict(REFUTED,
                    f"{cve} is recorded against {kev.get('vendor_project')} {kev.get('product')}, "
                    f"with no mention of {claimed_product}",
                    {"vendor": kev.get("vendor_project"), "product": kev.get("product"),
                     "citation": got.get("citation")})


CHECKS = {
    "identifier_exists": lambda c: check_identifier_exists(c["identifier"]),
    "cwe_mapping": lambda c: check_cwe_mapping(c["cve"], c["claimed_cwes"]),
    "known_exploited": lambda c: check_known_exploited(c["cve"], c["claimed"]),
    "ransomware_linked": lambda c: check_ransomware_linked(c["cve"], c["claimed"]),
    "taxonomy_class": lambda c: check_taxonomy_class(c["identifier"], c["claimed_class"]),
    "product_affected": lambda c: check_product_affected(c["cve"], c["claimed_product"]),
}


def check(claim: dict) -> dict:
    kind = claim.get("type")
    if kind not in CHECKS:
        return {**claim, **_verdict(UNVERIFIABLE, f"no checker for claim type {kind!r}")}
    return {**claim, **CHECKS[kind](claim)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", help="path to a JSON list of claims; omit to read stdin")
    args = parser.parse_args()
    raw = Path(args.claims).read_text() if args.claims else sys.stdin.read()
    claims = json.loads(raw)
    results = [check(c) for c in (claims if isinstance(claims, list) else [claims])]
    print(json.dumps({
        "schema": "sparta.claim_check.v1",
        "checked": len(results),
        "refuted": sum(1 for r in results if r["verdict"] == REFUTED),
        "verified": sum(1 for r in results if r["verdict"] == VERIFIED),
        "unverifiable": sum(1 for r in results if r["verdict"] == UNVERIFIABLE),
        "results": results,
    }, indent=1))


if __name__ == "__main__":
    main()
