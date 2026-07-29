"""Unit checks for the static blinded listener-study rater page."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = _load("render_blinded_listener_rater_page")


STIMULI = [
    ("control", "S01", "neutral"),
    ("dream", "S02", "firm_boundary"),
    ("adversarial", "S03", "cheerful"),
    ("baseline", "S04", "careful_concerned"),
]


def _write_study(tmp_path: Path) -> Path:
    study = tmp_path / "study"
    stimuli_dir = study / "stimuli"
    stimuli_dir.mkdir(parents=True)
    manifest = []
    stimuli = []
    for slot, (condition, stimulus_id, tone) in enumerate(STIMULI, start=1):
        audio = stimuli_dir / f"{condition}.wav"
        audio.write_bytes(f"RIFF....WAVEfmt {condition}".encode())
        manifest.append({"condition": condition, "slot": slot, "stimulus_id": stimulus_id})
        stimuli.append(
            {
                "condition": condition,
                "audio": str(audio),
                "bytes": audio.stat().st_size,
                "sha256": renderer.sha_file(audio),
                "engine": "chatterbox_base",
                "voice_delivery": {"tone": tone, "intensity": 0.5, "valence": -0.1},
            }
        )
    prereg = {
        "schema": "persona_dream.blinded_listener_study.v1",
        "presentation_manifest": manifest,
        "stimuli": stimuli,
    }
    response_schema = {
        "schema": "persona_dream.blinded_listener_response_schema.v1",
        "response_object_contract": {
            "target_emotion_choice": {
                "allowed_values": ["neutral", "careful_concerned", "firm_boundary", "cheerful"]
            }
        },
        "example_row": {
            "rater_id": "human_001",
            "responses": [{"stimulus_id": "S01", "target_emotion_choice": "neutral"}],
        },
    }
    (study / "PREREGISTRATION.json").write_text(json.dumps(prereg), encoding="utf-8")
    (study / "RESPONSE_SCHEMA.json").write_text(json.dumps(response_schema), encoding="utf-8")
    (study / "responses.jsonl").write_text("", encoding="utf-8")
    return study


def _args(study: Path):
    return type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": study / "rater_page.html",
            "receipt_out": study / "RATER_PAGE_RECEIPT.json",
            "json": True,
        },
    )()


def test_rater_page_uses_blinded_audio_filenames_and_no_condition_labels(tmp_path):
    study = _write_study(tmp_path)

    receipt = renderer.run(_args(study))
    html = (study / "rater_page.html").read_text(encoding="utf-8")

    assert receipt["status"] == "PASS_BLINDED_LISTENER_RATER_PAGE_READY"
    assert receipt["failed_gates"] == []
    assert "stimuli/control.wav" not in html
    assert "stimuli/dream.wav" not in html
    assert "stimuli/adversarial.wav" not in html
    assert "stimuli/baseline.wav" not in html
    for _condition, stimulus_id, _tone in STIMULI:
        blinded = study / "blinded_stimuli" / f"{stimulus_id}.wav"
        assert blinded.is_file()
        assert f"blinded_stimuli/{stimulus_id}.wav" in html
        assert stimulus_id in html


def test_rater_page_blocks_when_preregistered_audio_hash_changes(tmp_path):
    study = _write_study(tmp_path)
    (study / "stimuli" / "dream.wav").write_bytes(b"changed")

    receipt = renderer.run(_args(study))

    assert receipt["status"] == "BLOCKED_BLINDED_LISTENER_RATER_PAGE"
    assert "stimulus_hash_match:S02" in receipt["failed_gates"]
    assert receipt["claims"]["proves"] == []
