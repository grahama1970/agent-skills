from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dewey_overnight_run.py"
spec = importlib.util.spec_from_file_location("dewey_overnight_run", SCRIPT)
dewey = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["dewey_overnight_run"] = dewey
spec.loader.exec_module(dewey)


def test_health_summary_parses_standard_format() -> None:
    health = dewey.extract_health(
        {
            "summary": "24/29 PASS",
            "dimensions": [
                {"name": "embedding_gaps", "status": "FAIL"},
                {"name": "description_completeness", "status": "FAIL"},
                {"name": "inline_embedding_policy", "status": "FAIL"},
                {"name": "qra_coverage_per_control", "status": "FAIL"},
                {"name": "sparta_explorer_page_purpose", "status": "FAIL"},
            ],
        }
    )
    assert health["passed"] == 24
    assert health["total"] == 29
    assert health["green_29_of_29"] is False
    assert health["operator_required_failures"] == ["sparta_explorer_page_purpose"]
    assert "qra_coverage_per_control" in health["repair_cycle_failures"]


def test_health_summary_extracts_qra_counters_from_nested_checks() -> None:
    health = dewey.extract_health(
        {
            "summary": {"passed": 26, "total": 29},
            "checks": [
                {
                    "dimension": "qra_coverage_per_control",
                    "ok": False,
                    "details": {
                        "qra_missing_generation_required": 4873,
                        "qra_ok": 6427,
                    },
                }
            ],
        }
    )

    assert health["qra_missing_generation_required"] == 4873
    assert health["qra_ok"] == 6427


def test_health_summary_29_pass() -> None:
    health = dewey.extract_health({"summary": {"passed": 29, "total": 29}, "dimensions": []})
    assert health["green_29_of_29"] is True
    assert health["failing"] == []


def test_health_json_accepts_monitor_health_failure_return_code(monkeypatch, tmp_path: Path) -> None:
    payload = {"checks": [{"dimension": "qra_coverage_per_control", "ok": False}], "passed": 26, "total": 29}

    def fake_run_command(command, *, cwd, timeout_s, env=None, **_kwargs):
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=1,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(dewey, "run_command", fake_run_command)
    raw, receipt = dewey.health_json(tmp_path, timeout_s=1)

    assert raw == payload
    assert receipt.returncode == 1
    assert receipt.ok is False


