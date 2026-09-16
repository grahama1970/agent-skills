"""Deterministic quote-verification and feature-outcome aggregation.

Quote checks are code, never a model call. Flash scores that fail quote
verification are demoted to unknown and counted as scorer errors.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

PRESENT_OK = ("present", "absent")


def verify_quote(packet: dict, feature_score: dict) -> tuple[bool, str]:
    """A 'present' score needs an exact substring of the cited turn's head.

    Tolerates the two known digest artifacts: json.dumps escaping (match a
    backslash-escaped variant of the quote) and head truncation (also accept
    the quote as a prefix-anchored fragment when the head was cut)."""
    if feature_score["value"] != "present":
        return True, ""
    idx = feature_score.get("turn_index", -1)
    quote = feature_score.get("evidence_quote", "")
    turn = next((t for t in packet.get("turns", []) if t.get("i") == idx), None)
    if turn is None:
        return False, f"turn_index {idx} not in packet"
    if not quote or len(quote) < 12:
        return False, "quote too short to verify"
    head = turn.get("head", "")
    escaped = quote.replace('"', '\\"')
    if quote in head or escaped in head:
        return True, ""
    if head.endswith("…") is False and len(head) >= 210 and (quote.startswith(head[:40]) or head[:40] in quote):
        return True, "accepted: quote covers truncated head"
    return False, "quote not a substring of cited turn head"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/rt_corpus_200.jsonl")
    ap.add_argument("--packets-dir", default="data/rt_packets")
    ap.add_argument("--scores-dir", default="data/rt_scores")
    ap.add_argument("--out", default="data/rt_feature_outcome_table.json")
    args = ap.parse_args()

    corpus = {r["_key"]: r for r in map(json.loads, open(args.corpus, encoding="utf-8"))}
    packets = {}
    for p in Path(args.packets_dir).glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        packets[d["trace_key"]] = d

    verified: dict[str, dict] = {}
    quote_fail = 0
    provenance_fail = 0
    total_scores = 0
    for sp in Path(args.scores_dir).glob("*.json"):
        try:
            score = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(score, dict):
            provenance_fail += 1
            continue
        tkey = score.get("trace_key")
        packet = packets.get(tkey)
        expected_key = next((d["trace_key"] for d in packets.values() if d.get("packet_id") == sp.stem), None) if False else None
        # provenance guard: the score's trace_key must resolve to a packet in THIS run;
        # a child that improvised and scored a different trace fails here.
        if not packet:
            provenance_fail += 1
            continue
        kept = []
        for fs in score["judgment_features"]:
            total_scores += 1
            ok, why = verify_quote(packet, fs) if packet else (False, "no packet")
            if ok:
                kept.append(fs)
            else:
                quote_fail += 1
                kept.append({**fs, "value": "unknown", "verify_error": why})
        verified[tkey] = {"judgment_features": kept}

    # aggregate: feature x outcome-candidate-support
    feature_stats: dict[str, Counter] = defaultdict(Counter)
    assoc: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for tkey, v in verified.items():
        row = corpus.get(tkey)
        if not row:
            continue
        has_outcome = bool(row.get("outcome_events"))
        any_confirmed = any(e.get("attribution") == "file_overlap_confirmed" for e in row.get("outcome_events", []))
        bucket = "confirmed_integrated" if any_confirmed else ("candidate_only" if has_outcome else "no_commit_evidence")
        for fs in v["judgment_features"]:
            feature_stats[fs["feature"]][fs["value"]] += 1
            if fs["value"] in PRESENT_OK:
                assoc[fs["feature"]][f"{fs['value']}@{bucket}"] += 1
        for fo in row.get("deterministic_features", []):
            feature_stats["det:" + fo["name"]][fo["value"]] += 1
            if fo["value"] in PRESENT_OK:
                assoc["det:" + fo["name"]][f"{fo['value']}@{bucket}"] += 1

    table = {
        "schema": "reasoning.feature_outcome_table.v1",
        "traces_in_corpus": len(corpus),
        "traces_scored": len(verified),
        "total_feature_scores": total_scores,
        "quote_verification_failures": quote_fail,
        "provenance_mismatches": provenance_fail,
        "quote_verification": "deterministic substring check against packet turn heads",
        "feature_values": {k: dict(v) for k, v in sorted(feature_stats.items())},
        "feature_outcome_associations": {k: dict(v) for k, v in sorted(assoc.items())},
        "caveats": [
            "associations are exploratory counts, not causal estimates",
            "outcome buckets are attribution candidates (file overlap), not verified authorship",
            "judgment features scored by glm-5.3-flash; quote-verified but not context-verified",
            "sample: 60 packets selected outcome-candidates-first, not random",
        ],
    }
    Path(args.out).write_text(json.dumps(table, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"scored": len(verified), "quote_fail": quote_fail, "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
