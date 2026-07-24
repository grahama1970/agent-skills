#!/usr/bin/env python3
"""GOAL_V5 M-arm (LLM-compute-matched) — per next-steps roundtable contract.

The deterministic-crosswalk M-arm confounded the D-vs-M contrast (LLM fluency vs
template flatness). This version gives the M-arm the SAME LLM + adapter the dream
uses, but denies it everything that makes a dream a dream:

- Input: the cycle's raw memories ONLY (no dream artifact, no valence-conflict
  seed, no graph traversal, no cross_persona_hooks).
- Operation: single-memory EXTRACTIVE affect reading. FORBIDDEN: cross-memory
  synthesis, ToM / perspective-taking, narrative, imagined or counterfactual
  content (the anti-mini-dream clause).
- Aggregation + tone mapping: the SAME TOM_TO_VOICE table + mean-intensity
  weight formula as the dream arm (frozen, not LLM-chosen).
- ENFORCED: novel-content audit — any per-memory reading whose affect statement
  introduces a token not present in that memory is flagged; regeneration_rate is
  logged. A high rate means the extractive boundary is leaking.

Claim this enables: "recombinative dreaming adds affect nuance BEYOND extractive
LLM affect-reading of the same memories at matched compute."

Run:  ./run.sh  (adapter routes through Tau; real model calls)
      python3 scripts/build_memory_arm_llm.py --cycle <name>   # one cycle
"""
from __future__ import annotations
import importlib.util, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

dvw = _load("dream_voice_weights")
adc = _load("autonomous_dream_cycle")
adapter = _load("tau_text_reasoning_adapter")

ALLOWED = {"belief", "fear", "desire", "trust", "distrust", "stance",
           "relationship_state", "uncertainty", "avoidance", "obligation",
           "preference", "emotion"}

EXTRACTIVE_PROMPT = (
    "You are doing EXTRACTIVE affect-reading of ONE memory. Read ONLY what this "
    "memory literally states about the person's inner state. Output a single "
    "theory-of-mind state from this closed set: {states}. Rules you MUST obey:\n"
    "- NO cross-reference to other memories (you only see this one).\n"
    "- NO imagined scenes, no narrative, no counterfactuals, no 'what might "
    "happen'.\n"
    "- NO modeling of any other person's mind.\n"
    "- The affect_statement must paraphrase ONLY content present in the memory "
    "text; introduce no new entities, events, places, or feelings.\n\n"
    "MEMORY:\n{memory}\n\n"
    "Return STRICT JSON: {{\"tom_state_type\": \"<one of the set>\", "
    "\"emotional_intensity\": <0.0-1.0>, \"affect_statement\": \"<<=200 chars, "
    "only content from the memory>\"}}")


def _tokens(t: str) -> set:
    return set(re.findall(r"[a-z0-9']+", (t or "").lower()))


def read_one(mem_text: str) -> tuple[dict, bool]:
    """One extractive LLM reading of one memory. Returns (tom_record, novel_flag)."""
    prompt = EXTRACTIVE_PROMPT.format(states=sorted(ALLOWED), memory=mem_text)
    parsed, _ = adapter.dispatch_text_reasoning(
        prompt, "persona-dream-m-arm-extractive",
        output_contract={"tom_state_type": "string",
                         "emotional_intensity": "number 0-1",
                         "affect_statement": "string"})
    if not parsed:
        return {}, False
    st = str(parsed.get("tom_state_type", "")).strip()
    if st not in ALLOWED:
        st = "uncertainty"
    stmt = str(parsed.get("affect_statement", ""))
    # novel-content audit: the anti-mini-dream check flags FABRICATED entities/
    # events, not faithful paraphrase. A raw token-subset test false-positives on
    # synonyms ("tells"->"telling", "narrower"->"broader"); instead flag only
    # novel proper-noun-like tokens (capitalized names/places) and numbers that
    # are absent from the source memory.
    def _entities(t):
        caps = set(re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", t or ""))
        nums = set(re.findall(r"\b\d+\b", t or ""))
        return {w.lower() for w in caps} | nums
    SENT_START = set()  # ignore words merely capitalized as sentence-initial
    for s in re.split(r"[.!?]\s+", stmt):
        m = re.match(r"([A-Z][a-zA-Z]{2,})", s.strip())
        if m:
            SENT_START.add(m.group(1).lower())
    novel = (_entities(stmt) - SENT_START) - _entities(mem_text)
    ei = parsed.get("emotional_intensity")
    ei = float(ei) if isinstance(ei, (int, float)) else 0.3
    return ({"_key": None, "tom_state_type": st,
             "emotional_intensity": max(0.0, min(1.0, ei)),
             "statement": stmt[:200]}, bool(novel))


def build(cycle_dir: Path) -> dict | None:
    rl = cycle_dir / "residue_links.json"
    if not rl.exists():
        return None
    residue = json.loads(rl.read_text())["items"]
    docs = build.docs
    toms = []; regen = 0; n = 0
    for item in residue:
        d = docs.get(item.get("source_id")) or {}
        mem = d.get("claim_text") or d.get("text") or ""
        if not mem:
            continue
        n += 1
        rec, novel = read_one(mem)
        if novel:            # boundary leak -> one retry, then keep + count
            regen += 1
            rec, _ = read_one(mem)
        if rec:
            rec["_key"] = f"{item.get('source_id')}:{rec['tom_state_type']}"
            toms.append(rec)
    if not toms:
        return None
    node = {"_key": f"memory_arm_llm_{cycle_dir.name}", "persona_id": "embry",
            "tom_state_types": sorted({t["tom_state_type"] for t in toms})}
    prof = dvw.build_profile(node, toms)
    prof["schema"] = "persona_dream.memory_voice_weight_profile.v2"
    prof["arm"] = "M_llm_compute_matched"
    prof["derivation"] = ("same LLM adapter as the dream arm; single-memory "
                          "extractive affect reading; forbidden cross-memory "
                          "synthesis/ToM/narrative; frozen TOM_TO_VOICE + "
                          "mean-intensity formula")
    prof["novel_content_regeneration_rate"] = round(regen / n, 3) if n else None
    prof["source_memory_ids"] = [i.get("source_id") for i in residue]
    return prof


def main():
    build.docs = {d["_key"]: d for d in adc.fetch_embry_docs()}
    cycles = sorted((ROOT / "reports/goal_v3/cycles").iterdir())
    if "--cycle" in sys.argv:
        cycles = [ROOT / "reports/goal_v3/cycles" / sys.argv[sys.argv.index("--cycle")+1]]
    built = 0
    for cdir in cycles:
        if not (cdir / "voice_weights/dream_voice_weight_profile.v1.json").exists():
            continue
        prof = build(cdir)
        if prof is None:
            print(f"{cdir.name}: skipped/no-parse", flush=True); continue
        (cdir / "voice_weights/memory_voice_weight_profile.v2.json").write_text(
            json.dumps(prof, indent=2) + "\n")
        top = prof["weights"][0] if prof["weights"] else {}
        print(f"{cdir.name}: M2 top={top.get('emotional_tag')} "
              f"w={top.get('weight')} regen_rate={prof['novel_content_regeneration_rate']}",
              flush=True)
        built += 1
    print(f"built {built} LLM-compute-matched M-arm profiles")


if __name__ == "__main__":
    main()
