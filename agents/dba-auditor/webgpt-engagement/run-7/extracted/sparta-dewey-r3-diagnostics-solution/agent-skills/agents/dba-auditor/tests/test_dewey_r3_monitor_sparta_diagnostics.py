from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[4]
    module_path = repo_root / "memory" / "scripts" / "validation" / "monitor_sparta_r3_diagnostics.py"
    spec = importlib.util.spec_from_file_location("monitor_sparta_r3_diagnostics", module_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(name: str):
    repo_root = Path(__file__).resolve().parents[4]
    with (repo_root / "fixtures" / "dewey_r3" / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_embed_lane_reports_noop_mismatch():
    mod = _load_module()
    receipt = _fixture("repair_cycle_noop_input.json")
    enriched = mod.enrich_repair_cycle_receipt(receipt)
    embed_step = next(step for step in enriched["steps"] if step["id"] == "sparta_qdrant_embed_batch")

    assert embed_step["eligible_count"] == 170
    assert embed_step["changed_count"] == 0
    assert embed_step["skip_reason"] == "all_processed_documents_already_present_in_qdrant"
    assert embed_step["health_embed_mismatch"] is True
    assert embed_step["embed_metrics"]["processed"] == 200
    assert embed_step["embed_metrics"]["dropped"] == 200


def test_health_fix_reports_per_dimension_results():
    mod = _load_module()
    receipt = _fixture("repair_cycle_noop_input.json")
    enriched = mod.enrich_repair_cycle_receipt(receipt)
    health_fix = next(step for step in enriched["steps"] if step["id"] == "monitor_health_fix")

    assert health_fix["status"] == "attempted_no_progress"
    assert health_fix["changed_count"] == 0
    per_dim = {item["dimension"]: item for item in health_fix["per_dimension_results"]}
    assert per_dim["embedding_gaps"]["result"] == "stuck"
    assert per_dim["embedding_gaps"]["eligible_count"] == 170
    assert per_dim["description_completeness"]["affected_count_before"] == 12
    assert per_dim["inline_embedding_policy"]["result"] == "stuck"
    assert per_dim["qra_coverage_per_control"]["skip_reason"] == "operator_review_required"
    assert per_dim["sparta_explorer_page_purpose"]["skip_reason"] == "not_repairable_by_monitor_sparta"


def test_qra_contract_option_b_flags_old_worker_launch():
    mod = _load_module()
    receipt = _fixture("repair_cycle_noop_input.json")
    enriched = mod.enrich_repair_cycle_receipt(receipt)
    qra_step = next(step for step in enriched["steps"] if step["id"] == "create_qras_backfill")

    assert qra_step["contract_violation"] is True
    assert qra_step["changed_count"] == 0
    assert qra_step["skip_reason"] == "qra_coverage_per_control_should_use_operator_lane_not_default_worker"
    assert enriched["r3_diagnostics"]["contract"] == "Option B: QRA coverage is operator/review-gated and remains unfixable by Dewey"
    assert "qra_coverage_per_control" in enriched["r3_diagnostics"]["remaining_unfixable_dimensions"]


def test_worker_wait_reports_timed_out_still_running():
    mod = _load_module()
    receipt = _fixture("repair_cycle_noop_input.json")
    enriched = mod.enrich_repair_cycle_receipt(receipt)

    assert enriched["worker_wait"]["timed_out"] is True
    assert enriched["worker_wait"]["still_running"] is True
    assert enriched["worker_wait"]["status"] == "timed_out"
    assert enriched["worker_wait"]["waited_s"] == 300


def test_operator_manifest_entry_is_jsonl(tmp_path):
    mod = _load_module()
    receipt = _fixture("repair_cycle_noop_input.json")
    path = tmp_path / "operator_queue.jsonl"
    entry = mod.write_operator_manifest_entry(path, session_id="r3-test", baseline_health=receipt["baseline"])

    assert entry["dimension"] == "qra_coverage_per_control"
    assert entry["eligible_count"] == 5080
    line = path.read_text(encoding="utf-8").strip()
    decoded = json.loads(line)
    assert decoded["contract"] == "Option B"
    assert decoded["session_id"] == "r3-test"
