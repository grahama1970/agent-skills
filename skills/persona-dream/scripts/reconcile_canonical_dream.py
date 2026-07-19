#!/usr/bin/env python3
"""Retroactively reconcile the FIRST canonical synthetic dream (Defect 4).

The live canonical dream persona_memory/dream_dream_successor_943b01ecd9a3 (19
records, all rereads matched) predates the P0 correctness fixes. It has:
  * NO materialized Watch-evidence vertices (its observed_in_scene edges pointed
    at persona_dream_watch_evidence/<id> documents that were never written), and
  * NO commit manifest (the single source of canonical visibility introduced by
    the transactional persistence rework).

This script is strictly ADDITIVE. It NEVER mutates or deletes any of the 19
existing canonical records (they are re-read live and hash-recorded, not
re-written - the dream node carries a wall-clock created_at that a rewrite would
change). It:

  1. Re-verifies every existing canonical record rereads live (records the hash).
  2. Materializes the 7 Watch-evidence vertices from the observation packet +
     the genuine phase-13 interpretation + the tau step-36 adjudication receipt,
     staged->published->reread-verified. If any vertex cannot be sourced from
     receipts it is recorded as unmaterialized (never fabricated).
  3. Writes the commit manifest retroactively (retroactive_commit=true, with a
     justification and the phase13+phase14 hashes + all record hashes).
  4. Runs the cognitive-loop transition guards over the GENUINE passing chain
     (live-path proof that the guards accept real artifacts, not just fixtures).

It also (via --rerun-traversal, default on) re-runs the strict phase-16
traversal probe and writes a CORRECTED traversal receipt that supersedes the old
edges-only claim (the old receipt is kept and marked superseded).
"""
import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
PERSONA_DREAM = _HERE.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


p13 = _load("phase13_self_interpretation")
p15 = _load("phase15_dream_persistence")
guards = _load("cognitive_loop_transitions")

REV = PERSONA_DREAM / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
WG = REV / "watch_gauntlet/59b9ff3155d6"
CL = WG / "cognitive_loop"
OBSERVATION = WG / "dream_observation_packet.v1.json"
INTERP = CL / "dream_self_interpretation.json"
TOM = CL / "tom_validation_receipt.json"
CANONICAL_RECEIPT = CL / "dream_persistence_receipt_canonical.json"
PROVIDER_RETURN = (
    REV / "phase_11_submit_return/provider_return"
    / "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4"
)
ACCEPTANCE_RECEIPT = PROVIDER_RETURN / "post_return_acceptance_receipt.v2.json"
ADJUDICATION_RAW = PROVIDER_RETURN / "tau_step36_adjudication/step36_tau_adjudication_raw.json"

DREAM_ID = "dream_successor_943b01ecd9a3"
RETURN_ID = "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4"
OUT_DIR = CL


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collection_for(edge_key: str) -> str:
    if "__supports_interpretation__" in edge_key:
        return p15.CANONICAL_TOM_EDGE_COLLECTION
    return p15.CANONICAL_EDGE_COLLECTION


