"""Contract tests for the PCTOM-R v2 corpus and episode-conditioned estimator (#1131).

These pin the properties the measurement-validity-v2 gate depends on.  They are
NOT the proof that the repair works -- that proof is the real gate re-run over
the real corpus (``run.sh run-pctom-v2-validity-lane``).  These stop a future
edit from silently reintroducing a degeneracy between gate runs.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "prospective-tom" / "scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load("pctom_v2_builder", "build_pctom_v2_corpus.py")
runner = _load("pctom_v2_runner", "run_pctom_v2_condition_comparison.py")
controls = _load("pctom_v2_controls", "check_pctom_v2_negative_controls.py")

DEV = builder.build_corpus("development")
HELDOUT = builder.build_corpus("heldout")


# ---------------------------------------------------------------- corpus
def test_labels_are_not_degenerate():
    counts = DEV["label_counts"]["all"]
    assert len(counts) >= 2, counts
    assert counts.get("TRUE") and counts.get("FALSE") and counts.get("UNKNOWN")


def test_every_family_carries_more_than_one_label_value():
    for family, counts in DEV["label_counts_by_family"].items():
        assert len(counts) >= 2, (family, counts)


def test_labels_agree_with_the_hidden_state_oracle():
    assert controls.audit_labels_against_oracle(DEV) == []
    assert controls.audit_labels_against_oracle(HELDOUT) == []


def test_splits_are_disjoint_by_id_seed_and_template():
    assert controls.audit_split_disjointness(DEV, HELDOUT) == []


def test_splits_are_not_structural_duplicates():
    """Disjoint ids are not enough; the visible evidence must differ too."""
    def cue_multiset(corpus):
        return sorted(
            json.dumps(e["visible_evidence"]["cues"], sort_keys=True) for e in corpus["episodes"]
        )

    assert cue_multiset(DEV) != cue_multiset(HELDOUT)


def test_corpus_build_is_byte_deterministic():
    assert json.dumps(builder.build_corpus("heldout"), sort_keys=True) == json.dumps(
        HELDOUT, sort_keys=True
    )


def test_generator_source_contains_no_circularity_token():
    text = (SCRIPTS / "build_pctom_v2_corpus.py").read_text()
    for token in ("CONDITION_PROFILES", "expected_winner", "winning_set", "cd_wins", "condition_receipt"):
        assert token not in text, token


def test_no_cue_is_a_perfect_indicator_of_the_label():
    """If a cue were a perfect indicator the task would be trivial and the
    condition owning it could not lose."""
    for cue in ("cue_recency", "cue_ack", "cue_hedge", "cue_contrast"):
        seen = {}
        for episode in DEV["episodes"]:
            value = episode["visible_evidence"]["cues"][cue]
            label = episode["ground_truth_tom_labels"][0]["value"]
            seen.setdefault(value, set()).add(label)
        assert any(len(labels) > 1 for labels in seen.values()), cue


# ------------------------------------------------------------- estimator
def test_prediction_depends_on_evidence_not_on_condition_alone():
    cues_a = {"cue_recency": 1, "cue_ack": 0, "cue_hedge": 0, "cue_contrast": 1}
    cues_b = {"cue_recency": 0, "cue_ack": 1, "cue_hedge": 1, "cue_contrast": 0}
    for condition in runner.CONDITIONS:
        assert runner.predict(cues_a, condition, 1) != runner.predict(cues_b, condition, 1)


def test_predictions_are_normalised_probability_vectors():
    cues = {"cue_recency": 1, "cue_ack": 1, "cue_hedge": 0, "cue_contrast": 1}
    for condition in runner.CONDITIONS:
        for order in (1, 2):
            dist = runner.predict(cues, condition, order)
            assert abs(sum(e["probability"] for e in dist) - 1.0) < 1e-6
            assert all(0.0 <= e["probability"] <= 1.0 for e in dist)


def test_condition_cannot_read_a_cue_outside_its_visible_subset():
    partial = {"cue_recency": 1}
    assert runner.predict(partial, "M", 1)  # M only needs cue_recency
    for condition in ("R", "D", "CD"):
        try:
            runner.predict(partial, condition, 1)
        except KeyError:
            continue
        raise AssertionError(f"{condition} silently tolerated a missing cue")


def test_prevalence_baseline_is_intercept_only():
    dist = runner.prevalence_baseline(DEV, 1)
    assert abs(sum(e["probability"] for e in dist) - 1.0) < 1e-6
    # identical for every episode by construction: it reads no episode feature
    assert dist == runner.prevalence_baseline(DEV, 1)


def test_brier_is_proper():
    perfect = [{"value": "TRUE", "probability": 1.0}, {"value": "FALSE", "probability": 0.0}]
    wrong = [{"value": "TRUE", "probability": 0.0}, {"value": "FALSE", "probability": 1.0}]
    assert runner.brier(perfect, "TRUE") == 0.0
    assert runner.brier(wrong, "TRUE") == 2.0


# -------------------------------------------------------- full preflight
def test_preflight_passes_and_every_condition_can_lose(tmp_path):
    receipt = runner.run(
        split="heldout",
        output_root=tmp_path / "root",
        receipt_out=tmp_path / "receipt.json",
    )
    assert receipt["status"] == runner.PASS_STATUS, receipt["errors"]
    wtl = receipt["counts"]["win_tie_loss_by_condition"]
    for condition in runner.CONDITIONS:
        assert wtl[condition]["loss"] >= 1, (condition, wtl[condition])
        assert receipt["counts"]["distinct_distributions_by_condition"][condition] >= 2
        assert receipt["counts"]["evidence_ref_count_by_condition"][condition] > 0


def test_score_variance_is_nonzero_within_each_label_class(tmp_path):
    receipt = runner.run(
        split="heldout",
        output_root=tmp_path / "root",
        receipt_out=tmp_path / "receipt.json",
    )
    for condition, by_class in receipt["score_variance_within_label_class"].items():
        for label_class, row in by_class.items():
            assert row["distinct_values"] >= 2, (condition, label_class, row)
            assert row["variance"] > 0, (condition, label_class, row)


def test_all_negative_controls_block(tmp_path):
    rows = controls.run_controls(tmp_path)
    failed = [r for r in rows if r["status"] != "PASS_NEGATIVE_CONTROL"]
    assert not failed, failed
    assert len(rows) >= 11
