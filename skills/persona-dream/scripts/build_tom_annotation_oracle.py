#!/usr/bin/env python3
"""GOAL_V5 Gate 2 — source-to-affect annotation oracle builder.

Per cycle: take the frozen residue snapshot (residue_links.json) and produce
  D = the certified dream-derived affect profile (tags/weights/ToM summaries,
      NO dream prose)
  M = direct-memory affect profile derived deterministically from the SAME
      residue texts with a dream-free lexicon mapper (v0; recorded limitation:
      not compute-matched to the dream pipeline — upgrade before listener use)
then emit blinded packets: profiles shuffled to A/B per cycle (order sealed by
sha256 of the cycle id), with the sealed key written separately. Annotators see
source memories + counterpart + anonymized profiles only.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/goal_v5/tom_oracle"
OUT.mkdir(parents=True, exist_ok=True)

LEXICON = {
    "boundary": ["boundary", "chose not", "stays", "refuse", "plainly", "duty",
                 "priorit", "limit", "no.", "declin", "firm", "keeps to"],
    "warmth": ["together", "family", "helps", "laugh", "warm", "grandmother",
               "recipe", "shared", "thanks", "close", "comfort"],
    "hesitance": ["unsure", "hesit", "maybe", "uncertain", "worri", "afraid",
                  "doubt", "pause", "waits"],
    "yearning": ["misses", "wish", "longing", "reminder", "distant", "away",
                 "wants", "hopes", "someday", "call"],
    "reflection": ["later she", "admits", "thinks", "realizes", "considers",
                   "looking back", "understands", "learns", "chooses",
                   "decision", "choice"],
}


def memory_affect_profile(residue_items: list[dict]) -> dict:
    """Dream-free deterministic mapper: residue text -> tag weights."""
    scores = {t: 0 for t in LEXICON}
    evidence = {t: [] for t in LEXICON}
    for item in residue_items:
        text = str(item.get("text") or "").lower()
        for tag, kws in LEXICON.items():
            for kw in kws:
                if kw in text:
                    scores[tag] += 1
                    if len(evidence[tag]) < 3:
                        evidence[tag].append(
                            {"source_id": item.get("source_id"), "keyword": kw})
    total = sum(scores.values()) or 1
    weights = sorted(
        ({"emotional_tag": t, "weight": round(s / total, 3),
          "evidence": evidence[t]} for t, s in scores.items() if s),
        key=lambda w: -w["weight"])
    return {"schema": "persona_dream.memory_affect_profile.v0",
            "derivation": "deterministic_lexicon_dream_free",
            "compute_matched": False,
            "weights": weights}


def anonymize(profile: dict, kind: str) -> dict:
    ws = []
    for w in profile.get("weights", [])[:3]:
        row = {"emotional_tag": w["emotional_tag"],
               "weight": w.get("weight")}
        if kind == "D":
            row["tom_summaries"] = [s.get("statement")
                                    for s in w.get("sources", [])][:2]
        ws.append(row)
    return {"ranked_affect": ws}


def main():
    cycles = sorted((ROOT / "reports/goal_v3/cycles").iterdir())
    packets, key = [], {}
    for cdir in cycles:
        rl = cdir / "residue_links.json"
        dp = cdir / "voice_weights/dream_voice_weight_profile.v1.json"
        if not (rl.exists() and dp.exists()):
            continue
        residue = json.loads(rl.read_text())["items"]
        dream = json.loads(dp.read_text())
        mem = memory_affect_profile(residue)
        (OUT / f"{cdir.name}_memory_affect_profile.v0.json").write_text(
            json.dumps(mem, indent=2) + "\n")
        counterparts = sorted({p for item in residue for p in
                               str(item.get("text", "")).split("people:")[-1]
                               .split(";")[0].split(",")})
        first_is_dream = int(hashlib.sha256(cdir.name.encode())
                             .hexdigest(), 16) % 2 == 0
        pair = ([("A", "D"), ("B", "M")] if first_is_dream
                else [("A", "M"), ("B", "D")])
        key[cdir.name] = {label: kind for label, kind in pair}
        profs = {"D": anonymize(dream, "D"), "M": anonymize(mem, "M")}
        packets.append({
            "packet_id": cdir.name,
            "source_memories": [{"source_id": i.get("source_id"),
                                 "text": i.get("text")} for i in residue],
            "counterpart_candidates": [c.strip() for c in counterparts
                                       if c.strip()][:6],
            "profiles": {label: profs[kind] for label, kind in pair},
        })
    (OUT / "annotation_packets.v1.json").write_text(json.dumps(
        {"schema": "persona_dream.tom_annotation_packets.v1",
         "blinding": "profiles labeled A/B; D/M mapping sealed separately",
         "n_packets": len(packets), "packets": packets}, indent=2) + "\n")
    (OUT / "SEALED_blinding_key.json").write_text(json.dumps(
        {"schema": "persona_dream.tom_annotation_blinding_key.v1",
         "do_not_open_until": "all three annotator responses captured",
         "key": key}, indent=2) + "\n")
    print(f"built {len(packets)} packets; key sealed")


if __name__ == "__main__":
    main()
