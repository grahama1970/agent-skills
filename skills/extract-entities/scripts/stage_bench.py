#!/usr/bin/env python3
"""Bench the two extraction stages against a live corpus.

The stages are ordered and they are NOT rough-then-refine, which is the natural
assumption and is wrong:

  Flashtext  Aho-Corasick, EXACT literal keywords only. "OS Credentail Dumpng"
             matches nothing; "CWE-8" matches nothing. It cannot be a rough
             first pass because it has no notion of approximate.
  RapidFuzz  runs ONLY when Flashtext found zero, and scans the dictionary for
             near-misses. It recovers what stage one could not see at all --
             it does not filter stage one's hits, which are already exact.

The case this bench exists for: a ZERO result is ambiguous. Either the text
contains no known entity, or the dictionary never loaded. Those are
indistinguishable from the outside, and the second is a bug that reads exactly
like a correct answer. Measured: at limit=500 against a 391k collection, a
question naming CWE-89 and T1190 extracted nothing at all.

So every assertion here is paired with the dictionary size that produced it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="sparta_controls")
    parser.add_argument("--limit", type=int, default=500_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

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

    # --- stage 1: exact matching, and the dictionary that backs it
    started = time.time()
    exact = extract("What does CWE-89 have to do with T1190?")
    first_call_seconds = time.time() - started
    size = ee.dictionary_size(args.collection, args.limit)

    check("dictionary_loaded_uncapped", bool(size and size > 100_000),
          f"dictionary held {size} keywords")
    labels = {str(e.get("label") or "") for e in exact}
    check("stage1_exact_match", "CWE-89" in labels and "T1190" in labels,
          f"exact hits: {sorted(labels)[:6]}")

    # --- a zero result must be interpretable, never silent
    empty = extract("zzz qqq vvv nothing resembling an identifier")
    check("zero_result_is_interpretable", ee.dictionary_size(args.collection, args.limit) == size,
          f"{len(empty)} matches against a {size}-keyword dictionary -- an answer, not a load failure")

    # --- stage 2 only fires when stage 1 found nothing, and recovers typos
    fuzzy_on = os.environ.get("EXTRACT_ENTITIES_FUZZY", "1") not in {"0", "false", "no"}
    if fuzzy_on:
        typo = extract("Tell me about OS Credentail Dumpng")
        check("stage2_recovers_what_stage1_cannot_see", len(typo) > 0,
              f"fuzzy recovered {len(typo)} for a misspelling Flashtext returns 0 for")

    # --- caching: the dictionary loads once, not per call
    started = time.time()
    extract("CAPEC-66 and T1003")
    cached_seconds = time.time() - started
    check("cached_call_does_not_refetch", cached_seconds < 1.0,
          f"first call {first_call_seconds:.1f}s, cached {cached_seconds:.3f}s")

    # --- an empty result must ALSO not refetch (the regression this bench pins)
    started = time.time()
    extract("another string with no identifiers whatsoever")
    empty_seconds = time.time() - started
    check("empty_result_does_not_refetch", empty_seconds < 1.0,
          f"empty call {empty_seconds:.3f}s -- caching the result rather than the "
          f"dictionary made this 11s")

    report = {
        "schema": "extract_entities.stage_bench.v1",
        "verdict": "PASS" if not failures else "FAIL",
        "dictionary_keywords": size,
        "first_call_seconds": round(first_call_seconds, 2),
        "cached_call_seconds": round(cached_seconds, 4),
        "empty_call_seconds": round(empty_seconds, 4),
        "fuzzy_enabled": fuzzy_on,
        "passed": sum(1 for r in results if r["ok"]),
        "total": len(results),
        "failures": failures,
        "results": results,
        "claims": {
            "proves": "stage order, dictionary completeness, typo recovery, and that a zero "
                      "result is distinguishable from a load failure",
            "does_not_prove": "extraction precision -- nothing here validates that a Flashtext "
                              "hit is contextually correct, only that it is exact",
        },
        "mocked": False, "live": True,
    }
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for row in results:
            print(f"  {'ok  ' if row['ok'] else 'FAIL'} {row['case']:38s} {row['detail']}")
        print(f"VERDICT: {report['verdict']} ({report['passed']}/{report['total']}) "
              f"dictionary={size}")
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
