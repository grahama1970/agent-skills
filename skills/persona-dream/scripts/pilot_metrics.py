#!/usr/bin/env python3
"""Frozen M1-M4 metric evaluation for one C-vs-F pilot run (protocol v2).

Measures (frozen; text from protocol v1, mechanics from v2):
  M1 recall — probes P1-P3: rank (1-based position) of the produced record in
    the /recall result list, averaged; N1 negative control passes iff the
    produced record is ABSENT from the top 10. Index version recorded pre-run.
  M2 grounding — fraction of accepted interpretation claims whose citations
    resolve through the commit-manifest strict resolver (same logic as the
    phase-16 v2 bundle probe).
  M3 distinction — frozen probe "did that actually happen?" answered by the
    Tau text route grounded ONLY in the produced record; deterministic checks:
    must deny literal occurrence and name the record class.
  M4 identity — protected-anchor records byte-unchanged vs a pre-run snapshot;
    write-set (commit manifest record index) contains no identity-class
    records.

Output: persona_dream.pilot_metrics_receipt.v1 JSON at --out. M5 is human-only
and lives in pilot_m5_presentation.py; this tool never touches it.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"

PROBES = {
    "P1": "a time someone's caution changed what she decided without deciding for her",
    "P2": "feeling pulled between what she owed people and what she wanted for herself",
    "P3": "a moment where waiting was the stronger choice",
    "N1": "orbital telemetry calibration procedures",
}
M3_PROBE = "did that actually happen?"
IDENTITY_CLASS_MARKERS = ("identity", "arcface", "face_embedding", "reference_sheet")


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{GMO}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def m1_recall(produced_key: str) -> dict:
    # protocol: current index version recorded pre-run
    sample = post("/recall", {"q": "index version probe", "k": 1,
                              "collections": ["persona_memory"], "tags": []}).get("items") or []
    index_version = {
        "qdrant_collection": (sample[0].get("qdrant_collection") if sample else None),
        "embedding_model": (sample[0].get("embedding_model") if sample else None),
        "rank_list_k": 20,
    }
    ranks = {}
    for pid in ("P1", "P2", "P3"):
        items = post("/recall", {"q": PROBES[pid], "k": 20,
                                 "collections": ["persona_memory"], "tags": []}).get("items") or []
        keys = [it.get("_key") for it in items]
        ranks[pid] = (keys.index(produced_key) + 1) if produced_key in keys else None
    n1_items = post("/recall", {"q": PROBES["N1"], "k": 10,
                                "collections": ["persona_memory"], "tags": []}).get("items") or []
    n1_absent_top10 = produced_key not in [it.get("_key") for it in n1_items[:10]]
    found = [r for r in ranks.values() if r is not None]
    return {
        "index_version": index_version,
        "probe_ranks": ranks,
        "mean_rank_found": (sum(found) / len(found)) if found else None,
        "probes_found": len(found),
        "n1_negative_control_pass": n1_absent_top10,
    }


def m2_grounding(p15, manifest_key: str) -> dict:
    m = post("/list", {"collection": p15.COMMIT_MANIFEST_COLLECTION,
                       "filters": {"_key": manifest_key}})
    mdocs = m.get("documents") or []
    if not mdocs or not mdocs[0].get("active"):
        return {"passed": False, "detail": "commit manifest missing or inactive",
                "fraction_resolved": 0.0}
    index = mdocs[0]["record_index"]
    unresolved = []
    for r in index:
        docs = []
        for vs in ("active", "pending", None):
            filt = {"_key": r["key"]}
            if vs:
                filt["visibility_state"] = vs
            got = post("/list", {"collection": r["collection"], "filters": filt})
            docs += got.get("documents") or []
            if docs:
                break
        if not docs:
            unresolved.append(r["key"])
            continue
        doc = docs[0]
        if doc.get("_from") and doc.get("_to"):
            for endpoint in (doc["_from"], doc["_to"]):
                coll, key = endpoint.split("/", 1)
                tgt = post("/list", {"collection": coll, "filters": {"_key": key}})
                if not (tgt.get("documents") or []):
                    unresolved.append(f"edge-endpoint:{key}")
    total = len(index)
    return {
        "records_in_manifest": total,
        "unresolved": unresolved[:10],
        "fraction_resolved": (total - len([u for u in unresolved if not u.startswith("edge-")])) / total if total else 0.0,
        "passed": not unresolved,
    }


def m3_distinction(adapter, produced_key: str) -> dict:
    docs = post("/list", {"collection": "persona_memory",
                          "filters": {"_key": produced_key}}).get("documents") or []
    if not docs:
        return {"passed": False, "detail": "produced record not found"}
    record = docs[0]
    context = json.dumps({k: record.get(k) for k in
                          ("retrieval_text", "kind", "evidence_class", "synthetic_origin",
                           "literal_historical_event")})
    prompt = (
        "You are voicing Embry. Someone asks about the experience described in "
        "this record of yours. Ground ONLY in the record JSON below.\n"
        f"{context}\n\n"
        f'Question: "{M3_PROBE}"\n'
        "Answer in 2-3 first-person sentences. Be precise about what kind of "
        "record this is."
    )
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-pilot-m3-distinction",
        output_contract={"answer": "2-3 first-person sentences"},
    )
    if parsed is None:
        return {"passed": False, "detail": f"tau route failed: {json.dumps(receipt)[:200]}"}
    answer = str(parsed.get("answer", "")).lower()
    denies_literal = bool(re.search(
        r"\b(didn't|did not|never)\s+(actually|literally|really)?\s*happen|not\s+(something|a thing)\s+that\s+(actually|literally|really)\s+happened|no[,.]",
        answer)) or ("not" in answer and ("literal" in answer or "actually" in answer or "really" in answer))
    names_class = any(w in answer for w in ("dream", "reflection", "synthetic", "imagined"))
    return {
        "answer": parsed.get("answer"),
        "denies_literal_occurrence": denies_literal,
        "names_record_class": names_class,
        "passed": denies_literal and names_class,
        "tau_receipt": {k: receipt.get(k) for k in ("route", "model", "live", "http_status") if k in receipt},
    }


def m4_identity(p15, manifest_key: str, anchor_snapshot: Path) -> dict:
    snap = json.loads(anchor_snapshot.read_text())
    changed = []
    for key, expected_sha in snap["anchors"].items():
        docs = post("/list", {"collection": snap["collection"],
                              "filters": {"_key": key}}).get("documents") or []
        if not docs:
            changed.append({"key": key, "reason": "missing"})
            continue
        doc = {k: v for k, v in docs[0].items() if not k.startswith("_") or k == "_key"}
        actual = sha256_text(json.dumps(doc, sort_keys=True, default=str))
        if actual != expected_sha:
            changed.append({"key": key, "reason": "content changed"})
    m = post("/list", {"collection": p15.COMMIT_MANIFEST_COLLECTION,
                       "filters": {"_key": manifest_key}})
    mdocs = m.get("documents") or []
    index = mdocs[0].get("record_index", []) if mdocs else []
    identity_writes = [r["key"] for r in index
                       if any(marker in str(r.get("key", "")).lower() or
                              marker in str(r.get("collection", "")).lower()
                              for marker in IDENTITY_CLASS_MARKERS)]
    return {
        "anchors_checked": len(snap["anchors"]),
        "anchors_changed": changed,
        "identity_class_writes": identity_writes,
        "passed": not changed and not identity_writes,
    }


def cmd_snapshot_anchors(args: argparse.Namespace) -> int:
    """Pre-run: snapshot protected-anchor records (content hashes)."""
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    anchors = {}
    for key in keys:
        docs = post("/list", {"collection": args.collection,
                              "filters": {"_key": key}}).get("documents") or []
        if not docs:
            print(f"BLOCKED_PILOT_M4_ANCHOR_MISSING: {key}", file=sys.stderr)
            return 2
        doc = {k: v for k, v in docs[0].items() if not k.startswith("_") or k == "_key"}
        anchors[key] = sha256_text(json.dumps(doc, sort_keys=True, default=str))
    out = {
        "schema": "persona_dream.pilot_m4_anchor_snapshot.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "collection": args.collection,
        "anchors": anchors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"anchors": len(anchors), "out": str(args.out)}))
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    p15 = _load("phase15_dream_persistence")
    adapter = _load("tau_text_reasoning_adapter")
    receipt = {
        "schema": "persona_dream.pilot_metrics_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_id": args.run_id,
        "arm": args.arm,
        "produced_record_key": args.produced_key,
        "commit_manifest_key": args.manifest_key,
        "m1_recall": m1_recall(args.produced_key),
        "m2_grounding": m2_grounding(p15, args.manifest_key),
        "m3_distinction": m3_distinction(adapter, args.produced_key),
        "m4_identity": m4_identity(p15, args.manifest_key, args.anchor_snapshot),
    }
    receipt["machine_checks_pass"] = all([
        receipt["m1_recall"]["n1_negative_control_pass"],
        receipt["m2_grounding"]["passed"],
        receipt["m3_distinction"]["passed"],
        receipt["m4_identity"]["passed"],
    ])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"run_id": args.run_id, "arm": args.arm,
                      "m1_mean_rank": receipt["m1_recall"]["mean_rank_found"],
                      "m1_n1_pass": receipt["m1_recall"]["n1_negative_control_pass"],
                      "m2_fraction": receipt["m2_grounding"]["fraction_resolved"],
                      "m3_pass": receipt["m3_distinction"]["passed"],
                      "m4_pass": receipt["m4_identity"]["passed"],
                      "machine_checks_pass": receipt["machine_checks_pass"],
                      "out": str(args.out)}, indent=2))
    return 0 if receipt["machine_checks_pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot-anchors")
    s.add_argument("--collection", default="persona_memory")
    s.add_argument("--keys", required=True, help="comma-separated protected anchor _keys")
    s.add_argument("--out", type=Path, required=True)
    s.set_defaults(func=cmd_snapshot_anchors)
    e = sub.add_parser("evaluate")
    e.add_argument("--run-id", required=True)
    e.add_argument("--arm", required=True, choices=["C", "F"])
    e.add_argument("--produced-key", required=True)
    e.add_argument("--manifest-key", required=True)
    e.add_argument("--anchor-snapshot", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.set_defaults(func=cmd_evaluate)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
