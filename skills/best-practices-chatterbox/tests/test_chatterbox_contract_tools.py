from __future__ import annotations

import math
import sys
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chatterbox_contract_tools import (  # noqa: E402
    check_reference_audio,
    plan_render_chunks,
    preprocess_text,
    ssml_to_chatterbox,
    sweep_plan,
)


def test_preprocess_anchors_tags_and_emphasis() -> None:
    result = preprocess_text("I *cannot* -- [SIGH] keep pretending....")
    assert "CANNOT" in result
    assert "—" in result
    assert "... [sigh]" in result
    assert "pretending ..." in result


def test_ssml_break_and_expression_conversion() -> None:
    result = ssml_to_chatterbox('<speak>Wait <break time="800ms"/><express-as type="gasp">look out</express-as></speak>')
    assert "[pause:800ms]" in result
    assert "... [gasp]" in result
    assert "look out" in result


def test_plan_silence_compiles_pause_tokens_out_of_answer_text() -> None:
    plan = plan_render_chunks("I need a second. [pause:1.2s] [sniff] [sniff] ... give me a second.", tone="grief_safe")
    assert "[pause:" not in plan["answer_text"]
    assert plan["render_chunks"][0]["pause_after_ms"] == 1200
    assert plan["render_chunks"][0]["tone"] == "grief_safe"


def test_sweep_plan_is_backend_aware() -> None:
    plan = sweep_plan("hello", backend="chatterbox_base")
    assert plan["run_count"] == 16
    assert "chatterbox_turbo ignores" in plan["boundary"]


def test_reference_checker_accepts_clean_wav(tmp_path: Path) -> None:
    sample_rate = 24_000
    seconds = 3.2
    samples = array("h")
    for idx in range(int(sample_rate * seconds)):
        value = int(0.35 * 32767 * math.sin(2 * math.pi * 220 * idx / sample_rate))
        samples.append(value)
    path = tmp_path / "reference.wav"
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(samples.tobytes())
    report = check_reference_audio(path)
    assert report.duration_sec == 3.2
    assert report.clipping_ratio == 0.0
    assert report.rms_db > -35.0
