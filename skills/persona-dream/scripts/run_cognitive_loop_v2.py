#!/usr/bin/env python3
"""GOAL_V2 P0.2: v2-derived cognitive lineage as a REVISION BUNDLE.

Runs phases 13/14 live (Tau-routed) on the ACCEPTED observation packet v2,
persists the derived evidence as a versioned revision bundle through the
certified transactional path — the existing dream-event node is REFERENCED,
never rewritten (one dream event per media hash; PROV wasRevisionOf design:
new versioned ToM nodes + interpretation vertices with supersedes edges to
their v1 predecessors) — then writes the lineage receipt GOAL_V2's checker
validates. Fail-closed everywhere; dream-node integrity proven by pre/post
hash of the stored node.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
RR = ROOT / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
WG = RR / "watch_gauntlet/59b9ff3155d6"
OUT = WG / "cognitive_loop_v2"
BUNDLE_REV = "v2r1"

DREAM_ID = "dream_successor_943b01ecd9a3"
REVISION_ID = "rev_successor_943b01ecd9a3"
RUN_ID = "pipeline-complete"
PERSONA = "embry"
RETURN_ID = "97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4"
V1_TOM_KEYS = ["tom-001", "tom-002", "tom-003", "tom-004"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def stored_dream_node_sha(p15) -> str | None:
    r = post("/list", {
        "collection": p15.CANONICAL_DREAM_COLLECTION,
        "filters": {"_key": "dream_dream_successor_943b01ecd9a3"},
    })
    docs = r.get("documents") or []
    return p15.authored_sha(docs[0]) if docs else None


def main() -> int:
    p13 = _load("phase13_self_interpretation")
    p14 = _load("phase14_tom_validation")
    p15 = _load("phase15_dream_persistence")
    OUT.mkdir(parents=True, exist_ok=True)

    observation_path = WG / "dream_observation_packet.v2.json"
    v1_loop_dir = WG / "cognitive_loop"
    # Residue: the successor revision's own phase-01 residue_links.v1 packet.
    residue_path = RR / "phase_01_idea/residue_links.json"

    dream_sha_before = stored_dream_node_sha(p15)
    if dream_sha_before is None:
        print("BLOCKED: canonical dream node not readable"); return 1

    # Phase 13 live on packet v2.
    interp = p13.run_phase13(
        observation_path, residue_path, None, None,
        DREAM_ID, REVISION_ID, RUN_ID, PERSONA, live=True,
    )
    p13.write_json(OUT / "dream_self_interpretation.v2.json", interp)
    if not interp["status"].startswith("PASS") or not interp["accepted_interpretations"]:
        print(f"BLOCKED at phase13: {interp['status']}"); return 1

    # Version the derived ids so bundle keys never collide with v1.
    for c in interp["accepted_interpretations"]:
        c["interpretation_id"] = f"{BUNDLE_REV}-{c['interpretation_id']}"

    # Phase 14 live.
    tom = p14.run_phase14(interp, DREAM_ID, REVISION_ID, RUN_ID, live=True)
    p13.write_json(OUT / "tom_validation_receipt.v2.json", tom)
    if not tom["status"].startswith("PASS") or not tom["accepted_tom_candidates"]:
        print(f"BLOCKED at phase14: {tom['status']}"); return 1
    for c in tom["accepted_tom_candidates"]:
        c["candidate_id"] = f"{BUNDLE_REV}-{c['candidate_id']}"

    packet = p13.read_json(observation_path)
    causal = p15.build_causal_family_fields(
        PERSONA, DREAM_ID,
        sorted({b.get("source_id") for b in interp.get("source_memory_bindings", []) if b.get("source_id")})
        or ["embry_age15_19_b03_memory_014"],
        None,
    )
    causal["bundle_rev"] = BUNDLE_REV
    dream_doc_ref = {  # reference-only: used for keys/edges, NEVER written.
        "_key": "dream_dream_successor_943b01ecd9a3",
        "persona_id": PERSONA, "dream_id": DREAM_ID,
    }
    interp_vertices = p15.build_interpretation_vertices(
        interp, PERSONA, DREAM_ID, causal_fields=causal
    )
    # Supersedes edges: new versioned ToM nodes -> v1 raw-key ToM nodes.
    supersedes = []
    for old in V1_TOM_KEYS:
        new_key = p15.ns_tom_key(PERSONA, DREAM_ID, f"{BUNDLE_REV}-tom-{old.split('-')[1]}")
        supersedes.append({
            "collection": p15.CANONICAL_TOM_EDGE_COLLECTION,
            "kind": "edge",
            "document": {
                "_key": f"dream:{PERSONA}:{DREAM_ID}:supersedes:{BUNDLE_REV}:{old}",
                "_from": f"{p15.TOM_CANDIDATE_COLLECTION}/{new_key}",
                "_to": f"{p15.TOM_CANDIDATE_COLLECTION}/{old}",
                "relationship_type": "supersedes",
                "prov": "wasRevisionOf",
                **causal,
            },
        })

    acceptance = p13.read_json(
        RR / "phase_11_submit_return/provider_return" / RETURN_ID
        / "post_return_acceptance_receipt.v2.json"
    )
    allowed, blockers = p15.canonical_write_decision(
        packet, True, RETURN_ID, acceptance_receipt=acceptance
    )
    if not allowed:
        print(f"BLOCKED at write decision: {blockers}"); return 1

    proof = p15.persist_canonical(
        dream_doc_ref, interp, tom, [], BASE,
        dream_id=DREAM_ID, return_id=RETURN_ID, packet=packet,
        phase13_sha=p15.canonical_sha(interp), phase14_sha=p15.canonical_sha(tom),
        interpretation_vertices=interp_vertices, causal_fields=causal,
        include_dream_node=False, extra_edges=supersedes,
        justification=f"GOAL_V2 P0.2 revision bundle {BUNDLE_REV} from observation packet v2",
    )
    p13.write_json(OUT / "bundle_persist_proof.v2.json", proof)
    manifest = proof.get("commit_manifest") or {}
    written = bool(
        proof.get("all_exact_reread_match") and manifest.get("exact_reread_match")
        and manifest.get("active")
    )
    dream_sha_after = stored_dream_node_sha(p15)

    receipt = {
        "schema": "persona_dream.v2_lineage_receipt.v1",
        "status": "PASS_V2_LINEAGE" if (written and dream_sha_after == dream_sha_before) else "BLOCKED_V2_LINEAGE",
        "bundle_rev": BUNDLE_REV,
        "observation_packet": str(observation_path.relative_to(ROOT)),
        "observation_packet_sha256": interp.get("observation_packet_sha256"),
        "accepted_interpretations": len(interp["accepted_interpretations"]),
        "accepted_tom_candidates": len(tom["accepted_tom_candidates"]),
        "phase14_status": tom["status"],
        "canonical_written": written,
        "commit_manifest_key": manifest.get("key"),
        "dream_node_untouched": dream_sha_after == dream_sha_before,
        "dream_node_sha_before": dream_sha_before,
        "dream_node_sha_after": dream_sha_after,
        "supersedes_edges": len(supersedes),
        "predecessor_artifacts": {
            "v1_interpretation_sha256": p15.canonical_sha(p13.read_json(v1_loop_dir / "dream_self_interpretation.json")),
            "v1_tom_sha256": p15.canonical_sha(p13.read_json(v1_loop_dir / "tom_validation_receipt.json")),
            "superseded_tom_keys": V1_TOM_KEYS,
        },
    }
    p13.write_json(OUT / "lineage_receipt.v1.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "canonical_written", "dream_node_untouched", "accepted_interpretations", "accepted_tom_candidates", "commit_manifest_key")}, indent=2))
    return 0 if receipt["status"] == "PASS_V2_LINEAGE" else 1


if __name__ == "__main__":
    sys.exit(main())
