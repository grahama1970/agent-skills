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
