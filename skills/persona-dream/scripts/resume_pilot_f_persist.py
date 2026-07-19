#!/usr/bin/env python3
"""Resume an F-arm run at the persist step from its saved artifacts.

Used when the run crashed AFTER phase 13/14 completed but BEFORE any store
write (verified case: R2-F read-timeout inside existing_commit_manifest, the
read-only first persist step, during an unrelated ArangoDB load burst).
Re-drives exactly the tail of run_pilot_arm_f.main: write decision ->
certified transactional persist -> arm receipt. No generation, no phase
calls, no gate is re-run — the saved artifacts are used as-is.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8601"
PERSONA = "embry"
RUN_ID = "pilot-c-vs-f"
REVISION_ID = "pilot_c_vs_f"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", required=True, choices=["r1", "r2"])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--http-timeout", type=float, default=90.0,
                        help="per-call store timeout (loaded-store resilience)")
    args = parser.parse_args()

    out = args.out_dir
    run_name = f"{args.set.upper()}-F"
    dream_id = f"pilot_{args.set}_f"
    other_person = {"r1": "Brandon", "r2": "Marketa Lawson"}[args.set]

    if (out / "persist_proof.json").exists():
        print("BLOCKED_RESUME_ALREADY_PERSISTED", file=sys.stderr)
        return 2

    p13 = _load("phase13_self_interpretation")
    p15 = _load("phase15_dream_persistence")
    # loaded-store resilience: longer per-call timeout, same call semantics
    _orig_http = p15._http_post
    p15._http_post = lambda url, payload, timeout=args.http_timeout: _orig_http(
        url, payload, timeout=max(timeout, args.http_timeout))

    packet = json.loads((out / "observation_packet.json").read_text())
    interp = json.loads((out / "phase13_interpretation.json").read_text())
    tom = json.loads((out / "phase14_tom.json").read_text())
    assert interp["status"].startswith("PASS") and tom["status"].startswith("PASS")

    media_sha = sha256_file(out / "storyboard_contact_sheet.png")
    assert packet.get("source_video_sha256") == f"sha256:{media_sha}", "packet/media mismatch"
    return_id = f"storyboard_{media_sha[:32]}"

    frames_dir = out / "frames"
    accepted_frames = []
    for arc in sorted(frames_dir.glob("*_arcface.json")):
        verdict = json.loads(arc.read_text())
        if verdict.get("status") != "PASS":
            continue
        m = re.match(r"(sb_\d+)\.attempt_(\d+)_arcface\.json", arc.name)
        panel_id, attempt = m.group(1), int(m.group(2))
        frame_png = frames_dir / f"{panel_id}.attempt_{attempt:02d}.png"
        if not any(f["panel_id"] == panel_id for f in accepted_frames):
            accepted_frames.append({
                "panel_id": panel_id, "frame": str(frame_png),
                "frame_sha256": sha256_file(frame_png), "attempt": attempt,
                "arcface": {"status": "PASS",
                            "entity_results": verdict.get("entity_results")}})
    assert len(accepted_frames) == 4, f"expected 4 accepted panels, got {len(accepted_frames)}"
    image_calls = len(list(frames_dir.glob("*_generation_receipt.json")))

    root_ids = sorted({b.get("source_id") for b in interp.get("source_memory_bindings", [])
                       if b.get("source_id")})
    causal = p15.build_causal_family_fields(PERSONA, dream_id, root_ids, None)
    causal["pilot_run"] = run_name
    dream_doc = p15.build_dream_memory_document(
        dream_id, REVISION_ID, RUN_ID, PERSONA, packet, interp, tom,
        causal_fields=causal)
    dream_doc["evidence_class"] = "synthetic_dream"
    dream_doc["tags"] = [f"persona:{PERSONA}", "synthetic_dream",
                         "persona_dream", "pilot_c_vs_f"]
    interp_vertices = p15.build_interpretation_vertices(
        interp, PERSONA, dream_id, causal_fields=causal)
    allowed, blockers = p15.canonical_write_decision(packet, True, return_id)
    if not allowed:
        print(f"BLOCKED_RESUME_WRITE_DECISION: {blockers}", file=sys.stderr)
        return 1
    proof = p15.persist_canonical(
        dream_doc, interp, tom, [], BASE,
        dream_id=dream_id, return_id=return_id, packet=packet,
        phase13_sha=p15.canonical_sha(interp), phase14_sha=p15.canonical_sha(tom),
        interpretation_vertices=interp_vertices, causal_fields=causal,
        include_dream_node=True,
        justification=f"pilot v3 arm {run_name}: storyboard dream loop (persist resumed)",
    )
    p13.write_json(out / "persist_proof.json", proof)
    manifest = proof.get("commit_manifest") or {}
    written = bool(proof.get("all_exact_reread_match") and manifest.get("exact_reread_match")
                   and manifest.get("active"))
    if not written:
        print("BLOCKED_RESUME_PERSIST", file=sys.stderr)
        return 1

    receipt = {
        "schema": "persona_dream.pilot_arm_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run": run_name, "arm": "F", "set": args.set, "dream_id": dream_id,
        "evidence_class": "synthetic_dream",
        "produced_record_key": dream_doc["_key"],
        "commit_manifest_key": manifest.get("key"),
        "root_ids": root_ids,
        "media_sha256": media_sha,
        "frames": accepted_frames,
        "image_generation_calls": image_calls,
        "phase13_status": interp["status"],
        "phase14_status": tom["status"],
        "accepted_interpretations": len(interp["accepted_interpretations"]),
        "accepted_tom_candidates": len(tom["accepted_tom_candidates"]),
        "blinding_receipt": str(out / f"blinding_{run_name}.json"),
        "persist_resumed": "crash was pre-write (read timeout in existing_commit_manifest during unrelated DB load); tail re-driven from saved artifacts",
        "scope_notes": [
            "render boundary: no non-paid video renderer exists at run time; "
            "the storyboard frames are the visual artifact (protocol v3 F clause)",
            f"{other_person} presence is advisory (no identity reference sheet); "
            "ArcFace certifies Embry only",
        ],
    }
    p13.write_json(out / f"arm_receipt_{run_name}.json", receipt)
    print(json.dumps({"run": run_name, "produced": dream_doc["_key"],
                      "manifest": manifest.get("key"), "media_sha": media_sha[:16],
                      "image_calls": image_calls}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
