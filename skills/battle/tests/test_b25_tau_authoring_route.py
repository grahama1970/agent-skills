"""B25: Red/Blue authoring must cross the Tau route boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_skill.team_artifact_pipeline import (
    annotate_tau_authoring_route_receipts,
    run_team_artifact_pipeline,
    tau_authoring_route_errors,
)


def _response(root: Path, team: str, role: str) -> Path:
    path = root / f"{team}-tau-response-receipt.json"
    path.write_text(json.dumps({"status": "PASS", "team": team, "role": role}), encoding="utf-8")
    return path


def _provider(team: str, role: str) -> dict[str, object]:
    return {
        "schema": "tau.subagent_receipt.v1",
        "result": {"status": "PASS"},
        "tau_task": {
            "schema": "tau.battle_team_task_id.v1",
            "id": f"battle-004/run-b25/{team}/{role}",
            "battle_id": "battle-004",
            "run_id": "run-b25",
            "team": team,
            "role": role,
        },
        "route_identity": {
            "boundary": "tau",
            "router": "tau.battle_live_handoff",
            "route_id": f"tau://battle-004/run-b25/{team}/{role}",
        },
        "authority_refs": {
            "authorization_receipt_sha256": "auth-sha",
            "evaluator_lock_sha256": "lock-sha",
        },
        "evaluator_authority": "locked_host_judge",
    }


def _materialized(root: Path, source: Path, team: str, role: str, artifact_type: str) -> dict[str, object]:
    receipt = _response(root, team, role)
    receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return {
        "schema": "tau.battle_materialized_artifact_receipt.v1",
        "status": "PASS",
        "artifact_type": artifact_type,
        "path": str(source.resolve()),
        "artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "artifact_bytes": source.stat().st_size,
        "strategy_genome_sha256": "genome-sha",
        "scillm_call_receipt_sha256": receipt_sha,
        "tau_task": {
            "schema": "tau.battle_team_task_id.v1",
            "id": f"battle-004/run-b25/{team}/{role}",
            "battle_id": "battle-004",
            "run_id": "run-b25",
            "team": team,
            "role": role,
        },
        "route_identity": {
            "boundary": "tau",
            "router": "tau.battle_live_handoff",
            "route_id": f"tau://battle-004/run-b25/{team}/{role}",
        },
        "authority_refs": {
            "authorization_receipt_sha256": "auth-sha",
            "evaluator_lock_sha256": "lock-sha",
        },
        "retained_response_receipt": {
            "path": str(receipt),
            "sha256": receipt_sha,
        },
        "evaluator_authority": "locked_host_judge",
    }


def test_b25_accepts_red_and_blue_tau_routed_authoring(tmp_path: Path) -> None:
    red_source = tmp_path / "red.py"
    red_source.write_text("from app import import_zip\n", encoding="utf-8")
    blue_source = tmp_path / "blue.py"
    blue_source.write_text("def import_zip(src, dst):\n    return None\n", encoding="utf-8")

    red_provider = _provider("red", "red_case_proposal")
    red_materialized = _materialized(tmp_path, red_source, "red", "red_case_proposal", "red_exploit")
    blue_provider = _provider("blue", "blue_patch_proposal")
    blue_materialized = _materialized(tmp_path, blue_source, "blue", "blue_patch_proposal", "blue_patch")

    assert tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=red_provider,
        materialization_payload=red_materialized,
    ) == []
    assert tau_authoring_route_errors(
        team="blue",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=blue_provider,
        materialization_payload=blue_materialized,
    ) == []


def test_b25_blocks_team_worker_evaluator_authority_override(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
    materialized["evaluator_authority_override"] = "worker_selected_judge"

    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau materialization attempted evaluator authority override" in errors


def test_b25_annotation_replaces_worker_authority_refs(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider_path = tmp_path / "provider.json"
    materialized_path = tmp_path / "materialized.json"
    scillm_path = _response(tmp_path, "red", "red_case_proposal")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(
        tmp_path, source, "red", "red_case_proposal", "red_exploit"
    )
    provider["authority_refs"] = {
        "authorization_receipt_sha256": "worker-auth",
        "evaluator_lock_sha256": "worker-lock",
    }
    materialized["authority_refs"] = dict(provider["authority_refs"])
    materialized["retained_response_receipt"] = {"path": str(scillm_path), "sha256": "stale"}
    provider_path.write_text(json.dumps(provider), encoding="utf-8")
    materialized_path.write_text(json.dumps(materialized), encoding="utf-8")

    trusted = {
        "authorization_receipt_sha256": "controller-auth",
        "evaluator_lock_sha256": "controller-lock",
    }
    annotate_tau_authoring_route_receipts(
        battle_id="battle-004",
        run_id="run-b25",
        team="red",
        worker_id="red-0",
        provider_receipt=provider_path,
        materialization_receipt=materialized_path,
        scillm_call_receipt=scillm_path,
        authority_refs=trusted,
    )

    assert json.loads(provider_path.read_text(encoding="utf-8"))["authority_refs"] == trusted
    assert json.loads(materialized_path.read_text(encoding="utf-8"))["authority_refs"] == trusted
    refreshed = json.loads(materialized_path.read_text(encoding="utf-8"))["retained_response_receipt"]
    assert refreshed["sha256"] == hashlib.sha256(scillm_path.read_bytes()).hexdigest()


def test_b25_blocks_retained_response_receipt_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
    materialized["retained_response_receipt"]["sha256"] = "0" * 64

    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau materialization retained response receipt sha mismatch" in errors


def test_b25_blocks_non_competitive_retained_response_status(tmp_path: Path) -> None:
    for state in ["TIMEOUT", "PROVIDER_QUOTA_EXCEEDED", "CANCELLED"]:
        source = tmp_path / "red.py"
        source.write_text("from app import import_zip\n", encoding="utf-8")
        provider = _provider("red", "red_case_proposal")
        materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
        receipt = tmp_path / "red-tau-response-receipt.json"
        receipt.write_text(
            json.dumps({"status": state, "team": "red", "role": "red_case_proposal"}),
            encoding="utf-8",
        )
        sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
        materialized["retained_response_receipt"]["sha256"] = sha
        materialized["scillm_call_receipt_sha256"] = sha

        errors = tau_authoring_route_errors(
            team="red",
            battle_id="battle-004",
            run_id="run-b25",
            provider_payload=provider,
            materialization_payload=materialized,
        )

        assert any(
            "retained response receipt non-competitive status cannot be a win" in error
            for error in errors
        ), state


def test_b25_blocks_non_competitive_retained_result_status(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
    receipt = tmp_path / "red-tau-response-receipt.json"
    receipt.write_text(
        json.dumps({"status": "PASS", "result": {"status": "TIMEOUT"}}), encoding="utf-8"
    )
    sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    materialized["retained_response_receipt"]["sha256"] = sha
    materialized["scillm_call_receipt_sha256"] = sha

    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert any(
        "retained response receipt non-competitive status cannot be a win" in error
        for error in errors
    )


def test_b25_blocks_scillm_call_receipt_binding_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
    materialized["scillm_call_receipt_sha256"] = "call-sha"

    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert (
        "Tau materialization SciLLM call receipt binding does not match retained response receipt"
        in errors
    )

    del materialized["scillm_call_receipt_sha256"]
    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau materialization missing SciLLM call receipt binding" in errors


def test_b25_blocks_task_and_route_ids_for_wrong_team_role(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider = _provider("red", "red_case_proposal")
    materialized = _materialized(
        tmp_path, source, "red", "red_case_proposal", "red_exploit"
    )
    provider["tau_task"]["id"] = "battle-004/run-b25/red/other-role"
    materialized["tau_task"]["id"] = provider["tau_task"]["id"]
    provider["route_identity"]["route_id"] = "tau://battle-004/run-b25/red/other-role"
    materialized["route_identity"]["route_id"] = provider["route_identity"]["route_id"]

    errors = tau_authoring_route_errors(
        team="red",
        battle_id="battle-004",
        run_id="run-b25",
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau authoring route task id does not match Battle team role" in errors
    assert "Tau provider route id does not match Battle team role" in errors
    assert "Tau materialization route id does not match Battle team role" in errors


def test_b25_pipeline_blocks_missing_tau_route_before_compile(tmp_path: Path) -> None:
    source = tmp_path / "red.py"
    source.write_text("from app import import_zip\n", encoding="utf-8")
    provider_path = tmp_path / "provider.json"
    provider_path.write_text(json.dumps({"schema": "tau.subagent_receipt.v1", "result": {"status": "PASS"}}), encoding="utf-8")
    materialized = _materialized(tmp_path, source, "red", "red_case_proposal", "red_exploit")
    materialized_path = tmp_path / "materialized.json"
    materialized_path.write_text(json.dumps(materialized), encoding="utf-8")

    try:
        run_team_artifact_pipeline(
            battle_id="battle-004",
            run_id="run-b25",
            generation=1,
            team="red",
            source_artifact=source,
            provider_receipt=provider_path,
            materialization_receipt=materialized_path,
            target_identity_sha256="target-sha",
            out_dir=tmp_path / "pipeline",
        )
    except ValueError as exc:
        assert "Tau authoring route missing typed task ids" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing Tau route was accepted")
