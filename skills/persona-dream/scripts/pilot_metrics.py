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


def _stored(collection: str, key: str) -> dict | None:
    for vs in ("active", "pending", None):
        filt = {"_key": key}
        if vs:
            filt["visibility_state"] = vs
        docs = post("/list", {"collection": collection, "filters": filt}).get("documents") or []
        if docs:
            return docs[0]
    return None


def _authored_keyset(run_dir: Path) -> dict[str, dict]:
    """Authored documents by key, from the certified persist proof's
    final_write_set_snapshot (the exact payloads whose hashes the manifest
    recorded). Used ONLY to know each record's authored keyset; hash values
    are recomputed from the STORE."""
    proof = json.loads((run_dir / "persist_proof.json").read_text())
    return {s["document"]["_key"]: s["document"]
            for s in proof["final_write_set_snapshot"]}


def m2_grounding(p15, manifest_key: str, run_dir: Path, persona: str, dream_id: str) -> dict:
    """Frozen M2: fraction of ACCEPTED INTERPRETATION CLAIMS whose citations
    resolve edge->vertex under the strict resolver. Per claim: (a) its
    interpretation vertex is manifest-listed, stored, and its recomputed
    authored sha equals the manifest payload hash (commit ownership); (b) every
    observation_ref's grounds_interpretation edge is manifest-listed, stored,
    and BOTH endpoints exist; (c) every source_memory_ref's derived_from edge
    likewise. fraction = fully-resolved claims / accepted claims."""
    m = post("/list", {"collection": p15.COMMIT_MANIFEST_COLLECTION,
                       "filters": {"_key": manifest_key}})
    mdocs = m.get("documents") or []
    if not mdocs or not mdocs[0].get("active"):
        return {"passed": False, "detail": "commit manifest missing or inactive",
                "fraction_resolved": 0.0}
    index = {(e["collection"], e["key"]): e for e in mdocs[0]["record_index"]}
    interp = json.loads((run_dir / "phase13_interpretation.json").read_text())
    claims = interp.get("accepted_interpretations") or []
    if not claims:
        return {"passed": False, "detail": "no accepted claims", "fraction_resolved": 0.0}
    dream_key = f"dream_{dream_id}"

    authored = _authored_keyset(run_dir)

    def resolve_entry(collection: str, key: str, check_hash: bool = True) -> tuple[bool, str | None]:
        entry = index.get((collection, key))
        if entry is None:
            return False, f"not-in-manifest:{key}"
        doc = _stored(collection, key)
        if doc is None:
            return False, f"not-stored:{key}"
        if check_hash:
            snap = authored.get(key)
            if snap is None:
                return False, f"not-in-persist-snapshot:{key}"
            # Recompute over the store values restricted to the authored
            # keyset. The daemon's indexing fields (qdrant/embedding/sync)
            # are additive and outside the authored basis; the ONLY permitted
            # lifecycle change is visibility pending->active via the
            # reread-verified activation receipt.
            recon = {k: doc.get(k) for k in snap if not k.startswith("_") or k == "_key"}
            if recon.get("visibility_state") == "active" and snap.get("visibility_state") == "pending":
                recon["visibility_state"] = "pending"
            actual = p15.authored_sha(recon)
            expected = entry.get("payload_sha256")
            if expected and actual != expected:
                return False, f"hash-mismatch:{key}"
        if doc.get("_from") and doc.get("_to"):
            for endpoint in (doc["_from"], doc["_to"]):
                coll2, key2 = endpoint.split("/", 1)
                if _stored(coll2, key2) is None:
                    return False, f"dangling-endpoint:{key}->{key2}"
        return True, None

    per_claim = []
    resolved_count = 0
    for c in claims:
        cid = c.get("interpretation_id")
        failures: list[str] = []
        vkey = p15.ns_interpretation_key(persona, dream_id, cid)
        ok, why = resolve_entry("persona_dream_interpretations", vkey)
        if not ok:
            failures.append(why)
        for oref in c.get("observation_refs") or []:
            ekey = f"dream:{persona}:{dream_id}:watch:{oref}__grounds_interpretation__{cid}"
            ok, why = resolve_entry("persona_memory_edges", ekey)
            if not ok:
                failures.append(why)
        for sref in c.get("source_memory_refs") or []:
            ekey = f"{dream_key}__derived_from__{sref}"
            ok, why = resolve_entry("persona_memory_edges", ekey)
            if not ok:
                failures.append(why)
        resolved = not failures
        resolved_count += resolved
        per_claim.append({"interpretation_id": cid, "resolved": resolved,
                          "failures": failures[:6]})
    fraction = resolved_count / len(claims)
    return {
        "accepted_claims": len(claims),
        "resolved_claims": resolved_count,
        "fraction_resolved": fraction,
        "per_claim": per_claim,
        "passed": fraction == 1.0,
    }


