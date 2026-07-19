#!/usr/bin/env python3
"""Refined step-36 Embry-presence check: max Embry cosine over ALL faces per frame.

Answers 'is an Embry-matching face present anywhere in the frame' (fair drift
check), instead of assigning only the largest face to Embry. Reuses the same
embedder + cosine from the subgate library.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sg", HERE / "identity_face_embedding_subgate.py")
sg = importlib.util.module_from_spec(spec); sys.modules["sg"] = sg; spec.loader.exec_module(sg)

REV = HERE.parent / "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"
FRAMES = sorted((REV / "watch_gauntlet/59b9ff3155d6/watch/frames").glob("frame_*.jpg"))
EMBRY_REF = Path("/mnt/storage12tb/media/personas/embry/assets/contact_sheets/embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png")
OUT = REV / "watch_gauntlet/59b9ff3155d6/step36_embry_presence_refine.json"

emb = sg.InsightFaceEmbedder()
ref_faces = emb.detect(EMBRY_REF)
thr = sg.DEFAULT_THRESHOLD
rows = []
for fp in FRAMES:
    faces = emb.detect(fp)
    best = None; best_sex = None
    for c in faces:
        for rf in ref_faces:
            cs = sg.cosine(c.embedding, rf.embedding)
            if best is None or cs > best:
                best = cs; best_sex = c.sex
    rows.append({"frame": fp.name, "faces": len(faces),
                 "max_embry_cosine": round(best, 6) if best is not None else None,
                 "best_face_sex": best_sex,
                 "present": bool(best is not None and best >= thr)})
present = [r for r in rows if r["present"]]
cos = [r["max_embry_cosine"] for r in rows if r["max_embry_cosine"] is not None]
summary = {"schema": "persona_dream.step36_embry_presence_refine.v1",
           "method": "max cosine over all detected faces vs all embry_v3 reference faces",
           "threshold": thr, "reference_faces_in_sheet": len(ref_faces),
           "frame_count": len(FRAMES),
           "frames_with_embry_present": len(present),
           "cosine_min": min(cos) if cos else None, "cosine_max": max(cos) if cos else None,
           "cosine_mean": round(sum(cos)/len(cos), 6) if cos else None,
           "per_frame": rows}
OUT.write_text(json.dumps(summary, indent=2, sort_keys=True))
print(json.dumps({k: summary[k] for k in summary if k != "per_frame"}, indent=2))
for r in rows: print(f"{r['frame']:11} faces={r['faces']} maxcos={r['max_embry_cosine']} present={r['present']} sex={r['best_face_sex']}")
print("WROTE", OUT)
