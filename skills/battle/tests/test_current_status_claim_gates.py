from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


CLAIMS = {
    "production_deployment_ready": "battle.production_infrastructure_deployment_proof.v1",
    "full_adaptive_improvement_proven": "battle.full_adaptive_improvement_proof.v1",
    "kill_promotion_fastest_crash_supported": "battle.judge_kill_fastest_crash_semantics.v1",
    "fast_sanity_is_live_product_proof": "battle.live_product_qualification_receipt.v1",
}


def _load_current_status_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "current_status.py"
    spec = importlib.util.spec_from_file_location("battle_current_status", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated_status(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    mod = _load_current_status_module()
    path = tmp_path_factory.mktemp("current-status") / "CURRENT_STATUS.json"
    assert mod.generate(path) == 0
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_claimed_true(status: dict[str, Any], claim: str) -> dict[str, Any]:
    mutated = json.loads(json.dumps(status))
    mutated[claim] = True
    for item in mutated["unsupported"]:
        if item["claim"] == claim:
            item["status"] = "PASS"
            item["asserted"] = True
            break
    else:  # pragma: no cover - fixture contract guard
        raise AssertionError(f"unsupported claim missing: {claim}")
    return mutated


def test_generated_current_status_still_checks_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    generated_status: dict[str, Any],
) -> None:
    mod = _load_current_status_module()
    monkeypatch.setattr(mod, "TERMINAL_SEMANTICS_RECEIPT_PATH", tmp_path / "terminal-semantics.json")
    path = tmp_path / "CURRENT_STATUS.json"
    path.write_text(json.dumps(generated_status), encoding="utf-8")

    assert mod.check(path) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PASS"
    assert output["errors"] == []


@pytest.mark.parametrize("claim,required_schema", CLAIMS.items())
def test_unsupported_claim_true_requires_specific_receipt_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    generated_status: dict[str, Any],
    claim: str,
    required_schema: str,
) -> None:
    mod = _load_current_status_module()
    monkeypatch.setattr(mod, "TERMINAL_SEMANTICS_RECEIPT_PATH", tmp_path / f"terminal-{claim}.json")
    path = tmp_path / f"{claim}.json"
    path.write_text(json.dumps(_assert_claimed_true(generated_status, claim)), encoding="utf-8")

    assert mod.check(path) != 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAIL"
    error = f"unsupported_claim_promoted_without_receipt:{claim}:requires:{required_schema}"
    assert any(item.startswith(error) for item in output["errors"])
    if claim == "fast_sanity_is_live_product_proof":
        assert "fast_sanity_is_live_product_proof_requires_live_product_receipt_not_battle.tiered_fast_sanity_gate.v1" in output["errors"]
