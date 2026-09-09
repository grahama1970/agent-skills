"""Contract tests for the paired adaptive-improvement Docker proof runner.

These exercise the runner's argument surface and fail-closed behavior without
Docker. The live Judge-replay effect is proven by the retained
`battle-adaptive-improvement` agentic eval, not here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prove_adaptive_improvement.py"


def _module():
    import os

    os.environ["BATTLE_ADAPTIVE_PROOF_RUNTIME"] = "1"
    spec = importlib.util.spec_from_file_location("prove_adaptive_improvement", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_unsupported_fixture_reports_not_proven(tmp_path: Path) -> None:
    mod = _module()
    output = tmp_path / "proof.json"
    receipt = mod.run(fixture="battle-999", output=output)

    assert receipt["status"] == "NOT_PROVEN"
    assert receipt["execution_started"] is False
    assert receipt["error"] == "ValueError: unsupported_fixture"
    assert json.loads(output.read_text()) == receipt


def test_missing_source_reports_not_proven_before_execution(tmp_path: Path) -> None:
    mod = _module()
    output = tmp_path / "proof.json"
    receipt = mod.run(
        fixture="battle-004",
        output=output,
        campaign_path=tmp_path / "absent-campaign.json",
        promotion_path=tmp_path / "absent-promotion.json",
    )

    assert receipt["status"] == "NOT_PROVEN"
    assert receipt["execution_started"] is False
    assert receipt["live"] is False
    assert receipt["mocked"] is False
    assert receipt["error"].startswith(("OSError", "FileNotFoundError", "ValueError", "KeyError"))


def test_proof_scope_never_claims_learning(tmp_path: Path) -> None:
    mod = _module()
    output = tmp_path / "proof.json"
    receipt = mod.run(fixture="battle-999", output=output)

    does_not_prove = receipt["proof_scope"]["does_not_prove"]
    assert "new provider learning" in does_not_prove
    assert "production-scale learning" in does_not_prove
    # A NOT_PROVEN receipt must not advertise a proven effect.
    assert receipt["proof_scope"]["proves"] == []
