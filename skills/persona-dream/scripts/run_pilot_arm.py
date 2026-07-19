#!/usr/bin/env python3
"""Execute one pilot arm run (protocol v3) with receipts.

Arms:
  C — structured text reflection: the reflection packet (root memories as the
      sole observation surface) through the SAME phase-13/14 gates, persisted
      through the SAME transactional path with evidence_class
      synthetic_reflection. No storyboard, render, or Watch.
  F — full loop (storyboard lane); implemented separately per run because it
      drives the media-spine scripts. This runner currently executes arm C;
      invoking --arm F exits BLOCKED so the frozen run order can never
      silently skip F's real implementation.

Order of operations for C (fail-closed at each step):
  1. Producer-blinding receipt over {producer contract, root_set_reading.md}
     (denylist scan; abort on any hit).
  2. Manifest verify (pilot_run_manifest.py logic) — drift aborts the run.
  3. phase13 live on the reflection packet + residue (standard gates).
  4. phase14 live (standard gates).
  5. canonical_write_decision + persist_canonical (include_dream_node=True,
     new keys pilot_<set>_<arm>) with evidence_class stamped
     synthetic_reflection on the produced record (explicit, never silent).
  6. Arm receipt with produced record key, manifest key, tau receipts, and
     model-call count (for the C=F budget check).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
PERSONA = "embry"
RUN_ID = "pilot-c-vs-f"
REVISION_ID = "pilot_c_vs_f"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True, choices=["C", "F"])
    parser.add_argument("--set", required=True, choices=["r1", "r2"])
    parser.add_argument("--inputs-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    if args.arm == "F":
        print("BLOCKED_PILOT_ARM_F_NOT_IMPLEMENTED_IN_THIS_RUNNER", file=sys.stderr)
        return 2

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    run_name = f"{args.set.upper()}-{args.arm}"
    dream_id = f"pilot_{args.set}_{args.arm.lower()}"

    # 1. producer blinding (fail closed before anything else)
    contract = ROOT / f"contracts/pilot_producer_contract_{args.arm}.v1.md"
    blinding_out = out / f"blinding_{run_name}.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_producer_blinding.py"),
         "--producer-role", run_name,
         "--shown-file", str(contract),
         "--shown-file", str(args.inputs_dir / "root_set_reading.md"),
         "--out", str(blinding_out)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"BLOCKED_PILOT_ARM_BLINDING: {proc.stderr[-400:]}", file=sys.stderr)
        return 2

    # 2. manifest verify
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/pilot_run_manifest.py"), "--verify"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"BLOCKED_PILOT_ARM_MANIFEST_DRIFT: {proc.stderr[-400:]}", file=sys.stderr)
        return 2

    p13 = _load("phase13_self_interpretation")
    p14 = _load("phase14_tom_validation")
    p15 = _load("phase15_dream_persistence")

    packet_path = args.inputs_dir / "reflection_packet.json"
    residue_path = args.inputs_dir / "residue_links.json"
    packet = p13.read_json(packet_path)
    return_id = f"reflection_{sha256_text(packet_path.read_text())[:32]}"

    # 3. phase 13 live (standard gates, unmodified)
    interp = p13.run_phase13(
        packet_path, residue_path, None, None,
        dream_id, REVISION_ID, RUN_ID, PERSONA, live=True,
    )
    p13.write_json(out / "phase13_interpretation.json", interp)
    if not interp["status"].startswith("PASS") or not interp["accepted_interpretations"]:
        print(f"BLOCKED_PILOT_ARM_PHASE13: {interp['status']}", file=sys.stderr)
        return 1

    # 4. phase 14 live (standard gates, unmodified)
    tom = p14.run_phase14(interp, dream_id, REVISION_ID, RUN_ID, live=True)
    p13.write_json(out / "phase14_tom.json", tom)
    if not tom["status"].startswith("PASS") or not tom["accepted_tom_candidates"]:
        print(f"BLOCKED_PILOT_ARM_PHASE14: {tom['status']}", file=sys.stderr)
        return 1

    # 5. persist through the certified transactional path
    root_ids = sorted({b.get("source_id") for b in interp.get("source_memory_bindings", [])
                       if b.get("source_id")})
    causal = p15.build_causal_family_fields(PERSONA, dream_id, root_ids, None)
    causal["pilot_run"] = run_name
    dream_doc = p15.build_dream_memory_document(
        dream_id, REVISION_ID, RUN_ID, PERSONA, packet, interp, tom,
        causal_fields=causal,
    )
    # explicit evidence-class stamp — never a silent conversion: this record is
    # a REFLECTION product, not a dream observation product.
    dream_doc["kind"] = "synthetic_reflection_memory"
    dream_doc["evidence_class"] = "synthetic_reflection"
    dream_doc["tags"] = [f"persona:{PERSONA}", "synthetic_reflection",
                         "persona_dream", "pilot_c_vs_f"]

    interp_vertices = p15.build_interpretation_vertices(
        interp, PERSONA, dream_id, causal_fields=causal)

    allowed, blockers = p15.canonical_write_decision(packet, True, return_id)
    if not allowed:
        print(f"BLOCKED_PILOT_ARM_WRITE_DECISION: {blockers}", file=sys.stderr)
        return 1
    proof = p15.persist_canonical(
        dream_doc, interp, tom, [], BASE,
        dream_id=dream_id, return_id=return_id, packet=packet,
        phase13_sha=p15.canonical_sha(interp), phase14_sha=p15.canonical_sha(tom),
        interpretation_vertices=interp_vertices, causal_fields=causal,
        include_dream_node=True,
        justification=f"pilot v3 arm {run_name}: structured text reflection",
    )
    p13.write_json(out / "persist_proof.json", proof)
    manifest = proof.get("commit_manifest") or {}
    written = bool(proof.get("all_exact_reread_match") and manifest.get("exact_reread_match")
                   and manifest.get("active"))
    if not written:
        print("BLOCKED_PILOT_ARM_PERSIST", file=sys.stderr)
        return 1

    tau_calls = 1 + len(interp.get("accepted_interpretations", []))  # p13 draft + p14 per-candidate
    receipt = {
        "schema": "persona_dream.pilot_arm_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run": run_name,
        "arm": args.arm,
        "set": args.set,
        "dream_id": dream_id,
        "evidence_class": "synthetic_reflection",
        "produced_record_key": dream_doc["_key"],
        "commit_manifest_key": manifest.get("key"),
        "root_ids": root_ids,
        "phase13_status": interp["status"],
        "phase14_status": tom["status"],
        "accepted_interpretations": len(interp["accepted_interpretations"]),
        "accepted_tom_candidates": len(tom["accepted_tom_candidates"]),
        "blinding_receipt": str(blinding_out),
        "model_call_note": {"approx_tau_calls": tau_calls,
                            "detail": "per-call tau receipts embedded in phase13/14 artifacts"},
    }
    p13.write_json(out / f"arm_receipt_{run_name}.json", receipt)
    print(json.dumps({"run": run_name, "produced": dream_doc["_key"],
                      "manifest": manifest.get("key"),
                      "p13": interp["status"], "p14": tom["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
