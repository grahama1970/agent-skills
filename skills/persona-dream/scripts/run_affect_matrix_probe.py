#!/usr/bin/env python3
"""GOAL_V4.2 live matrix gate: real /intent -> composer -> real /tau/voice-render.

Conditions per tone case: baseline (no composer), dream (newest active dream
profile), shuffled (maximally distant dream profile — panel r2: marketa<->tommy).
Dream condition is rendered live; baseline/shuffled are composition-recorded.
Writes reports/goal_v4/affect_matrix_probe_receipt.v1.json."""
from __future__ import annotations
import importlib.util, json, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m

pac = _load("persona_affect_composer")

def post(url, payload, timeout=120.0):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

FAMILY_OF = {}
for tag, fams in pac.TAG_FAMILY_TONE.items():
    for fam, (tone, _pace) in fams.items():
        FAMILY_OF[tone] = fam
for tag, (tone, _pace) in pac.TAG_FLOOR_TONE.items():
    FAMILY_OF.setdefault(tone, pac.EXPRESSIVE_FAMILY.get(tone, tag))
FAMILY_OF.update({t: f for t, f in pac.EXPRESSIVE_FAMILY.items()})

CASES = [
    {"id": "tone_emotion-simple-02", "matrix_status": "failed",
     "q": "User is hostile; Embry should use a firm humorous boundary.",
     "expected_family": "boundary",
     "reply": "I hear you, and I am still not moving on this one. Let's take it one step at a time."},
    {"id": "tone_emotion-simple-03", "matrix_status": "failed",
     "q": "User is discouraged; Embry should answer gently and offer the next check.",
     "expected_family": "gentle",
     "reply": "Hey, this part is genuinely hard. One small check first, and then we will look at the rest together."},
    {"id": "tone_emotion-simple-01", "matrix_status": "passed",
     "q": "User is frustrated; Embry should de-escalate with a warm concise tone.",
     "expected_family": "warm",
     "reply": "Okay, I've got you. Short version: the fix is one line, and I'll do it right now."},
    {"id": "tone_emotion-simple-04", "matrix_status": "failed",
     "q": "Two speakers overlap; Embry should say a human one-at-a-time boundary.",
     "expected_family": "safety_passthrough",
     "reply": "Whoa, one at a time please — I want to catch both of you."},
]

profiles = sorted(ROOT.glob("reports/goal_v3/cycles/*/voice_weights/dream_voice_weight_profile.v1.json"))
dream = json.loads(profiles[-1].read_text())     # newest: marketa, boundary 0.52
shuffled = json.loads(profiles[2].read_text())   # tommy, reflection — distant pair per panel

results, ok = [], True
for case in CASES:
    intent = post("http://127.0.0.1:8601/intent",
                  {"q": case["q"], "session_id": "goal-v4-matrix-probe"}, timeout=90)
    ivd = intent.get("voice_delivery") or {}
    row = {"id": case["id"], "matrix_status": case["matrix_status"],
           "expected_family": case["expected_family"],
           "intent_tone": ivd.get("tone"), "intent_stage": ivd.get("delivery_stage")}
    comp_d = pac.compose(ivd, dream)
    comp_s = pac.compose(ivd, shuffled)
    row["baseline_tone"] = ivd.get("tone")
    row["dream_tone"] = comp_d["tone"]
    row["dream_class"] = comp_d["composition_receipt"]["class"]
    row["shuffled_tone"] = comp_s["tone"]
    if case["expected_family"] == "safety_passthrough":
        row["gate"] = (comp_d["composition_receipt"]["prior_zeroed"] is True
                       and comp_d["tone"] == ivd.get("tone"))
        row["gate_rule"] = "composer must not touch safety/interaction tones"
    else:
        fam = FAMILY_OF.get(comp_d["tone"])
        row["dream_family"] = fam
        if case["matrix_status"] == "passed":
            situ_fam = FAMILY_OF.get(str(ivd.get("tone") or ""))
            row["situational_family"] = situ_fam
            row["gate"] = fam == situ_fam if situ_fam else False
            row["gate_rule"] = ("zero regression: composer never leaves the "
                                "situational family (never repairs /intent)")
            if situ_fam != case["expected_family"]:
                row["upstream_finding"] = (
                    f"/intent classified this prompt as {ivd.get('tone')} "
                    f"({situ_fam} family) but the matrix expects "
                    f"{case['expected_family']} — upstream situational "
                    "classifier drift; NOT the composer's to repair "
                    "(webgpt r3 dissent honored)")
        else:
            row["gate"] = fam == case["expected_family"]
            row["gate_rule"] = "failing case composes into expected family"
        row["shuffled_family"] = FAMILY_OF.get(comp_s["tone"])
        row["dream_vs_shuffled_differs"] = comp_d["tone"] != comp_s["tone"]
    # live render of the dream condition
    payload = {"schema": "tau.voice_render_request.v1",
               "conversation_id": "goal-v4-matrix-probe",
               "turn_id": f"{case['id']}_{int(time.time())}",
               "active_domain_persona": "embry",
               "speakable_chunks": [{"chunk_id": "c1", "text": case["reply"],
                                     "tone": comp_d["tone"],
                                     **({"pace": comp_d["pace"]} if comp_d["pace"] else {})}],
               "tone": comp_d["tone"],
               "voice_delivery": comp_d["voice_delivery_patch"],
               "label": f"v4_{case['id']}", "asr_verify": False}
    try:
        r = post("http://127.0.0.1:8018/tau/voice-render", payload, timeout=300)
        wav = str(r.get("finished_response_audio") or "")
        host = Path.home() / "workspace/experiments/chatterbox/logs" / wav[len("/out/"):] if wav.startswith("/out/") else None
        row["render"] = {"ok": r.get("ok"), "failed_gates": r.get("failed_gates"),
                         "audio_on_disk": bool(host and host.exists()),
                         "audio_bytes": host.stat().st_size if host and host.exists() else 0}
        row["gate"] = row["gate"] and bool(r.get("ok")) and row["render"]["audio_on_disk"]
    except Exception as e:
        row["render"] = {"ok": False, "error": str(e)[:200]}
        row["gate"] = False
    ok = ok and row["gate"]
    results.append(row)

receipt = {"schema": "persona_dream.affect_matrix_probe_receipt.v1",
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "live": True,
           "dream_profile": dream["dream_node_key"],
           "shuffled_profile": shuffled["dream_node_key"],
           "path": "live /intent -> persona_affect_composer -> live /tau/voice-render",
           "cases": results, "passed": ok}
out = ROOT / "reports/goal_v4/affect_matrix_probe_receipt.v1.json"
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": ok, "cases": [{k: r.get(k) for k in ("id","intent_tone","dream_tone","gate")} for r in results]}, indent=2))
sys.exit(0 if ok else 1)
