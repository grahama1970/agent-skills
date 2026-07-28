"""Fixtures for the PCTOM-R measurement-validity-v2 gate (#1056).

The live proof is that the gate found the real defect on the committed path:
24/24 labels TRUE, one distinct distribution per condition across 72
predictions, and CD winning 24/24 with no possible loss. These pin each failure
mode, and pin that a genuinely varying path passes.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "prospective-tom" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "mv2", SCRIPTS / "check_pctom_measurement_validity_v2.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mv2 = _load()


def _corpus(values):
    return {
        "episodes": [
            {
                "episode_id": f"ep-{i}",
                "ground_truth_tom_labels": [
                    {
                        "hypothesis_id": f"ep-{i}-tom1",
                        "perspective_order": 1,
                        "mental_state_type": "belief",
                        "value": v,
                    }
                ],
            }
            for i, v in enumerate(values)
        ]
    }


def test_all_true_labels_block():
    problems = []
    got = mv2.check_labels(_corpus(["TRUE"] * 6), problems)
    assert got["by_value"] == {"TRUE": 6}
    assert "degenerate_ground_truth_labels" in {p["rule"] for p in problems}


def test_varying_labels_pass():
    problems = []
    got = mv2.check_labels(_corpus(["TRUE", "FALSE", "UNKNOWN", "TRUE"]), problems)
    assert got["distinct_values"] == 3
    assert problems == []


def _preds(condition, dists):
    return [
        {
            "condition": condition,
            "episode_id": f"ep-{i}",
            "distribution": d,
            "evidence_refs": [{"source_id": f"ep-{i}:obs:0"}],
        }
        for i, d in enumerate(dists)
    ]


def _flat(p):
    return [{"value": "TRUE", "probability": p}, {"value": "FALSE", "probability": 1 - p}]


def test_constant_distribution_blocks():
    problems = []
    mv2.check_predictions(None, problems, _preds("CD", [_flat(0.7)] * 5))
    assert "constant_prediction_distribution" in {p["rule"] for p in problems}


def test_varying_distribution_passes():
    problems = []
    mv2.check_predictions(None, problems, _preds("CD", [_flat(0.6), _flat(0.7), _flat(0.8)]))
    assert problems == []


def test_missing_evidence_refs_block():
    problems = []
    preds = _preds("CD", [_flat(0.6), _flat(0.7)])
    for p in preds:
        p["evidence_refs"] = []
    mv2.check_predictions(None, problems, preds)
    assert "no_evidence_refs" in {p["rule"] for p in problems}


def test_brier_is_a_proper_score():
    # perfect prediction scores 0; confidently wrong scores 2.0 on two classes
    assert mv2.brier(_flat(1.0), "TRUE") == 0.0
    assert mv2.brier(_flat(0.0), "TRUE") == 2.0
    assert 0 < mv2.brier(_flat(0.5), "TRUE") < 2.0


def test_circularity_tokens_block(tmp_path):
    gen = tmp_path / "gen.py"
    gen.write_text("from x import CONDITION_PROFILES\n")
    problems = []
    mv2.check_anticircularity(gen, problems)
    assert "corpus_generation_inspects_conditions" in {p["rule"] for p in problems}


def test_clean_generator_passes(tmp_path):
    gen = tmp_path / "gen.py"
    gen.write_text("def build(seed):\n    return seed\n")
    problems = []
    row = mv2.check_anticircularity(gen, problems)
    assert problems == []
    assert row["hits"] == []
    assert row["sha256"].startswith("sha256:")


def test_missing_generator_blocks():
    problems = []
    mv2.check_anticircularity(Path("/nonexistent/gen.py"), problems)
    assert "generator_not_readable" in {p["rule"] for p in problems}


def test_llm_judge_blocks():
    problems = []
    mv2.check_seals({"llm_judge_used": True, "sealed": True}, problems)
    assert "llm_judge_used" in {p["rule"] for p in problems}


def test_absent_seals_block():
    problems = []
    mv2._SEAL_HINT.clear()
    mv2.check_seals({"anything": 1}, problems)
    assert "no_sealed_commitments" in {p["rule"] for p in problems}
