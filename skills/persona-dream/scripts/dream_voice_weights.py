#!/usr/bin/env python3
"""GOAL_V3.1: derive chatterbox voice weights from a canonical dream node.

The dream is the persona's affect engine (operator purpose statement,
GOAL_V2_AMENDMENT_1): its ToM states and interpretations become weights for
conversational tone and emotional tags consumed by the chatterbox voice.

Deterministic mapping (frozen in this file):
  ToM state type -> (emotional_tag, tone, pace)
    desire      -> ("yearning",     "yearning_warm",        "measured")
    stance      -> ("boundary",     "firm_boundary",        "steady")
    trust       -> ("warmth",       "warm_open",            "relaxed")
    uncertainty -> ("hesitance",    "hesitant_reflective",  "measured")
    (other)     -> ("reflection",   "neutral_reflective",   "measured")
  weight = mean(emotional_intensity of contributing ToM candidates), read
  live from the store; synthesis temperature = 0.6 + 0.3 * max_intensity
  (clamped to [0.6, 0.9]), inside chatterbox's supported param set.

--render synthesizes the top-weighted tag through the LIVE /synthesize route
using the dream's own top-intensity ToM statement as the spoken line, and the
receipt binds dream key -> profile sha -> WAV sha (ffprobe-verified).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GMO = "http://127.0.0.1:8601"
CHATTERBOX = "http://127.0.0.1:8018"
CHATTERBOX_OUT_HOST = Path.home() / "workspace/experiments/chatterbox/logs"

TOM_TO_VOICE = {
    "desire": ("yearning", "yearning_warm", "measured"),
    "stance": ("boundary", "firm_boundary", "steady"),
    "trust": ("warmth", "warm_open", "relaxed"),
    "uncertainty": ("hesitance", "hesitant_reflective", "measured"),
}
DEFAULT_VOICE = ("reflection", "neutral_reflective", "measured")


def post(url: str, payload: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def stored(collection: str, key: str) -> dict | None:
    for vs in ("active", "pending", None):
        filt: dict = {"_key": key}
        if vs:
            filt["visibility_state"] = vs
        docs = post(f"{GMO}/list", {"collection": collection,
                                    "filters": filt}).get("documents") or []
        if docs:
            return docs[0]
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_tom_candidates(node: dict) -> list[dict]:
    """Fail closed on missing candidates; when the dream has a commit
    manifest, every loaded candidate key must be manifest-owned."""
    persona = node.get("persona_id")
    dream_id = node.get("dream_id")
    manifest_keys = None
    commit_id = node.get("commit_id")
    if commit_id:
        m = stored("persona_dream_commit_manifests", commit_id)
        if m and m.get("record_index"):
            manifest_keys = {e["key"] for e in m["record_index"]}
    out = []
    for cid in node.get("accepted_tom_candidate_ids") or []:
        doc = (stored("tom_candidates", f"dream:{persona}:{dream_id}:tom:{cid}")
               or stored("tom_candidates", cid))
        if not doc:
            raise SystemExit(f"BLOCKED_VOICE_WEIGHTS_TOM_MISSING: {cid}")
        if manifest_keys is not None and doc["_key"] not in manifest_keys:
            raise SystemExit(f"BLOCKED_VOICE_WEIGHTS_TOM_NOT_MANIFEST_OWNED: {doc['_key']}")
        out.append(doc)
    return out


def build_profile(node: dict, toms: list[dict]) -> dict:
    groups: dict[str, list[dict]] = {}
    for t in toms:
        tag, tone, pace = TOM_TO_VOICE.get(str(t.get("tom_state_type")), DEFAULT_VOICE)
        groups.setdefault(tag, []).append({"tone": tone, "pace": pace, "tom": t})
    weights = []
    max_intensity = 0.0
    for tag, members in sorted(groups.items()):
        intensities = [
            float(m["tom"]["emotional_intensity"])
            if m["tom"].get("emotional_intensity") is not None else 0.5
            for m in members]
        weight = sum(intensities) / len(intensities)
        max_intensity = max(max_intensity, max(intensities))
        weights.append({
            "emotional_tag": tag,
            "tone": members[0]["tone"],
            "pace": members[0]["pace"],
            "weight": round(weight, 4),
            "sources": [{"tom_key": m["tom"].get("_key"),
                         "tom_state_type": m["tom"].get("tom_state_type"),
                         "emotional_intensity": m["tom"].get("emotional_intensity"),
                         "statement": str(m["tom"].get("statement"))[:200]}
                        for m in members],
        })
    weights.sort(key=lambda w: -w["weight"])
    return {
        "schema": "persona_dream.dream_voice_weight_profile.v1",
        "dream_node_key": node["_key"],
        "persona_id": node.get("persona_id"),
        "tom_state_types": node.get("tom_state_types"),
        "weights": weights,
        "synthesis_params": {
            "temperature": round(min(0.9, max(0.6, 0.6 + 0.3 * max_intensity)), 3),
        },
        "mapping": "frozen in scripts/dream_voice_weights.py (TOM_TO_VOICE)",
    }


def render_top_weight(profile: dict, out_dir: Path) -> dict:
    top = profile["weights"][0]
    line = top["sources"][0]["statement"] or "I dreamed, and something in it stayed with me."
    label = f"vw_{profile['dream_node_key'][-12:]}_{top['emotional_tag']}"
    resp = post(f"{CHATTERBOX}/synthesize", {
        "text": line, "label": label,
        "tone": top["tone"], "pace": top["pace"],
        "temperature": profile["synthesis_params"]["temperature"],
    }, timeout=180.0)
    audio_ref = str(resp.get("audio") or "")
    if not audio_ref.startswith("/out/"):
        raise RuntimeError(f"unexpected audio ref: {audio_ref!r}")
    host = CHATTERBOX_OUT_HOST / audio_ref[len("/out/"):]
    if not host.exists():
        raise RuntimeError(f"rendered audio missing on host: {host}")
    wav = out_dir / f"{label}.wav"
    shutil.copy(host, wav)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(wav)], capture_output=True, text=True, timeout=30)
    duration = float(probe.stdout.strip() or 0)
    if duration <= 0.2:
        raise RuntimeError(f"rendered audio invalid: duration={duration}")
    return {
        "wav": str(wav),
        "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "duration_seconds": duration,
        "rendered_tag": top["emotional_tag"],
        "tone": top["tone"], "pace": top["pace"],
        "line": line[:200],
        "engine_meta": {k: v for k, v in resp.items() if k not in ("audio",)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dream-key", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    node = stored("persona_memory", args.dream_key)
    if not node or node.get("visibility_state") not in ("active", None):
        print(f"BLOCKED_VOICE_WEIGHTS_DREAM_NOT_ACTIVE: {args.dream_key}", file=sys.stderr)
        return 2
    toms = load_tom_candidates(node)
    if not toms:
        print("BLOCKED_VOICE_WEIGHTS_NO_TOM_CANDIDATES", file=sys.stderr)
        return 2

    out_dir = args.out_dir or (ROOT / "reports/goal_v3/voice_weights" / args.dream_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = build_profile(node, toms)
    profile_path = out_dir / "dream_voice_weight_profile.v1.json"
    profile_path.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n")

    receipt = {
        "schema": "persona_dream.dream_voice_weights_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dream_node_key": args.dream_key,
        "tom_candidates_read": len(toms),
        "profile_path": str(profile_path),
        "profile_sha256": sha256_text(profile_path.read_text()),
        "weights_summary": [{k: w[k] for k in ("emotional_tag", "tone", "weight")}
                            for w in profile["weights"]],
        "render": None,
        "live": None,  # set from the engine response after render
    }
    if args.render:
        receipt["render"] = render_top_weight(profile, out_dir)
        em = receipt["render"].get("engine_meta") or {}
        receipt["live"] = bool(em.get("live", em.get("engine") == "chatterbox_turbo"))
    receipt_path = out_dir / "dream_voice_weights_receipt.v1.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"profile": receipt["weights_summary"],
                      "render": (receipt["render"] or {}).get("wav_sha256", "not-rendered")[:16],
                      "receipt": str(receipt_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
