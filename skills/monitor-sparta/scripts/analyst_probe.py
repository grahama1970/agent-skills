#!/usr/bin/env python3
"""Non-expert analyst probe over the SPARTA knowledge corpus.

Answers security-identifier questions from the graph WITHOUT requiring the
operator to hold cybersecurity minutia. The contract that makes it usable by a
non-specialist is that it never confabulates and never overstates what a miss
means:

  RESOLVED            the identifier is in the corpus; the grounded record is returned
  NOT_IN_CORPUS       the identifier is absent from a corpus dense enough for that
                      absence to be meaningful evidence
  UNVERIFIED_LOCALLY  the identifier is absent from a corpus too sparse to support
                      any conclusion -- explicitly NOT evidence of fabrication

The third state is the load-bearing one. CVE space is enormous -- ~250k
published -- and the local slice holds only a few thousand, so a miss there
establishes nothing about whether a CVE is real.

Two sub-corpora behave differently and the probe distinguishes them:

  CISA_KEV  complete as of the backfilled catalog. Presence answers a stronger
            question than "does this exist": CISA observed it exploited in the
            wild. Ransomware linkage and CWE mapping ride along.
  NVD       a sparse recent-CVE feed. Absence is not evidence of anything.

So "not in KEV" is a meaningful negative -- this is not a known-exploited
vulnerability -- while "not in the corpus at all" remains an honest shrug.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

DAEMON = "http://127.0.0.1:8601"
COLLECTION = "sparta_controls"

# Corpus density posture per framework. AUTHORITATIVE means the local slice is
# near-complete for that taxonomy, so a miss is real evidence. SPARSE means the
# slice is a sample and a miss establishes nothing.
POSTURE = {
    "CISA_KEV": "authoritative",
    "MITRE_ATLAS": "authoritative",
    "CWE": "authoritative",
    "CAPEC": "authoritative",
    "ATT_CK_Enterprise": "authoritative",
    "ATT_CK_Mobile": "authoritative",
    "ATT_CK_ICS": "authoritative",
    "attack": "authoritative",
    "D3FEND": "authoritative",
    "NIST": "authoritative",
    "SPARTA": "authoritative",
    "EMB3D": "authoritative",
    "NVD": "sparse",
}

# Which framework an identifier claims to belong to, from its own syntax.
ID_PATTERNS = [
    (re.compile(r"^CWE-\d+$", re.I), "CWE"),
    (re.compile(r"^CAPEC-\d+$", re.I), "CAPEC"),
    (re.compile(r"^CVE-\d{4}-\d+$", re.I), "NVD"),
    (re.compile(r"^T\d{4}(\.\d{3})?$", re.I), "ATT_CK_Enterprise"),
    (re.compile(r"^D3-[A-Z]+$", re.I), "D3FEND"),
    (re.compile(r"^AML\.(T|M)\d{4}(\.\d{3})?$", re.I), "MITRE_ATLAS"),
]

UNVERIFIED_NOTE = (
    "Absent from the local slice, which is a sample rather than a complete "
    "index. This is NOT evidence the identifier is fabricated. Verify against "
    "the authoritative upstream source before making any claim about it."
)


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        DAEMON + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req, timeout=60))


def classify_identifier(identifier: str) -> str | None:
    for pattern, framework in ID_PATTERNS:
        if pattern.match(identifier.strip()):
            return framework
    return None


def resolve(identifier: str) -> dict:
    identifier = identifier.strip()
    claimed = classify_identifier(identifier)
    docs = post("/list", {"collection": COLLECTION, "limit": 1,
                          "filters": {"control_id": identifier}}).get("documents", [])
    if docs:
        doc = docs[0]
        answer = {
            "schema": "sparta.analyst_probe.v1",
            "identifier": identifier,
            "status": "RESOLVED",
            "framework": doc.get("source_framework"),
            "name": doc.get("name"),
            "description": doc.get("description"),
            "grounded": True,
            "citation": f"{COLLECTION}/{doc.get('_key')}",
        }
        # KEV membership is a stronger claim than mere presence: CISA observed
        # this exploited in the wild. Surface it, plus ransomware linkage and the
        # CWE mapping, since that is what threat analysis actually turns on.
        kev = doc.get("kev")
        if isinstance(kev, dict):
            answer["known_exploited"] = True
            answer["kev"] = {
                "date_added": kev.get("date_added"),
                "vendor_project": kev.get("vendor_project"),
                "product": kev.get("product"),
                "known_ransomware_campaign_use": kev.get("known_ransomware_campaign_use"),
                "cwes": kev.get("cwes"),
                "required_action": kev.get("required_action"),
            }
        return answer

    # A miss means different things depending on how dense the local slice is.
    posture = POSTURE.get(claimed or "", "sparse")
    if claimed is None:
        return {
            "schema": "sparta.analyst_probe.v1",
            "identifier": identifier,
            "status": "UNVERIFIED_LOCALLY",
            "framework": None,
            "grounded": False,
            "reason": "identifier does not match any known taxonomy syntax",
            "note": UNVERIFIED_NOTE,
        }
    if posture == "sparse":
        return {
            "schema": "sparta.analyst_probe.v1",
            "identifier": identifier,
            "status": "UNVERIFIED_LOCALLY",
            "framework": claimed,
            "grounded": False,
            "reason": f"{claimed} slice is sparse; absence is not evidence",
            "note": UNVERIFIED_NOTE,
        }
    return {
        "schema": "sparta.analyst_probe.v1",
        "identifier": identifier,
        "status": "NOT_IN_CORPUS",
        "framework": claimed,
        "grounded": False,
        "reason": f"{claimed} slice is near-complete locally and has no such entry",
        "note": (
            "Absence from a near-complete taxonomy slice is meaningful evidence "
            "that the identifier is invalid, but confirm upstream before "
            "asserting it publicly."
        ),
    }


def search(text: str, limit: int = 5, framework: str | None = None) -> dict:
    """Find candidate records by description text. Returns candidates only --
    ranking is lexical, so the caller must read the records, not trust order."""
    filters = {"source_framework": framework} if framework else {}
    body = {"collection": COLLECTION, "limit": 500, "filters": filters}
    terms = [t for t in re.split(r"\W+", text.lower()) if len(t) > 3]
    hits, offset = [], 0
    while offset < 13000:
        body["offset"] = offset
        docs = post("/list", body).get("documents", [])
        if not docs:
            break
        for doc in docs:
            haystack = f"{doc.get('name') or ''} {doc.get('description') or ''}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                hits.append((score, doc))
        offset += 500
    hits.sort(key=lambda pair: -pair[0])
    return {
        "schema": "sparta.analyst_probe.v1",
        "query": text,
        "status": "CANDIDATES" if hits else "NO_CANDIDATES",
        "match_basis": "lexical_term_overlap",
        "candidates": [
            {
                "control_id": doc.get("control_id"),
                "framework": doc.get("source_framework"),
                "name": doc.get("name"),
                "terms_matched": score,
                "citation": f"{COLLECTION}/{doc.get('_key')}",
            }
            for score, doc in hits[:limit]
        ],
        "caveat": (
            "Lexical overlap ranks these; it does not establish that the top "
            "candidate is the correct answer. Read the records."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    resolve_cmd = sub.add_parser("resolve", help="look up one security identifier")
    resolve_cmd.add_argument("identifier")
    search_cmd = sub.add_parser("search", help="find records by description text")
    search_cmd.add_argument("text")
    search_cmd.add_argument("--limit", type=int, default=5)
    search_cmd.add_argument("--framework")
    args = parser.parse_args()

    if args.command == "resolve":
        result = resolve(args.identifier)
    else:
        result = search(args.text, args.limit, args.framework)
    print(json.dumps(result, indent=1))
    sys.exit(0)


if __name__ == "__main__":
    main()
