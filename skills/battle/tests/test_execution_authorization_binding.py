"""Execution authorization binding tests for Battle production campaigns."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.campaign_contract import run_contract_campaign  # noqa: E402
from battle_skill.production_adapter import run_production_round  # noqa: E402
from test_campaign_contract import _profile, _request  # noqa: E402
from test_production_adapter import TARGET, _enrollment  # noqa: E402


def _authorization(path: Path, *, image: str, target: str = TARGET) -> str:
    canonical_id, immutable_ref = target.split("@", 1)
    path.write_text(json.dumps({
        "schema": "security.target_authorization.v1",
        "authorization_id": "battle-b04-test",
        "issuer": "agent-skills test",
        "approver": "agent-skills test",
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "target": {
            "kind": "docker-image",
            "canonical_id": canonical_id,
            "immutable_ref": immutable_ref,
            "image": image,
            "digest": image,
        },
        "allowed_target_urls": ["http://127.0.0.1"],
        "allowed_cidrs": ["127.0.0.0/8"],
        "allowed_ports": [80],
        "runtime_modes": ["docker"],
        "allowed_actions": ["battle"],
        "allowed_probe_classes": ["path_traversal"],
        "denied_probe_classes": [],
        "network_policy": "none",
        "egress_policy": "deny_external",
        "limits": {"requests_per_second": 1, "max_concurrency": 1, "duration_seconds": 60, "cpu": 1, "memory_mb": 256, "storage_mb": 128},
        "permissions": {"destructive": False, "persistence": False, "credential": False, "denial_of_service": False, "nonlocal": False},
        "artifact_root": "/tmp/battle-b04-test",
        "redaction_policy": "test fixture contains no secrets",
        "legal_non_opinion_ack": True,
    }), encoding="utf-8")
    return str(path)


def _docker_request(tmp_path: Path, image: str) -> dict:
    _profile()
    request = _request(tmp_path, f"docker run --rm -v {{input}}:/in:ro -v {{output}}:/out {image} run")
    return request


def test_production_adapter_binds_authorization_to_executable_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = "registry.example.invalid/target-b@sha256:222"
    request = _docker_request(tmp_path, image)
    calls: list[dict] = []

    def fake_campaign(bound_request: dict) -> dict:
        calls.append(copy.deepcopy(bound_request))
        return {"schema": "battle.campaign_contract_receipt.v1", "verdict": "PASS", "aggregation": {"cases_total": 1}}

    monkeypatch.setattr("battle_skill.production_adapter.run_contract_campaign", fake_campaign)
    result = run_production_round({
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": _authorization(tmp_path / "auth.json", image=image),
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
        "base_request": request,
        "enforce_docker_boundary": True,
    })

    assert result["status"] == "PASS"
    assert len(calls) == 1
    auth = calls[0]["authorization_receipt"]
    assert auth["status"] == "PASS"
    assert auth["expected_target"] == TARGET
    assert auth["expected_execution_target"] == image
    assert auth["requested_action"] == "battle"
    assert auth["requested_runtime_mode"] == "docker"


def test_authorization_for_other_image_blocks_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr("battle_skill.production_adapter.run_contract_campaign", lambda request: calls.append(request))
    result = run_production_round({
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": _authorization(tmp_path / "auth.json", image="registry.example.invalid/target-a@sha256:111"),
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
        "base_request": _docker_request(tmp_path, "registry.example.invalid/target-b@sha256:222"),
        "enforce_docker_boundary": True,
    })

    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "adapter-authorization-invalid"
    assert result["target_launches"] == 0
    assert calls == []
    assert "authorization target alias is not bound to executed target" in result["authorization_receipt"]["errors"]


def test_lower_level_docker_campaign_requires_bound_authorization_receipt(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="docker campaign request missing authorization_receipt"):
        run_contract_campaign(_docker_request(tmp_path, "registry.example.invalid/target-b@sha256:222"))


def test_lower_level_docker_campaign_rejects_receipt_for_other_image(tmp_path: Path) -> None:
    request = _docker_request(tmp_path, "registry.example.invalid/target-b@sha256:222")
    request["authorization_receipt"] = {
        "status": "PASS",
        "requested_action": "battle",
        "requested_runtime_mode": "docker",
        "expected_execution_target": "registry.example.invalid/target-a@sha256:111",
    }
    with pytest.raises(ValueError, match="docker campaign authorization target does not match executable image"):
        run_contract_campaign(request)
