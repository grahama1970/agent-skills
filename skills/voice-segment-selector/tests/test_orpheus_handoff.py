from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from lib.orpheus_handoff import _apply_literal_tag_asr_check, _prompt_event_tags, build_model_card, publish_orpheus_model


def test_build_model_card_includes_provenance() -> None:
    card = build_model_card(
        speaker="embry",
        repo_id="user/embry-orpheus-lora",
        train_receipt={"schema": "voice_segment_selector.orpheus_train_receipt.v1", "example_count": 10, "model_name": "unsloth/orpheus-3b-0.1-ft", "dataset": "/tmp/hf_dataset", "train_metrics": {"train_loss": 4.2}},
        inference_receipt={"schema": "voice_segment_selector.orpheus_inference_receipt.v1", "status": "PASS", "wav_path": "/tmp/inference_smoke.wav", "duration_sec": 2.5},
    )
    assert "embry" in card
    assert "user/embry-orpheus-lora" in card
    assert "Limitations" in card
    assert "## Evaluation" in card
    assert "## Training" in card


def test_publish_blocks_without_inference_pass(tmp_path: Path) -> None:
    lora = tmp_path / "lora"
    lora.mkdir()
    (lora / "adapter_config.json").write_text("{}", encoding="utf-8")
    (lora.parent / "train_receipt.json").write_text(json.dumps({"example_count": 1}), encoding="utf-8")
    (lora.parent / "inference_receipt.json").write_text(json.dumps({"status": "FAIL"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Inference receipt"):
        publish_orpheus_model(
            speaker="embry",
            lora_dir=lora,
            publish_dir=tmp_path / "publish",
            repo_id="user/embry-orpheus-lora",
            execute=False,
        )


def test_prompt_event_tags_detects_square_bracket_audio_tag() -> None:
    assert _prompt_event_tags("I've got a bad cold.. [cough!!!!!!] Continue.") == ["cough"]
    assert _prompt_event_tags("[laugh] What do you mean?!") == ["laugh"]


def test_literal_tag_asr_check_fails_when_tag_word_is_spoken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = tmp_path / "inference_smoke.wav"
    wav.write_bytes(b"RIFFfake")

    fake_transcribe = types.ModuleType("lib.transcribe")
    fake_transcribe.transcribe_clip = lambda path: ("I've got a bad cold. Cough. Continue.", 0.51)
    monkeypatch.setitem(sys.modules, "lib.transcribe", fake_transcribe)

    receipt = _apply_literal_tag_asr_check(
        receipt={"status": "PASS", "prompt": "I've got a bad cold.. [cough!!!!!!] Continue."},
        output_dir=tmp_path,
        prompt="I've got a bad cold.. [cough!!!!!!] Continue.",
    )

    assert receipt["status"] == "FAIL"
    assert receipt["verified"] == "literal_tag_spoken"
    assert receipt["literal_tag_check"]["spoken_literal_tags"] == ["cough"]


def test_literal_tag_asr_check_passes_when_tag_word_is_not_spoken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = tmp_path / "inference_smoke.wav"
    wav.write_bytes(b"RIFFfake")

    fake_transcribe = types.ModuleType("lib.transcribe")
    fake_transcribe.transcribe_clip = lambda path: ("I've got a bad cold. Continue.", 0.77)
    monkeypatch.setitem(sys.modules, "lib.transcribe", fake_transcribe)

    receipt = _apply_literal_tag_asr_check(
        receipt={"status": "PASS", "prompt": "I've got a bad cold.. [cough!!!!!!] Continue."},
        output_dir=tmp_path,
        prompt="I've got a bad cold.. [cough!!!!!!] Continue.",
    )

    assert receipt["status"] == "PASS"
    assert receipt["literal_tag_check"]["status"] == "PASS"
    assert receipt["literal_tag_check"]["spoken_literal_tags"] == []
