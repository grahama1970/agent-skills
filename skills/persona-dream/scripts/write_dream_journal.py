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


def build_prompt(cyc: Path) -> dict:
    sb = json.loads((cyc / "storyboard_plan.json").read_text())
    sel = json.loads((cyc / "selection_receipt.v1.json").read_text())["chosen"]
    tom = json.loads((cyc / "phase14_tom.json").read_text()).get("accepted_tom_candidates", [])
    w = json.loads((cyc / "voice_weights/dream_voice_weight_profile.v1.json").read_text())["weights"]
    tags = [(x["emotional_tag"], x["weight"]) for x in w]
    states = "\n".join(f"- {t.get('tom_state_type')}: {t.get('statement')}" for t in tom[:5])
    competing = ", ".join(f"{t}({round(v,2)})" for t, v in tags)
    prompt = (
        "You are Embry, writing a short private journal entry the morning after "
        "this dream. Write in FIRST PERSON, past tense, plainly — a self "
        "reflecting on itself, not a report.\n\n"
        f"The dream (synthetic, not literal memory): {sb.get('dream_synopsis','')}\n\n"
        f"What the dream stirred in you, in tension with itself: {competing}.\n"
        f"Inferred inner states:\n{states}\n\n"
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
    return {"prompt": prompt, "emphasis": sel.get("valence_emphasis"),
            "tags": tags, "cycle": cyc.name}


def main():
    if "--cycle" not in sys.argv:
        raise SystemExit("usage: write_dream_journal.py --cycle <name>")
    cyc = ROOT / "reports/goal_v3/cycles" / sys.argv[sys.argv.index("--cycle") + 1]
    meta = build_prompt(cyc)
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
    }
    (cyc / "dream_journal.v1.json").write_text(json.dumps(entry, indent=2) + "\n")
    (cyc / "dream_journal.md").write_text(
        f"# Embry's journal — {meta['cycle']} ({meta['emphasis']} emphasis)\n\n"
        f"{entry['journal']}\n\n---\n*Unresolved: {entry['unresolved_tension']}*\n"
        f"*(synthetic dream reflection; dream-provenance, not a dream seed)*\n")
    print(f"journal written ({len(entry['journal'].split())} words)")
    print("MOOD:", entry["session_mood"]["mood_label"], "|",
          entry["session_mood"]["mood_description"])
    print("UNRESOLVED:", entry["unresolved_tension"])
    print("---")
    print(entry["journal"])


if __name__ == "__main__":
    main()