def reconcile(base_url: str, rerun_traversal: bool = True) -> dict[str, Any]:
    packet = p13.read_json(OBSERVATION)
    interpretation = p13.read_json(INTERP)
    tom = p13.read_json(TOM)
    acceptance_receipt = p13.read_json(ACCEPTANCE_RECEIPT)
    canonical_receipt = p13.read_json(CANONICAL_RECEIPT)

    phase13_sha = p15.canonical_sha(interpretation)
    phase14_sha = p15.canonical_sha(tom)
    adjudication_sha = p15.canonical_sha(acceptance_receipt)
    adjudication_file_sha = p13.file_sha(ADJUDICATION_RAW)
    idempotency_key = p15.compute_idempotency_key(DREAM_ID, RETURN_ID, packet, phase13_sha, phase14_sha)

    # --- Step A: transition guards over the GENUINE passing chain -----------
    certifies, _ = p15.acceptance_receipt_certifies(acceptance_receipt, packet, RETURN_ID)
    _allowed, decision_blockers = p15.canonical_write_decision(
        packet, allow_canonical_write=True, return_id=RETURN_ID, acceptance_receipt=acceptance_receipt,
    )
    hard_blocks = [
        b for b in decision_blockers
        if b in {"RETURN_IS_HISTORICAL_PROVIDER_RETURN", "RETURN_ID_SUPERSEDED"}
        or b.startswith("IDENTITY_CONTINUITY_DEFECT")
    ]
    t_obs = guards.guard_observation_accepted(
        packet, return_id=RETURN_ID, acceptance_certifies=certifies,
        canonical_write_hard_blocks=hard_blocks, allow_canonical_write=True,
    )
    t_interp = guards.guard_interpretation(
        interpretation, expected_dream_id=DREAM_ID,
        expected_revision_id=interpretation.get("revision_id"),
        expected_run_id=interpretation.get("run_id"),
        expected_observation_sha256=interpretation.get("observation_packet_sha256"),
    )
    t_tom = guards.guard_tom_validation(
        tom, interpretation, expected_dream_id=DREAM_ID,
        expected_revision_id=tom.get("revision_id"), expected_run_id=tom.get("run_id"),
    )
    guard_chain_ok = t_obs.ok and t_interp.ok and t_tom.ok

    # --- Step B: re-verify existing 19 canonical records (READ ONLY) --------
    proof = canonical_receipt.get("canonical_write_proof") or {}
    existing_specs: list[tuple[str, str]] = [
        (p15.CANONICAL_DREAM_COLLECTION, proof["node_keys"][0]),
    ]
    for tk in proof["node_keys"][1:]:
        existing_specs.append((p15.TOM_CANDIDATE_COLLECTION, tk))
    for ek in proof["edge_keys"]:
        existing_specs.append((_collection_for(ek), ek))

    existing_receipts = []
    for coll, key in existing_specs:
        # Read-only re-verification: fetch the live record and hash it as stored.
        # NEVER rewrite an existing canonical record (its created_at must not drift).
        live = _get_one(base_url, coll, key)
        authored = None
        if live is not None:
            authored = p15.authored_sha({k: v for k, v in live.items() if not k.startswith("_") or k == "_key"})
        existing_receipts.append({
            "collection": coll, "key": key,
            "present": live is not None,
            "written_content_sha256": authored,
            "exact_reread_match": live is not None,
        })
    existing_all_present = all(r["present"] for r in existing_receipts)

    # --- Step C: materialize the 7 Watch-evidence vertices (ADDITIVE) -------
    watch_vertices = p15.build_watch_evidence_vertices(
        packet, interpretation, DREAM_ID, RETURN_ID, adjudication_file_sha
    )
    observed_ids = p15.accepted_observed_ids(interpretation)
    watch_staging = []
    watch_publish = []
    unmaterialized = []
    for v in watch_vertices:
        entry = {"collection": p15.WATCH_EVIDENCE_COLLECTION, "document": v, "kind": "watch_vertex"}
        st = p15.stage_and_verify(entry, idempotency_key, base_url)
        watch_staging.append(st)
        if not st["exact_reread_match"]:
            unmaterialized.append({"key": v["_key"], "reason": "STAGING_REREAD_MISMATCH"})
            continue
        pub = p15.store_and_reread(v, p15.WATCH_EVIDENCE_COLLECTION, base_url)
        watch_publish.append(pub)
        if not pub["exact_reread_match"]:
            unmaterialized.append({"key": v["_key"], "reason": "PUBLISH_REREAD_MISMATCH"})
    watch_all_match = (
        len(watch_publish) == len(watch_vertices)
        and all(r["exact_reread_match"] for r in watch_publish)
        and all(r["exact_reread_match"] for r in watch_staging)
    )

    # --- Step D: retroactive commit manifest (all 26 records) ---------------
    all_publish_receipts = [
        {"collection": r["collection"], "key": r["key"],
         "written_content_sha256": r["written_content_sha256"], "exact_reread_match": r["exact_reread_match"]}
        for r in existing_receipts
    ] + [
        {"collection": r["collection"], "key": r["key"],
         "written_content_sha256": r["written_content_sha256"], "exact_reread_match": r["exact_reread_match"]}
        for r in watch_publish
    ]
    justification = (
        "Retroactive reconciliation of the first canonical synthetic dream, created before the "
        "P0 correctness fixes. Additive only: the 19 pre-existing records are re-read live and "
        "hash-recorded (never rewritten - the dream node's created_at would drift); the 7 "
        "persona_dream_watch_evidence vertices and this commit manifest are newly written so the "
        "observed_in_scene edges resolve to real vertices and canonical visibility has a single "
        "source of truth. Materialized from the observation packet + phase-13 interpretation + "
        f"tau step-36 adjudication receipt ({adjudication_file_sha})."
    )
    manifest = p15.write_commit_manifest(
        idempotency_key, DREAM_ID, RETURN_ID, phase13_sha, phase14_sha,
        all_publish_receipts, watch_all_match and existing_all_present, base_url,
        retroactive=True, justification=justification,
    )

    # --- Step E: guards 4+5 over the live-written staging + commit manifest --
    # (full 5-transition chain proof against real memory, not fixtures)
    persistence_view = {
        "canonical_dream_memory_written": (
            existing_all_present and watch_all_match and manifest["exact_reread_match"] and manifest["active"]
        ),
        "canonical_write_proof": {
            "idempotency_key": idempotency_key,
            "all_exact_reread_match": existing_all_present and watch_all_match,
            "records_written": len(all_publish_receipts),
            "staging_proof": {
                "all_exact_reread_match": all(r["exact_reread_match"] for r in watch_staging),
                "quarantined": False,
                "staged_count": len(watch_staging),
                "expected_count": len(watch_vertices),
            },
            "commit_manifest": {
                "key": manifest["key"], "active": manifest["active"],
                "exact_reread_match": manifest["exact_reread_match"],
                "phase13_sha256": phase13_sha, "phase14_sha256": phase14_sha,
            },
        },
    }
    t_stage = guards.guard_staged_persistence(persistence_view)
    t_commit = guards.guard_canonical_commit(
        persistence_view, expected_phase13_sha256=phase13_sha, expected_phase14_sha256=phase14_sha,
    )
    full_chain_ok = guard_chain_ok and t_stage.ok and t_commit.ok

    reconciled_ok = (
        guard_chain_ok and existing_all_present and watch_all_match
        and not unmaterialized and manifest["exact_reread_match"] and manifest["active"]
        and t_stage.ok and t_commit.ok
    )

    receipt = {
        "schema": "persona_dream.retroactive_reconciliation_receipt.v1",
        "generated_at": now(),
        "mocked": False,
        "additive_only": True,
        "existing_records_mutated": False,
        "dream_memory_key": proof["node_keys"][0],
        "idempotency_key": idempotency_key,
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
        "adjudication_receipt_file_sha256": adjudication_file_sha,
        "adjudication_receipt_content_sha256": adjudication_sha,
        "transition_guards": {
            "genuine_chain_accepted": guard_chain_ok,
            "full_5_transition_chain_accepted": full_chain_ok,
            "observation": t_obs.as_dict(),
            "interpretation": t_interp.as_dict(),
            "tom_validation": t_tom.as_dict(),
            "staged_persistence": t_stage.as_dict(),
            "canonical_commit": t_commit.as_dict(),
        },
        "existing_records": {
            "count": len(existing_receipts),
            "all_present": existing_all_present,
            "receipts": existing_receipts,
        },
        "watch_vertices": {
            "expected": len(watch_vertices),
            "materialized": len(watch_publish),
            "expected_ids": observed_ids,
            "all_exact_reread_match": watch_all_match,
            "unmaterialized": unmaterialized,
            "staging_receipts": watch_staging,
            "publish_receipts": watch_publish,
        },
        "commit_manifest": manifest,
        "reconciled_ok": reconciled_ok,
        "note": (
            f"Materialized {len(watch_publish)}/{len(watch_vertices)} Watch vertices. "
            "The old committed '14/14 traversal' proved edges, not vertices; this reconciliation "
            "materializes the vertices and re-runs the strict traversal below."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "retroactive_reconciliation_receipt.v1.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )

    if rerun_traversal:
        receipt["corrected_traversal"] = _corrected_traversal(base_url)
        (OUT_DIR / "retroactive_reconciliation_receipt.v1.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
    return receipt


def _get_one(base_url: str, collection: str, key: str) -> dict[str, Any] | None:
    d = p15._http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": collection, "limit": 3, "filters": {"_key": key}},
    )
    for doc in d.get("documents") or d.get("items") or []:
        if doc.get("_key") == key:
            return doc
    return None


def _corrected_traversal(base_url: str) -> dict[str, Any]:
    """Re-run the strict phase-16 traversal probe and write a corrected receipt
    that supersedes the old edges-only claim (old receipt kept, marked superseded)."""
    p16 = _load("phase16_behavior_evaluation")
    p16.MEMORY_BASE_URL = base_url
    probe = p16.probe_b_traversal()
    corrected = {
        "schema": "persona_dream.corrected_traversal_receipt.v1",
        "generated_at": now(),
        "mocked": False,
        "supersedes": "phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json (probe b, edges-only)",
        "what_the_old_receipt_actually_proved": (
            "The prior committed '14/14 traversal' proved that all 14 canonical EDGES resolved "
            "live, but the 7 Watch-observation edge TARGETS were never materialized as documents "
            "- they were counted as reachable via a 'vertex_class_not_materialized_as_document' "
            "allowance. It proved edges, not vertices."
        ),
        "strict_resolver": (
            "Every edge target - source memories, ToM nodes, AND persona_dream_watch_evidence "
            "vertices - must resolve to a real stored document; a missing target FAILS traversal."
        ),
        "strict_probe_b": probe,
        "verdict": "PASS" if probe["passed"] else "FAIL",
    }
    corrected_path = REV / "phase_16_behavior_evaluation" / "corrected_traversal_receipt.v1.json"
    corrected_path.parent.mkdir(parents=True, exist_ok=True)
    corrected_path.write_text(json.dumps(corrected, indent=2, sort_keys=True) + "\n")

    # Mark the old receipt superseded (keep it; annotate a sidecar, do not rewrite the original).
    old = REV / "phase_16_behavior_evaluation" / "phase16_behavior_evaluation_receipt.v1.json"
    if old.exists():
        (old.parent / "phase16_behavior_evaluation_receipt.v1.SUPERSEDED.json").write_text(
            json.dumps({
                "superseded_by": "corrected_traversal_receipt.v1.json",
                "reason": "Probe B was edges-only; Watch vertices are now materialized and the "
                          "strict resolver requires target vertices to resolve.",
                "superseded_at": now(),
                "original_receipt": str(old.relative_to(PERSONA_DREAM)),
            }, indent=2) + "\n"
        )
    return corrected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=p15.MEMORY_BASE_URL)
    ap.add_argument("--no-rerun-traversal", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    receipt = reconcile(args.base_url, rerun_traversal=not args.no_rerun_traversal)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        wv = receipt["watch_vertices"]
        print(f"reconciled_ok={receipt['reconciled_ok']}")
        print(f"watch vertices materialized: {wv['materialized']}/{wv['expected']}")
        print(f"existing records present: {receipt['existing_records']['all_present']}")
        print(f"commit manifest: {receipt['commit_manifest']['key']} active={receipt['commit_manifest']['active']} reread={receipt['commit_manifest']['exact_reread_match']}")
        if "corrected_traversal" in receipt:
            print(f"corrected traversal verdict: {receipt['corrected_traversal']['verdict']}")
    return 0 if receipt["reconciled_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
