"""Evaluator lock enforcement tests for Battle executable components."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.campaign_contract import run_contract_campaign, validate_request  # noqa: E402
from battle_skill.evaluator_lock import verify_evaluator_lock  # noqa: E402
from test_execution_authorization_binding import _authorization, _docker_request  # noqa: E402


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _lock(path: Path, request: dict, *, extra_files: list[str] | None = None) -> str:
    files = [
        str(Path(request["generator"]).resolve()),
        str(Path(request["judge"]).resolve()),
        str(Path(request["functional_judge"]).resolve()),
        str((REPO / "skills/battle/src/battle_skill/campaign_contract.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/invariant_campaign.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/invariant_judge.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/production_adapter.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/docker_runtime.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/strict_json.py").resolve()),
        str((REPO / "skills/battle/src/battle_skill/evaluator_lock.py").resolve()),
        *(extra_files or []),
    ]
    manifest = sorted([[item, _sha(Path(item))] for item in files])
    path.write_text(json.dumps({
        "schema": "battle.evaluator_lock.v1",
        "source_repo_path": "/",
        "commit": "test",
        "bundle_files": files,
        "bundle_manifest_sha256": "sha256:" + hashlib.sha256(json.dumps(manifest).encode()).hexdigest(),
    }), encoding="utf-8")
    return str(path)


def test_docker_campaign_verifies_lock_before_loading_generator(tmp_path: Path) -> None:
    request = _docker_request(tmp_path, "registry.example.invalid/target@sha256:1")
    request["authorization_receipt"] = {
        "status": "PASS",
        "requested_action": "battle",
        "requested_runtime_mode": "docker",
        "expected_execution_target": "registry.example.invalid/target@sha256:1",
    }
    request["lock_path"] = _lock(tmp_path / "battle.lock.json", request)
    validate_request(request)
    assert request["evaluator_lock_receipt"]["status"] == "PASS"


def test_changed_imported_helper_invalidates_lock_before_launch(tmp_path: Path) -> None:
    request = _docker_request(tmp_path, "registry.example.invalid/target@sha256:1")
    helper = tmp_path / "helper.py"
    helper.write_text("value = 1\n", encoding="utf-8")
    request["lock_path"] = _lock(tmp_path / "battle.lock.json", request, extra_files=[str(helper)])
    helper.write_text("value = 2\n", encoding="utf-8")
    receipt = verify_evaluator_lock(request["lock_path"], request)
    assert receipt["status"] == "BLOCKED"
    assert "lock bundle manifest mismatch" in receipt["problems"][0]


def test_worker_cannot_replace_evaluator_and_expected_digest_in_request(tmp_path: Path) -> None:
    request = _docker_request(tmp_path, "registry.example.invalid/target@sha256:1")
    request["generator"] = str(tmp_path / "evil_generator.py")
    Path(request["generator"]).write_text("def generate(work_dir, params):\n    return []\n", encoding="utf-8")
    request["lock_path"] = _lock(tmp_path / "battle.lock.json", _docker_request(tmp_path, "registry.example.invalid/target@sha256:1"))
    receipt = verify_evaluator_lock(request["lock_path"], request)
    assert receipt["status"] == "BLOCKED"
    assert "generator not covered by evaluator lock" in receipt["problems"][0]


def test_lock_mismatch_produces_zero_target_launches(tmp_path: Path) -> None:
    request = _docker_request(tmp_path, "registry.example.invalid/target@sha256:1")
    request["authorization_receipt"] = {
        "status": "PASS",
        "requested_action": "battle",
        "requested_runtime_mode": "docker",
        "expected_execution_target": "registry.example.invalid/target@sha256:1",
    }
    lock = tmp_path / "battle.lock.json"
    request["lock_path"] = _lock(lock, request)
    data = json.loads(lock.read_text())
    data["bundle_manifest_sha256"] = "sha256:" + "0" * 64
    lock.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="lock-verification-failed"):
        run_contract_campaign(request)
    assert not (tmp_path / "work" / "out").exists()
