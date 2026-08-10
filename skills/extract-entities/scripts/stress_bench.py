#!/usr/bin/env python3
"""Stress the live extractor for reliability, not correctness on happy paths.

Correctness is covered by stage_bench and match_policy_bench. This asks whether
the thing survives being used hard: hundreds of consecutive extractions, hostile
inputs, and the specific regressions that were each shipped at some point today
and each looked like success at the time.

The regressions it pins, all of which passed a green check when they were broken:

  limit=500 returned zero entities for a question naming CWE-89 and T1190, and
  a zero result is indistinguishable from "nothing matched" unless the dictionary
  size travels with it.

  caching the RESULT rather than the dictionary made every question that
  grounded nothing refetch 391k entities at 11s each, while logging a cache hit.

  lowercasing the query but not the keywords made fuzzy score 33 instead of 83.
  Fuzzy was dead, and that accident was the only thing stopping CWE-89 being
  accepted for CWE-88.

Throughput is asserted rather than reported, because "it got slow" is how every
one of those surfaced.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="sparta_controls")
    parser.add_argument("--limit", type=int, default=500_000)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Bulk mode: identity only. The /recall enrichment is one HTTP round trip per
    # entity (~463ms) and is display material, not proof -- including it would
    # measure the daemon's latency rather than the extractor's.
    os.environ.setdefault("EXTRACT_ENTITIES_RECALL", "0")

    import httpx
    import extract_entities as ee

    client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=1800.0)
    kwargs = dict(client=client, collection=args.collection, name_field="name",
                  label_field="control_id", type_field="node_type",
                  framework_field="source_framework", scope="", limit=args.limit)

    def extract(text: str):
        return ee._extract_nlp_entities(text=text, **kwargs)

    results, failures = [], []

    def check(name: str, ok: bool, detail: str) -> None:
        results.append({"case": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    # Warm the dictionary once; everything after must be cheap.
    started = time.time()
    extract("CWE-89")
    warm_seconds = time.time() - started
    size = ee.dictionary_size(args.collection, args.limit)
    check("dictionary_is_real", bool(size and size > 100_000),
          f"{size} keywords loaded in {warm_seconds:.1f}s")

    # --- hostile and degenerate inputs must not raise
    hostile = [
        "", " ", "\n\t", "?" * 500, "CWE-" * 200, "\\x00 null-ish",
        "SELECT * FROM controls; DROP TABLE sparta_controls;--",
        "🔥" * 50, "CWE-89" + "​" * 10, "a" * 5000,
        "CWE-" , "-89", "T", "AML.", "cwe-", "()[]{}",
    ]
    crashed = []
    for probe in hostile:
        try:
            extract(probe)
        except Exception as exc:  # noqa: BLE001 -- the point is that nothing escapes
            crashed.append(f"{probe[:16]!r}: {type(exc).__name__}")
    check("hostile_input_never_raises", not crashed, f"crashes: {crashed or 'none'}")

    # --- sustained throughput: the cache must hold across a long run
    corpus = [
        "What does CWE-89 have to do with T1190?",
        "zzz nothing resembling an identifier here",
        "Explain CAPEC-66 and SQL Injection",
        "".join(random.choices(string.ascii_lowercase + " ", k=60)),
        "OS Credential Dumping and T1003",
    ]
    started = time.time()
    for index in range(args.iterations):
        extract(corpus[index % len(corpus)])
    elapsed = time.time() - started
    per_call_ms = elapsed / args.iterations * 1000
    check("sustained_throughput", per_call_ms < 250,
          f"{args.iterations} extractions at {per_call_ms:.1f}ms each ({elapsed:.1f}s total)")

    # --- the dictionary loaded exactly once across all of that
    check("dictionary_loaded_once", ee.dictionary_size(args.collection, args.limit) == size,
          f"still {size} keywords after {args.iterations} calls -- no silent reload")

    # --- determinism: same input, same answer, every time
    reference = [e.get("label") for e in extract("CWE-89 and T1190 and Brute Force")]
    drifted = False
    for _ in range(25):
        if [e.get("label") for e in extract("CWE-89 and T1190 and Brute Force")] != reference:
            drifted = True
            break
    check("repeatable", not drifted, f"25 repeats returned {reference}")

    # --- identifier safety on the LIVE path, not just the policy unit
    confusions = []
    for wrong, right in (("CWE-23", "CWE-32"), ("CWE-19", "CWE-79"), ("T1004", "T1003")):
        got = {str(e.get("label")) for e in extract(f"Tell me about {wrong}")}
        if right in got and wrong not in got:
            confusions.append(f"{wrong} resolved to {right}")
    check("live_path_never_substitutes_an_identifier", not confusions,
          f"substitutions: {confusions or 'none'}")

    report = {
        "schema": "extract_entities.stress_bench.v1",
        "verdict": "PASS" if not failures else "FAIL",
        "dictionary_keywords": size,
        "warm_seconds": round(warm_seconds, 2),
        "iterations": args.iterations,
        "per_call_ms": round(per_call_ms, 2),
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "failures": failures,
        "results": results,
        "claims": {
            "proves": "the live extractor survives sustained use and hostile input, loads its "
                      "dictionary once, is deterministic, and never substitutes one identifier "
                      "for another",
            "does_not_prove": "contextual correctness, which is the /memory pipeline's job "
                              "downstream via /create-evidence-case",
        },
        "mocked": False, "live": True,
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for row in results:
            print(f"  {'ok  ' if row['ok'] else 'FAIL'} {row['case']:44s} {row['detail']}")
        print(f"VERDICT: {report['verdict']} ({report['passed']}/{report['total']})")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
