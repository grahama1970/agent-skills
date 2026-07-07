from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill import arena_battle_proof as proof  # noqa: E402
from battle_skill import cli as battle_cli  # noqa: E402


def test_ssrf_metadata_probe_arena_battle_contract(tmp_path: Path, monkeypatch) -> None:
    def fake_arena(*, out_dir: Path, battle_id: str, run_id: str, prior_scoreboard: Path | None, query: str, docker_image: str) -> dict[str, Any]:
        (out_dir / "target").mkdir(parents=True, exist_ok=True)
        (out_dir / "team-public" / "target").mkdir(parents=True, exist_ok=True)
        (out_dir / "private" / "oracle").mkdir(parents=True, exist_ok=True)
        (out_dir / "target" / "app.py").write_text("def placeholder(): return True\n", encoding="utf-8")
        (out_dir / "arena-receipt.json").write_text(json.dumps({"status": "PASS"}) + "\n", encoding="utf-8")
        (out_dir / "run-receipt.json").write_text(json.dumps({"status": "PASS"}) + "\n", encoding="utf-8")
        (out_dir / "scenario.json").write_text(
            json.dumps(
                {
                    "schema": "battle.arena_scenario.v1",
                    "battle_id": battle_id,
                    "run_id": run_id,
                    "scenario_id": "placeholder",
                    "scenario_kind": "zip-slip",
                    "public_entrypoint": "/api/import-zip",
                    "target_language": "python",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return {"status": "PASS", "battle_id": battle_id, "run_id": run_id, "mocked": False}

    def fake_docker_image_id(image: str) -> str:
        return f"sha256:test-{image}"

    def fake_run_command(command: list[str], *, out_dir: Path, name: str) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = out_dir / f"{name}.stdout.txt"
        stderr_path = out_dir / f"{name}.stderr.txt"
        stdout = ""
        exit_code = 0
        if name in {"ssrf-metadata-hidden-oracle", "red-exploit"}:
            stdout = "SSRF_METADATA_CONFIRMED\n"
        elif name == "judge-functionality":
            stdout = "True\n"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "command": command,
            "exit_code": exit_code,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }

    monkeypatch.setattr(proof, "run_arena_subagent_proof", fake_arena)
    monkeypatch.setattr(proof, "_docker_image_id", fake_docker_image_id)
    monkeypatch.setattr(proof, "_run_command", fake_run_command)

    receipt = proof.run_arena_battle_proof(
        out_dir=tmp_path / "proof",
        battle_id="battle-005",
        run_id="run-ssrf",
        scenario_kind="ssrf-metadata-probe",
    )

    scenario = json.loads((tmp_path / "proof" / "arena" / "scenario.json").read_text(encoding="utf-8"))
    override = json.loads((tmp_path / "proof" / "arena" / "ssrf-metadata-hidden-oracle-receipt.json").read_text(encoding="utf-8"))
    red = json.loads((tmp_path / "proof" / "red-receipt.json").read_text(encoding="utf-8"))
    judge = json.loads((tmp_path / "proof" / "judge" / "judge-receipt.json").read_text(encoding="utf-8"))
    scoreboard = json.loads((tmp_path / "proof" / "scoreboard.json").read_text(encoding="utf-8"))

    assert receipt["status"] == "PASS"
    assert receipt["live"] == "brave_search_and_docker_red_blue_judge"
    assert receipt["artifacts"]["arena_override_oracle_receipt"] == "arena/ssrf-metadata-hidden-oracle-receipt.json"
    assert scenario["scenario_id"] == "arena-ssrf-metadata-probe-001"
    assert scenario["scenario_kind"] == "ssrf-metadata-probe"
    assert scenario["cwe"] == "CWE-918"
    assert override["status"] == "PASS"
    assert override["mocked"] is False
    assert override["exploit_confirmed"] is True
    assert red["finding_id"] == "arena-hidden-ssrf-metadata-001"
    assert red["exploit_confirmed"] is True
    assert judge["verdict"] == "BLUE_SUCCESS"
    assert scoreboard["verdict"] == "BLUE_SUCCESS"
    assert scoreboard["asc"] == 1


def test_arena_battle_proof_cli_accepts_ssrf_metadata_probe(tmp_path: Path, monkeypatch) -> None:
    calls: dict[str, Any] = {}

    def fake_run_arena_battle_proof(**kwargs: Any) -> dict[str, Any]:
        calls.update(kwargs)
        return {
            "status": "PASS",
            "battle_id": kwargs["battle_id"],
            "run_id": kwargs["run_id"],
            "scenario_kind": kwargs["scenario_kind"],
        }

    monkeypatch.setattr(proof, "run_arena_battle_proof", fake_run_arena_battle_proof)

    result = CliRunner().invoke(
        battle_cli.app,
        [
            "arena-battle-proof",
            "battle-005",
            "--out",
            str(tmp_path / "proof"),
            "--scenario-kind",
            "ssrf-metadata-probe",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["battle_id"] == "battle-005"
    assert calls["scenario_kind"] == "ssrf-metadata-probe"
