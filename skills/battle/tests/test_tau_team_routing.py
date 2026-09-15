"""WebGPT B25 seed proof for Tau-routed Battle team authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from battle_skill.team_artifact_pipeline import tau_authoring_route_errors


BATTLE_ID = "battle-004"
RUN_ID = "run-b25"
AUTHORITY_REFS = {
    "authorization_receipt_sha256": "auth-sha",
    "evaluator_lock_sha256": "lock-sha",
}


def _task(team: str, role: str) -> dict[str, str]:
    return {
        "schema": "tau.battle_team_task_id.v1",
        "id": f"{BATTLE_ID}/{RUN_ID}/{team}/{role}",
        "battle_id": BATTLE_ID,
        "run_id": RUN_ID,
        "team": team,
        "role": role,
    }


def _route(
    team: str, role: str, *, router: str = "tau.battle_live_handoff"
) -> dict[str, str]:
    return {
        "boundary": "tau",
        "router": router,
        "route_id": f"tau://{BATTLE_ID}/{RUN_ID}/{team}/{role}",
    }


def _receipts(root: Path, team: str, role: str) -> tuple[dict[str, object], dict[str, object]]:
    response = root / f"{team}-response.json"
    response.write_text(json.dumps({"status": "PASS", "team": team, "role": role}), encoding="utf-8")
    response_sha = hashlib.sha256(response.read_bytes()).hexdigest()
    provider = {
        "schema": "tau.subagent_receipt.v1",
        "result": {"status": "PASS"},
        "tau_task": _task(team, role),
        "route_identity": _route(team, role),
        "authority_refs": AUTHORITY_REFS,
        "evaluator_authority": "locked_host_judge",
    }
    materialized = {
        "schema": "tau.battle_materialized_artifact_receipt.v1",
        "status": "PASS",
        "tau_task": _task(team, role),
        "route_identity": _route(team, role),
        "authority_refs": AUTHORITY_REFS,
        "scillm_call_receipt_sha256": response_sha,
        "retained_response_receipt": {
            "path": str(response),
            "sha256": response_sha,
        },
        "evaluator_authority": "locked_host_judge",
    }
    return provider, materialized


def test_scripted_red_and_blue_seats_cross_tau_route_boundary(tmp_path: Path) -> None:
    for team, role in [("red", "red_case_proposal"), ("blue", "blue_patch_proposal")]:
        provider, materialized = _receipts(tmp_path, team, role)

        assert tau_authoring_route_errors(
            team=team,
            battle_id=BATTLE_ID,
            run_id=RUN_ID,
            provider_payload=provider,
            materialization_payload=materialized,
        ) == []


def test_battle_local_provider_path_is_not_a_tau_scripted_seat(tmp_path: Path) -> None:
    provider, materialized = _receipts(tmp_path, "red", "red_case_proposal")
    provider["route_identity"] = _route("red", "red_case_proposal", router="battle-local-provider")
    materialized["route_identity"] = _route("red", "red_case_proposal", router="battle-local-provider")

    errors = tau_authoring_route_errors(
        team="red",
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau provider route uses Battle-local provider path" in errors
    assert "Tau materialization route uses Battle-local provider path" in errors


def test_arbitrary_non_battle_router_is_not_a_tau_scripted_seat(tmp_path: Path) -> None:
    provider, materialized = _receipts(tmp_path, "red", "red_case_proposal")
    provider["route_identity"] = _route("red", "red_case_proposal", router="other-router")
    materialized["route_identity"] = _route(
        "red", "red_case_proposal", router="other-router"
    )

    errors = tau_authoring_route_errors(
        team="red",
        battle_id=BATTLE_ID,
        run_id=RUN_ID,
        provider_payload=provider,
        materialization_payload=materialized,
    )

    assert "Tau provider route router is not tau.battle_live_handoff" in errors
    assert "Tau materialization route router is not tau.battle_live_handoff" in errors


def test_non_competitive_tau_states_do_not_become_wins(tmp_path: Path) -> None:
    for state in ["QUOTA_EXCEEDED", "TIMEOUT", "MALFORMED_RESPONSE", "CANCELLED"]:
        provider, materialized = _receipts(tmp_path, "red", "red_case_proposal")
        provider["result"] = {"status": state}

        errors = tau_authoring_route_errors(
            team="red",
            battle_id=BATTLE_ID,
            run_id=RUN_ID,
            provider_payload=provider,
            materialization_payload=materialized,
        )

        assert any("non-competitive result cannot be a win" in error for error in errors)
