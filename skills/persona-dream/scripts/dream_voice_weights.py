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
import importlib.util
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


def _load(name):
    """Load a sibling script as a module (same pattern as write_dream_journal.py)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

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
    manifest_entries = None
    commit_id = node.get("commit_id")
    if commit_id:
        m = stored("persona_dream_commit_manifests", commit_id)
        if not m or not m.get("active") or not m.get("record_index"):
            raise SystemExit(
                f"BLOCKED_VOICE_WEIGHTS_MANIFEST_UNAVAILABLE: commit {commit_id} "
                "missing, inactive, or without record_index")
        manifest_entries = {(e["collection"], e["key"]) for e in m["record_index"]}
    out = []
    for cid in node.get("accepted_tom_candidate_ids") or []:
        doc = (stored("tom_candidates", f"dream:{persona}:{dream_id}:tom:{cid}")
               or stored("tom_candidates", cid))
        if not doc:
            raise SystemExit(f"BLOCKED_VOICE_WEIGHTS_TOM_MISSING: {cid}")
        if manifest_entries is not None:
            if ("tom_candidates", doc["_key"]) not in manifest_entries:
                raise SystemExit(f"BLOCKED_VOICE_WEIGHTS_TOM_NOT_MANIFEST_OWNED: {doc['_key']}")
            if doc.get("commit_id") != commit_id:
                raise SystemExit(f"BLOCKED_VOICE_WEIGHTS_TOM_COMMIT_MISMATCH: "
                                 f"{doc['_key']} commit={doc.get('commit_id')!r}")
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


def arc_state_brief(ledger: dict) -> dict:
    """Compact, plain summary of the persona's ACCUMULATED self (arc_state),
    the part that changes over cycles. Path B feeds this into the spoken line so
    the voice carries the accumulated character, not just today's dream."""
    arc = (ledger or {}).get("arc_state") or {}
    def _clip(items, n=4):
        return [str(x)[:200] for x in (items or [])][:n]
    deltas = arc.get("recent_arc_deltas") or []
    return {
        "self_claims": _clip(arc.get("current_self_claims")),
        "active_tensions": _clip(arc.get("active_tensions")),
        "earned_permissions": _clip(arc.get("earned_permissions")),
        "recurring_avoidances": _clip(arc.get("recurring_avoidances")),
        "cycles_lived": len(deltas),
        "latest_shift": (deltas[-1].get("now") if deltas else None),
    }


def arc_conditioned_line(persona_id: str, dream_statement: str, tag: str) -> dict:
    """Path B: generate the ONE short line the persona would actually SAY now,
    conditioned on (a) its accumulated self from the Continuity Ledger and
    (b) today's dream residue. The persona (system prompt + accumulated-self
    context) drives the wording, so the accumulated character is audible in what
    and how it is said. Routed through the documented /tau text-reasoning adapter
    (no direct scillm). Falls back to the raw dream statement if unavailable."""
    provenance = {"mode": "arc_conditioned", "persona_id": persona_id,
                  "fallback_used": False, "fallback_reason": None}
    try:
        continuity_ledger = _load("continuity_ledger")
        adapter = _load("tau_text_reasoning_adapter")
        ledger = continuity_ledger.read_ledger(persona_id)
        brief = arc_state_brief(ledger)
        core = (ledger or {}).get("identity_core") or {}
        persona_name = persona_id.replace("_", " ").title()
        prompt = (
            f"You ARE {persona_name}. This is your voice, spoken aloud, right now.\n\n"
            f"Who you are (immutable core): {json.dumps(core.get('persistent_conflicts') or core, ensure_ascii=False)[:600]}\n"
            f"Who you have BECOME across {brief['cycles_lived']} dream-cycles (this is the accumulated self "
            f"that must colour how you speak now):\n"
            f"- self-claims: {brief['self_claims']}\n"
            f"- active tensions: {brief['active_tensions']}\n"
            f"- earned permissions: {brief['earned_permissions']}\n"
            f"- recurring avoidances: {brief['recurring_avoidances']}\n"
            f"- most recent shift: {brief['latest_shift']}\n\n"
            f"Tonight's dream left this residue in you (emotional register '{tag}'):\n"
            f"  \"{str(dream_statement)[:300]}\"\n\n"
            f"Say ONE short line aloud (<= 30 words) — the thing you would actually say now, "
            f"in first person. It must sound like someone who has lived those {brief['cycles_lived']} "
            f"cycles: the wording, restraint, and emphasis carry the accumulated self, not a summary of it. "
            f"Do not explain, do not narrate the dream, do not name the emotion.\n\n"
            f'Respond ONLY as a JSON object: {{"spoken_line": "<the line>", '
            f'"why_this_wording": "<one short clause on what in the accumulated self shaped it>"}}'
        )
        parsed, _ = adapter.dispatch_text_reasoning(
            prompt, "persona-dream-arc-voice-line",
            output_contract={"spoken_line": "string", "why_this_wording": "string"})
        line = (parsed or {}).get("spoken_line", "").strip()
        if not line:
            raise RuntimeError("adapter returned no spoken_line")
        return {"line": line, "brief": brief,
                "why": (parsed or {}).get("why_this_wording", "").strip()[:300],
                "provenance": provenance}
    except Exception as e:  # noqa: BLE001 — Path B is additive; never break the deterministic path
        provenance.update(fallback_used=True, fallback_reason=str(e)[:200])
        return {"line": str(dream_statement), "brief": None, "why": None,
                "provenance": provenance}


def render_top_weight(profile: dict, out_dir: Path, spoken_line: str | None = None) -> dict:
    top = profile["weights"][0]
    line = spoken_line or top["sources"][0]["statement"] or "I dreamed, and something in it stayed with me."
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
    parser.add_argument("--arc-voice", action="store_true",
                        help="Path B: condition the spoken line on the persona's "
                             "accumulated arc_state (Continuity Ledger), so the voice "
                             "carries the accumulated character, not just today's dream.")
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

    spoken_line = None
    if args.arc_voice:
        top = profile["weights"][0]
        av = arc_conditioned_line(
            node.get("persona_id"),
            top["sources"][0]["statement"] or "",
            top["emotional_tag"])
        spoken_line = av["line"]
        profile["arc_voice"] = av  # audit: brief, generated line, provenance/fallback

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
        "arc_voice": profile.get("arc_voice"),  # Path B: arc_state-conditioned line + provenance
        "render": None,
        "live": None,  # set from the engine response after render
    }
    if args.render:
        receipt["render"] = render_top_weight(profile, out_dir, spoken_line=spoken_line)
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
