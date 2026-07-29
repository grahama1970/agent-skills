"""Unit checks for the blinded listener-study bundle validator."""
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


validator = _load("validate_blinded_listener_study")


def _valid_response(rater_id: str) -> dict:
    return {
        "rater_id": rater_id,
        "responses": [
            {
                "stimulus_id": "S01",
                "target_emotion_choice": "neutral",
                "embry_identity": "yes",
                "identity_confidence": 4,
                "naturalness": 4,
                "content_equivalent": "yes",
                "preference_rank": 1,
            }
        ],
    }


def _write_study(tmp_path: Path, *, response_count: int = 0, empty_responses: bool = False) -> Path:
    study = tmp_path / "study"
    stimuli = study / "stimuli"
    stimuli.mkdir(parents=True)
    audio = stimuli / "control.wav"
    audio.write_bytes(b"RIFF....WAVEfmt ")
    sha = validator.sha_file(audio)
    prereg = {
        "schema": "persona_dream.blinded_listener_study.v1",
        "stimulus_source": {"answer_text": "The answer is unchanged."},
        "presentation_manifest": [{"condition": "control", "stimulus_id": "S01"}],
        "stimuli": [
            {
                "condition": "control",
                "audio": str(audio),
                "bytes": audio.stat().st_size,
                "sha256": sha,
                "engine": "chatterbox_base",
                "voice_delivery": {"tone": "neutral", "intensity": 0.0, "valence": 0.0},
            }
        ],
    }
    (study / "PREREGISTRATION.json").write_text(json.dumps(prereg), encoding="utf-8")
    (study / "RESPONSE_SCHEMA.json").write_text(json.dumps({"schema": "test.response.schema"}), encoding="utf-8")
    (study / "RATER_INSTRUCTIONS.md").write_text("Use stimulus IDs only.\n", encoding="utf-8")
    rows = []
    for idx in range(response_count):
        rater_id = f"rater_{idx:03d}"
        row = {"rater_id": rater_id, "responses": []} if empty_responses else _valid_response(rater_id)
        rows.append(json.dumps(row))
    (study / "responses.jsonl").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return study


def test_matching_stimulus_hashes_are_ready_for_human_raters(tmp_path):
    study = _write_study(tmp_path)
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": None,
            "required_raters": 20,
            "asr": False,
            "asr_base_url": "http://127.0.0.1:9000",
            "asr_api_key": "none",
            "max_wer": 0.0,
        },
    )()

    receipt = validator.run(args)

    assert receipt["status"] == "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS"
    assert receipt["stimuli"][0]["hash_match"] is True
    assert receipt["responses_summary"]["unique_rater_count"] == 0
    assert "human_responses_complete" in receipt["failed_gates"]


def test_missing_stimulus_blocks(tmp_path):
    study = _write_study(tmp_path)
    (study / "stimuli" / "control.wav").unlink()
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": None,
            "required_raters": 20,
            "asr": False,
            "asr_base_url": "http://127.0.0.1:9000",
            "asr_api_key": "none",
            "max_wer": 0.0,
        },
    )()

    receipt = validator.run(args)

    assert receipt["status"] == "BLOCKED_BLINDED_LISTENER_STUDY"
    assert "stimulus_hash_match:control" in receipt["failed_gates"]


def test_enough_distinct_raters_can_advance_to_response_present_status(tmp_path):
    study = _write_study(tmp_path, response_count=2)
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": None,
            "required_raters": 2,
            "asr": False,
            "asr_base_url": "http://127.0.0.1:9000",
            "asr_api_key": "none",
            "max_wer": 0.0,
        },
    )()

    receipt = validator.run(args)

    assert receipt["status"] == "PASS_BLINDED_LISTENER_STUDY_RESPONSES_PRESENT"
    assert receipt["responses_summary"]["unique_rater_count"] == 2
    assert receipt["responses_summary"]["unique_valid_rater_count"] == 2


def test_empty_response_rows_do_not_count_as_complete(tmp_path):
    study = _write_study(tmp_path, response_count=2, empty_responses=True)
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": None,
            "required_raters": 2,
            "asr": False,
            "asr_base_url": "http://127.0.0.1:9000",
            "asr_api_key": "none",
            "max_wer": 0.0,
        },
    )()

    receipt = validator.run(args)

    assert receipt["status"] == "BLOCKED_BLINDED_LISTENER_STUDY"
    assert receipt["responses_summary"]["unique_rater_count"] == 2
    assert receipt["responses_summary"]["unique_valid_rater_count"] == 0
    assert "human_responses_complete" in receipt["failed_gates"]
    assert any("responses_missing" in gate for gate in receipt["failed_gates"])
