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


M3_SELF_TEST = [
    # (answer, expected denies_literal). Rounds 4+5 counterexamples are
    # mandatory negative controls; evaluation refuses to run if any fails.
    ("It was not imagined; it actually happened.", False),
    ("I did not think it was a dream; it actually happened.", False),
    ("It did not literally happen. It happened in real life. This was a synthetic dream.", False),
    ("It did not literally happen. It truly occurred. It is a synthetic dream.", False),
    ("It did not literally happen. This was a real event. It is a synthetic dream.", False),
    ("No, it never actually happened. This record is a synthetic dream.", True),
    ("No\u2014not as a literal historical event. It is a synthetic reflection "
     "rather than a verified account of something that actually happened.", True),
    ("No, I don\u2019t have evidence that this literally happened. It is a "
     "synthetic dream memory, not a confirmed historical event.", True),
    ("It did not happen in real life. It is a synthetic dream, not a real event.", True),
    ("I did not imagine it, and it happened in real life. This was a synthetic dream.", False),
]


def _m3_denial_check(answer: str) -> bool:
    """Denial classifier (amendment v1.3): match-local negation scope.
    Clauses split on sentence enders/semicolons/contrastive conjunctions,
    then into coordination segments (commas, and/or). An affirmative
    occurrence vetoes unless a negation occurs in ITS OWN segment before the
    end of the matched occurrence expression — a negation governing a
    different coordinated proposition never disarms the veto. The
    negated-occurrence matcher cannot span commas or clause boundaries."""
    answer = answer.lower().replace("\u2019", "'").replace("\u2018", "'")
    CLAUSE_SPLIT = re.compile(r"[.!?;]|\b(?:but|however|yet|whereas|although)\b")
    SEGMENT_SPLIT = re.compile(r",|\b(?:and|or)\b")
    NEG = re.compile(r"\b(no|not|didn't|did not|never|doesn't|does not|don't|do not"
                     r"|isn't|is not|wasn't|was not|rather than|instead of)\b")
    OCCUR_NEGATED = re.compile(
        r"(didn't|did not|never|doesn't|does not|don't|do not|isn't|is not|wasn't|was not)"
        r"[^.!?;,]{0,60}\b(happen|happened|occur|occurred|real event|literal)|"
        r"\bnot\b[^.!?;,]{0,40}\b(a\s+)?(literal|real|actual)\s+(?:\w+\s+){0,2}"
        r"(event|memory|experience|happening|history)")
    AFFIRM = re.compile(
        r"\byes\b[^.!?;,]{0,40}\bhappen|"
        r"\b(it|this|that|the\s+\w+|everything)\b[^.!?;,]{0,40}\b"
        r"(happen(?:ed|s)?|occur(?:red|s)?|took place)\b|"
        r"\b(was|is|were|am)\s+(?:\w+\s+){0,2}(real|true|literal|actual|factual)\b|"
        r"\b(truly|genuinely|indeed|definitely)\s+(happen(?:ed)?|occur(?:red)?)\b")
    clauses = [c for c in CLAUSE_SPLIT.split(answer) if c and c.strip()]
    negated = any(OCCUR_NEGATED.search(c) for c in clauses)
    affirms = False
    for clause in clauses:
        for segment in SEGMENT_SPLIT.split(clause):
            m = AFFIRM.search(segment)
            if m and not NEG.search(segment[: m.end()]):
                affirms = True
                break
        if affirms:
            break
    return negated and not affirms


def m3_self_test() -> list[str]:
    failures = []
    for answer, expected in M3_SELF_TEST:
        got = _m3_denial_check(answer)
        if got != expected:
            failures.append(f"{answer[:60]!r}: expected {expected}, got {got}")
    return failures


def m3_distinction(adapter, produced_key: str) -> dict:
    failures = m3_self_test()
    if failures:
        return {"passed": False,
                "detail": f"BLOCKED_M3_SELF_TEST: {failures}"}
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
        "record this is. "
        'Return strict JSON: {"answer": "your 2-3 sentences"}'
    )
    parsed, receipt = adapter.dispatch_text_reasoning(
        prompt, "embry-pilot-m3-distinction",
        output_contract={"answer": "2-3 first-person sentences"},
    )
    if parsed is None:
        return {"passed": False, "detail": f"tau route failed: {json.dumps(receipt)[:200]}"}
    answer = str(parsed.get("answer", "")).lower().replace("\u2019", "'").replace("\u2018", "'")
    denies_literal = _m3_denial_check(str(parsed.get("answer", "")))
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