def test_monitored_health_json_writes_child_telemetry(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    script = repo / "scripts" / "validation" / "monitor_sparta.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        textwrap.dedent(
            """
            #!/usr/bin/env python3
            import json
            import time

            time.sleep(1.2)
            print(json.dumps({"summary": {"passed": 28, "total": 29}, "failing": ["qra_coverage_per_control"]}))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    run_dir = tmp_path / "run"
    monkeypatch.setenv("DEWEY_CHILD_HEARTBEAT_S", "1")

    raw, receipt = dewey.health_json(repo, timeout_s=5, run_dir=run_dir)

    assert raw["summary"]["passed"] == 28
    assert receipt.returncode == 0
    log = (run_dir / "dewey.log").read_text(encoding="utf-8")
    assert "child_start name=health_json" in log
    assert "child_heartbeat name=health_json" in log
    assert "child_exit name=health_json" in log
    assert "stdout=" in log
    assert "stderr=" in log


def test_repair_cycle_enables_monitor_mutation_for_owned_repair(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run_command(command, *, cwd, timeout_s, env=None, **_kwargs):
        captured["command"] = list(command)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        captured["env"] = dict(env or {})
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=1,
            stdout=json.dumps({"steps": [{"status": "succeeded", "changed_count": 1, "error_count": 0}]}),
            stderr="",
        )

    monkeypatch.setattr(dewey, "run_command", fake_run_command)

    receipt = dewey.repair_cycle(
        tmp_path,
        cycle=1,
        run_dir=tmp_path / "run",
        wait_timeout_s=60,
        embed_batch_limit=200,
        repair_timeout_s=120,
        health_json_timeout_s=90,
        health_fix_timeout_s=30,
        target_dimension="qra_coverage_per_control",
    )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["SPARTA_MONITOR_MUTATION_ENABLED"] == "1"
    assert env["DEWEY_TARGET_DIMENSION"] == "qra_coverage_per_control"
    assert "--target-dimension" in captured["command"]
    assert receipt.returncode == 1
    assert dewey.repair_cycle_allows_after_health(receipt) is True
    assert receipt.json["steps"][0]["changed_count"] == 1


def test_health_summary_waives_mutation_default() -> None:
    health = dewey.extract_health({"summary": {"passed": 28, "total": 28}, "waived_dimensions": ["mutation_default"]})
    assert health["passed"] == 29
    assert health["total"] == 29
    assert health["green_29_of_29"] is True


def test_health_summary_waives_dewey_mutation_enabled_guard() -> None:
    health = dewey.extract_health(
        {
            "summary": {"passed": 26, "total": 29},
            "failing": [
                "monitor_sparta_mutation_default",
                "qra_coverage_per_control",
                "sparta_explorer_page_purpose",
            ],
        }
    )

    assert "monitor_sparta_mutation_default" not in health["failing"]
    assert "monitor_sparta_mutation_default" in health["waived_dimensions"]
    assert health["repair_cycle_failures"] == ["qra_coverage_per_control"]
    assert health["operator_required_failures"] == ["sparta_explorer_page_purpose"]
    assert health["unknown_failures"] == []


def test_unfixable_short_circuit_ignores_dewey_mutation_enabled_guard() -> None:
    health = dewey.extract_health(
        {
            "summary": {"passed": 27, "total": 29},
            "failing": ["monitor_sparta_mutation_default", "sparta_explorer_page_purpose"],
        }
    )

    assert health["failing"] == ["sparta_explorer_page_purpose"]
    assert dewey.only_known_unfixable(health) is True


def test_health_diff_improvement() -> None:
    before = {"passed": 24, "total": 29, "failing": ["a", "b"], "green_29_of_29": False}
    after = {"passed": 25, "total": 29, "failing": ["b"], "green_29_of_29": False}
    diff = dewey.health_diff(before, after)
    assert diff.status == "IMPROVED"
    assert diff.pass_delta == 1
    assert diff.fixed == ["a"]


def test_health_diff_regression() -> None:
    before = {"passed": 25, "total": 29, "failing": ["b"], "green_29_of_29": False}
    after = {"passed": 24, "total": 29, "failing": ["a", "b"], "green_29_of_29": False}
    diff = dewey.health_diff(before, after)
    assert diff.status == "REGRESSED"
    assert diff.regressed == ["a"]


def test_health_diff_no_change() -> None:
    before = {"passed": 24, "total": 29, "failing": ["a"], "green_29_of_29": False}
    after = {"passed": 24, "total": 29, "failing": ["a"], "green_29_of_29": False}
    assert dewey.health_diff(before, after).status == "STUCK"


def test_health_diff_qra_counter_improvement() -> None:
    before = {
        "passed": 26,
        "total": 29,
        "failing": ["qra_coverage_per_control"],
        "green_29_of_29": False,
        "qra_missing_generation_required": 4874,
        "qra_ok": 6426,
    }
    after = {
        "passed": 26,
        "total": 29,
        "failing": ["qra_coverage_per_control"],
        "green_29_of_29": False,
        "qra_missing_generation_required": 4873,
        "qra_ok": 6427,
    }
    diff = dewey.health_diff(before, after)

    assert diff.status == "IMPROVED"
    assert diff.pass_delta == 0
    assert diff.qra_missing_delta == -1
    assert diff.qra_ok_delta == 1
    line = dewey.format_diff_line(diff, cycle=1)
    assert "qra_missing_delta=-1" in line
    assert "qra_ok_delta=+1" in line


def test_health_diff_full_pass() -> None:
    before = {"passed": 28, "total": 29, "failing": ["a"], "green_29_of_29": False}
    after = {"passed": 29, "total": 29, "failing": [], "green_29_of_29": True}
    assert dewey.health_diff(before, after).status == "FULL_PASS"


def test_format_diff_line() -> None:
    diff = dewey.health_diff(
        {"passed": 24, "total": 29, "failing": ["a"], "green_29_of_29": False},
        {"passed": 24, "total": 29, "failing": ["a"], "green_29_of_29": False},
    )
    line = dewey.format_diff_line(diff, cycle=3)
    assert "cycle=3" in line
    assert "STUCK" in line
    assert "24/29 PASS" in line


def test_format_repair_steps() -> None:
    lines = dewey.format_repair_steps(
        {
            "steps": [
                {"name": "health_json_baseline", "status": "ok", "duration_s": 66.1},
                {"name": "health_fix_non_json", "ok": True, "duration_s": 120.2, "summary": "fix lanes done"},
                {"name": "wait_for_monitor_workers", "status": "skipped", "duration_s": 0.0, "summary": "no workers launched"},
            ]
        }
    )
    joined = "\n".join(lines)
    assert "health_json_baseline" in joined
    assert "duration_s=66.1" in joined
    assert "fix lanes done" in joined
    assert "wait_for_monitor_workers" in joined
    assert "duration_s=0.0" in joined


def test_format_stall_warnings() -> None:
    tracker = dewey.StallTracker(limit=2)
    before = {"passed": 24, "total": 29, "failing": ["sparta_explorer_page_purpose"], "green_29_of_29": False}
    after = {"passed": 24, "total": 29, "failing": ["sparta_explorer_page_purpose"], "green_29_of_29": False}
    for cycle in (1, 2):
        tracker.observe(dewey.health_diff(before, after), cycle=cycle)
    warnings = tracker.warnings(after)
    assert any("STALL" in w for w in warnings)
    assert any("OPERATOR_REQUIRED" in w for w in warnings)
    assert "WARNING" in dewey.format_stall_warnings(warnings)


def test_format_stall_warnings_no_warning() -> None:
    assert dewey.format_stall_warnings([]) == ""


def test_compact_cycle_record() -> None:
    before = {"passed": 24, "total": 29, "failing": ["a"], "green_29_of_29": False}
    after = {"passed": 25, "total": 29, "failing": [], "green_29_of_29": False}
    diff = dewey.health_diff(before, after)
    receipt = dewey.CommandReceipt(
        name="repair_cycle",
        command=["monitor", "repair-cycle"],
        started_at="t0",
        finished_at="t1",
        duration_s=1.2,
        returncode=0,
        ok=True,
    )
    record = dewey.compact_cycle_record(1, before, after, receipt, diff)
    assert record["cycle"] == 1
    assert record["repair_duration_s"] == 1.2
    assert record["diff_status"] == "IMPROVED"
    assert record["repair_lane_evidence"]["review_verdict"] is None


def test_compact_repair_lane_evidence_surfaces_qra_proof_paths() -> None:
    evidence = dewey.compact_repair_lane_evidence(
        {
            "steps": [
                {
                    "id": "create_qras_repair_lane",
                    "dimension": "qra_coverage_per_control",
                    "review_verdict": "FULL_RUN_OK",
                    "changed_count": 4,
                    "error_count": 0,
                    "eligible_count": 1,
                    "manifest_source": "source_text_qra_coverage",
                    "artifacts": {
                        "source_text_qra_manifest": "/tmp/manifest.json",
                        "source_text_backfill_manifest": "/tmp/backfill.json",
                    },
                    "skill_read_receipt": {"path": "/tmp/create_qras_skill_read_receipt.json"},
                    "prompt_reviewer": {
                        "status": "prompt_reviewer_pass",
                        "receipt_status": "PASS",
                        "subagent_status": "prompt_reviewer_cached_pass",
                        "subagent_invoked": False,
                        "required_receipt": "/tmp/prompt-reviewer-receipt.json",
                        "request_path": "/tmp/prompt-review-request.json",
                        "expected_response_contract": "/tmp/expected_response_contract.json",
                        "validator_contract": "/tmp/validator_contract.json",
                        "bundle_path": "/tmp/prompt_review_bundle.json",
                        "contract_hash": "abc123",
                    },
                    "substeps": [
                        {
                            "id": "create_qras_manifest_canary",
                            "ok": True,
                            "exit_code": 0,
                            "duration_s": 128.0,
                            "heartbeat_path": "/tmp/canary.heartbeats.jsonl",
                            "stdout_path": "/tmp/canary.stdout.txt",
                            "stderr_path": "/tmp/canary.stderr.txt",
                            "stdout_tail": "Generated 4 QRAs, 0 skipped, 0 errors",
                            "timed_out": False,
                            "timeout_s": 21600,
                            "attempt": 1,
                            "max_attempts": 2,
                        }
                    ],
                }
            ]
        }
    )

    assert evidence["review_verdict"] == "FULL_RUN_OK"
    assert evidence["changed_count"] == 4
    assert evidence["source_text_qra_manifest"] == "/tmp/manifest.json"
    assert evidence["skill_read_receipt_path"] == "/tmp/create_qras_skill_read_receipt.json"
    assert evidence["prompt_reviewer"]["receipt_status"] == "PASS"
    assert evidence["prompt_reviewer"]["required_receipt"] == "/tmp/prompt-reviewer-receipt.json"
    assert evidence["substeps"][0]["generated_qra_count"] == 4
    assert evidence["substeps"][0]["heartbeat_path"] == "/tmp/canary.heartbeats.jsonl"


def test_terminal_state_exposes_machine_readable_remaining_work() -> None:
    health = {
        "passed": 26,
        "total": 29,
        "failing": ["qra_coverage_per_control", "sparta_explorer_page_purpose"],
        "repair_cycle_failures": ["qra_coverage_per_control"],
        "operator_required_failures": ["sparta_explorer_page_purpose"],
        "unknown_failures": [],
        "waived_dimensions": ["monitor_sparta_mutation_default"],
        "qra_missing_generation_required": 4873,
        "qra_ok": 6427,
        "green_29_of_29": False,
    }

    summary = dewey.compact_health_summary(health)
    terminal = dewey.terminal_state_for("cycle_budget_exhausted", 1, health)

    assert summary["passed"] == 26
    assert summary["qra_missing_generation_required"] == 4873
    assert terminal["schema"] == "dewey.terminal_state.v1"
    assert terminal["status"] == "REPAIRABLE_FAILURES_REMAIN"
    assert terminal["repairable_failures"] == ["qra_coverage_per_control"]
    assert terminal["operator_required_failures"] == ["sparta_explorer_page_purpose"]
    assert terminal["unknown_failures"] == []
    assert terminal["waived_dimensions"] == ["monitor_sparta_mutation_default"]


def test_terminal_state_exposes_runner_error() -> None:
    terminal = dewey.terminal_state_for(
        "unhandled_exception",
        5,
        {"passed": 0, "total": 29, "failing": ["dewey_not_started"], "green_29_of_29": False},
    )

    assert terminal["status"] == "RUNNER_ERROR"
    assert terminal["stop_reason"] == "unhandled_exception"
    assert terminal["exit_code"] == 5


def test_evidence_summary_compacts_qra_cycle_deltas(tmp_path: Path) -> None:
    receipt = {
        "run_id": "unit-summary",
        "run_dir": str(tmp_path / "run"),
        "started_at": "t0",
        "finished_at": "t1",
        "stop_reason": "cycle_budget_exhausted",
        "exit_code": 1,
        "parameters": {"backup_required": False, "force_backup": False},
        "initial_summary": {
            "qra_missing_generation_required": 4865,
            "qra_ok": 6435,
        },
        "final_summary": {
            "qra_missing_generation_required": 4863,
            "qra_ok": 6437,
            "repairable_failures": ["qra_coverage_per_control"],
            "operator_required_failures": ["sparta_explorer_page_purpose"],
            "unknown_failures": [],
        },
        "terminal_state": {"status": "REPAIRABLE_FAILURES_REMAIN"},
        "cycles": [
            {
                "cycle": 1,
                "diff_status": "IMPROVED",
                "repair_returncode": 1,
                "repair_progress_count": 4,
                "repair_nonzero_accepted": True,
                "qra_missing_delta": -1,
                "qra_ok_delta": 1,
                "operator_required_failures": ["sparta_explorer_page_purpose"],
                "unknown_failures": [],
            },
            {
                "cycle": 2,
                "diff_status": "IMPROVED",
                "repair_returncode": 1,
                "repair_progress_count": 4,
                "repair_nonzero_accepted": True,
                "qra_missing_delta": -1,
                "qra_ok_delta": 1,
                "operator_required_failures": ["sparta_explorer_page_purpose"],
                "unknown_failures": [],
            },
        ],
    }

    summary = dewey.build_evidence_summary(receipt, morning_report=tmp_path / "run" / "morning_report.md")

    assert summary["schema"] == "dewey.evidence_summary.v1"
    assert summary["mocked"] is False
    assert summary["live"] is True
    assert "does_not_prove" in summary["claims"]
    assert summary["terminal_status"] == "REPAIRABLE_FAILURES_REMAIN"
    assert summary["qra_missing_delta_total"] == -2
    assert summary["qra_ok_delta_total"] == 2
    assert summary["cycle_count"] == 2
    assert summary["cycles"][0]["repair_artifact_dir"].endswith("repair-cycle-0001")
    assert summary["backup_required"] is False
    assert summary["force_backup"] is False


def test_evidence_summary_recovers_repair_lane_evidence_from_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    repair_dir = run_dir / "repair-cycle-0001"
    repair_dir.mkdir(parents=True)
    dewey.write_json(
        repair_dir / "repair_cycle.json",
        {
            "steps": [
                {
                    "id": "create_qras_repair_lane",
                    "review_verdict": "FULL_RUN_OK",
                    "changed_count": 4,
                    "error_count": 0,
                    "prompt_reviewer": {
                        "receipt_status": "PASS",
                        "required_receipt": str(repair_dir / "prompt-review" / "prompt-reviewer-receipt.json"),
                    },
                    "substeps": [
                        {
                            "id": "create_qras_manifest_canary",
                            "ok": True,
                            "stdout_tail": "Generated 4 QRAs, 0 skipped, 0 errors",
                            "heartbeat_path": str(repair_dir / "03_manifest_canary.heartbeats.jsonl"),
                        }
                    ],
                }
            ]
        },
    )
    receipt = {
        "run_id": "unit-summary-recover",
        "run_dir": str(run_dir),
        "parameters": {"backup_required": False, "force_backup": False},
        "initial_summary": {"qra_missing_generation_required": 2, "qra_ok": 1},
        "final_summary": {"qra_missing_generation_required": 1, "qra_ok": 2},
        "terminal_state": {"status": "REPAIRABLE_FAILURES_REMAIN"},
        "cycles": [{"cycle": 1, "diff_status": "IMPROVED", "repair_progress_count": 4}],
    }

    summary = dewey.build_evidence_summary(receipt)
    lane = summary["cycles"][0]["repair_lane_evidence"]

    assert lane["review_verdict"] == "FULL_RUN_OK"
    assert lane["changed_count"] == 4
    assert lane["prompt_reviewer"]["receipt_status"] == "PASS"
    assert lane["substeps"][0]["generated_qra_count"] == 4


def test_status_reads_latest_evidence_summary(tmp_path: Path, capsys) -> None:
    session = tmp_path / "sessions"
    run_dir = session / "unit-status"
    run_dir.mkdir(parents=True)
    dewey.write_json(
        run_dir / "dewey_evidence_summary.json",
        {
            "schema": "dewey.evidence_summary.v1",
            "run_id": "unit-status",
            "terminal_status": "REPAIRABLE_FAILURES_REMAIN",
            "stop_reason": "cycle_budget_exhausted",
            "exit_code": 1,
            "initial_qra_missing_generation_required": 10,
            "final_qra_missing_generation_required": 9,
            "qra_missing_delta_total": -1,
            "cycle_count": 1,
            "backup_required": False,
            "force_backup": False,
        },
    )

    code = dewey.main(["status", "--session-root", str(session), "--json"])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["schema"] == "dewey.status.v1"
    assert out["ok"] is True
    assert out["summary"]["run_id"] == "unit-status"
    assert out["summary"]["qra_missing_delta_total"] == -1


def test_status_falls_back_to_nightly_receipt(tmp_path: Path, capsys) -> None:
    session = tmp_path / "sessions"
    run_dir = session / "unit-old-run"
    run_dir.mkdir(parents=True)
    dewey.write_json(
        run_dir / "nightly_receipt.json",
        {
            "run_id": "unit-old-run",
            "run_dir": str(run_dir),
            "stop_reason": "cycle_budget_exhausted",
            "exit_code": 1,
            "parameters": {"backup_required": False, "force_backup": False},
            "initial_summary": {"qra_missing_generation_required": 2, "qra_ok": 1},
            "final_summary": {
                "qra_missing_generation_required": 1,
                "qra_ok": 2,
                "repairable_failures": ["qra_coverage_per_control"],
                "operator_required_failures": [],
                "unknown_failures": [],
            },
            "terminal_state": {"status": "REPAIRABLE_FAILURES_REMAIN"},
            "cycles": [],
        },
    )

    code = dewey.main(["status", "--session-root", str(session), "--run-id", "unit-old-run", "--json"])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["summary"]["schema"] == "dewey.evidence_summary.v1"
    assert out["summary"]["qra_missing_delta_total"] == -1
    assert out["summary"]["nightly_receipt_path"] == str(run_dir / "nightly_receipt.json")


def test_status_latest_filter_selects_repair_progress_over_newer_runner_error(tmp_path: Path, capsys) -> None:
    session = tmp_path / "sessions"
    repair_run = session / "repair-run"
    error_run = session / "error-run"
    repair_run.mkdir(parents=True)
    error_run.mkdir(parents=True)
    dewey.write_json(
        repair_run / "dewey_evidence_summary.json",
        {
            "schema": "dewey.evidence_summary.v1",
            "run_id": "repair-run",
            "terminal_status": "REPAIRABLE_FAILURES_REMAIN",
            "cycles": [
                {
                    "cycle": 1,
                    "diff_status": "IMPROVED",
                    "repair_progress_count": 4,
                }
            ],
        },
    )
    dewey.write_json(
        error_run / "dewey_evidence_summary.json",
        {
            "schema": "dewey.evidence_summary.v1",
            "run_id": "error-run",
            "terminal_status": "RUNNER_ERROR",
            "cycles": [],
        },
    )
    # Ensure the runner-error directory is newer than the repair-progress run.
    import os

    os.utime(repair_run, (1, 1))
    os.utime(error_run, (2, 2))

    code = dewey.main(["status", "--session-root", str(session), "--latest-filter", "repair-progress", "--json"])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["latest_filter"] == "repair-progress"
    assert out["summary"]["run_id"] == "repair-run"


def test_repair_cycle_allows_after_health_for_nonzero_structured_progress() -> None:
    receipt = dewey.CommandReceipt(
        name="repair_cycle",
        command=["monitor", "repair-cycle"],
        started_at="t0",
        finished_at="t1",
        duration_s=1.2,
        returncode=1,
        ok=False,
        json={
            "steps": [
                {
                    "name": "create_qras_repair_lane",
                    "status": "succeeded",
                    "changed_count": 4,
                    "error_count": 0,
                }
            ]
        },
    )

    assert dewey.repair_cycle_progress_count(receipt.json) == 4
    assert dewey.repair_cycle_allows_after_health(receipt) is True


def test_repair_cycle_nonzero_without_progress_still_fails() -> None:
    receipt = dewey.CommandReceipt(
        name="repair_cycle",
        command=["monitor", "repair-cycle"],
        started_at="t0",
        finished_at="t1",
        duration_s=1.2,
        returncode=1,
        ok=False,
        json={
            "steps": [
                {
                    "name": "create_qras_repair_lane",
                    "status": "failed",
                    "changed_count": 0,
                    "error_count": 1,
                }
            ]
        },
    )

    assert dewey.repair_cycle_progress_count(receipt.json) == 0
    assert dewey.repair_cycle_allows_after_health(receipt) is False


def test_repair_cycle_timeout_default_and_override() -> None:
    assert dewey.compute_repair_cycle_timeout_s(60) == 660
    assert dewey.compute_repair_cycle_timeout_s(300) == 900
    assert dewey.compute_repair_cycle_timeout_s(7200) == 7800
    assert dewey.compute_repair_cycle_timeout_s(300, repair_timeout_s=1234) == 1234


def test_unfixable_dimensions_short_circuit() -> None:
    health = dewey.extract_health(
        {
            "summary": {"passed": 28, "total": 29},
            "failing": ["sparta_explorer_page_purpose"],
        }
    )
    assert dewey.only_known_unfixable(health) is True
    assert dewey.should_stop_for_unfixable_only(health) is True


def test_verify_detected_regression_from_pass_count_drop() -> None:
    receipt = dewey.CommandReceipt(
        name="db_repair_session_verify",
        command=["db", "verify"],
        started_at="t0",
        finished_at="t1",
        duration_s=0.0,
        returncode=0,
        ok=True,
        json={"status": "ok"},
    )
    assert dewey.verify_detected_regression(
        receipt,
        baseline={"passed": 25, "total": 29, "failing": ["a"], "green_29_of_29": False},
        current={"passed": 24, "total": 29, "failing": ["a", "b"], "green_29_of_29": False},
    ) is True


def make_fake_monitor(
    repo: Path,
    health: dict[str, object],
    after_health: dict[str, object] | None = None,
    *,
    repair_returncode: int = 0,
    repair_changed_count: int = 0,
) -> None:
    script = repo / "scripts" / "validation" / "monitor_sparta.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        textwrap.dedent(
            f"""
            #!/usr/bin/env python3
            import json, pathlib, sys
            HEALTH = {json.dumps(health)!r}
            AFTER = {json.dumps(after_health or health)!r}
            FORBIDDEN = {{'--receipt', '--worker-poll-s', '--qra-batch-limit'}}
            REQUIRED = {{'--artifact-dir', '--embed-batch-limit', '--wait-timeout-s', '--json'}}
            def arg_value(args, flag):
                if flag not in args:
                    return None
                i = args.index(flag)
                return args[i+1] if i + 1 < len(args) else None
            def main():
                args = sys.argv[1:]
                state = pathlib.Path('state.json')
                if args[:2] == ['health', '--json']:
                    if state.exists():
                        print(AFTER)
                    else:
                        print(HEALTH)
                    return 0
                if args and args[0] == 'repair-cycle':
                    flags = set(args[1:])
                    bad = sorted(FORBIDDEN & flags)
                    if bad:
                        print(json.dumps({{'ok': False, 'error': 'forbidden flags', 'flags': bad}}))
                        return 44
                    missing = sorted(flag for flag in REQUIRED if flag not in flags)
                    if missing:
                        print(json.dumps({{'ok': False, 'error': 'missing flags', 'flags': missing}}))
                        return 45
                    artifact_dir = pathlib.Path(arg_value(args, '--artifact-dir'))
                    artifact_dir.mkdir(parents=True, exist_ok=True)
                    (artifact_dir / 'argv.json').write_text(json.dumps(args))
                    state.write_text(json.dumps({{'ran': True}}))
                    data = {{
                        'ok': True,
                        'artifact_dir': str(artifact_dir),
                        'steps': [
                            {{'name': 'health_json_baseline', 'status': 'ok', 'duration_s': 71.0}},
                            {{'name': 'qdrant_embed_batch', 'status': 'ok', 'duration_s': 3.0}},
                            {{'name': 'health_fix_non_json', 'status': 'ok', 'duration_s': 120.0, 'changed_count': {repair_changed_count}, 'error_count': 0}},
                            {{'name': 'wait_for_monitor_workers', 'status': 'skipped', 'duration_s': 0.0, 'summary': 'no workers launched'}},
                            {{'name': 'health_json_final', 'status': 'ok', 'duration_s': 71.0}},
                        ]
                    }}
                    (artifact_dir / 'repair_cycle.json').write_text(json.dumps(data))
                    print(json.dumps(data))
                    return {repair_returncode}
                print('unsupported ' + json.dumps(args), file=sys.stderr)
                return 2
            if __name__ == '__main__':
                raise SystemExit(main())
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def test_repair_cycle_uses_real_monitor_sparta_api_only(tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    session = tmp_path / "sessions"
    run_dir = session / "unit-api"
    run_dir.mkdir(parents=True)
    make_fake_monitor(repo, {"summary": {"passed": 24, "total": 29}, "failing": ["embedding_gaps"]})
    receipt = dewey.repair_cycle(
        repo,
        cycle=1,
        run_dir=run_dir,
        wait_timeout_s=300,
        embed_batch_limit=50,
        repair_timeout_s=None,
        health_json_timeout_s=300,
        health_fix_timeout_s=240,
    )
    assert receipt.ok, receipt.stderr_tail
    command = receipt.command
    assert "--artifact-dir" in command
    assert "--embed-batch-limit" in command
    assert "--wait-timeout-s" in command
    assert "--json" in command
    assert "--receipt" not in command
    assert "--worker-poll-s" not in command
    assert "--qra-batch-limit" not in command
    argv_path = run_dir / "repair-cycle-0001" / "argv.json"
    assert argv_path.exists()


def test_once_runs_without_backup_and_writes_morning_report(tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    session = tmp_path / "sessions"
    health = {
        "summary": {"passed": 25, "total": 29},
        "failing": ["embedding_gaps", "description_completeness", "inline_embedding_policy", "sparta_explorer_page_purpose"],
    }
    make_fake_monitor(repo, health)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "once",
            "--memory-repo-root",
            str(repo),
            "--session-root",
            str(session),
            "--run-id",
            "unit-once",
            "--wait-timeout-s",
            "60",
            "--repair-timeout-s",
            "120",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    run_dir = Path(data["run_dir"])
    assert (run_dir / "dewey.log").exists()
    assert (run_dir / "morning_report.md").exists()
    assert (run_dir / "dewey_evidence_summary.json").exists()
    assert (run_dir / "repair-cycle-0001" / "repair_cycle.json").exists()
    summary = json.loads((run_dir / "dewey_evidence_summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == "dewey.evidence_summary.v1"
    assert summary["nightly_receipt_path"] == str(run_dir / "nightly_receipt.json")
    assert summary["morning_report_path"] == str(run_dir / "morning_report.md")
    log = (run_dir / "dewey.log").read_text(encoding="utf-8")
    assert "BACKUP skipped" in log
    assert "EVIDENCE_SUMMARY path=" in log
    assert "REPAIR_STEP cycle=1" in log
    assert "health_fix_non_json" in log
    assert "wait_for_monitor_workers" in log
    assert "duration_s=0.0" in log
    repair_command = next(c for c in data["commands"] if c["name"] == "repair_cycle")["command"]
    assert "--receipt" not in repair_command
    assert "--worker-poll-s" not in repair_command
    assert "--qra-batch-limit" not in repair_command


def test_once_continues_after_productive_nonzero_repair_cycle(tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    session = tmp_path / "sessions"
    health = {
        "summary": {"passed": 25, "total": 29},
        "failing": ["qra_coverage_per_control", "sparta_explorer_page_purpose"],
        "qra_missing_generation_required": 4874,
        "qra_ok": 6426,
    }
    after_health = {
        "summary": {"passed": 25, "total": 29},
        "failing": ["qra_coverage_per_control", "sparta_explorer_page_purpose"],
        "qra_missing_generation_required": 4873,
        "qra_ok": 6427,
    }
    make_fake_monitor(
        repo,
        health,
        after_health,
        repair_returncode=1,
        repair_changed_count=4,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "once",
            "--memory-repo-root",
            str(repo),
            "--session-root",
            str(session),
            "--run-id",
            "unit-once-productive-nonzero",
            "--wait-timeout-s",
            "60",
            "--repair-timeout-s",
            "120",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["stop_reason"] == "cycle_budget_exhausted"
    assert data["cycles"][0]["diff_status"] == "IMPROVED"
    assert data["cycles"][0]["pass_delta"] == 0
    assert data["cycles"][0]["qra_missing_delta"] == -1
    assert data["cycles"][0]["qra_ok_delta"] == 1
    assert data["cycles"][0]["repair_ok"] is False
    assert data["cycles"][0]["repair_returncode"] == 1
    assert data["cycles"][0]["repair_progress_count"] == 4
    assert data["cycles"][0]["repair_nonzero_accepted"] is True
    assert any("REPAIR_CYCLE_NONZERO_ACCEPTED" in warning for warning in data["warnings"])
    log = (Path(data["run_dir"]) / "dewey.log").read_text(encoding="utf-8")
    assert "REPAIR_CYCLE_NONZERO_ACCEPTED" in log
    assert "cycle=1 IMPROVED" in log
    assert "qra_missing_delta=-1" in log


def test_once_short_circuits_known_unfixable_only(tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    session = tmp_path / "sessions"
    health = {
        "summary": {"passed": 28, "total": 29},
        "failing": ["sparta_explorer_page_purpose"],
    }
    make_fake_monitor(repo, health)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "once",
            "--memory-repo-root",
            str(repo),
            "--session-root",
            str(session),
            "--run-id",
            "unit-unfixable",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert result.returncode == 10
    data = json.loads(result.stdout)
    assert data["stop_reason"] == "operator_required_unfixable_only"
    assert not any(Path(data["run_dir"]).glob("repair-cycle-*"))
    assert any("OPERATOR_REQUIRED" in w for w in data["warnings"])


def test_start_handles_missing_db_repair_session_gracefully(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEWEY_ARANGO_BACKUP_RECEIPT", str(tmp_path / "missing_latest_backup_receipt.json"))
    repo = tmp_path / "memory"
    agent_skills = tmp_path / "agent-skills"
    session = tmp_path / "sessions"
    health = {
        "summary": {"passed": 25, "total": 29},
        "failing": ["embedding_gaps", "description_completeness", "inline_embedding_policy", "sparta_explorer_page_purpose"],
    }
    make_fake_monitor(repo, health)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start",
            "--memory-repo-root",
            str(repo),
            "--agent-skills-root",
            str(agent_skills),
            "--session-root",
            str(session),
            "--run-id",
            "unit-start-missing-db-script",
            "--max-cycles",
            "1",
            "--wait-timeout-s",
            "60",
            "--repair-timeout-s",
            "120",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["stop_reason"] == "cycle_budget_exhausted"
    assert any("BACKUP_UNAVAILABLE" in w for w in data["warnings"])
    begin = next(c for c in data["commands"] if c["name"] == "db_repair_session_begin")
    assert begin["returncode"] == 127
    assert begin["ok"] is True
    log = (Path(data["run_dir"]) / "dewey.log").read_text(encoding="utf-8")
    assert "continuing without backup" in log
    assert "REPAIR_STEP cycle=1" in log


def test_start_skips_backup_when_global_arango_receipt_is_today(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "memory"
    agent_skills = tmp_path / "agent-skills"
    session = tmp_path / "sessions"
    receipt_path = tmp_path / "latest_backup_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": "arangodb_backup_receipt.v1",
                "completed_at": dewey.utc_now(),
                "backup_dir": "/mnt/storage12tb/backups/arangodb/20990101-000000",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEWEY_ARANGO_BACKUP_RECEIPT", str(receipt_path))
    health = {
        "summary": {"passed": 25, "total": 29},
        "failing": ["embedding_gaps", "sparta_explorer_page_purpose"],
    }
    make_fake_monitor(repo, health)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "start",
            "--memory-repo-root",
            str(repo),
            "--agent-skills-root",
            str(agent_skills),
            "--session-root",
            str(session),
            "--run-id",
            "unit-start-global-backup-receipt",
            "--max-cycles",
            "1",
            "--wait-timeout-s",
            "60",
            "--repair-timeout-s",
            "120",
            "--json",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert any("BACKUP_SKIPPED_ALREADY_TAKEN_TODAY" in w for w in data["warnings"])
    assert not any(c["name"] == "db_repair_session_begin" for c in data["commands"])
    log = (Path(data["run_dir"]) / "dewey.log").read_text(encoding="utf-8")
    assert "BACKUP_SKIPPED_ALREADY_TAKEN_TODAY" in log


def test_start_retries_until_only_operator_owned_gap_remains(monkeypatch, tmp_path: Path) -> None:
    session = tmp_path / "sessions"
    repo = tmp_path / "memory"
    agent_skills = tmp_path / "agent-skills"
    health_sequence = [
        {
            "passed": 26,
            "total": 29,
            "failed": 3,
            "failing": ["qra_coverage_per_control", "sparta_explorer_page_purpose"],
            "green_29_of_29": False,
            "repair_cycle_failures": ["qra_coverage_per_control"],
            "operator_required_failures": ["sparta_explorer_page_purpose"],
            "unknown_failures": [],
            "qra_missing_generation_required": 2,
            "qra_ok": 10,
        },
        {
            "passed": 26,
            "total": 29,
            "failed": 3,
            "failing": ["qra_coverage_per_control", "sparta_explorer_page_purpose"],
            "green_29_of_29": False,
            "repair_cycle_failures": ["qra_coverage_per_control"],
            "operator_required_failures": ["sparta_explorer_page_purpose"],
            "unknown_failures": [],
            "qra_missing_generation_required": 1,
            "qra_ok": 11,
        },
        {
            "passed": 28,
            "total": 29,
            "failed": 1,
            "failing": ["sparta_explorer_page_purpose"],
            "green_29_of_29": False,
            "repair_cycle_failures": [],
            "operator_required_failures": ["sparta_explorer_page_purpose"],
            "unknown_failures": [],
            "qra_missing_generation_required": 0,
            "qra_ok": 12,
        },
    ]
    health_calls = {"count": 0}
    repair_calls: list[int] = []

    def fake_health_json(*_args, **_kwargs):
        index = min(health_calls["count"], len(health_sequence) - 1)
        health_calls["count"] += 1
        payload = {"unit_health_index": index}
        return payload, dewey.CommandReceipt(
            name="health_json",
            command=["monitor_sparta.py", "health", "--json"],
            started_at=dewey.utc_now(),
            finished_at=dewey.utc_now(),
            duration_s=0.01,
            returncode=1,
            ok=False,
            json=payload,
        )

    def fake_extract(raw):
        return dict(health_sequence[int(raw["unit_health_index"])])

    def fake_repair(*_args, cycle: int, **_kwargs):
        repair_calls.append(cycle)
        return dewey.CommandReceipt(
            name="repair_cycle",
            command=["monitor_sparta.py", "repair-cycle"],
            started_at=dewey.utc_now(),
            finished_at=dewey.utc_now(),
            duration_s=0.01,
            returncode=1,
            ok=False,
            json={
                "steps": [
                    {
                        "name": "create_qras_repair_lane",
                        "status": "succeeded",
                        "changed_count": 1,
                        "error_count": 0,
                    }
                ]
            },
        )

    monkeypatch.setattr(dewey, "health_json", fake_health_json)
    monkeypatch.setattr(dewey, "extract_health", fake_extract)
    monkeypatch.setattr(dewey, "repair_cycle", fake_repair)

    code = dewey.main([
        "start",
        "--no-backup",
        "--memory-repo-root",
        str(repo),
        "--agent-skills-root",
        str(agent_skills),
        "--session-root",
        str(session),
        "--run-id",
        "unit-start-retry-until-operator-only",
        "--max-cycles",
        "5",
        "--json",
    ])

    assert code == dewey.EXIT_OPERATOR_REQUIRED
    assert repair_calls == [1, 2]
    receipt = json.loads((session / "unit-start-retry-until-operator-only" / "nightly_receipt.json").read_text(encoding="utf-8"))
    assert receipt["stop_reason"] == "operator_required_unfixable_only"
    assert receipt["terminal_state"]["status"] == "OPERATOR_REQUIRED_ONLY"
    assert receipt["final_summary"]["repairable_failures"] == []
    assert receipt["final_summary"]["operator_required_failures"] == ["sparta_explorer_page_purpose"]
    assert [cycle["qra_missing_delta"] for cycle in receipt["cycles"]] == [-1, -1]
    assert [cycle["repair_nonzero_accepted"] for cycle in receipt["cycles"]] == [True, True]
