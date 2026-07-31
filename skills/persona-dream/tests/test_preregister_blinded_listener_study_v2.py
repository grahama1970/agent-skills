"""#1126 v2 design-receipt checks: counterbalancing, ITT primary, independent catch.

Negative fixtures pin the fail-closed behaviour the ticket requires: restoring
the v1 fixed global order or the outcome-dependent adversarial exclusion must
fail the focused check, and v1 human rows must block v2 activation.
"""
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prereg_v2 = _load("preregister_blinded_listener_study_v2")
analyzer = _load("analyze_blinded_listener_study")


def _copy_study(tmp_path: Path) -> Path:
    study = tmp_path / "study"
    study.mkdir()
    for name in (
        "PREREGISTRATION.json",
        "RESPONSE_SCHEMA.json",
        "RATER_INSTRUCTIONS.md",
        "rater_page.html",
    ):
        shutil.copyfile(STUDY_DIR / name, study / name)
    (study / "responses.jsonl").write_text("", encoding="utf-8")
    return study


def _run(study: Path, out: Path):
    args = type("Args", (), {"study_dir": study, "out": out, "dry_run": False})()
    return prereg_v2.run(args)


def test_real_bundle_design_receipt_passes(tmp_path):
    study = _copy_study(tmp_path)
    got = _run(study, tmp_path / "receipt.json")
    assert got["status"] == "PASS_BLINDED_LISTENER_STUDY_DESIGN_V2", got["failed_gates"]
    assert got["checks"]["distinct_counterbalanced_orders"] >= 4
    assert got["checks"]["v1_zero_responses_before_activation"] is True
    assert (study / "PREREGISTRATION_V2.json").is_file()
    assert (study / "responses_v2.jsonl").is_file()


def test_v1_human_rows_block_activation(tmp_path):
    study = _copy_study(tmp_path)
    prereg = json.loads((study / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    tones = {
        str((s.get("voice_delivery") or {}).get("tone"))
        for s in prereg["stimuli"]
    }
    row = {
        "rater_id": "human_v1",
        "created_at": "2026-07-30T00:00:00Z",
        "responses": [
            {
                "stimulus_id": item["stimulus_id"],
                "target_emotion_choice": sorted(tones)[0],
                "embry_identity": "yes",
                "identity_confidence": 3,
                "naturalness": 3,
                "content_equivalent": "yes",
                "preference_rank": idx,
            }
            for idx, item in enumerate(prereg["presentation_manifest"], start=1)
        ],
    }
    (study / "responses.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    got = _run(study, tmp_path / "receipt.json")

    assert got["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_DESIGN_V2"
    assert "v1_responses_present_requires_fresh_v2_response_file" in got["failed_gates"]
    assert not (study / "PREREGISTRATION_V2.json").is_file()


def test_restoring_fixed_global_order_fails(tmp_path, monkeypatch):
    """A single global order for every rater must fail the counterbalance gate."""
    study = _copy_study(tmp_path)
    monkeypatch.setattr(
        prereg_v2, "order_for_rater", lambda rater_id, ids: list(ids)
    )

    got = _run(study, tmp_path / "receipt.json")

    assert got["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_DESIGN_V2"
    assert "counterbalanced_orders_insufficient" in got["failed_gates"]


def test_restoring_adversarial_exclusion_fails(tmp_path, monkeypatch):
    """Re-introducing outcome-based exclusion into the primary analysis must fail."""
    study = _copy_study(tmp_path)

    real = analyzer.summarize_responses_v2

    def excluding(rows, *, prereg, valid_row_indexes):
        got = real(rows, prereg=prereg, valid_row_indexes=valid_row_indexes)
        primary = got["primary"]
        primary["excluded_rater_ids"] = ["itt_confused"]
        primary["included_rater_ids"] = [
            rid for rid in primary["included_rater_ids"] if rid != "itt_confused"
        ]
        return got

    monkeypatch.setattr(
        prereg_v2, "_load_module",
        lambda name: analyzer if name == "analyze_blinded_listener_study" else _load(name),
    )
    monkeypatch.setattr(analyzer, "summarize_responses_v2", excluding)

    got = _run(study, tmp_path / "receipt.json")

    assert got["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_DESIGN_V2"
    assert "primary_analysis_excludes_on_outcome" in got["failed_gates"]


def test_condition_labels_in_page_fail(tmp_path):
    study = _copy_study(tmp_path)
    page = (study / "rater_page.html").read_text(encoding="utf-8")
    (study / "rater_page.html").write_text(
        page + '\n<audio src="stimuli/dream.wav"></audio>\n', encoding="utf-8"
    )

    got = _run(study, tmp_path / "receipt.json")

    assert got["status"] == "BLOCKED_BLINDED_LISTENER_STUDY_DESIGN_V2"
    assert "condition_labels_leak_into_rater_page" in got["failed_gates"]


def test_attention_flag_never_reads_emotion_judgments():
    prereg = json.loads((STUDY_DIR / "PREREGISTRATION_V2.json").read_text(encoding="utf-8"))
    word = prereg["attention_check"]["correct_answer"]
    rows = [
        {"rater_id": "a", "attention_final_word": word, "responses": []},
        {"rater_id": "b", "attention_final_word": "banana", "responses": []},
    ]
    flags = analyzer.attention_flags(rows, word)
    assert flags == {"a": False, "b": True}
    for row in rows:
        row["responses"] = [{"stimulus_id": "S01", "target_emotion_choice": "cheerful"}]
    assert analyzer.attention_flags(rows, word) == flags


def test_v2_analyzer_keeps_all_valid_raters_in_primary():
    prereg = json.loads((STUDY_DIR / "PREREGISTRATION_V2.json").read_text(encoding="utf-8"))
    word = prereg["attention_check"]["correct_answer"]
    confused = prereg_v2._synthetic_row(
        "confused", prereg, adversarial_as_dream_tone=True, attention_word=word
    )
    catch_fail = prereg_v2._synthetic_row(
        "catch_fail", prereg, adversarial_as_dream_tone=False, attention_word="nope"
    )
    got = analyzer.summarize_responses_v2(
        [confused, catch_fail], prereg=prereg, valid_row_indexes={1, 2}
    )
    assert set(got["primary"]["included_rater_ids"]) == {"confused", "catch_fail"}
    assert got["primary"]["excluded_rater_ids"] == []
    assert got["sensitivity_attention_check_only"]["excluded_rater_ids"] == ["catch_fail"]
    assert got["sensitivity_attention_check_only"]["exclusion_reasons"] == {
        "catch_fail": "attention_check_failed"
    }
    assert got["primary"]["denominator"] == 2
    assert got["sensitivity_attention_check_only"]["denominator"] == 1
