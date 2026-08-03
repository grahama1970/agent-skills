from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
HELPER_PATH = ROOT / "prompt_reviewer_receipt.py"
DEWEY_PATH = ROOT / "dewey_overnight_run.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


receipt = load_module("prompt_reviewer_receipt", HELPER_PATH)
dewey = load_module("dewey_overnight_run", DEWEY_PATH)


def test_prompt_review_request_and_pass_receipt_validate(tmp_path: Path):
    request_path, md_path, receipt_path, request_sha = receipt.write_prompt_review_bundle(
        tmp_path,
        request_id="unit-cycle-0001",
        failed_dimensions=["qra_coverage_per_control"],
        qra_missing_count=4883,
        model_pool="qra-deepseek-pool",
    )
    assert request_path.exists()
    assert md_path.exists()
    pass_receipt = receipt.sample_pass_receipt(request_sha256=request_sha, mocked=True)
    receipt.write_json(receipt_path, pass_receipt)
    result = receipt.validate_receipt_file(receipt_path, request_path=request_path, allow_mock=True)
    assert result.ok is True
    assert result.verdict == "PASS"


def test_prompt_reviewer_receipt_rejects_missing_and_non_pass(tmp_path: Path):
    request_path, _, receipt_path, request_sha = receipt.write_prompt_review_bundle(
        tmp_path,
        request_id="unit-cycle-0002",
        failed_dimensions=["qra_coverage_per_control"],
        qra_missing_count=1,
        model_pool="qra-deepseek-pool",
    )
    result = receipt.validate_receipt_file(receipt_path, request_path=request_path, allow_mock=True)
    assert not result.ok
    needs_changes = {
        "schema_version": receipt.SCHEMA_RECEIPT_V1,
        "request_sha256": request_sha,
        "verdict": "NEEDS_CHANGES",
        "prompt_contract_ok": False,
        "response_contract_ok": True,
        "approved_for_qra_generation": False,
        "blocking_findings": [{"message": "prompt lacks provenance constraints"}],
        "honesty": {"mocked": True, "live": False, "database_mutation_allowed": False},
    }
    receipt.write_json(receipt_path, needs_changes)
    result = receipt.validate_receipt_file(receipt_path, request_path=request_path, allow_mock=True)
    assert not result.ok
    assert "not PASS" in result.reason


def test_create_qras_gate_cannot_pass_with_mock_unless_allowed(tmp_path: Path):
    request_path, _, receipt_path, request_sha = receipt.write_prompt_review_bundle(
        tmp_path,
        request_id="unit-cycle-0003",
        failed_dimensions=["qra_coverage_per_control"],
        qra_missing_count=2,
        model_pool="qra-deepseek-pool",
    )
    receipt.write_json(receipt_path, receipt.sample_pass_receipt(request_sha256=request_sha, mocked=True))
    result = receipt.validate_receipt_file(receipt_path, request_path=request_path, allow_mock=False)
    assert not result.ok
    assert "mock" in result.reason


def test_prompt_reviewer_command_construction_is_deterministic(tmp_path: Path):
    req = tmp_path / "request.md"
    req_json = tmp_path / "request.json"
    out = tmp_path / "receipt.json"
    req.write_text("hello", encoding="utf-8")
    req_json.write_text("{}", encoding="utf-8")
    cmd = receipt.build_prompt_reviewer_command(
        request_markdown=req,
        request_json=req_json,
        receipt_json=out,
        template="ask.ask --agent prompt-reviewer --question-file {request_markdown} --receipt {receipt_json}",
    )
    assert cmd == ["ask.ask", "--agent", "prompt-reviewer", "--question-file", str(req), "--receipt", str(out)]


def test_no_inline_embedding_fields_in_status_artifacts():
    ok = {"failed_dimensions": ["embedding_gaps"], "payload": {"count": 170}}
    receipt.assert_no_inline_embedding_fields(ok)
    bad = {"payload": {"embedding": [0.1, 0.2]}}
    try:
        receipt.assert_no_inline_embedding_fields(bad)
    except receipt.PromptReviewerGateError as exc:
        assert "inline embedding" in str(exc)
    else:
        raise AssertionError("expected inline embedding rejection")


def test_qra_dimension_requires_prompt_review_and_selects_one_lane():
    health = {"failing": ["sparta_explorer_page_purpose", "qra_coverage_per_control", "embedding_gaps"]}
    assert dewey.qra_prompt_review_required(health) is True
    assert dewey.select_target_dimension(health) == "embedding_gaps"
    health = {"failing": ["qra_coverage_per_control"]}
    assert dewey.only_known_unfixable(health) is False
    assert dewey.select_target_dimension(health) == "qra_coverage_per_control"


