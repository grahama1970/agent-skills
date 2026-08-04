from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill import arena_live_battle_proof as proof  # noqa: E402
from battle_skill import cli as battle_cli  # noqa: E402
from battle_skill.ux_contract_validator import ContractError, validate_exploit_lifecycle_receipts, validate_exploit_lifecycle_receipts_path  # noqa: E402


def test_canonical_zip_slip_scenario_is_marked_canary_not_balanced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_write_target_files(target_dir: Path):  # type: ignore[no-untyped-def]
        target_dir.mkdir(parents=True)
        app_path = target_dir / "app.py"
        exploit_path = target_dir / "exploit.py"
        app_path.write_text("def import_zip(): pass\n", encoding="utf-8")
        exploit_path.write_text("print('RED_EXPLOIT_CONFIRMED')\n", encoding="utf-8")
        return app_path, exploit_path

    monkeypatch.setattr(proof, "_write_target_files", fake_write_target_files)
    monkeypatch.setattr(
        proof,
        "_run_oracle",
        lambda **_: {
            "command": ["python", "exploit.py"],
            "exit_code": 0,
            "stdout_path": "stdout.txt",
            "stderr_path": "stderr.txt",
        },
    )

    receipt_path = proof._write_canonical_zip_slip_scenario(
        arena_out=tmp_path / "arena",
        battle_id="battle-004",
        run_id="run-001",
        docker_image="python:3.12-slim",
    )

    scenario = json.loads((tmp_path / "arena" / "scenario.json").read_text(encoding="utf-8"))
    public_brief = json.loads((tmp_path / "arena" / "team-public" / "scenario-brief.json").read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    balance = scenario["arena_balance_contract"]
    assert balance["schema"] == proof.ARENA_BALANCE_CONTRACT_SCHEMA
    assert balance["competitive_relevance"] == "NOT_QUALIFIED"
    assert balance["qualification_status"] == "CANARY_ONLY"
    assert "repeated automatic BLUE_SUCCESS" in balance["disqualifying_patterns"]
    assert "terminal receipt with balance_diagnosis" in balance["required_for_balanced_arena"]
    assert public_brief["arena_balance_contract"] == balance
    assert receipt["arena_balance_contract"] == balance


def test_tau_abort_manifest_preserves_partial_materialized_worker_receipts(
    tmp_path: Path,
) -> None:
    tau_out = tmp_path / "tau-live"
    red_dir = tau_out / "red"
    blue_dir = tau_out / "blue"
    red_dir.mkdir(parents=True)
    blue_dir.mkdir(parents=True)

    red_artifact = red_dir / "red_exploit_submission.py"
    red_artifact.write_text("print('RED_EXPLOIT_CONFIRMED')\n", encoding="utf-8")
    (red_dir / "handoff.json").write_text(
        json.dumps({"worker_id": "red-0", "lane_id": "payload-857-receipt"}),
        encoding="utf-8",
    )
    (red_dir / "materialized-artifact-receipt.json").write_text(
        json.dumps(
            {
                "schema": "tau.battle_materialized_artifact_receipt.v1",
                "status": "PASS",
                "artifact_type": "red_exploit",
                "path": str(red_artifact),
            }
        ),
        encoding="utf-8",
    )
    (red_dir / "tau-subagent-receipt.json").write_text(
        json.dumps(
            {
                "schema": "tau.subagent_receipt.v1",
                "context": {
                    "battle": {
                        "team": "red",
                        "worker_id": "red-0",
                        "lane_id": "payload-857-receipt",
                    }
                },
                "result": {"status": "PASS"},
            }
        ),
        encoding="utf-8",
    )
    (blue_dir / "handoff.json").write_text(
        json.dumps({"worker_id": "blue-0", "lane_id": "payload-857-blue-0"}),
        encoding="utf-8",
    )

    manifest = proof._partial_tau_manifest_from_worker_receipts(
        tau_out=tau_out,
        battle_id="battle-004",
        run_id="run-001",
        scenario_id="arena-zip-slip-import-001",
        command=["uv", "run", "python", "-m", "tau_coding.battle_live_handoff"],
        exit_code=1,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        model="opencode-go/kimi-k2.6",
        scillm_base_url="http://localhost:4001",
        red_workers=1,
        blue_workers=1,
    )

    assert manifest["status"] == "BLOCKED"
    assert manifest["reason"] == "tau_harness_command_failed_before_manifest"
    assert manifest["materialized_counts"] == {"red": 1, "blue": 0}
    assert manifest["requested_workers"] == {"red": 1, "blue": 1}
    assert [entry["team"] for entry in manifest["teams"]] == ["red", "blue"]
    assert proof._materialized_entries(manifest, "red")[0]["path"] == str(red_artifact)
    assert proof._materialized_entries(manifest, "blue") == []
    judge = proof._judge_tau_artifacts(
        out_dir=tmp_path / "judge-proof",
        scenario={
            "scenario_id": "arena-zip-slip-import-001",
            "public_entrypoint": "/api/import-zip",
        },
        docker_image="python:3.12-slim",
        tau_manifest=manifest,
    )
    assert judge["status"] == "INSUFFICIENT_EVIDENCE"
    assert judge["red_artifact_count"] == 1
    assert judge["blue_artifact_count"] == 0


def test_judge_pair_records_source_to_docker_workspace_byte_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_dir = tmp_path / "proof"
    target = out_dir / "arena" / "team-public" / "target"
    target.mkdir(parents=True)
    (target / "app.py").write_text("def import_zip(): pass\n", encoding="utf-8")
    red_artifact = tmp_path / "red_exploit_submission.py"
    blue_artifact = tmp_path / "patched_app.py"
    red_artifact.write_text("print('RED_EXPLOIT_CONFIRMED')\n", encoding="utf-8")
    blue_artifact.write_text("def import_zip(): return 'blocked'\n", encoding="utf-8")
    red_sha = proof._sha256(red_artifact)
    blue_sha = proof._sha256(blue_artifact)

    def fake_run_command(command, *, out_dir: Path, name: str):  # type: ignore[no-untyped-def]
        stdout = out_dir / f"{name}.stdout"
        stderr = out_dir / f"{name}.stderr"
        if name == "judge-original-input-hashes":
            stdout.write_text(
                json.dumps({"red_exploit_submission.py": red_sha}, sort_keys=True),
                encoding="utf-8",
            )
        elif name == "judge-patched-input-hashes":
            stdout.write_text(
                json.dumps(
                    {
                        "app.py": blue_sha,
                        "red_exploit_submission.py": red_sha,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
        else:
            stdout.write_text(
                "RED_EXPLOIT_CONFIRMED\n"
                if name == "judge-red-exploit-original"
                else "",
                encoding="utf-8",
            )
        stderr.write_text("", encoding="utf-8")
        return {
            "command": command,
            "exit_code": 1 if name == "judge-red-exploit-patched" else 0,
            "stdout_path": str(stdout),
            "stderr_path": str(stderr),
        }

    monkeypatch.setattr(proof, "_run_command", fake_run_command)
    monkeypatch.setattr(proof, "_smoke_import", lambda **_: True)

    attempt = proof._judge_pair(
        out_dir=out_dir,
        scenario={"scenario_id": "arena-zip-slip-import-001"},
        docker_image="python:3.12-slim",
        red={
            "worker_id": "red-0",
            "lane_id": "payload-red-0",
            "path": str(red_artifact),
        },
        blue={
            "worker_id": "blue-0",
            "action_id": "blue-0-patch",
            "path": str(blue_artifact),
        },
    )

    assert attempt["status"] == "PASS"
    assert attempt["verdict"] == "BLUE_SUCCESS"
    assert attempt["judge_input_byte_binding_pass"] is True
    assert attempt["container_input_hash_pass"] is True
    assert [item["status"] for item in attempt["container_input_hashes"]] == [
        "PASS",
        "PASS",
    ]
    assert attempt["container_input_hashes"][0]["observed_sha256"] == {
        "red_exploit_submission.py": red_sha,
    }
    assert attempt["container_input_hashes"][1]["observed_sha256"] == {
        "app.py": blue_sha,
        "red_exploit_submission.py": red_sha,
    }
    assert len(attempt["commands_run"]) == 4
    bindings = {item["role"]: item for item in attempt["judge_input_byte_bindings"]}
    assert set(bindings) == {
        "red_original_exploit",
        "red_patched_exploit",
        "blue_patched_app",
    }
    assert bindings["red_original_exploit"]["source_sha256"] == attempt["red_artifact_sha256"]
    assert bindings["red_original_exploit"]["execution_sha256"] == attempt["red_artifact_sha256"]
    assert bindings["red_original_exploit"]["docker_workspace_path"] == "/workspace/red_exploit_submission.py"
    assert bindings["blue_patched_app"]["source_sha256"] == attempt["blue_artifact_sha256"]
    assert bindings["blue_patched_app"]["execution_sha256"] == attempt["blue_artifact_sha256"]
    assert bindings["blue_patched_app"]["docker_workspace_path"] == "/workspace/app.py"


def test_parent_spawn_flag_runs_parent_first_and_records_lineage_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    def write_json(path: Path, payload: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def fake_arena(*, out_dir: Path, battle_id: str, run_id: str, query: str, docker_image: str) -> dict[str, Any]:
        return {"status": "PASS", "battle_id": battle_id, "run_id": run_id, "query": query}

    def fake_canonical(*, arena_out: Path, battle_id: str, run_id: str, docker_image: str) -> Path:
        write_json(
            arena_out / "scenario.json",
            {
                "battle_id": battle_id,
                "run_id": run_id,
                "scenario_id": "arena-zip-slip-import-001",
                "title": "Archive import path traversal",
                "public_entrypoint": "/api/import-zip",
                "cwe": "CWE-22",
            },
        )
        return write_json(arena_out / "arena-receipt.json", {"status": "PASS"})

    def fake_ledger(*, arena_out: Path, battle_id: str, scenario: dict[str, Any], oracle_receipt: Path) -> Path:
        return write_json(arena_out / "private" / "ledger.json", {"battle_id": battle_id})

    def fake_context(
        *,
        out_dir: Path,
        battle_id: str,
        run_id: str,
        scenario: dict[str, Any],
        red_workers: int,
        blue_workers: int,
    ) -> Path:
        return write_json(out_dir / "tau-public-context.json", {"red_workers": red_workers, "blue_workers": blue_workers})

    def fake_tau_harness(
        *,
        out_dir: Path,
        battle_id: str,
        run_id: str,
        scenario_id: str,
        context_path: Path,
        red_persona: str,
        blue_persona: str,
        model: str,
        scillm_base_url: str,
        timeout_s: float,
        red_workers: int,
        blue_workers: int,
    ) -> Path:
        calls["initial_red_workers"] = red_workers
        calls["initial_blue_workers"] = blue_workers
        manifest = {
            "status": "PASS",
            "duration_seconds": 3.0,
            "started_at": "2026-07-04T00:00:00Z",
            "ended_at": "2026-07-04T00:00:03Z",
            "teams": [
                {
                    "team": "red",
                    "worker_id": "red-0",
                    "lane_id": "payload-857-receipt",
                    "subagent_receipt": "tau-live/red/red-0/tau-subagent-receipt.json",
                    "materialized": {"path": "tau-live/red/red-0/exploit.py"},
                },
                {
                    "team": "blue",
                    "worker_id": "blue-0",
                    "lane_id": "blue-0",
                    "subagent_receipt": "tau-live/blue/blue-0/tau-subagent-receipt.json",
                    "materialized": {"path": "tau-live/blue/blue-0/patch.py"},
                },
            ],
        }
        write_json(out_dir / "tau-live" / "red" / "red-0" / "tau-subagent-receipt.json", {"status": "PASS"})
        return write_json(out_dir / "tau-live" / "manifest.json", manifest)

    def fake_validation(*, out_dir: Path, tau_manifest: dict[str, Any]) -> dict[str, Any]:
        return {"status": "PASS"}

    def fake_judge(
        *,
        out_dir: Path,
        scenario: dict[str, Any],
        docker_image: str,
        tau_manifest: dict[str, Any],
        timing_origin: float | None = None,
    ) -> dict[str, Any]:
        attempts = [
            {
                "pair_id": "red-0__blue-0",
                "red_worker_id": "red-0",
                "red_lane_id": "payload-857-receipt",
                "blue_worker_id": "blue-0",
                "verdict": "BLUE_SUCCESS",
                "exploit_confirmed_before_patch": True,
                "blue_artifact": "tau-live/blue/blue-0/patch.py",
            }
        ]
        if any(item.get("worker_id") == "red-1" for item in tau_manifest.get("teams", [])):
            attempts.append(
                {
                    "pair_id": "red-1__blue-0",
                    "red_worker_id": "red-1",
                    "red_lane_id": "payload-857-red-1",
                    "blue_worker_id": "blue-0",
                    "verdict": "BLUE_SUCCESS",
                    "exploit_confirmed_before_patch": True,
                    "blue_artifact": "tau-live/blue/blue-0/patch.py",
                }
            )
        return {
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "judged_pair_count": len(attempts),
            "blue_success_count": len(attempts),
            "red_success_count": 0,
            "attempts": attempts,
        }

    def fake_lineage(
        *,
        out_dir: Path,
        battle_id: str,
        run_id: str,
        scenario_id: str,
        context_path: Path,
        tau_manifest: dict[str, Any],
        judge: dict[str, Any],
        red_persona: str,
        model: str,
        scillm_base_url: str,
        timeout_s: float,
        docker_image: str,
        scenario: dict[str, Any],
        timing_origin: float | None = None,
    ) -> dict[str, Any]:
        calls["lineage_called"] = True
        merged_manifest = dict(tau_manifest)
        merged_manifest["teams"] = [
            *tau_manifest["teams"],
            {
                "team": "red",
                "worker_id": "red-1",
                "lane_id": "payload-857-red-1",
                "subagent_receipt": "tau-live/red/red-1/tau-subagent-receipt.json",
                "materialized": {"path": "tau-live/red/red-1/exploit.py"},
            },
        ]
        lineage_path = write_json(
            out_dir / "lineage-receipts.json",
            {
                "schema": proof.LINEAGE_SCHEMA,
                "status": "PASS",
                "spawns": [
                    {
                        "receipt_id": "lineage-spawn-red-0-red-1",
                        "parent_lane_id": "payload-857-receipt",
                        "child_lane_id": "payload-857-red-1",
                        "spawn_type": "post_block_handoff",
                    }
                ],
            },
        )
        return {
            "tau_manifest": merged_manifest,
            "judge": fake_judge(out_dir=out_dir, scenario=scenario, docker_image=docker_image, tau_manifest=merged_manifest),
            "lineage_receipt_path": lineage_path,
        }

    monkeypatch.setattr(proof, "run_arena_subagent_proof", fake_arena)
    monkeypatch.setattr(proof, "_write_canonical_zip_slip_scenario", fake_canonical)
    monkeypatch.setattr(proof, "_write_multi_vuln_ledger", fake_ledger)
    monkeypatch.setattr(proof, "_write_tau_public_context", fake_context)
    monkeypatch.setattr(proof, "_run_tau_harness", fake_tau_harness)
    monkeypatch.setattr(proof, "_visibility_validation", fake_validation)
    monkeypatch.setattr(proof, "_judge_tau_artifacts", fake_judge)
    monkeypatch.setattr(proof, "_run_parent_spawn_lineage_rung", fake_lineage)

    receipt = proof.run_arena_tau_public_only_proof(
        out_dir=tmp_path / "proof",
        battle_id="battle-004",
        run_id="run-001",
        red_workers=1,
        blue_workers=1,
        spawn_red_child_on_blue_success=True,
    )

    assert calls["initial_red_workers"] == 1
    assert calls["initial_blue_workers"] == 1
    assert calls["lineage_called"] is True
    assert receipt["worker_counts"]["red_requested"] == 1
    assert receipt["worker_counts"]["red_initial_requested"] == 1
    assert receipt["worker_counts"]["red_child_spawn_requested"] is True
    assert receipt["worker_counts"]["red_materialized"] == 2
    assert receipt["worker_counts"]["blue_success_pairs"] == 2
    assert receipt["lineage_request"] == {
        "condition": "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested",
        "mode": "spawn_red_child_after_blue_success",
        "receipt": "lineage-receipts.json",
        "requested": True,
        "status": "PASS",
    }
    assert receipt["timing_receipts"]["schema"] == "battle.control_plane_timing_receipts.v1"
    assert receipt["timing_receipts"]["source"] == "battle_control_plane_perf_counter"
    assert [event["stage"] for event in receipt["timing_receipts"]["events"]] == [
        "arena_context_ready",
        "initial_tau_manifest_ready",
        "visibility_validation_ready",
        "parent_judge_ready",
        "lineage_receipts_ready",
    ]
    assert all(isinstance(event["elapsed_seconds"], float) for event in receipt["timing_receipts"]["events"])
    lifecycle_path = tmp_path / "proof" / "exploit-lifecycle-receipts.json"
    report = validate_exploit_lifecycle_receipts_path(lifecycle_path)
    assert report["status"] == "PASS"
    assert report["schema"] == "battle.exploit_lifecycle_receipts.v1"
    assert report["live"] is True
    assert report["mocked"] is False
    assert report["proof_mode"] == "live_tau"
    assert "post_block_handoff" in report["spawn_decisions"]
    assert "spawn_pressure_conceded" in report["outcome_classes"]
    lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
    assert lifecycle["summary"]["bug_learning_notes"] == [
        "Existing battle-004 parent-spawn path spawns after Judge BLUE_SUCCESS; it is post_block_handoff, not strategic_pre_kill survival.",
        "Pressure observations are recorded as observations and do not claim Blue kill without a kill receipt.",
    ]
    spawn_receipts = [
        item
        for item in lifecycle["receipts"]
        if item["event_type"] == "spawn_decision_recorded"
    ]
    assert spawn_receipts
    assert spawn_receipts[0]["spawn_decision"]["decision"] == "post_block_handoff"
    assert spawn_receipts[0]["spawn_decision"]["parent_state"] == "blocked"
    assert spawn_receipts[0]["pressure_observation"]["confirmed_blue_action"] is True
    assert spawn_receipts[0]["pressure_observation"]["suspected_pressure"] is False


def test_arena_parent_spawn_proof_cli_uses_canonical_spawn_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_run_arena_tau_public_only_proof(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return {
            "status": "PASS",
            "battle_id": kwargs["battle_id"],
            "run_id": kwargs["run_id"],
            "worker_counts": {
                "red_requested": kwargs["red_workers"],
                "blue_requested": kwargs["blue_workers"],
                "red_child_spawn_requested": kwargs["spawn_red_child_on_blue_success"],
            },
            "lineage_request": {
                "requested": True,
                "mode": "spawn_red_child_after_blue_success",
                "status": "PASS",
            },
        }

    monkeypatch.setattr(proof, "run_arena_tau_public_only_proof", fake_run_arena_tau_public_only_proof)
    monkeypatch.setattr(
        battle_cli,
        "_write_ux_transport_artifacts",
        lambda *, out, battle_id: {"status": "PASS", "battle_id": battle_id, "out": str(out)},
    )

    result = CliRunner().invoke(
        battle_cli.app,
        [
            "arena-parent-spawn-proof",
            "--out",
            str(tmp_path / "proof"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["battle_id"] == "battle-004"
    assert str(calls["out_dir"]) == str(tmp_path / "proof")
    assert calls["query"] == "OWASP file upload zip slip path traversal vulnerability"
    assert calls["docker_image"] == "python:3.12-slim"
    assert calls["model"] == "gpt-5.5"
    assert calls["scillm_base_url"] == "http://localhost:4001"
    assert calls["timeout_s"] == 1200.0
    assert calls["red_workers"] == 2
    assert calls["blue_workers"] == 2
    assert calls["spawn_red_child_on_blue_success"] is True
    assert calls["run_id"].startswith("arena-parent-spawn-")


def test_arena_prekill_survival_proof_cli_uses_prekill_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_run_arena_prekill_survival_proof(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return {
            "status": "PASS",
            "battle_id": kwargs["battle_id"],
            "run_id": kwargs["run_id"],
            "worker_counts": {
                "red_requested": kwargs["red_workers"],
                "blue_requested": kwargs["blue_workers"],
                "red_prekill_survival_requested": True,
            },
            "prekill_survival_contract": {"status": "PASS"},
        }

    monkeypatch.setattr(proof, "run_arena_prekill_survival_proof", fake_run_arena_prekill_survival_proof)
    monkeypatch.setattr(
        battle_cli,
        "_write_ux_transport_artifacts",
        lambda *, out, battle_id: {"status": "PASS", "battle_id": battle_id, "out": str(out)},
    )

    result = CliRunner().invoke(
        battle_cli.app,
        [
            "arena-prekill-survival-proof",
            "--out",
            str(tmp_path / "proof"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["battle_id"] == "battle-004"
    assert str(calls["out_dir"]) == str(tmp_path / "proof")
    assert calls["red_workers"] == 2
    assert calls["blue_workers"] == 2
    assert calls["run_id"].startswith("arena-prekill-survival-")


def test_tau_repository_can_be_selected_for_clean_compatibility_run(
    tmp_path: Path,
) -> None:
    source = Path(proof.__file__).read_text(encoding="utf-8")

    assert 'os.environ.get("TAU_REPO"' in source
    assert str(proof.TAU_REPO)


def test_prekill_pressure_callback_runs_before_terminal_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    order: list[str] = []
    red_path = tmp_path / "red.py"
    blue_path = tmp_path / "blue.py"
    red_path.write_text("print('RED_EXPLOIT_CONFIRMED')\n", encoding="utf-8")
    blue_path.write_text("def import_zip(*args):\n    return None\n", encoding="utf-8")
    red_sha = proof._sha256(red_path)
    blue_sha = proof._sha256(blue_path)

    original_hash_stdout = tmp_path / "original-hash.stdout"
    original_hash_stderr = tmp_path / "original-hash.stderr"
    patched_hash_stdout = tmp_path / "patched-hash.stdout"
    patched_hash_stderr = tmp_path / "patched-hash.stderr"
    before_stdout = tmp_path / "before.stdout"
    before_stderr = tmp_path / "before.stderr"
    after_stdout = tmp_path / "after.stdout"
    after_stderr = tmp_path / "after.stderr"
    original_hash_stdout.write_text(
        json.dumps({"red_exploit_submission.py": red_sha}, sort_keys=True),
        encoding="utf-8",
    )
    original_hash_stderr.write_text("", encoding="utf-8")
    patched_hash_stdout.write_text(
        json.dumps(
            {"app.py": blue_sha, "red_exploit_submission.py": red_sha},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    patched_hash_stderr.write_text("", encoding="utf-8")
    before_stdout.write_text("RED_EXPLOIT_CONFIRMED\n", encoding="utf-8")
    before_stderr.write_text("", encoding="utf-8")
    after_stdout.write_text("", encoding="utf-8")
    after_stderr.write_text("blocked\n", encoding="utf-8")
    commands = [
        {
            "exit_code": 0,
            "stdout_path": str(original_hash_stdout),
            "stderr_path": str(original_hash_stderr),
            "command": ["original-hash"],
        },
        {
            "exit_code": 0,
            "stdout_path": str(patched_hash_stdout),
            "stderr_path": str(patched_hash_stderr),
            "command": ["patched-hash"],
        },
        {
            "exit_code": 0,
            "stdout_path": str(before_stdout),
            "stderr_path": str(before_stderr),
            "command": ["before"],
        },
        {
            "exit_code": 1,
            "stdout_path": str(after_stdout),
            "stderr_path": str(after_stderr),
            "command": ["after"],
        },
    ]

    monkeypatch.setattr(
        proof,
        "_copy_tree",
        lambda source, destination: destination.mkdir(
            parents=True,
            exist_ok=True,
        ),
    )
    monkeypatch.setattr(
        proof,
        "_python_docker_command",
        lambda **kwargs: ["python"],
    )

    call_index = 0

    def fake_run_command(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal call_index
        command = commands[call_index]
        call_index += 1
        return command

    monkeypatch.setattr(proof, "_run_command", fake_run_command)

    def fake_smoke_import(**kwargs: Any) -> bool:
        order.append("terminal")
        return True

    monkeypatch.setattr(proof, "_smoke_import", fake_smoke_import)

    def on_pressure(signal: dict[str, Any]) -> None:
        order.append("pressure")
        assert signal["parent_worker_id"] == "red-0"
        assert signal["parent_lane_id"] == "payload-857-receipt"
        assert signal["blue_worker_id"] == "blue-0"

    attempt = proof._judge_pair(
        out_dir=tmp_path / "proof",
        scenario={"scenario_id": "arena-zip-slip-import-001"},
        docker_image="python:3.12-slim",
        red={
            "worker_id": "red-0",
            "lane_id": "payload-857-receipt",
            "path": str(red_path),
        },
        blue={
            "worker_id": "blue-0",
            "action_id": "blue-0-patch",
            "path": str(blue_path),
        },
        on_parent_pressure_before_terminal=on_pressure,
    )

    assert order == ["pressure", "terminal"]
    assert attempt["verdict"] == "BLUE_SUCCESS"


def test_prekill_contract_requires_parent_pressure_inheritance_and_child_after_terminal() -> None:
    parent_lane = "payload-857-receipt"
    child_lane = "payload-857-red-1"
    inherited_refs = [
        {
            "kind": "parent_pressure",
            "receipt_id": "pressure-1",
            "sha256": "a" * 64,
        },
        {
            "kind": "parent_tau_subagent",
            "receipt_id": "parent-1",
            "sha256": "b" * 64,
        },
        {
            "kind": "parent_materialized_artifact",
            "receipt_id": "artifact-1",
            "sha256": "c" * 64,
        },
    ]
    pressure = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:pressure",
        lane_id=parent_lane,
        event_type="pressure_assessed",
        phase="pressure",
        actor_team="red",
        subagent_id="red-0",
        pressure_observation={
            "present": True,
            "signals": ["judge_block_receipt"],
            "baseline_probe_receipt_id": "before",
            "current_probe_receipt_id": "after",
            "pressure_score": 1.0,
            "confidence": "high",
            "suspected_pressure": False,
            "confirmed_blue_action": True,
            "source_receipt_id": "pressure-1",
            "source_receipt_sha256": "a" * 64,
            "overclaim_guard": (
                "observation_only_unless_blue_or_judge_receipt_present"
            ),
        },
        source_time={
            "started_elapsed_seconds": 1.0,
            "ended_elapsed_seconds": 1.0,
        },
    )
    spawn = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:spawn",
        lane_id=parent_lane,
        event_type="spawn_decision_recorded",
        phase="spawn_policy",
        actor_team="red",
        subagent_id="red-0",
        spawn_decision={
            "present": True,
            "decision": "strategic_pre_kill",
            "allowed": True,
            "parent_state": "alive",
            "author_worker_id": "red-0",
            "author_lane_id": parent_lane,
            "pressure_receipt_id": "pressure-1",
            "pressure_receipt_sha256": "a" * 64,
            "inherited_evidence_refs": inherited_refs,
            "child_exploit_id": child_lane,
            "confirmed_kill_receipt_before_spawn": False,
        },
        source_time={
            "started_elapsed_seconds": 2.0,
            "ended_elapsed_seconds": 2.0,
        },
    )
    child_materialized = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:child-materialized",
        lane_id=child_lane,
        event_type="child_materialized",
        phase="spawn",
        actor_team="red",
        subagent_id="red-1",
        parent_exploit_id=parent_lane,
        generation=1,
        source_time={
            "started_elapsed_seconds": 3.0,
            "ended_elapsed_seconds": 3.0,
        },
    )
    child_started = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:child-started",
        lane_id=child_lane,
        event_type="child_lifecycle_started",
        phase="runtime",
        actor_team="red",
        subagent_id="red-1",
        parent_exploit_id=parent_lane,
        generation=1,
        knowledge_packet={
            "present": True,
            "packet_id": "decision-1",
            "inherited_evidence_refs": inherited_refs,
            "research_goals": ["continue"],
            "parent_analysis": {},
            "child_ack": {
                "required": True,
                "received": True,
                "used_before_first_probe": True,
            },
        },
        source_time={
            "started_elapsed_seconds": 3.0,
            "ended_elapsed_seconds": 3.0,
        },
    )
    terminal = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:terminal",
        lane_id=parent_lane,
        event_type="judge_blue_success",
        phase="terminal",
        actor_team="judge",
        source_time={
            "started_elapsed_seconds": 3.5,
            "ended_elapsed_seconds": 4.0,
        },
    )
    lineage = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:lineage",
        lane_id=child_lane,
        event_type="lineage_registered",
        phase="spawn",
        actor_team="orchestrator",
        parent_exploit_id=parent_lane,
        generation=1,
        source_time={
            "started_elapsed_seconds": 2.5,
            "ended_elapsed_seconds": 3.0,
        },
    )
    post_terminal = proof._make_lifecycle_receipt(
        battle_id="battle-004",
        run_id="run-prekill-001",
        scenario_id="arena-zip-slip-import-001",
        receipt_id="lifecycle:post-terminal",
        lane_id=child_lane,
        event_type="child_lifecycle_receipt_after_parent_terminal",
        phase="post_parent_terminal",
        actor_team="red",
        subagent_id="red-1",
        parent_exploit_id=parent_lane,
        generation=1,
        evidence=[
            {
                "evidence_id": "child-judge-attempt",
                "evidence_type": "judge_action",
                "source": "judge",
                "sha256": "d" * 64,
            }
        ],
        source_time={
            "started_elapsed_seconds": 5.0,
            "ended_elapsed_seconds": 5.0,
        },
    )

    receipts = [
        pressure,
        spawn,
        child_materialized,
        child_started,
        terminal,
        lineage,
        post_terminal,
    ]
    contract = proof._prekill_survival_contract_from_receipts(receipts)
    assert contract["status"] == "PASS"

    spawn["spawn_decision"]["pressure_receipt_sha256"] = "wrong"
    contract = proof._prekill_survival_contract_from_receipts(receipts)
    assert contract["status"] == "INSUFFICIENT_EVIDENCE"
    assert "spawn decision pressure receipt hash does not match" in contract["errors"]

def test_live_lifecycle_receipts_reject_pressure_overclaimed_as_kill() -> None:
    bundle = {
        "schema": "battle.exploit_lifecycle_receipts.v1",
        "battle_id": "battle-004",
        "run_id": "run-overclaim",
        "scenario_id": "arena-zip-slip-import-001",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "proof_mode": "live_tau",
        "source": "battle_004_parent_spawn_live_tau",
        "receipts": [
            {
                "schema": "battle.exploit_lifecycle_receipt.v1",
                "receipt_id": "bad-pressure-kill",
                "battle_id": "battle-004",
                "run_id": "run-overclaim",
                "scenario_id": "arena-zip-slip-import-001",
                "lane_id": "payload-857-receipt",
                "source_time": {"sequence": 0, "clock": "battle_control_plane_perf_counter"},
                "actor": {"team": "orchestrator", "subagent_id": None, "persona_id": None, "tau_task_id": None},
                "exploit": {
                    "exploit_id": "payload-857-receipt",
                    "lineage_id": "battle-004:arena-zip-slip-import-001:lineage",
                    "parent_exploit_id": None,
                    "generation": 0,
                    "profile": {
                        "strength": 0.8,
                        "complexity": 0.7,
                        "durability": 0.7,
                        "score_weight": 0.7,
                        "actor_visual_variant_id": "crimson_hornbreaker",
                    },
                },
                "event_type": "pressure_assessed",
                "phase": "pressure",
                "evidence": [],
                "pressure_observation": {
                    "present": True,
                    "signals": ["stderr_drift", "response_body_drift"],
                    "baseline_probe_receipt_id": "baseline",
                    "current_probe_receipt_id": "current",
                    "pressure_score": 0.7,
                    "confidence": "medium",
                    "suspected_pressure": True,
                    "confirmed_blue_action": False,
                    "overclaim_guard": "observation_only_unless_blue_or_judge_receipt_present",
                },
                "spawn_decision": {
                    "present": False,
                    "decision": "none",
                    "allowed": False,
                    "reason_codes": [],
                    "parent_state": "alive",
                    "child_exploit_id": None,
                    "confirmed_kill_receipt_before_spawn": False,
                    "budget_remaining_after_spawn": 0,
                },
                "outcome": {
                    "candidate_class": "confirmed_blue_kill_no_child",
                    "required_receipt_ids": [],
                    "classification_reason": "bad overclaim",
                },
                "score": {
                    "applied": False,
                    "blue_points": 0,
                    "red_points": 0,
                    "score_weight": 0.7,
                    "scorekeeper_receipt_id": None,
                },
                "validation": {
                    "mocked": False,
                    "live": True,
                    "proof_mode": "live_tau",
                    "validator_version": "battle-live-lifecycle-v1",
                },
            }
        ],
        "summary": {
            "receipt_count": 1,
            "event_types": ["pressure_assessed"],
            "spawn_decisions": [],
            "pressure_receipt_count": 1,
            "lineage_receipt_count": 0,
            "outcome_classes": ["confirmed_blue_kill_no_child"],
            "bug_learning_notes": ["bad fixture"],
        },
        "claims": {"proves": ["bad"], "does_not_prove": ["bad"]},
    }
    with pytest.raises(ContractError, match="pressure observation must not claim confirmed kill"):
        validate_exploit_lifecycle_receipts(bundle)


def _minimal_lifecycle_bundle(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "battle.exploit_lifecycle_receipts.v1",
        "battle_id": "battle-004",
        "run_id": "run-contract-negative",
        "scenario_id": "arena-zip-slip-import-001",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "proof_mode": "live_tau",
        "source": "battle_004_parent_spawn_live_tau",
        "receipts": receipts,
        "summary": {
            "receipt_count": len(receipts),
            "event_types": [str(receipt.get("event_type")) for receipt in receipts],
            "spawn_decisions": [
                str(receipt.get("spawn_decision", {}).get("decision"))
                for receipt in receipts
                if isinstance(receipt.get("spawn_decision"), dict) and receipt.get("spawn_decision", {}).get("decision") != "none"
            ],
            "pressure_receipt_count": 0,
            "lineage_receipt_count": 0,
            "outcome_classes": [],
            "bug_learning_notes": ["contract negative fixture"],
        },
        "claims": {"proves": ["contract negative fixture"], "does_not_prove": ["live execution"]},
    }


def _minimal_receipt(receipt_id: str, event_type: str, phase: str) -> dict[str, Any]:
    return {
        "schema": "battle.exploit_lifecycle_receipt.v1",
        "receipt_id": receipt_id,
        "event_type": event_type,
        "phase": phase,
        "validation": {"mocked": False, "live": True, "proof_mode": "live_tau", "validator_version": "test"},
        "pressure_observation": {
            "present": False,
            "signals": [],
            "pressure_score": 0,
            "confidence": "none",
            "suspected_pressure": False,
            "confirmed_blue_action": False,
            "overclaim_guard": "observation_only_unless_blue_or_judge_receipt_present",
        },
        "spawn_decision": {
            "present": False,
            "decision": "none",
            "allowed": False,
            "reason_codes": [],
            "parent_state": "unknown",
            "child_exploit_id": None,
            "confirmed_kill_receipt_before_spawn": False,
            "budget_remaining_after_spawn": 0,
        },
        "outcome": {"candidate_class": "none", "required_receipt_ids": [], "classification_reason": ""},
        "score": {"applied": False, "blue_points": 0, "red_points": 0, "score_weight": 1, "scorekeeper_receipt_id": None},
    }


def _minimal_live_observation() -> dict[str, Any]:
    return {
        "present": True,
        "stdout": {},
        "stderr": {},
        "http_response": {},
        "timing": {},
        "network_summary": {
            "capture_requested": True,
            "available": False,
            "full_packet_capture_proven": False,
            "reason": "packet_capture_artifact_missing",
        },
    }


def test_lifecycle_validator_rejects_missing_packet_capture_diagnosis() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    probe = _minimal_receipt("probe", "probe_executed", "probe")
    probe["observation"] = {
        "present": True,
        "stdout": {},
        "stderr": {},
        "http_response": {},
        "timing": {},
        "network_summary": {
            "capture_requested": True,
            "available": False,
            "full_packet_capture_proven": False,
        },
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, probe])

    with pytest.raises(ContractError, match="unavailable network capture must include reason"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_spawn_without_parent_knowledge_packet() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    spawn = _minimal_receipt("spawn", "spawn_decision_recorded", "spawn_policy")
    spawn["spawn_decision"] = {
        "present": True,
        "decision": "strategic_pre_kill",
        "allowed": True,
        "reason_codes": ["suspected_pressure"],
        "parent_state": "alive",
        "child_exploit_id": "payload-857-red-1",
        "confirmed_kill_receipt_before_spawn": False,
        "budget_remaining_after_spawn": 100,
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, spawn])

    with pytest.raises(ContractError, match="spawn knowledge packet missing"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_uncalibrated_score_points() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    outcome = _minimal_receipt("outcome", "semantic_outcome_classified", "outcome")
    outcome["outcome"] = {
        "candidate_class": "pre_spawn_blue_block",
        "required_receipt_ids": ["judge"],
        "classification_reason": "fixture",
    }
    outcome["score"] = {
        "applied": True,
        "blue_points": 1,
        "red_points": 0,
        "score_weight": 0.5,
        "scorekeeper_receipt_id": "scoreboard.json",
        "score_calibration": {
            "schema": "battle.semantic_score_calibration.v1",
            "outcome_class": "pre_spawn_blue_block",
            "blue_base_points": 100,
            "red_base_points": 0,
            "score_weight": 0.5,
        },
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, outcome])

    with pytest.raises(ContractError, match="blue score does not match calibration"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_threat_assessment_claiming_kill() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    threat = _minimal_receipt("threat", "threat_assessment_recorded", "pressure")
    threat["observation"] = _minimal_live_observation()
    threat["threat_assessment"] = {
        "present": True,
        "schema": "battle.parent_threat_assessment.v1",
        "claim_authority": "tau_claim_only",
        "confirmed_kill": True,
        "cited_observation_receipt_ids": ["probe"],
        "cited_drift_receipt_ids": ["drift"],
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, threat])

    with pytest.raises(ContractError, match="threat assessment must not confirm kill"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_tau_spawn_request_with_battle_authority() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    request = _minimal_receipt("request", "spawn_request_recorded", "spawn_policy")
    request["spawn_request"] = {
        "present": True,
        "schema": "battle.spawn_request.v1",
        "claim_authority": "tau_claim_only",
        "requested_decision": "strategic_pre_kill",
        "child_exploit_id": "payload-857-red-1",
        "battle_allowed": True,
        "policy_owner": "battle",
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, request])

    with pytest.raises(ContractError, match="spawn request must not approve itself"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_tau_branch_decision_without_observed_evidence() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    branch = _minimal_receipt("branch", "tau_branch_decision_recorded", "branch")
    branch["tau_branch_decision"] = {
        "present": True,
        "schema": "battle.tau_branch_decision.v1",
        "decision_authority": "tau_subagent",
        "battle_policy_authority": "battle",
        "decision": "keep_going",
        "observed_evidence_refs": [],
        "rationale": "continue probing",
        "confidence": "medium",
        "why_not_spawn": "spawn is not useful yet",
        "battle_policy_result": "not_requested",
        "overclaim_guard": "tau_reasoning_only_battle_validates_policy_and_outcomes",
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, branch])

    with pytest.raises(ContractError, match="Tau branch decision must cite observed evidence refs"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_tau_branch_decision_overclaiming_kill() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    branch = _minimal_receipt("branch", "tau_branch_decision_recorded", "branch")
    branch["tau_branch_decision"] = {
        "present": True,
        "schema": "battle.tau_branch_decision.v1",
        "decision_authority": "tau_subagent",
        "battle_policy_authority": "battle",
        "decision": "spawn_requested",
        "observed_evidence_refs": ["probe", "drift"],
        "rationale": "claiming too much",
        "confidence": "high",
        "confirmed_kill": True,
        "requested_child_profile": {"child_exploit_id": "payload-857-red-1"},
        "inherited_goals": ["inherit parent context"],
        "battle_policy_result": "pending",
        "overclaim_guard": "tau_reasoning_only_battle_validates_policy_and_outcomes",
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, branch])

    with pytest.raises(ContractError, match="Tau branch decision must not confirm kill"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_requires_decision_specific_tau_branch_fields() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    branch = _minimal_receipt("branch", "tau_branch_decision_recorded", "branch")
    branch["tau_branch_decision"] = {
        "present": True,
        "schema": "battle.tau_branch_decision.v1",
        "decision_authority": "tau_subagent",
        "battle_policy_authority": "battle",
        "decision": "research_more",
        "observed_evidence_refs": ["probe", "drift"],
        "rationale": "needs more source context",
        "confidence": "low",
        "research_questions": [],
        "battle_policy_result": "not_requested",
        "overclaim_guard": "tau_reasoning_only_battle_validates_policy_and_outcomes",
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, branch])

    with pytest.raises(ContractError, match="research_more must include research questions"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_child_plan_without_inherited_refs() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    plan = _minimal_receipt("plan", "child_inherited_plan_recorded", "research")
    plan["knowledge_packet"] = {
        "present": True,
        "packet_id": "knowledge:parent",
        "research_goals": ["inherit parent analysis"],
        "child_ack": {"required": True, "received": True, "used_before_first_probe": True},
    }
    plan["child_plan"] = {
        "present": True,
        "schema": "battle.child_inherited_plan.v1",
        "plan_id": "child-plan",
        "knowledge_packet_id": "knowledge:parent",
        "inherited_item_refs": [],
        "used_before_first_probe": True,
        "scope_inherited": True,
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, plan])

    with pytest.raises(ContractError, match="child inherited refs missing"):
        validate_exploit_lifecycle_receipts(bundle)


def test_lifecycle_validator_rejects_child_probe_without_inherited_state() -> None:
    scenario = _minimal_receipt("scenario", "scenario_authorized", "authorized")
    runtime = _minimal_receipt("runtime", "runtime_provisioned", "runtime")
    probe = _minimal_receipt("probe", "child_inherited_probe_recorded", "probe")
    probe["observation"] = _minimal_live_observation()
    probe["inherited_probe"] = {
        "present": True,
        "schema": "battle.child_inherited_probe.v1",
        "child_plan_id": "child-plan",
        "knowledge_packet_id": "knowledge:parent",
        "used_inherited_state": False,
        "inherited_item_refs": ["knowledge:parent"],
    }
    bundle = _minimal_lifecycle_bundle([scenario, runtime, probe])

    with pytest.raises(ContractError, match="child inherited probe must use inherited state"):
        validate_exploit_lifecycle_receipts(bundle)
