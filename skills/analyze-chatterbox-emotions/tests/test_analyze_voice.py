from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_voice  # noqa: E402
import make_fixture_wav  # noqa: E402


def test_fixture_pause_and_quality_metrics(tmp_path: Path):
    wav = tmp_path / "fixture.wav"
    make_fixture_wav.write_fixture(wav)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"chatterbox_pause_plan": [{"pause_after_ms": 400}]}), encoding="utf-8")

    result = analyze_voice.analyze(
        wav,
        expected_text="hello tender voice",
        transcript="hello tender voice",
        target_label="tender",
        target_arousal=None,
        target_valence=None,
        render_plan=plan,
    )

    assert result["schema"] == "analyze_chatterbox_emotions.voice_eval.v1"
    assert result["prosody"]["duration_sec"] > 1.0
    assert result["pauses"]["planned_pause_after_ms"] == [400]
    assert result["pauses"]["pause_count"] >= 1
    assert result["quality"]["clipping_fraction"] == 0
    assert result["intelligibility"]["text_similarity"] == 1.0


def test_cli_writes_json_and_markdown(tmp_path: Path):
    wav = tmp_path / "fixture.wav"
    out = tmp_path / "out.json"
    report = tmp_path / "report.md"
    make_fixture_wav.write_fixture(wav)

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "analyze_voice.py"),
            "--audio",
            str(wav),
            "--target-label",
            "reassuring",
            "--expected-text",
            "hello world",
            "--transcript",
            "hello world",
            "--out",
            str(out),
            "--report",
            str(report),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    payload = json.loads(out.read_text())
    assert payload["schema"] == "analyze_chatterbox_emotions.voice_eval.v1"
    assert payload["status"] in {"PASS_VOICE_EVAL", "REVIEW_VOICE_EVAL", "FAIL_VOICE_EVAL"}
    assert "Chatterbox voice-quality evaluation" in report.read_text()
