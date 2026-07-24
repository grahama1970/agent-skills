#!/usr/bin/env python3
"""Close the loop: after Embry WATCHES her dream, she writes a first-person
journal entry about it — the way a human might after waking.

This is where conflict becomes personality (operator theory 2026-07-24): the
structured ToM tags MEASURE the tension; the journal is where Embry HOLDS it in
her own voice. The entry is prompted to SUSTAIN the ambivalence, never resolve
it — the unresolved pull is the point.

Loop-guard safe (GOAL_V4.3): the entry carries dream provenance
(affect_source=persona_dream) so it is EXCLUDED from future dream SEEDING; it
enriches identity/self-retrieval without creating the dream->journal->memory->
dream amplification the loop guard prevents.

Run:  python3 scripts/write_dream_journal.py --cycle <cycle_dir_name>
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m

adapter = _load("tau_text_reasoning_adapter")
adc = _load("autonomous_dream_cycle")


def _edge_targets(doc) -> list[str]:
    """Read graph edges under BOTH corpus conventions (target_memory_id AND
    target_id) — half the edged memories use each; reading one misses the other."""
    out = []
    for e in (doc.get("graph_edges_raw") or []):
        if isinstance(e, dict):
            t = e.get("target_memory_id") or e.get("target_id")
            if t:
                out.append(t)
    return out


def traverse_memory_web(seed_ids, docs, hops: int = 2) -> list[dict]:
    """Multi-hop /memory graph traversal from the dream's source memories.
    Returns, per reached node, the real characters/places/objects (entity_text)
    and the clear theory-of-mind (tom_content) — the grounded web the journal
    reflects across. Deterministic BFS, de-duplicated, hop-labeled."""
    seen, frontier, web = set(seed_ids), list(seed_ids), []
    for h in range(hops + 1):
        nxt = []
        for k in frontier:
            d = docs.get(k) or {}
            web.append({
                "memory_id": k, "hop": h,
                "entities": d.get("entity_text") or "",
                "tom_state_type": d.get("tom_state_type"),
                "tom": (d.get("tom_content") or "")[:240],
                "claim": (d.get("claim_text") or d.get("text") or "")[:160],
            })
            for t in _edge_targets(d):
                if t not in seen:
                    seen.add(t); nxt.append(t)
        frontier = nxt
        if not frontier:
            break
    return web


def build_prompt(cyc: Path, docs: dict) -> dict:
    sb = json.loads((cyc / "storyboard_plan.json").read_text())
    sel = json.loads((cyc / "selection_receipt.v1.json").read_text())["chosen"]
    tom = json.loads((cyc / "phase14_tom.json").read_text()).get("accepted_tom_candidates", [])
    w = json.loads((cyc / "voice_weights/dream_voice_weight_profile.v1.json").read_text())["weights"]
    residue = json.loads((cyc / "residue_links.json").read_text())["items"]
    seed_ids = [i["source_id"] for i in residue]
    web = traverse_memory_web(seed_ids, docs, hops=2)   # multi-hop /memory graph
    tags = [(x["emotional_tag"], x["weight"]) for x in w]
    states = "\n".join(f"- {t.get('tom_state_type')}: {t.get('statement')}" for t in tom[:5])
    competing = ", ".join(f"{t}({round(v,2)})" for t, v in tags)
    web_lines = "\n".join(
        f"- (hop {n['hop']}) {n['entities']} | she felt [{n['tom_state_type']}]: {n['tom']}"
        for n in web if n["entities"] or n["tom"])
    prompt = (
        "You are Embry, writing a short private journal entry the morning after "
        "this dream. Write in FIRST PERSON, past tense, plainly — a self "
        "reflecting on itself, not a report.\n\n"
        f"The dream (synthetic, not literal memory): {sb.get('dream_synopsis','')}\n\n"
        f"What the dream stirred in you, in tension with itself: {competing}.\n"
        f"Inferred inner states:\n{states}\n\n"
        "The web of memory this dream reaches (multi-hop — real people, places, "
        "objects you carry, and what you felt about each). Let your reflection "
        "MOVE across this web; ground it in these specific people/places/objects, "
        "not abstractions:\n" + (web_lines or "(no linked web)") + "\n\n"
        "RULES — this is self-reflection that DEEPENS the conflict, not resolves it:\n"
        "- REINFORCE and EXPAND the conflict. These feelings pull against each "
        "other (e.g. wanting closeness AND keeping a boundary). Turn the tension "
        "over; find a NEW facet of it, or a further question inside it, or what it "
        "reveals about who you are. Connect it outward.\n"
        "- Understanding the conflict does NOT mean dissolving it. A deeper "
        "understanding should make the two pulls SHARPER and more real, not "
        "tidier. Do NOT land on a lesson, a decision, or a resolution. End with "
        "the tension standing — ideally larger and better understood than it began.\n"
        "- Question your own reaction. Notice what the dream shows you about "
        "yourself; do not flatter or reassure yourself.\n"
        "- It is a dream, not a memory. Refer to it as a dream; assert no new "
        "facts about real people.\n"
        "- 140-220 words. No title, no preamble.\n\n"
        "Then name the MOOD this leaves you in — the lingering affective state "
        "you would carry into tomorrow's conversations (not a single feeling but "
        "the tension itself as a mood, e.g. 'guarded and quietly wanting'). This "
        "mood should persist across a whole session, coloring how you show up, "
        "not just one reply.\n\n"
        "Return STRICT JSON: {\"journal\": \"<the entry>\", "
        "\"unresolved_tension\": \"<one line naming the two feelings left in "
        "conflict>\", \"expanded_understanding\": \"<one line: the NEW facet or "
        "question the reflection opened up in the conflict>\", "
        "\"mood_label\": \"<2-4 words, snake_case, the carried mood>\", "
        "\"mood_description\": \"<one line: the mood you carry into a session>\"}")
    web_entities = " || ".join(n["entities"] for n in web if n["entities"])
    tom_summary = " || ".join(f"[{n['tom_state_type']}] {n['tom']}"
                              for n in web if n["tom"])
    return {"prompt": prompt, "emphasis": sel.get("valence_emphasis"),
            "tags": tags, "cycle": cyc.name, "seed_ids": seed_ids,
            "web_entities": web_entities, "tom_summary": tom_summary,
            "web_size": len(web)}


def persist_persona_journal(entry: dict, cyc: Path) -> dict:
    """Write the journal as a first-class document in the persona_journal /memory
    collection (parallel to persona_memory) via GMO /upsert, then EXACT read-back.
    The entry INCLUDES its multi-hop memory web (people/places/objects + ToM) and
    its dream FRAMES (the intense non-textual content) with a multimodal
    qdrant-embedding hint, so Embry can later RECALL it by image/mood, not only
    text. Kept OUT of persona_memory so it never re-seeds a dream (loop guard)."""
    key = f"embry_journal_{cyc.name}"
    frames = sorted(str(p) for p in (cyc / "frames").glob("sb_*.attempt_01.png"))
    contact = cyc / "storyboard_contact_sheet.png"
    doc = dict(entry)
    doc["_key"] = key
    doc["persona_id"] = adc.PERSONA
    doc["collection"] = "persona_journal"
    doc["text"] = entry["journal"]
    doc["retrieval_text"] = entry["journal"]
    doc["entity_text"] = entry.get("memory_web_entities", "")
    doc["tom_content"] = entry.get("tom_summary", "")
    # multimodal: the dream's non-textual content, embedded so recall can surface
    # the intense image/mood, not only the words.
    doc["media"] = {"frames": frames,
                    "contact_sheet": str(contact) if contact.exists() else None}
    doc["qdrant_embedding"] = {"modalities": ["text", "image"],
                               "text_source": "journal",
                               "image_sources": frames,
                               "target_qdrant_collection_hint": "persona_journal"}
    # link back into the memory web it reflected across (traversable/recallable)
    doc["graph_edges_raw"] = [{"edge_type": "reflects_on", "target_id": sid}
                              for sid in entry.get("source_memory_ids", [])]
    try:
        adc.post("/upsert", {"collection": "persona_journal", "documents": [doc]})
        back = adc.post("/list", {"collection": "persona_journal",
                                  "filters": {"_key": key}, "limit": 2})
        got = (back.get("documents") or [])
        ok = len(got) == 1 and got[0].get("_key") == key \
            and got[0].get("text") == entry["journal"]
        return {"persisted": ok, "key": key, "readback_count": len(got),
                "collection": "persona_journal", "frames": len(frames)}
    except Exception as e:  # noqa: BLE001
        return {"persisted": False, "key": key, "error": str(e)[:200]}


def main():
    if "--cycle" not in sys.argv:
        raise SystemExit("usage: write_dream_journal.py --cycle <name>")
    cyc = ROOT / "reports/goal_v3/cycles" / sys.argv[sys.argv.index("--cycle") + 1]
    docs = {d["_key"]: d for d in adc.fetch_embry_docs()}
    meta = build_prompt(cyc, docs)
    parsed, _ = adapter.dispatch_text_reasoning(
        meta["prompt"], "persona-dream-journal",
        output_contract={"journal": "string", "unresolved_tension": "string",
                         "expanded_understanding": "string",
                         "mood_label": "string", "mood_description": "string"})
    if not parsed or not parsed.get("journal"):
        raise SystemExit("BLOCKED_JOURNAL_NO_PARSE")
    entry = {
        "schema": "persona_dream.dream_journal.v1",
        "cycle": meta["cycle"],
        "valence_emphasis": meta["emphasis"],
        "competing_affect": meta["tags"],
        "journal": parsed["journal"].strip(),
        "unresolved_tension": parsed.get("unresolved_tension", "").strip(),
        "expanded_understanding": parsed.get("expanded_understanding", "").strip(),
        # session-facing: the carried MOOD that influences a user session
        # (a persistent dispositional state, not per-utterance /intent tone)
        "session_mood": {
            "mood_label": (parsed.get("mood_label") or "").strip(),
            "mood_description": (parsed.get("mood_description") or "").strip(),
            "carried_tension": parsed.get("unresolved_tension", "").strip(),
            "source_cycle": meta["cycle"],
            "affect_source": "persona_dream",
        },
        # loop-guard: dream-descended -> excluded from future dream seeding
        "affect_source": "persona_dream",
        "dream_provenance": {"cycle": meta["cycle"], "kind": "dream_journal",
                             "excluded_from_dream_seeding": True},
        # SELF-NARRATIVE layer, NOT episodic event-fact. The journal fills in
        # Embry's own inner detail (self-discovery / confabulation). It may
        # enrich identity/mood/self-retrieval but must NEVER be promoted to
        # event-fact canon or assert new facts about other people (that would be
        # the counterpart-leak the GOAL_V3 gate prevents).
        "memory_kind": "self_narrative",
        "canon_status": "synthetic_self_reflection",
        "never_promote_to_event_fact": True,
        "asserts_only_own_inner_state": True,
        # the multi-hop /memory web this reflection is grounded in (real people,
        # places, objects + ToM) — same substrate persona-dream traverses.
        "memory_web_entities": meta["web_entities"],
        "tom_summary": meta["tom_summary"],
        "memory_web_size": meta["web_size"],
        "source_memory_ids": meta["seed_ids"],
    }
    (cyc / "dream_journal.v1.json").write_text(json.dumps(entry, indent=2) + "\n")
    (cyc / "dream_journal.md").write_text(
        f"# Embry's journal — {meta['cycle']} ({meta['emphasis']} emphasis)\n\n"
        f"{entry['journal']}\n\n---\n*Unresolved: {entry['unresolved_tension']}*\n"
        f"*(synthetic dream reflection; dream-provenance, not a dream seed)*\n")
    persist = persist_persona_journal(entry, cyc)
    print(f"journal written ({len(entry['journal'].split())} words) | "
          f"memory-web hops entities={entry['memory_web_size']}")
    print("MOOD:", entry["session_mood"]["mood_label"], "|",
          entry["session_mood"]["mood_description"])
    print("persona_journal persist:", persist)
    print("---")
    print(entry["journal"])


if __name__ == "__main__":
    main()
