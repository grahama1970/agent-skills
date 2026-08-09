#!/usr/bin/env python3
"""Monitor what SPARTA can and cannot answer, against a declared manifest.

A corpus rots in two directions. It goes stale -- the daily KEV refresh handles
that -- and it goes *narrow*: the field moves, new frameworks land, and nobody
notices the corpus silently cannot answer the questions people now ask. Agentic
AI security did not exist as a framework two years ago; today it is among the
most common questions put to a security knowledge base.

This checks each framework in the manifest by resolving representative
identifiers through the live corpus, and reports three outcomes:

  covered      probes resolve; the corpus can answer questions here
  gap          declared absent, still absent -- known and named, not a surprise
  REGRESSION   declared covered but probes no longer resolve

Only a REGRESSION fails the run. A declared gap is not a failure; it is the
monitor doing its job, keeping the absence visible so it stays a decision rather
than a discovery. A gap that closes is reported too, since the manifest then
needs updating.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8601"
COLLECTION = "sparta_controls"
MANIFEST = Path(__file__).parent.parent / "fixtures" / "coverage_manifest.json"


def post(path: str, body: dict):
    req = urllib.request.Request(DAEMON + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))


def resolves(control_id: str) -> bool:
    docs = post("/list", {"collection": COLLECTION, "limit": 1,
                          "filters": {"control_id": control_id}}).get("documents", [])
    return bool(docs)


def framework_present(framework: str) -> bool:
    docs = post("/list", {"collection": COLLECTION, "limit": 1,
                          "filters": {"source_framework": framework}}).get("documents", [])
    return bool(docs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--output")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    rows, regressions, closed_gaps = [], [], []

    for entry in manifest["frameworks"]:
        probes = entry.get("probes") or []
        if probes:
            hits = [p for p in probes if resolves(p)]
            present = len(hits) == len(probes)
            detail = f"{len(hits)}/{len(probes)} probes resolve"
        elif entry.get("framework_field"):
            present = framework_present(entry["framework_field"])
            detail = f"source_framework={entry['framework_field']}"
        else:
            present = False
            detail = "no probes declared; treated as absent until ingested"

        expected = entry.get("expected", "covered")
        status = "covered" if present else "gap"
        if expected == "covered" and not present:
            status = "REGRESSION"
            regressions.append(f"{entry['id']}: {detail}")
        if expected == "gap" and present:
            status = "gap_closed"
            closed_gaps.append(entry["id"])

        rows.append({
            "framework": entry["id"], "why": entry["why"], "expected": expected,
            "status": status, "detail": detail,
            "source": entry.get("source"),
            "ingest_difficulty": entry.get("ingest_difficulty"),
        })

    covered = [r for r in rows if r["status"] == "covered"]
    gaps = [r for r in rows if r["status"] == "gap"]

    report = {
        "schema": "sparta.knowledge_coverage.v1",
        "verdict": "FAIL" if regressions else "PASS",
        "covered": len(covered),
        "gaps": len(gaps),
        "total": len(rows),
        "regressions": regressions,
        "gaps_closed_update_manifest": closed_gaps,
        "named_gaps": [{"framework": r["framework"], "why": r["why"],
                        "source": r["source"], "difficulty": r["ingest_difficulty"]}
                       for r in gaps],
        "rows": rows,
        "claims": {
            "proves": "which declared frameworks the live corpus can answer questions about",
            "does_not_prove": "answer quality, corpus freshness, or that the probe set is representative",
        },
        "mocked": False, "live": True,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=1))

    if args.quiet:
        print(f"COVERAGE: {report['verdict']} {len(covered)}/{len(rows)} covered, {len(gaps)} known gaps")
    else:
        for row in rows:
            mark = {"covered": "ok  ", "gap": "GAP ", "REGRESSION": "FAIL", "gap_closed": "NEW "}[row["status"]]
            print(f"{mark} {row['framework']:42s} {row['detail']}")
        print(f"\nCOVERAGE: {report['verdict']} -- {len(covered)}/{len(rows)} covered, {len(gaps)} known gaps")
        for gap in report["named_gaps"]:
            print(f"  gap: {gap['framework']} ({gap['difficulty']})")
        for regression in regressions:
            print(f"  REGRESSION: {regression}")
        for closed in closed_gaps:
            print(f"  gap closed, update the manifest: {closed}")

    sys.exit(0 if not regressions else 1)


if __name__ == "__main__":
    main()
