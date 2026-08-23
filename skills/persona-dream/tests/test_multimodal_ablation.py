import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "run_multimodal_ablation", ROOT / "scripts" / "run_multimodal_ablation.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ablation = _load()


def _valid_inputs(tmp_path):
    class Args:
        out_dir = tmp_path
        watch_packet = ablation.DEFAULT_PACKET
        watch_report = ablation.DEFAULT_WATCH_REPORT
        live_artifact_readback = False
        json = False

    receipt = ablation.run(Args)
    prereg = json.loads((tmp_path / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    visibility = json.loads((tmp_path / "ARM_VISIBILITY_MANIFEST.json").read_text(encoding="utf-8"))
    source = json.loads((tmp_path / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    commitments = [
        json.loads(line)
        for line in (tmp_path / "COMMITMENTS.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    scores = [
        json.loads(line)
        for line in (tmp_path / "SCORE_ROWS.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    packet_hash = ablation.artifact_ref(ablation.DEFAULT_PACKET)["sha256"]
    report_hash = ablation.artifact_ref(ablation.DEFAULT_WATCH_REPORT)["sha256"]
    return receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash


def _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash):
    return ablation.validate_experiment(
        prereg, visibility, commitments, scores, source, packet_hash, report_hash
    )


def test_runner_writes_required_matched_ablation_artifacts(tmp_path):
    receipt, _prereg, visibility, _source, _commitments, _scores, _packet_hash, _report_hash = _valid_inputs(tmp_path)

    assert receipt["status"] == "PASS_MULTIMODAL_ABLATION_RESULT"
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["terminal_result_class"] == "NULL_OR_TIE"
    assert receipt["dw_minus_strongest_simple"] == 0.0
    assert receipt["provider_calls"] == 0
    assert receipt["canonical_memory_writes"] == 0
    assert receipt["identity_writes"] == 0
    assert receipt["llm_judge_used"] is False
    assert receipt["human_hidden_state_scoring"] is False
    assert visibility["D"]["text_dream_sha256"] == visibility["DW"]["text_dream_sha256"]
    assert visibility["D"]["watch_observation_visible"] is False
    assert visibility["DW"]["watch_observation_visible"] is True
    for name in [
        "PREREGISTRATION.json",
        "SOURCE_MANIFEST.json",
        "ARM_VISIBILITY_MANIFEST.json",
        "COMMITMENTS.jsonl",
        "SCORE_ROWS.jsonl",
        "RESULT_RECEIPT.json",
    ]:
        assert (tmp_path / name).is_file()


def test_d_or_baseline_watch_visibility_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    visibility["D"]["watch_observation_visible"] = True

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_D_ARM_RECEIVED_WATCH_OBSERVATION" in failures


def test_dw_hidden_intention_or_acceptance_label_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    visibility["DW"]["hidden_script_intention_visible"] = True
    visibility["DW"]["acceptance_labels_visible"] = True

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_DW_RECEIVED_HIDDEN_SCRIPT_INTENTION" in failures
    assert "BLOCKED_DW_RECEIVED_ACCEPTANCE_LABELS" in failures


def test_source_memory_drift_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    visibility["R"]["source_memory_boundary_sha256"] = "sha256:different"

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_SOURCE_MEMORIES_DIFFER_ACROSS_ARMS" in failures


def test_task_or_rubric_change_after_commitment_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    commitments[0]["commitment"]["task_sha256"] = "sha256:changed"

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_COMMITMENT_CHANGED_AFTER_REVEAL_M" in failures


def test_commitment_hash_change_after_reveal_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    commitments[1]["commitment_sha256"] = "sha256:mutated"

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_COMMITMENT_CHANGED_AFTER_REVEAL_R" in failures
    assert "BLOCKED_SCORE_ROW_COMMITMENT_HASH_MISMATCH_R" in failures


def test_budget_or_retry_mismatch_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    commitments[2]["commitment"]["budget"]["retries"] = 1
    commitments[2]["commitment_sha256"] = ablation.sha256_text(
        ablation.canonical_json(commitments[2]["commitment"])
    )
    scores[2]["commitment_sha256"] = commitments[2]["commitment_sha256"]

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_MODEL_BUDGET_OR_RETRIES_DIFFER" in failures


def test_watch_hash_mutation_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, _packet_hash, report_hash = _valid_inputs(tmp_path)

    failures = _failures(prereg, visibility, source, commitments, scores, "sha256:mutated", report_hash)

    assert "BLOCKED_WATCH_OBSERVATION_HASH_MUTATED" in failures


def test_provider_or_canonical_write_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    prereg["provider_calls_allowed"] = 1
    prereg["canonical_memory_writes_allowed"] = 1
    prereg["identity_writes_allowed"] = 1

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_PROVIDER_CALL_ALLOWED" in failures
    assert "BLOCKED_CANONICAL_MEMORY_WRITE_ALLOWED" in failures
    assert "BLOCKED_IDENTITY_WRITE_ALLOWED" in failures


def test_positive_from_prose_or_preference_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    scores[3]["positive_evidence_basis"] = "richer_prose"

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_POSITIVE_INFERRED_FROM_NON_SCORE_EVIDENCE" in failures


def test_text_dream_hash_mismatch_blocks(tmp_path):
    _receipt, prereg, visibility, source, commitments, scores, packet_hash, report_hash = _valid_inputs(tmp_path)
    visibility["DW"]["text_dream_sha256"] = "sha256:changed"

    failures = _failures(prereg, visibility, source, commitments, scores, packet_hash, report_hash)

    assert "BLOCKED_D_DW_TEXT_DREAM_HASH_MISMATCH" in failures
