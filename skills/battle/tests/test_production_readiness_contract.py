import json
from pathlib import Path

from battle_skill.production_readiness_contract import validate_production_readiness


def test_production_readiness_blocks_without_external_receipts(tmp_path: Path) -> None:
    containerized = _write_containerized_receipt(tmp_path / "containerized.json")

    receipt = validate_production_readiness(
        out_dir=tmp_path / "out",
        repo_root=Path.cwd().parents[1],
        containerized_receipt=containerized,
    )

    assert receipt["schema"] == "battle.production_readiness_contract.v1"
    assert receipt["status"] == "BLOCKED"
    assert receipt["mocked"] is False
    assert receipt["local_working_frontend_backend_status"] == "PASS"
    assert receipt["local_checks"][0]["status"] == "PASS"
    assert {blocker["id"] for blocker in receipt["blockers"]} == {
        "production_infrastructure_missing_or_not_pass",
        "production_websocket_missing_or_not_pass",
        "unbounded_swarm_missing_or_not_pass",
    }
    stored = json.loads((tmp_path / "out" / "production-readiness-contract.json").read_text(encoding="utf-8"))
    assert stored["status"] == "BLOCKED"


def test_production_readiness_fails_on_bad_local_container_receipt(tmp_path: Path) -> None:
    containerized = _write_containerized_receipt(tmp_path / "containerized.json", status="FAIL")

    receipt = validate_production_readiness(
        out_dir=tmp_path / "out",
        repo_root=Path.cwd().parents[1],
        containerized_receipt=containerized,
    )

    assert receipt["status"] == "FAIL"
    assert receipt["local_working_frontend_backend_status"] == "FAIL"
    assert "containerized receipt status is not PASS" in receipt["errors"]


def test_production_readiness_passes_with_all_required_receipts(tmp_path: Path) -> None:
    containerized = _write_containerized_receipt(tmp_path / "containerized.json")
    infrastructure = _write_external_receipt(
        tmp_path / "infrastructure.json",
        schema="battle.production_infrastructure_deployment_proof.v1",
    )
    websocket = _write_external_receipt(
        tmp_path / "websocket.json",
        schema="battle.production_websocket_transport_proof.v1",
    )
    swarm = _write_external_receipt(
        tmp_path / "swarm.json",
        schema="battle.unbounded_swarm_execution_proof.v1",
    )

    receipt = validate_production_readiness(
        out_dir=tmp_path / "out",
        repo_root=Path.cwd().parents[1],
        containerized_receipt=containerized,
        production_infrastructure_receipt=infrastructure,
        production_websocket_receipt=websocket,
        unbounded_swarm_receipt=swarm,
    )

    assert receipt["status"] == "PASS"
    assert receipt["blockers"] == []
    assert [check["status"] for check in receipt["external_checks"]] == ["PASS", "PASS", "PASS"]


def test_production_readiness_blocks_wrong_external_schema(tmp_path: Path) -> None:
    containerized = _write_containerized_receipt(tmp_path / "containerized.json")
    websocket = _write_external_receipt(
        tmp_path / "websocket.json",
        schema="example.external_proof.v1",
    )

    receipt = validate_production_readiness(
        out_dir=tmp_path / "out",
        repo_root=Path.cwd().parents[1],
        containerized_receipt=containerized,
        production_websocket_receipt=websocket,
    )

    websocket_check = next(check for check in receipt["external_checks"] if check["id"] == "production_websocket")
    assert receipt["status"] == "BLOCKED"
    assert websocket_check["status"] == "BLOCKED"
    assert websocket_check["expected_schema"] == "battle.production_websocket_transport_proof.v1"


def _write_containerized_receipt(path: Path, *, status: str = "PASS") -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "battle.containerized_deployment_smoke.v1",
                "status": status,
                "mocked": False,
                "live": "containerized_http_sse_websocket_adapter_plus_vite_preview",
                "counts": {
                    "pr8_failed": 0,
                    "test_interactions_failed": 0,
                    "test_interactions_warned": 0,
                    "visual_findings": 0,
                },
                "proofs": {
                    "backend_live_transport_receipt": "backend.json",
                    "pr8_live_transport_summary": "summary.json",
                    "test_interactions_results": "results.json",
                    "visual_findings": "visual-findings.jsonl",
                    "screenshot": "screenshot.png",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_external_receipt(path: Path, *, schema: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "status": "PASS",
                "mocked": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path
