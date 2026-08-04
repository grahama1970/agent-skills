"""Contract tests for the append-only conversation writer (#1210).

The point of the writer is that a discussion about a dream outlives the browser
tab. So the properties worth testing are durability, append-only-ness, and the
asymmetry between an embry turn and a human one.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import append_conversation as ac  # noqa: E402


def _args(**kw):
    base = {"run_dir": None, "role": "human", "text": "hello", "tone": None,
            "audio": None, "created_at": "2026-01-01T00:00:00Z", "out": None, "json": False}
    base.update(kw)
    return type("Args", (), base)()


def _run_dir(tmp_path: Path) -> Path:
    d = tmp_path / "run"
    d.mkdir()
    (d / "journal_spoken.txt").write_text("I woke with what.\n", encoding="utf-8")
    return d


def test_a_turn_survives_the_process_that_wrote_it(tmp_path):
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, text="why did that memory surface"))
    assert r["status"] == "PASS_CONVERSATION_APPENDED"
    assert r["read_back"] is True
    rows = [json.loads(l) for l in (d / "conversation.jsonl").read_text().splitlines() if l.strip()]
    assert len(rows) == 1 and rows[0]["text"] == "why did that memory surface"


def test_appending_never_rewrites_an_earlier_turn(tmp_path):
    """A conversation you can edit afterwards is worth less than none."""
    d = _run_dir(tmp_path)
    ac.run(_args(run_dir=d, text="first"))
    ac.run(_args(run_dir=d, text="second"))
    r = ac.run(_args(run_dir=d, text="third"))
    rows = [json.loads(l) for l in (d / "conversation.jsonl").read_text().splitlines() if l.strip()]
    assert [x["text"] for x in rows] == ["first", "second", "third"]
    assert r["turns_before"] == 2 and r["turns_after"] == 3


def test_turn_is_bound_to_the_journal_it_discusses(tmp_path):
    """Otherwise a conversation could silently attach to a different run."""
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, text="about this entry"))
    assert r["appended"]["journal_spoken_sha256"].startswith("sha256:")


def test_embry_cannot_speak_without_a_tone_and_audio(tmp_path):
    """Her side must carry the same binding her journal does."""
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, role="embry", text="because I keep not resolving it"))
    assert r["status"] == "BLOCKED_CONVERSATION_APPEND"
    assert "embry_turn_requires_tone" in r["failed_gates"]
    assert "embry_turn_requires_audio" in r["failed_gates"]
    assert not (d / "conversation.jsonl").exists()


def test_embry_turn_records_tone_as_requested_not_achieved(tmp_path):
    d = _run_dir(tmp_path)
    (d / "journal.wav").write_bytes(b"RIFFfake")
    r = ac.run(_args(run_dir=d, role="embry", text="because I keep not resolving it",
                     tone="memory_uncertain", audio="journal.wav"))
    assert r["status"] == "PASS_CONVERSATION_APPENDED"
    turn = r["appended"]
    assert turn["requested_delivery_tone"] == "memory_uncertain"
    assert turn["audio"] == "journal.wav"
    assert turn["audio_sha256"].startswith("sha256:")
    assert "not achieved" in turn["tone_boundary"]


def test_a_human_turn_rejects_a_delivery_tone(tmp_path):
    """Dropping the flag silently would make the record claim less than the caller thinks."""
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, role="human", text="hi", tone="relieved"))
    assert r["status"] == "BLOCKED_CONVERSATION_APPEND"
    assert any("embry_only" in g for g in r["failed_gates"])


def test_empty_text_is_refused(tmp_path):
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, text="   "))
    assert r["status"] == "BLOCKED_CONVERSATION_APPEND"
    assert "empty_text" in r["failed_gates"]


def test_missing_audio_file_is_refused_rather_than_recorded(tmp_path):
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, role="embry", text="x", tone="relieved", audio="nope.wav"))
    assert r["status"] == "BLOCKED_CONVERSATION_APPEND"
    assert any(g.startswith("audio_not_found") for g in r["failed_gates"])


def test_receipt_never_claims_the_conversation_reached_memory(tmp_path):
    """The return arc is blocked upstream; the receipt must not imply otherwise."""
    d = _run_dir(tmp_path)
    r = ac.run(_args(run_dir=d, text="hello"))
    joined = " ".join(r["claims"]["does_not_prove"])
    assert "graph-memory-operator#99" in joined


def test_concurrent_writers_do_not_interleave_a_partial_line(tmp_path):
    """A human in one terminal and an agent in another must not corrupt a line."""
    d = _run_dir(tmp_path)
    procs = [
        subprocess.Popen(
            [sys.executable, str(SCRIPTS / "append_conversation.py"),
             "--run-dir", str(d), "--role", "agent", "--text", f"turn {i}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for i in range(8)
    ]
    for p in procs:
        p.wait(timeout=60)
    lines = [l for l in (d / "conversation.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 8
    for line in lines:
        json.loads(line)  # every line is whole and parseable
