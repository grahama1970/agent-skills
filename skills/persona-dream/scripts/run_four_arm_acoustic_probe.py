#!/usr/bin/env python3
"""Four-arm same-sentence acoustic experiment (panel-converged design).

Arms, identical sentence, all rendered live through /tau/voice-render:
  flat      — no tone (engine default)
  static    — Embry's current live default (memory_confident path: tone omitted,
              label distinct) rendered with tone 'memory_confident'
  dream     — HER newest dream profile composed via persona_affect_composer
              (bland situational input -> dispositional floor)
  wrong     — maximally distant dream profile (panel: marketa<->tommy pair)

Then deterministic prosody extraction per WAV (librosa pinned): F0 mean/SD/
range via pyin, voiced fraction, RMS mean/SD, duration, pause fraction
(low-energy frames). Receipt records raw metrics + deltas vs flat + the
dream-vs-wrong separation. This is the ACOUSTIC gate; perceived affect
still requires the blinded human read (sealed packet produced separately).
"""
from __future__ import annotations
import importlib.util, json, shutil, sys, time, urllib.request
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/goal_v4/four_arm"
OUT.mkdir(parents=True, exist_ok=True)
SENTENCE = ("I looked at what you sent, and I think we should take it "
            "one step at a time, together.")

def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m

def post(url, payload, timeout=300.0):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

pac = _load("persona_affect_composer")
profiles = sorted(ROOT.glob("reports/goal_v3/cycles/*/voice_weights/dream_voice_weight_profile.v1.json"))
dream = json.loads(profiles[-1].read_text())    # marketa: boundary 0.52
wrong = json.loads(profiles[2].read_text())     # tommy: reflection (distant pair)
comp_dream = pac.compose({"tone": "memory_confident"}, dream)
comp_wrong = pac.compose({"tone": "memory_confident"}, wrong)

ARMS = {
    "flat": {},
    "static": {"tone": "memory_confident"},
    "dream": {"tone": comp_dream["tone"], "pace": comp_dream["pace"]},
    "wrong": {"tone": comp_wrong["tone"], "pace": comp_wrong["pace"]},
}
N_RENDERS = int(sys.argv[sys.argv.index("--renders") + 1]) if "--renders" in sys.argv else 5
renders = {}
for arm, tags in ARMS.items():
    wavs = []
    for i in range(N_RENDERS):
        chunk = {"chunk_id": "c1", "text": SENTENCE, **tags}
        payload = {"schema": "tau.voice_render_request.v1",
                   "conversation_id": "goal-v4-four-arm",
                   "turn_id": f"{arm}_r{i}_{int(time.time())}",
                   "active_domain_persona": "embry",
                   "speakable_chunks": [chunk],
                   **({"tone": tags["tone"]} if "tone" in tags else {}),
                   "label": f"fourarm_{arm}_r{i}", "asr_verify": False}
        r = post("http://127.0.0.1:8018/tau/voice-render", payload)
        if not r.get("ok"):
            raise SystemExit(f"render failed: {arm} r{i}: {r}")
        wavref = str(r.get("finished_response_audio") or "")
        host = Path.home() / "workspace/experiments/chatterbox/logs" / wavref[len("/out/"):]
        dst = OUT / f"{arm}_r{i}.wav"
        shutil.copy(host, dst)
        wavs.append(str(dst))
        print(f"{arm} r{i}: rendered ok tags={tags}", flush=True)
    renders[arm] = {"ok": True, "tags": tags, "wavs": wavs}

