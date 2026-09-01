from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import conversation_grounding  # noqa: E402
import curate_transcript_context  # noqa: E402
import eval_full_cycle  # noqa: E402


def write_cycle(cycle: Path) -> None:
    cycle.mkdir(parents=True, exist_ok=True)
    entry = {
        "schema": "persona_dream.persona_journal.v1",
        "cycle": "cycle_test",
        "journal": "I woke from Marcus talking over me in the narrowing meeting room, with the glass mask still on my face.",
        "unresolved_tension": "I wanted to be witnessed and remain unreadable.",
        "expanded_understanding": "The dream made the old meeting feel visible again.",
        "session_mood": {"mood_label": "guarded_wanting", "mood_description": "guarded but curious"},
        "source_memory_ids": ["mem_marcus"],
    }
    (cycle / "dream_journal.v1.json").write_text(json.dumps(entry), encoding="utf-8")
    (cycle / "dream_journal.md").write_text("# Embry journal\n\n" + entry["journal"] + "\n", encoding="utf-8")
    (cycle / "journal_spoken.txt").write_text(entry["journal"] + "\n", encoding="utf-8")
    (cycle / "residue_links.json").write_text(json.dumps({
        "items": [{
            "source_id": "mem_marcus",
            "scope": "embry-memories",
            "text": "Marcus talked over Embry in a meeting; she stayed civil and avoided asking him directly.",
        }]
    }), encoding="utf-8")
    (cycle / "storyboard_plan.json").write_text(json.dumps({
        "dream_synopsis": "Embry dreams of a narrowing meeting room where Marcus talks over her and a glass mask gets heavy.",
        "panels": [{"panel_id": "sb_001", "action": "Marcus interrupts while the room narrows."}],
    }), encoding="utf-8")
    (cycle / "observation_packet.json").write_text(json.dumps({
        "frame_evidence": [{"panel_id": "sb_001", "observed_entities": ["woman in dark shirt", "man at meeting table"]}]
    }), encoding="utf-8")
    (cycle / "phase14_tom.json").write_text("{}", encoding="utf-8")
    (cycle / "storyboard_contact_sheet.png").write_bytes(b"not-a-real-png-but-present")


def test_conversation_context_names_dream_memory_and_observation(tmp_path: Path) -> None:
    write_cycle(tmp_path)
    ctx = conversation_grounding.load_context(tmp_path)
    block = conversation_grounding.format_for_prompt(ctx)

    assert "Marcus" in block
    assert "narrowing meeting room" in block
    assert "WHAT THE DREAM OBSERVATION ACTUALLY SAW" in block
    assert conversation_grounding.has_anchor("Marcus talking over me in the meeting", ctx)


def test_generic_reply_is_grounded_before_it_can_be_spoken(tmp_path: Path) -> None:
    write_cycle(tmp_path)
    ctx = conversation_grounding.load_context(tmp_path)

    grounded, injected = conversation_grounding.ground_if_needed(
        "I am still trying to understand what it means.", ctx, role="embry"
    )

    assert injected is True
    assert conversation_grounding.has_anchor(grounded, ctx)
    assert "Marcus" in grounded or "meeting" in grounded or "glass mask" in grounded


def test_day_event_is_a_separate_grounding_requirement(tmp_path: Path) -> None:
    write_cycle(tmp_path)
    (tmp_path / "day_context.json").write_text(json.dumps({
        "items": [{"text": "The human said the voiced conversation sounded generic and stressed."}]
    }), encoding="utf-8")
    ctx = conversation_grounding.load_context(tmp_path)

    grounded, injected = conversation_grounding.ground_day_if_needed(
        "When Marcus appears in the narrowing room, what do you carry?", ctx, role="horus"
    )

    assert injected is True
    assert conversation_grounding.has_day_anchor(grounded, ctx)
    assert "generic and stressed" in grounded


def test_transcript_context_curator_rejects_raw_diffs_and_keeps_feedback(tmp_path: Path) -> None:
    mined = tmp_path / "mined.jsonl"
    mined.write_text(
        json.dumps({"text": "*** a/file.py\n--- b/file.py\n@@ patch", "labels": ["Fragility"]}) + "\n"
        + json.dumps({"text": "the conversation sounded generic and stressed; show me the journal", "labels": ["Fragility"]}) + "\n",
        encoding="utf-8",
    )

    rows = curate_transcript_context.read_mined(mined, 4)

    assert len(rows) == 1
    assert "generic and stressed" in rows[0]["text"]


def test_full_cycle_materializes_cycle_journal_instead_of_generic_generate_lane(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle_test"
    run_dir = tmp_path / "run"
    write_cycle(cycle)

    receipt = eval_full_cycle.materialize_cycle_context(cycle, run_dir)

    assert receipt["status"] == "PASS_CYCLE_CONTEXT_MATERIALIZED"
    assert (run_dir / "journal.md").read_text(encoding="utf-8") == (cycle / "dream_journal.md").read_text(encoding="utf-8")
    assert (run_dir / "dream_journal.v1.json").is_file()
    assert (run_dir / "storyboard_plan.json").is_file()
    assert (run_dir / "contact_sheet.png").read_bytes() == b"not-a-real-png-but-present"