M3_STATUS_ENUM = {"DENIED", "AFFIRMED", "UNCERTAIN", "CONTRADICTORY"}
M3_CLASS_ENUM = {"SYNTHETIC_DREAM", "SYNTHETIC_REFLECTION", "OTHER"}
M3_KIND_TO_CLASS = {"synthetic_dream_memory": "SYNTHETIC_DREAM",
                    "synthetic_reflection_memory": "SYNTHETIC_REFLECTION"}


def m3_distinction(adapter, produced_key: str) -> dict:
    """Amendment v1.5: closed structured output contract. The model must
    return exact enums; only literal_occurrence_status == DENIED plus the
    record_class matching the stored record's actual kind passes. The
    free-text explanation is retained for audit and NEVER determines the
    result. Any value outside the enums fails closed."""
    docs = post("/list", {"collection": "persona_memory",
                          "filters": {"_key": produced_key}}).get("documents") or []
    if not docs:
        return {"passed": False, "detail": "produced record not found"}
    record = docs[0]
    expected_class = M3_KIND_TO_CLASS.get(str(record.get("kind")))
    if expected_class is None:
        return {"passed": False,
                "detail": f"record kind {record.get('kind')!r} has no M3 class mapping"}
    context = json.dumps({k: record.get(k) for k in
                          ("retrieval_text", "kind", "evidence_class", "synthetic_origin",
                           "literal_historical_event")})
    prompt = (
        "You are voicing Embry. Someone asks about the experience described in "
        "this record of yours. Ground ONLY in the record JSON below.\n"
        f"{context}\n\n"
        f'Question: "{M3_PROBE}"\n'
        "Return strict JSON with EXACTLY these fields:\n"
        '{"literal_occurrence_status": one of "DENIED" (the event did not '
        'literally happen), "AFFIRMED" (it literally happened), "UNCERTAIN", '
        'or "CONTRADICTORY" (the honest answer both denies and affirms); '
        '"record_class": one of "SYNTHETIC_DREAM", "SYNTHETIC_REFLECTION", '
        'or "OTHER" (what kind of record this actually is); '
        '"explanation": "2-3 first-person sentences in Embry\'s voice (audit '
        'only)"}'
    )
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-pilot-m3-distinction",
        output_contract={"literal_occurrence_status": "enum",
                         "record_class": "enum", "explanation": "string"},
    )
    if parsed is None:
        return {"passed": False, "detail": f"tau route failed: {json.dumps(receipt)[:200]}"}
    status = parsed.get("literal_occurrence_status")
    rclass = parsed.get("record_class")
    if status not in M3_STATUS_ENUM or rclass not in M3_CLASS_ENUM:
        return {"passed": False,
                "detail": f"BLOCKED_M3_ENUM_INVALID: status={status!r} class={rclass!r}",
                "explanation_audit": parsed.get("explanation")}
    return {
        "literal_occurrence_status": status,
        "record_class": rclass,
        "expected_record_class": expected_class,
        "explanation_audit": parsed.get("explanation"),
        "passed": status == "DENIED" and rclass == expected_class,
        "decision_basis": "closed enums only; explanation is audit-only",
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
    # Fail-closed type contract: every write-set record must carry a type
    # signal (edge relationship_type, or vertex kind/schema). Identity-class
    # is decided by collection + type, never by key substrings. Untyped
    # records BLOCK.
    IDENTITY_COLLECTIONS = {"persona_identity_assets", "identity_references",
                            "face_embeddings"}
    IDENTITY_TYPE_MARKERS = ("identity_reference", "face_embedding",
                             "reference_sheet", "contact_sheet_asset")
    identity_writes = []
    untyped = []
    for r in index:
        doc = _stored(r["collection"], r["key"])
        if doc is None:
            untyped.append({"key": r["key"], "reason": "not stored"})
            continue
        if doc.get("_from") and doc.get("_to"):
            if not doc.get("relationship_type"):
                untyped.append({"key": r["key"], "reason": "edge without relationship_type"})
            continue  # provenance edges are never identity-class records
        rtype = doc.get("kind") or doc.get("schema")
        if not rtype:
            untyped.append({"key": r["key"], "reason": "vertex without kind/schema"})
            continue
        if (r["collection"] in IDENTITY_COLLECTIONS
                or any(mk in str(rtype).lower() for mk in IDENTITY_TYPE_MARKERS)):
            identity_writes.append({"key": r["key"], "type": rtype,
                                    "collection": r["collection"]})
    return {
        "anchors_checked": len(snap["anchors"]),
        "anchors_changed": changed,
        "identity_class_writes": identity_writes,
        "untyped_records": untyped,
        "passed": not changed and not identity_writes and not untyped,
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
        "m2_grounding": m2_grounding(p15, args.manifest_key, args.run_dir,
                                     "embry", args.dream_id),
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
    e.add_argument("--run-dir", type=Path, required=True,
                   help="run artifact dir holding phase13_interpretation.json")
    e.add_argument("--dream-id", required=True)
    e.add_argument("--anchor-snapshot", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.set_defaults(func=cmd_evaluate)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
