#!/usr/bin/env python3
"""GOAL_V5 Gate 1 reach screen — live, real /tau/voice-render path.

Conditions per sentence:
  F  flat: one chunk, no tone/pace/pause fields
  P  preset: tone firm_boundary (deflecting stage) — known sub-variance control
  T  timing: clause-chunked, pause_after_ms=700, pace steady (deterministic lever)
  G  tags: inline paralinguistic text tag "[firm] " prefix (audibility unknown:
     consumed vs spoken aloud — duration inflation is the tell)
  TG timing + tags

Measures per render: duration, longest-silence, total-silence (RMS gate),
f0 median/sd via pyin when librosa available. Writes incremental receipt so
progress is observable while running.
"""
from __future__ import annotations
import json, shutil, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/goal_v5/reach_screen"
OUT.mkdir(parents=True, exist_ok=True)
LOGS = Path.home() / "workspace/experiments/chatterbox/logs"

SENTENCES = {
    "assert1": "I looked at what you sent, and I think we should take it one step at a time, together.",
    "assert2": "The results are in, and the numbers support the plan we agreed on last week.",
    "quest1": "Do you want me to walk you through what changed, or should we start with the part that worried you?",
    "quest2": "Before we go further, can you tell me what outcome you actually need from this?",
}

def clause_chunks(text: str) -> list[str]:
    parts, cur = [], []
    for tok in text.split():
        cur.append(tok)
        if tok.endswith((",", ";")) and len(" ".join(cur)) > 15:
            parts.append(" ".join(cur)); cur = []
    if cur:
        parts.append(" ".join(cur))
    return parts if len(parts) > 1 else [text]

def chunks_for(cond: str, text: str):
    tag = "[firm] " if cond in ("G", "TG") else ""
    if cond in ("T", "TG"):
        segs = clause_chunks(text)
        return [{"chunk_id": f"c{i+1}", "text": (tag if i == 0 else "") + s,
                 "pace": "steady", "pause_strategy": "deliberate",
                 "pause_after_ms": 700 if i < len(segs) - 1 else 0}
                for i, s in enumerate(segs)]
    chunk = {"chunk_id": "c1", "text": tag + text}
    if cond == "P":
        chunk["tone"] = "firm_boundary"
    return [chunk]

def post(payload, timeout=300.0):
    req = urllib.request.Request("http://127.0.0.1:8018/tau/voice-render",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def analyze(path: str):
    import numpy as np, librosa
    y, sr = librosa.load(path, sr=None, mono=True)
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    thr = max(float(np.percentile(rms, 90)) * 0.06, 1e-4)
    sil = rms < thr
    hop_s = 512 / sr
    runs, cur = [], 0
    for s in sil:
        cur = cur + 1 if s else 0
        if cur:
            runs.append(cur)
    longest = max(runs) * hop_s if runs else 0.0
    f0, _, _ = librosa.pyin(y, fmin=65, fmax=400, sr=sr)
    f0v = f0[~np.isnan(f0)]
    return {"duration_s": round(len(y) / sr, 3),
            "total_silence_s": round(float(sil.sum()) * hop_s, 3),
            "longest_silence_s": round(float(longest), 3),
            "f0_median_hz": round(float(np.median(f0v)), 2) if f0v.size else None,
            "f0_sd_hz": round(float(np.std(f0v)), 2) if f0v.size else None}

def main():
    n = int(sys.argv[sys.argv.index("--renders") + 1]) if "--renders" in sys.argv else 5
    receipt_path = OUT / "reach_screen_receipt.v1.json"
    results = {}
    for sid, text in SENTENCES.items():
        for cond in ("F", "P", "T", "G", "TG"):
            key = f"{sid}_{cond}"
            results[key] = {"sentence": text, "condition": cond,
                            "chunks": chunks_for(cond, text), "renders": []}
            for i in range(n):
                payload = {"schema": "tau.voice_render_request.v1",
                           "conversation_id": "goal-v5-reach",
                           "turn_id": f"{key}_r{i}_{int(time.time())}",
                           "active_domain_persona": "embry",
                           "speakable_chunks": chunks_for(cond, text),
                           "label": f"reach_{key}_r{i}", "asr_verify": False}
                try:
                    r = post(payload)
                except Exception as e:
                    results[key]["renders"].append({"ok": False, "error": str(e)})
                    continue
                wavref = str(r.get("finished_response_audio") or "")
                rec = {"ok": bool(r.get("ok")), "wav": None}
                if wavref.startswith("/out/"):
                    host = LOGS / wavref[len("/out/"):]
                    dst = OUT / f"{key}_r{i}.wav"
                    try:
                        shutil.copy(host, dst)
                        rec["wav"] = str(dst)
                        rec.update(analyze(str(dst)))
                    except Exception as e:
                        rec["analysis_error"] = str(e)
                results[key]["renders"].append(rec)
                receipt_path.write_text(json.dumps(
                    {"schema": "persona_dream.reach_screen_receipt.v1",
                     "live": True, "n_renders": n, "in_progress": True,
                     "completed_cells": len([k for k in results if len(results[k]["renders"]) == n]),
                     "results": results}, indent=2))
                print(f"{key} r{i} ok={rec['ok']} dur={rec.get('duration_s')} "
                      f"longest_sil={rec.get('longest_silence_s')}", flush=True)
    receipt_path.write_text(json.dumps(
        {"schema": "persona_dream.reach_screen_receipt.v1", "live": True,
         "n_renders": n, "in_progress": False, "results": results}, indent=2))
    print("REACH_SCREEN_COMPLETE")

if __name__ == "__main__":
    main()
