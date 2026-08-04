from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_buzz_review_emits_ops_buzz_agent_request_dry_run(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    run_dir = tmp_path / "nightly"
    run_result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(run_dir)])
    assert run_result.exit_code == 0, run_result.output

    out_dir = tmp_path / "buzz"
    result = runner.invoke(
        app,
        [
            "buzz-review",
            "--run",
            str(run_dir),
            "--channel",
            "00000000-0000-0000-0000-000000000000",
            "--target-agent",
            "codex",
            "--report-url",
            "http://example.invalid/report",
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    request = json.loads((out_dir / "buzz-agent-request.json").read_text(encoding="utf-8"))
    receipt = json.loads((out_dir / "buzz-agent-review-receipt.json").read_text(encoding="utf-8"))
    ops_buzz = receipt["ops_buzz_receipt"]["stdout_json"]

    assert request["schema"] == "ops_buzz.agent_request.v1"
    assert request["seam_validation"] == {"kind": "ops_buzz.agent_request.v1", "status": "PASS"}
    assert request["source_skill"] == "monitor-opportunities"
    assert request["source_artifact"] == str(run_dir / "report-manifest.json")
    assert request["source_url"] == "http://example.invalid/report"
    assert "Stay inside Stage 0" in request["prompt"]
    assert "Do not claim to apply, send, draft, or mutate" in request["expected_response"]

    assert receipt["status"] == "PASS"
    assert receipt["mocked"] is False
    assert receipt["live"] is False
    assert receipt["attempted_network"] is False
    assert receipt["external_effects"] is False
    assert ops_buzz["status"] == "DRY_RUN"
    assert ops_buzz["attempted_network"] is False
    assert (out_dir / "buzz-agent-request.md").exists()