import librosa
def prosody(path):
    y, sr = librosa.load(path, sr=None, mono=True)
    f0, voiced, _ = librosa.pyin(y, fmin=65, fmax=400, sr=sr)
    f0v = f0[~np.isnan(f0)]
    rms = librosa.feature.rms(y=y)[0]
    thresh = np.percentile(rms, 20)
    return {"duration_s": round(len(y)/sr, 3),
            "f0_mean_hz": round(float(np.mean(f0v)), 2) if f0v.size else None,
            "f0_sd_hz": round(float(np.std(f0v)), 2) if f0v.size else None,
            "f0_range_hz": round(float(np.percentile(f0v, 90) - np.percentile(f0v, 10)), 2) if f0v.size else None,
            "voiced_fraction": round(float(np.mean(voiced)), 3),
            "rms_mean": round(float(np.mean(rms)), 5),
            "rms_sd": round(float(np.std(rms)), 5),
            "low_energy_fraction": round(float(np.mean(rms < thresh + 1e-9)), 3),
            "speech_rate_proxy_syl_s": round(len(SENTENCE.split()) * 1.4 / (len(y)/sr), 2)}

KEYS = ("duration_s", "f0_mean_hz", "f0_sd_hz", "f0_range_hz", "voiced_fraction",
        "rms_mean", "rms_sd", "low_energy_fraction", "speech_rate_proxy_syl_s")
per_render = {arm: [prosody(w) for w in r["wavs"]] for arm, r in renders.items()}
def summarize(rows):
    out = {}
    for k in KEYS:
        vals = [r[k] for r in rows if r.get(k) is not None]
        if vals:
            out[k] = round(float(np.median(vals)), 3)
            out[k + "_spread"] = round(float(np.max(vals) - np.min(vals)), 3)
    return out
metrics = {arm: summarize(rows) for arm, rows in per_render.items()}
flat = metrics["flat"]
deltas = {}
for arm in ("static", "dream", "wrong"):
    deltas[arm] = {k: round(metrics[arm][k] - flat[k], 3)
                   for k in ("f0_mean_hz", "f0_sd_hz", "f0_range_hz",
                             "duration_s", "speech_rate_proxy_syl_s")
                   if metrics[arm].get(k) is not None and flat.get(k) is not None}
sep = {k: round(abs(metrics["dream"][k] - metrics["wrong"][k]), 3)
       for k in ("f0_mean_hz", "f0_sd_hz", "duration_s", "speech_rate_proxy_syl_s")
       if metrics["dream"].get(k) is not None and metrics["wrong"].get(k) is not None}
# same-parameter variance calibration: flat and wrong render with identical
# sampling params by design (wrong composes calm_precise -> neutral stage);
# their per-metric spreads bound single-render synthesis variance.
variance_calibration = {
    k: {"flat_spread": metrics["flat"].get(k + "_spread"),
        "wrong_spread": metrics["wrong"].get(k + "_spread"),
        "dream_median_shift_vs_flat": (round(metrics["dream"][k] - metrics["flat"][k], 3)
                                       if metrics["dream"].get(k) is not None
                                       and metrics["flat"].get(k) is not None else None)}
    for k in ("f0_mean_hz", "f0_sd_hz", "f0_range_hz", "duration_s",
              "speech_rate_proxy_syl_s", "voiced_fraction")}
receipt = {"schema": "persona_dream.four_arm_acoustic_receipt.v2",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sentence": SENTENCE, "live": True,
           "n_renders_per_arm": N_RENDERS,
           "arms": {a: {"tags": r["tags"], "wavs": r["wavs"]} for a, r in renders.items()},
           "per_render_metrics": per_render,
           "variance_calibration": variance_calibration,
           "dream_profile": dream["dream_node_key"], "wrong_profile": wrong["dream_node_key"],
           "dream_composed_tone": comp_dream["tone"], "wrong_composed_tone": comp_wrong["tone"],
           "metrics": metrics, "deltas_vs_flat": deltas,
           "dream_vs_wrong_separation": sep,
           "caveat": "acoustic gate only; perceived affect requires the "
                     "blinded human read (sealed packet)"}
(OUT / "four_arm_acoustic_receipt.v2.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"metrics": metrics, "dream_vs_wrong_separation": sep}, indent=2))
