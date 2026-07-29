"""Unit checks for the blinded listener-study analysis receipt."""
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


analyzer = _load("analyze_blinded_listener_study")


STIMULI = [
    ("control", "S01", "neutral"),
    ("dream", "S02", "firm_boundary"),
    ("adversarial", "S03", "cheerful"),
    ("baseline", "S04", "careful_concerned"),
]


def _valid_response(rater_id: str) -> dict:
    return {
        "rater_id": rater_id,
        "responses": [
            {
                "stimulus_id": stimulus_id,
                "target_emotion_choice": tone,
                "embry_identity": "yes",
                "identity_confidence": 4,
                "naturalness": 4,
                "content_equivalent": "yes",
                "preference_rank": idx,
            }
            for idx, (_condition, stimulus_id, tone) in enumerate(STIMULI, start=1)
        ],
    }


def _write_study(tmp_path: Path, *, response_count: int = 0, signed: bool = False) -> Path:
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
                "sha256": analyzer.sha_file(audio),
                "engine": "chatterbox_base",
                "voice_delivery": {"tone": tone, "intensity": 0.5, "valence": -0.1},
            }
        )
    prereg = {
        "schema": "persona_dream.blinded_listener_study.v1",
        "stimulus_source": {"answer_text": "The answer is unchanged."},
        "presentation_manifest": manifest,
        "stimuli": stimuli,
    }
    (study / "PREREGISTRATION.json").write_text(json.dumps(prereg), encoding="utf-8")
    (study / "STIMULUS_VALIDATION_RECEIPT.json").write_text(
        json.dumps({"status": "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS"}),
        encoding="utf-8",
    )
    rows = [_valid_response(f"rater_{idx:03d}") for idx in range(response_count)]
    (study / "responses.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    if signed:
        (study / "SIGNED_INTERPRETATION.json").write_text(
            json.dumps(
                {
                    "schema": "persona_dream.blinded_listener_study_signed_interpretation.v1",
                    "signed_by": "human_reviewer",
                    "signed_at": "2026-07-29T12:00:00Z",
                    "interpretation": "The raw counts were reviewed without changing the preregistered rule.",
                    "acknowledgements": {
                        "human_raters_only": True,
                        "no_llm_judge": True,
                        "no_agent_self_rating": True,
                        "raw_counts_reviewed": True,
                    },
                }
            ),
            encoding="utf-8",
        )
    return study


def _args(study: Path, *, required_raters: int = 2):
    return type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": study / "RECEIPT.json",
            "signed_interpretation": None,
            "required_raters": required_raters,
            "json": True,
        },
    )()


def test_analysis_blocks_without_human_responses_and_signature(tmp_path):
    receipt = analyzer.run(_args(_write_study(tmp_path)))

    assert receipt["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_ANALYSIS"
    assert "human_responses_complete" in receipt["failed_gates"]
    assert "signed_human_interpretation_missing" in receipt["failed_gates"]
    assert receipt["claims"]["proves"] == []


def test_analysis_blocks_when_responses_exist_without_signed_interpretation(tmp_path):
    receipt = analyzer.run(_args(_write_study(tmp_path, response_count=2)))

    assert receipt["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_ANALYSIS"
    assert "human_responses_complete" not in receipt["failed_gates"]
    assert "signed_human_interpretation_missing" in receipt["failed_gates"]
    assert receipt["response_analysis"]["primary_measure"]["result"]["successes"] == 2


def test_analysis_passes_with_valid_responses_and_signed_interpretation(tmp_path):
    receipt = analyzer.run(_args(_write_study(tmp_path, response_count=2, signed=True)))

    assert receipt["status"] == "PASS_BLINDED_LISTENER_STUDY_ANALYSIS"
    assert receipt["failed_gates"] == []
    assert receipt["response_analysis"]["included_human_raters"] == 2
    assert receipt["response_analysis"]["by_condition"]["dream"]["target_emotion_recognition"]["proportion"] == 1.0
    assert receipt["signed_interpretation_summary"]["signed_by"] == "human_reviewer"


def test_preregistered_attention_rule_excludes_adversarial_dream_tone_choice(tmp_path):
    study = _write_study(tmp_path, response_count=2, signed=True)
    rows = [json.loads(line) for line in (study / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[0]["responses"][2]["target_emotion_choice"] = "firm_boundary"
    (study / "responses.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    receipt = analyzer.run(_args(study))

    assert receipt["status"] == "PASS_BLINDED_LISTENER_STUDY_ANALYSIS"
    assert receipt["response_analysis"]["included_human_raters"] == 1
    assert receipt["response_analysis"]["excluded_by_preregistered_attention_rule"] == ["rater_000"]
