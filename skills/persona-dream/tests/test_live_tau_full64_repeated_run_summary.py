import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "prospective-tom" / "scripts" / "run_live_tau_full64_repeated_run_summary.py"
spec = importlib.util.spec_from_file_location("full64_repeated_summary", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    module._write_json(path, payload)


def _case_row(episode_id: str, condition: str, brier: float) -> dict:
    return {
        "episode_id": episode_id,
        "condition": condition,
        "scoring_metrics": {
            "belief_scores": [{"brier": brier}, {"brier": brier}],
            "action": {"brier": brier},
        },
    }


def _action_row(episode_id: str, condition: str, regret: float) -> dict:
    return {
        "episode_id": episode_id,
        "condition": condition,
        "planning_regret": regret,
    }


def _source_root(tmp_path: Path, name: str, *, cd_brier: float, cd_regret: float) -> Path:
    root = tmp_path / name
    condition_receipt_path = root / "live_tau_sealed_test_condition_comparison" / "live_tau_condition_comparison_receipt.v1.json"
    action_receipt_path = root / "live_tau_sealed_test_action_selection" / "live_tau_condition_action_selection_receipt.v1.json"
    case_index_path = root / "live_tau_sealed_test_condition_comparison" / "artifacts" / "live_condition_case_index.json"
    decision_index_path = root / "live_tau_sealed_test_action_selection" / "artifacts" / "live_condition_action_decisions.json"

    case_rows = []
    action_rows = []
    for episode in range(1, 65):
        episode_id = f"sealedte-info-asym-{episode:02d}"
        for condition in module.CONDITIONS:
            brier = cd_brier if condition == "CD" else 0.4
            regret = cd_regret if condition == "CD" else 0.3
            case_rows.append(_case_row(episode_id, condition, brier))
            action_rows.append(_action_row(episode_id, condition, regret))
    _write_json(case_index_path, case_rows)
    _write_json(decision_index_path, action_rows)
    _write_json(
        condition_receipt_path,
        {
            "status": "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON",
            "case_index_path": str(case_index_path),
        },
    )
    _write_json(
        action_receipt_path,
        {
            "status": "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION",
            "decision_index": str(decision_index_path),
        },
    )
    _write_json(
        root / "live_tau_sealed_test_replication_receipt.v1.json",
        {
            "status": module.SOURCE_PASS_STATUS,
            "full_64_episode_replication": True,
            "episode_limit": 64,
            "episodes_per_family": 16,
            "live": True,
            "mocked": False,
            "gate0_attribution_overlay_used": True,
            "gate0_attribution_record_count": 6,
            "gate0_case_root": "/tmp/gate0",
            "tau_call_attempts": 256,
            "tau_live_call_performed": 256,
            "live_tau_condition_comparison_receipt": str(condition_receipt_path),
            "live_tau_action_selection_receipt": str(action_receipt_path),
            "memory_write_attempts": 0,
            "provider_call_attempts": 0,
            "canonical_memory_write_attempts": 0,
            "identity_write_attempts": 0,
            "source_memory_write_attempts": 0,
        },
    )
    return root


def test_repeated_full64_summary_accepts_two_hash_bound_roots(tmp_path):
    root_a = _source_root(tmp_path, "run-a", cd_brier=0.2, cd_regret=0.2)
    root_b = _source_root(tmp_path, "run-b", cd_brier=0.25, cd_regret=0.2)
    output_root = tmp_path / "summary"

    receipt = module.summarize(
        source_roots=[root_a, root_b],
        output_root=output_root,
        receipt_out=output_root / "receipt.json",
        bootstrap_samples=100,
        bootstrap_seed=17,
        alpha=0.05,
    )

    assert receipt["status"] == module.PASS_STATUS
    assert receipt["counts"]["source_roots"] == 2
    assert receipt["counts"]["episode_metric_rows"] == 128
    assert receipt["counts"]["tau_live_calls_consumed"] == 512
    assert receipt["checks"]["episode_metric_rows_cover_all_runs"] is True
    assert receipt["metrics"]["belief_brier"]["benefit_with_confidence"] is True
    assert receipt["memory_write_attempts"] == 0
    assert receipt["provider_call_attempts"] == 0


def test_repeated_full64_summary_requires_two_roots(tmp_path):
    root_a = _source_root(tmp_path, "run-a", cd_brier=0.2, cd_regret=0.2)
    output_root = tmp_path / "summary"

    receipt = module.summarize(
        source_roots=[root_a],
        output_root=output_root,
        receipt_out=output_root / "receipt.json",
        bootstrap_samples=100,
        bootstrap_seed=17,
        alpha=0.05,
    )

    assert receipt["status"] == module.BLOCKED_STATUS
    assert "requires_at_least_two_full64_roots:1" in receipt["errors"]
