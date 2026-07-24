#!/usr/bin/env python3
"""GOAL_V5 M-arm — compute-matched direct-memory affect profile.

The D-arm (dream_voice_weights.build_profile) maps the DREAM's ToM candidates
through TOM_TO_VOICE and averages emotional_intensity per tag. The M-arm applies
the IDENTICAL mapping and weight formula to ToM taken straight from the source
memories — no dream, no image, no VLM. Same math, same schema; the only
difference is the ToM substrate (raw memory vs dream). That is the controlled
D-vs-M contrast the panel required, and it is pure and offline.

Per cycle with a residue snapshot: fetch the residue memories, read each one's
own tom_state_type / emotional_intensity, and build a
memory_voice_weight_profile.v1.json next to the dream profile.
"""
from __future__ import annotations
import importlib.util, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

dvw = _load("dream_voice_weights")
adc = _load("autonomous_dream_cycle")


# Memory ToM tags use a wider vocabulary than the dream arm; crosswalk each into
# the SAME ALLOWED_TOM_STATES the dream's phase-14 candidates use, so both arms
# feed identical inputs to TOM_TO_VOICE. Unknown tags -> "uncertainty" (exactly
# phase14's deterministic default).
TAG_CROSSWALK = {
    "belief": "belief", "fear": "fear", "trust": "trust", "distrust": "distrust",
    "desire": "desire", "goal": "desire", "want": "desire",
    "boundary": "stance", "stance": "stance",
    "relationship": "relationship_state", "relationship_state": "relationship_state",
    "knowledge_gap": "uncertainty", "unresolved_thread": "uncertainty",
    "uncertainty": "uncertainty", "avoidance": "avoidance",
    "obligation": "obligation", "preference": "preference", "emotion": "emotion",
}


def _intensity_0_1(d) -> float:
    """Memories store emotional_intensity on a 1-5 scale; the dream arm's
    candidates are 0-1. Normalize to 0-1. Fall back to intensity_score (already
    0-1) or 0.3 (phase14's deterministic default)."""
    ei = d.get("emotional_intensity")
    if isinstance(ei, (int, float)):
        return round(min(1.0, ei / 5.0), 4) if ei > 1.0 else float(ei)
    isc = d.get("intensity_score")
    if isinstance(isc, (int, float)):
        return round(min(1.0, float(isc)), 4)
    return 0.3


def memory_toms(residue_items: list[dict], docs: dict) -> list[dict]:
    """One ToM record per (memory, crosswalked tom state), from the memory's OWN
    fields, normalized into the dream arm's vocabulary and scale."""
    toms = []
    for item in residue_items:
        d = docs.get(item.get("source_id")) or {}
        raw = list(d.get("tom_tags") or [])
        if d.get("tom_state_type"):
            raw += str(d["tom_state_type"]).split(",")
        states = {TAG_CROSSWALK.get(str(t).replace("tom:", "").strip(), "uncertainty")
                  for t in raw} or {"uncertainty"}
        ei = _intensity_0_1(d)
        for st in sorted(states):
            toms.append({
                "_key": f"{item.get('source_id')}:{st}",
                "tom_state_type": st,
                "emotional_intensity": ei,
                "statement": (d.get("tom_content") or d.get("claim_text")
                              or d.get("text") or ""),
            })
    return toms


def build_memory_profile(cycle_dir: Path, docs: dict) -> dict | None:
    rl = cycle_dir / "residue_links.json"
    if not rl.exists():
        return None
    residue = json.loads(rl.read_text())["items"]
    toms = memory_toms(residue, docs)
    node = {"_key": f"memory_arm_{cycle_dir.name}", "persona_id": "embry",
            "tom_state_types": sorted({t["tom_state_type"] for t in toms})}
    profile = dvw.build_profile(node, toms)
    profile["schema"] = "persona_dream.memory_voice_weight_profile.v1"
    profile["arm"] = "M_direct_memory"
    profile["derivation"] = ("compute_matched: identical TOM_TO_VOICE mapping and "
                             "mean-intensity weight formula as the dream arm, ToM "
                             "sourced from source memories not the dream")
    profile["source_memory_ids"] = [i.get("source_id") for i in residue]
    return profile


def main():
    docs = {d["_key"]: d for d in adc.fetch_embry_docs()}
    cycles = sorted((ROOT / "reports/goal_v3/cycles").iterdir())
    built = 0
    for cdir in cycles:
        if not (cdir / "voice_weights/dream_voice_weight_profile.v1.json").exists():
            continue
        prof = build_memory_profile(cdir, docs)
        if prof is None:
            continue
        out = cdir / "voice_weights/memory_voice_weight_profile.v1.json"
        out.write_text(json.dumps(prof, indent=2) + "\n")
        top = prof["weights"][0] if prof["weights"] else {}
        print(f"{cdir.name}: M top tag={top.get('emotional_tag')} "
              f"weight={top.get('weight')}", flush=True)
        built += 1
    print(f"built {built} memory-arm profiles")


if __name__ == "__main__":
    main()
