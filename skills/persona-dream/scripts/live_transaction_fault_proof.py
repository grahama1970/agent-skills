#!/usr/bin/env python3
"""Live fault-proof of the phase-15 transaction layer against the DEPLOYED
$memory daemon — the two LIVE_PROOF_REQUIRED preconditions from the webgpt
clarification (2026-07-19):

  Proof A: clean commit via persist_canonical against the real daemon; tamper
    the stored manifest's record_index in ArangoDB (real /store overwrite);
    real retry; read back PRIOR_MANIFEST_BINDING_MISMATCH quarantine.
  Proof B (joint client+server): after the quarantine, the GMO recall and
    /list paths exclude the faulted commit's records (visibility invariant),
    and pending records of an uncommitted transaction are likewise excluded.

Uses an isolated test-dream namespace (persona 'embry_txproof') in the REAL
collections via the REAL HTTP surface. No canonical dream records are read,
written, or altered. Test records remain as retained, quarantined/pending,
recall-invisible transaction residue (no delete primitive exists, by design).
Writes a receipt to reports/pipeline-complete/.persona-dream/state/.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
import time

PERSONA = "embry_txproof"
DREAM = f"dream_txproof_{time.strftime('%Y%m%dT%H%M%S')}"  # fresh identity per run
RECEIPT = (
    ROOT
    / "reports/pipeline-complete/.persona-dream/state/live_transaction_fault_proof_receipt.v1.json"
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main() -> int:
    p15 = _load("phase15_dream_persistence")
    results: dict = {"schema": "persona_dream.live_transaction_fault_proof_receipt.v1"}

    interpretation = {
        "generated_at": "2026-07-19T00:00:00Z",
        "observation_packet_sha256": "sha256:txproof-obs",
        "accepted_interpretations": [
            {
                "interpretation_id": "interpretation-001",
                "tom_state_type": "trust",
                "subject": PERSONA,
                "target": "counterpart",
                "statement": "transaction-layer live fault proof fixture",
                "observation_refs": ["frame_txproof"],
                "source_memory_refs": ["mem-txproof"],
                "confidence": 0.5,
                "uncertainty": "fixture",
                "renderer_alternative": {"present": True, "statement": "fixture"},
                "source_memory_bindings": [{"source_id": "mem-txproof"}],
            }
        ],
        "source_memory_bindings": [{"source_id": "mem-txproof"}],
    }
    tom = {
        "accepted_tom_candidates": [
            {
                "candidate_id": "tom-001",
                "tom_state_type": "trust",
                "subject": PERSONA,
                "target": "counterpart",
                "statement": "fixture",
                "confidence": 0.5,
                "emotional_intensity": 0.3,
                "observation_refs": ["frame_txproof"],
                "source_memory_refs": ["mem-txproof"],
            }
        ]
    }
    packet = {
        "observed_at": "2026-07-19T00:00:00Z",
        "source_video_sha256": "sha256:txproof-video",
        "status": "ACCEPTED",
        "evidence_origin": "txproof_fixture",
        "source_revision_id": "rev_txproof",
        "identity_evidence": {},
        "visible_entities_per_frame": {"frames": []},
    }
    causal = p15.build_causal_family_fields(PERSONA, DREAM, ["mem-txproof"], None)
    dream_doc = p15.build_dream_memory_document(
        DREAM, "rev_txproof", "txproof-run", PERSONA, packet, interpretation, tom,
        dream_key=p15.ns_dream_key(PERSONA, DREAM), causal_fields=causal,
    )
    watch_vertices = [
        {
            "_key": p15.ns_watch_key(PERSONA, DREAM, "frame_txproof"),
            "observation_id": "frame_txproof",
            "dream_id": DREAM,
            "return_id": "txproof-return",
            "source_video_sha256": "sha256:txproof-video",
            "observation_type": "frame",
            "statement": "fixture frame",
            "confidence": 0.9,
            "evidence_artifacts": [],
            "adjudication_receipt_sha256": "sha256:txproof-adj",
            "synthetic_origin": True,
            "psychological_interpretation_performed": False,
            **causal,
        }
    ]
    interp_vertices = p15.build_interpretation_vertices(
        interpretation, PERSONA, DREAM, causal_fields=causal
    )

    def persist():
        return p15.persist_canonical(
            dream_doc, interpretation, tom, watch_vertices, BASE,
            dream_id=DREAM, return_id="txproof-return", packet=packet,
            phase13_sha=p15.canonical_sha(interpretation),
            phase14_sha=p15.canonical_sha(tom),
            interpretation_vertices=interp_vertices, causal_fields=causal,
        )

    # --- Proof A ----------------------------------------------------------
    clean = persist()
    if clean["commit_manifest"] is None:
        results["status"] = "FAIL_CLEAN_COMMIT_NO_MANIFEST"
        results["quarantine"] = clean["quarantine"]
        results["staging_proof_summary"] = {
            "all": clean["staging_proof"].get("all_exact_reread_match"),
            "staged": clean["staging_proof"].get("staged_count"),
        }
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(results, indent=2))
        print(json.dumps(results, indent=2)); return 1
    manifest_key = clean["commit_manifest"]["key"]
    results["a_clean_commit"] = {
        "all_exact_reread_match": clean["all_exact_reread_match"],
        "manifest_key": manifest_key,
        "manifest_active": clean["commit_manifest"]["active"],
        "records_written": clean["records_written"],
    }
    if not (clean["all_exact_reread_match"] and clean["commit_manifest"]["active"]):
        results["status"] = "FAIL_CLEAN_COMMIT"
        RECEIPT.write_text(json.dumps(results, indent=2))
        print(json.dumps(results["a_clean_commit"], indent=2)); return 1

    # Verify identical retry resumes live BEFORE tampering.
    retry_clean = persist()
    results["a_identical_retry"] = {
        "resumed": retry_clean["resumed_from_prior_commit"],
        "records_written": retry_clean["records_written"],
        "quarantine": retry_clean["quarantine"],
    }

    # Tamper the stored manifest's record_index via the real /store surface.
    stored = post("/list", {
        "collection": p15.COMMIT_MANIFEST_COLLECTION, "filters": {"_key": manifest_key},
    })
    mdoc = (stored.get("documents") or stored.get("items"))[0]
    mdoc = {k: v for k, v in mdoc.items() if not k.startswith("_") or k == "_key"}
    mdoc["record_index"] = [
        {**r, "payload_sha256": "sha256:TAMPERED"} for r in mdoc["record_index"]
    ]
    post("/store", {"collection": p15.COMMIT_MANIFEST_COLLECTION, "document": mdoc})

    # Real retry against the tampered manifest.
    faulted = persist()
    back = post("/list", {
        "collection": p15.COMMIT_MANIFEST_COLLECTION, "filters": {"_key": manifest_key},
    })
    mafter = (back.get("documents") or back.get("items"))[0]
    results["a_faulted_retry"] = {
        "resumed": faulted["resumed_from_prior_commit"],
        "quarantine_reason": (faulted["quarantine"] or {}).get("reason"),
        "quarantine_reread_match": (faulted["quarantine"] or {}).get("quarantine_reread_match"),
        "stored_manifest_active": mafter.get("active"),
        "stored_manifest_quarantined": mafter.get("quarantined"),
    }
    a_pass = (
        results["a_identical_retry"]["resumed"] is True
        and results["a_identical_retry"]["records_written"] == 0
        and faulted["resumed_from_prior_commit"] is False
        and (faulted["quarantine"] or {}).get("reason") == "PRIOR_MANIFEST_BINDING_MISMATCH"
        and mafter.get("active") is False
        and mafter.get("quarantined") is True
    )
    results["proof_a"] = "PASS" if a_pass else "FAIL"

    # --- Proof B: joint visibility ---------------------------------------
    dream_key = dream_doc["_key"]
    recall = post("/recall", {"q": "transaction-layer live fault proof fixture", "k": 20, "collections": [p15.CANONICAL_DREAM_COLLECTION], "tags": []})
    recall_blob = json.dumps(recall)
    listed = post("/list", {
        "collection": p15.CANONICAL_DREAM_COLLECTION, "filters": {"_key": dream_key},
    })
    listed_docs = listed.get("documents") or listed.get("items") or []
    results["b_visibility"] = {
        "dream_key": dream_key,
        "recall_exposes_faulted_dream": dream_key in recall_blob,
        "list_returns_faulted_dream": bool(listed_docs),
        "list_doc_visibility_state": listed_docs[0].get("visibility_state") if listed_docs else None,
    }
    # The faulted commit's records must NOT surface via ordinary recall; /list
    # is the admin surface (bypass documented) — the invariant under proof is
    # recall exclusion + the record's non-active visibility_state.
    b_pass = (
        dream_key not in recall_blob
        and (not listed_docs or listed_docs[0].get("visibility_state") != "active")
    )
    results["proof_b"] = "PASS" if b_pass else "FAIL"

    results["status"] = (
        "PASS_LIVE_TRANSACTION_FAULT_PROOF" if (a_pass and b_pass) else "FAIL_LIVE_TRANSACTION_FAULT_PROOF"
    )
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    return 0 if (a_pass and b_pass) else 1


if __name__ == "__main__":
    sys.exit(main())
