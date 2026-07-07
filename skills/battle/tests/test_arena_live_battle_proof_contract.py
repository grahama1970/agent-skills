from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill import arena_live_battle_proof as proof  # noqa: E402
from battle_skill import cli as battle_cli  # noqa: E402


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
    assert calls["timeout_s"] == 240.0
    assert calls["red_workers"] == 2
    assert calls["blue_workers"] == 2
    assert calls["spawn_red_child_on_blue_success"] is True
    assert calls["run_id"].startswith("arena-parent-spawn-")