def test_backup_guard_once_per_day(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEWEY_ARANGO_BACKUP_RECEIPT", str(tmp_path / "missing_latest_backup_receipt.json"))
    assert dewey.backup_already_taken_today(tmp_path) is False
    dewey.mark_backup_taken_today(tmp_path, {"ok": True, "mocked": False})
    assert dewey.backup_already_taken_today(tmp_path) is True


def test_backup_guard_honors_global_arango_receipt(monkeypatch, tmp_path: Path):
    receipt_path = tmp_path / "latest_backup_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "arangodb_backup_receipt.v1",
                "completed_at": dewey.utc_now(),
                "backup_dir": "/mnt/storage12tb/backups/arangodb/not-needed",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEWEY_ARANGO_BACKUP_RECEIPT", str(receipt_path))

    assert dewey.arango_backup_receipt_taken_today(receipt_path) is True
    assert dewey.backup_already_taken_today(tmp_path / "new-session-root") is True


def test_prompt_reviewer_failure_terminal_state_skips_repair(monkeypatch, tmp_path: Path):
    calls = {"repair": 0}
    health = {
        "passed": 23,
        "total": 29,
        "failed": 6,
        "failing": ["qra_coverage_per_control"],
        "green_29_of_29": False,
        "repair_cycle_failures": ["qra_coverage_per_control"],
        "operator_required_failures": [],
        "unknown_failures": [],
    }

    def fake_health_json(*args, **kwargs):
        return ({"summary": "23/29 PASS", "failed_dimensions": ["qra_coverage_per_control"]}, dewey.CommandReceipt(
            name="health_json", command=["health"], started_at=dewey.utc_now(), finished_at=dewey.utc_now(), duration_s=0.01,
            returncode=0, ok=True, json={"summary": "23/29 PASS", "failed_dimensions": ["qra_coverage_per_control"]}
        ))

    def fake_extract(raw):
        return dict(health)

    def fake_repair(*args, **kwargs):
        calls["repair"] += 1
        raise AssertionError("repair-cycle must not run before prompt-reviewer PASS")

    monkeypatch.setattr(dewey, "health_json", fake_health_json)
    monkeypatch.setattr(dewey, "extract_health", fake_extract)
    monkeypatch.setattr(dewey, "repair_cycle", fake_repair)
    code = dewey.main([
        "once",
        "--session-root", str(tmp_path),
        "--memory-repo-root", str(tmp_path),
        "--agent-skills-root", str(tmp_path),
        "--run-id", "unit-prompt-reviewer-blocked",
        "--external-prompt-reviewer-gate",
        "--json",
    ])
    assert code == dewey.EXIT_PROMPT_REVIEWER_GATE_FAILED
    assert calls["repair"] == 0
    receipt_path = tmp_path / "unit-prompt-reviewer-blocked" / "nightly_receipt.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["stop_reason"] == "prompt_reviewer_gate_failed"


def test_default_qra_prompt_review_defers_to_monitor_concrete_bundle(monkeypatch, tmp_path: Path):
    calls = {"repair": 0}
    health = {
        "passed": 23,
        "total": 29,
        "failed": 6,
        "failing": ["qra_coverage_per_control"],
        "green_29_of_29": False,
        "repair_cycle_failures": ["qra_coverage_per_control"],
        "operator_required_failures": [],
        "unknown_failures": [],
    }

    def fake_health_json(*args, **kwargs):
        return ({"summary": "23/29 PASS", "failed_dimensions": ["qra_coverage_per_control"]}, dewey.CommandReceipt(
            name="health_json", command=["health"], started_at=dewey.utc_now(), finished_at=dewey.utc_now(), duration_s=0.01,
            returncode=0, ok=True, json={"summary": "23/29 PASS", "failed_dimensions": ["qra_coverage_per_control"]}
        ))

    def fake_extract(raw):
        return dict(health)

    def fake_repair(*args, **kwargs):
        calls["repair"] += 1
        assert kwargs["target_dimension"] == "qra_coverage_per_control"
        assert kwargs["prompt_reviewer_receipt_path"] is None
        return dewey.CommandReceipt(
            name="repair_cycle",
            command=["repair-cycle"],
            started_at=dewey.utc_now(),
            finished_at=dewey.utc_now(),
            duration_s=0.01,
            returncode=1,
            ok=False,
            json={"steps": [{"id": "create_qras_repair_lane", "status": "prompt_review_required"}]},
        )

    monkeypatch.setattr(dewey, "health_json", fake_health_json)
    monkeypatch.setattr(dewey, "extract_health", fake_extract)
    monkeypatch.setattr(dewey, "repair_cycle", fake_repair)
    code = dewey.main([
        "once",
        "--session-root", str(tmp_path),
        "--memory-repo-root", str(tmp_path),
        "--agent-skills-root", str(tmp_path),
        "--run-id", "unit-monitor-concrete-gate",
        "--json",
    ])
    assert code == 4
    assert calls["repair"] == 1
    log_text = (tmp_path / "unit-monitor-concrete-gate" / "dewey.log").read_text(encoding="utf-8")
    assert "deferred_to_monitor_concrete_bundle" in log_text
