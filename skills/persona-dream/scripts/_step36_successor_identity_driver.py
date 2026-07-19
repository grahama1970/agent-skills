#!/usr/bin/env python3
"""Step-36 driver: deterministic ArcFace identity review of the SUCCESSOR return.

Reuses run_face_embedding_subgate / InsightFaceEmbedder (no scoring reinvented).
Builds a per-frame Embry cosine table (the EMBRY_IDENTITY_DRIFT moment of truth)
plus a Kai visibility pass, over the watch-gauntlet frames of the successor return.
Emits a JSON summary to stdout and a file.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sg", HERE / "identity_face_embedding_subgate.py")
sg = importlib.util.module_from_spec(spec)
sys.modules["sg"] = sg
spec.loader.exec_module(sg)

REV = HERE.parent / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
FRAMES_DIR = REV / "watch_gauntlet/59b9ff3155d6/watch/frames"
EMBRY_REF = Path("/mnt/storage12tb/media/personas/embry/assets/contact_sheets/embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png")
KAI_REF = REV / "phase_04_contact_sheets/source_artifacts/images/contact_sheet_kai_surfboard.png"
OUT = REV / "watch_gauntlet/59b9ff3155d6/step36_arcface_identity_summary.json"

frames = sorted(FRAMES_DIR.glob("frame_*.jpg"))
assert frames, f"no frames under {FRAMES_DIR}"

embedder = sg.InsightFaceEmbedder()  # CPU, deterministic
thr = sg.DEFAULT_THRESHOLD

embry_rows = []
kai_rows = []
for fp in frames:
    r = sg.run_face_embedding_subgate(
        frame_path=fp, references={"Embry": EMBRY_REF},
        required_entities=["Embry"], embedder=embedder, threshold=thr,
    )
    er = r["entity_results"][0] if r["entity_results"] else {}
    embry_rows.append({
        "frame": fp.name,
        "faces_detected": r.get("candidate_faces_detected"),
        "status": er.get("status"),
        "verdict": er.get("verdict"),
        "best_cosine": er.get("best_cosine"),
        "det_score": er.get("candidate_det_score"),
        "detected_sex": er.get("candidate_detected_sex"),
    })
    rk = sg.run_face_embedding_subgate(
        frame_path=fp, references={"Kai": KAI_REF},
        required_entities=["Kai"], embedder=embedder, threshold=thr,
    )
    ek = rk["entity_results"][0] if rk["entity_results"] else {}
    kai_rows.append({
        "frame": fp.name,
        "status": ek.get("status"),
        "verdict": ek.get("verdict"),
        "best_cosine": ek.get("best_cosine"),
        "detected_sex": ek.get("candidate_detected_sex"),
    })

embry_pass = [r for r in embry_rows if r["status"] == "PASS"]
embry_cos = [r["best_cosine"] for r in embry_rows if r["best_cosine"] is not None]
summary = {
    "schema": "persona_dream.step36_arcface_identity_summary.v1",
    "authority": "embedding_cosine",
    "model": "insightface:buffalo_l:w600k_r50",
    "threshold": thr,
    "embry_reference": str(EMBRY_REF),
    "embry_reference_sha256": "sha256:" + sg._sha256_file(EMBRY_REF),
    "kai_reference": str(KAI_REF.relative_to(HERE.parent)),
    "frames_dir": str(FRAMES_DIR.relative_to(HERE.parent)),
    "frame_count": len(frames),
    "embry_frames_pass": len(embry_pass),
    "embry_frames_total_with_face": len(embry_cos),
    "embry_cosine_min": min(embry_cos) if embry_cos else None,
    "embry_cosine_max": max(embry_cos) if embry_cos else None,
    "embry_cosine_mean": round(sum(embry_cos) / len(embry_cos), 6) if embry_cos else None,
    "embry_identity_verdict": "PASS_NO_DRIFT" if embry_cos and all(r["status"] == "PASS" for r in embry_rows if r["best_cosine"] is not None) else "DRIFT_OR_FAIL",
    "embry_per_frame": embry_rows,
    "kai_per_frame": kai_rows,
}
OUT.write_text(json.dumps(summary, indent=2, sort_keys=True))
print(json.dumps({k: summary[k] for k in summary if k not in ("embry_per_frame", "kai_per_frame")}, indent=2))
print("WROTE", OUT)
