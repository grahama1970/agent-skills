"""test_cross_mood_identity_matrix - tests.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/cross_mood_identity_matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("cross_mood_identity_matrix", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_preregistration_freezes_36_target_rows_and_disjoint_calibration(tmp_path):
    module = load_module()
    prereg = module.preregistration(
        {
            "supported_params": ["norm_loudness"],
            "voice_backends": {
                "chatterbox_base_affect": {
                    "state": "loaded",
                    "capability_digest": "sha256:test",
                }
            },
        },
        tmp_path,
    )

    assert prereg["matrix"]["target_render_count"] == 36
    assert prereg["matrix"]["calibration_render_count"] == 3
    assert prereg["seed_contract"]["target_and_calibration_disjoint"] is True
    assert prereg["seed_contract"]["route"] == "POST /synthesize-emotion"
    assert "/synthesize-batch has no seed field" in prereg["seed_contract"]["reason"]
    assert len({row["render_id"] for row in prereg["target_manifest"]}) == 36
    assert len({row["voice_delivery_sha256"] for row in prereg["target_manifest"]}) == 4
    assert prereg["backend"]["backend_id"] == "chatterbox_base_affect"


def test_calibration_thresholds_are_derived_without_target_rows():
    module = load_module()
    rows = [
        {"speaker": {"embry_similarity": 0.91, "embry_vs_adversarial_margin": 0.22}},
        {"speaker": {"embry_similarity": 0.86, "embry_vs_adversarial_margin": 0.18}},
        {"speaker": {"embry_similarity": 0.89, "embry_vs_adversarial_margin": 0.20}},
    ]

    got = module.derive_calibration(rows)

    assert got["status"] == "PASS_CROSS_MOOD_IDENTITY_CALIBRATION"
    assert got["derived_identity_floor"] == 0.836334
    assert got["derived_embry_vs_adversarial_margin"] == 0.09
    assert got["target_rows_used"] == 0
    assert got["calibration_score_summary"]["lower_bound_formula"].startswith("mean - 2*sample_stdev")


def test_row_gates_keep_quality_asr_and_identity_distinct():
    module = load_module()
    row = {
        "response_ok": True,
        "engine": "chatterbox_base",
        "audio": {"exists": True},
        "trustworthy_duration": {"ok": True},
        "asr": {"ok": True},
        "speaker": {"embry_similarity": 0.84, "embry_vs_adversarial_margin": 0.08},
        "answer_text_sha256": "sha256:same",
        "paired_answer_text_sha256": "sha256:same",
    }
    technical = {"status": "PASS_STIMULUS_TECHNICAL_SCREEN"}

    assert module.row_gates(row, floor=0.80, margin=0.06, technical=technical) == []

    row["speaker"] = {"embry_similarity": 0.79, "embry_vs_adversarial_margin": 0.04}
    gates = module.row_gates(row, floor=0.80, margin=0.06, technical={"status": "BLOCKED"})

    assert "embry_similarity_floor" in gates
    assert "embry_adversarial_margin" in gates
    assert "technical_screen_receipt_pass" in gates

    row["asr"] = {"ok": False}
    assert module.quality_gates(row) == ["asr_text_exact"]


def test_negative_controls_are_all_bound_to_aggregate_policy():
    module = load_module()
    aggregate = {
        "target_rows": [{"render_id": "r1"}, {"render_id": "r2"}],
        "calibration": {"target_rows_used": 0},
    }

    controls = module.negative_controls(aggregate)

    assert {row["control_id"] for row in controls} == {
        "target_wav_replaced_after_scoring",
        "non_embry_voice_inserted_as_target",
        "threshold_recomputed_from_target_matrix",
        "clip_shorter_than_trustworthy_duration_floor_certified",
        "mood_cell_omits_adversarial_comparisons",
        "canonical_answer_or_reference_differs_across_paired_moods",
        "technical_screen_receipt_blocked_or_mismatched",
        "aggregate_hides_failed_seed_text_cell",
    }
    assert all(row["status"] == "PASS_NEGATIVE_CONTROL_POLICY_BOUND" for row in controls)
    assert all(row["calibration_target_rows_used"] == 0 for row in controls)
