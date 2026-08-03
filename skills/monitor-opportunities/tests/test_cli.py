from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.verification import built_in_fixture

runner = CliRunner()


def test_status_json_is_truthful() -> None:
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["stage"] == "STAGE_0_RESEARCH_ONLY"
    assert payload["operational_readiness"] == "NOT_ESTABLISHED"
    assert payload["network_access"] is False
    assert payload["capabilities"]["gmail_send"] == "PERMANENTLY_FORBIDDEN"


def test_report_writes_self_contained_artifacts(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(built_in_fixture()), encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(app, ["report", "--input", str(input_path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    rendered = (out / "index.html").read_text(encoding="utf-8")
    assert "FEED_DOWN" in rendered
    assert "BLOCKED_STAGE_0" in rendered
    assert "human_required" in rendered
    assert "<form" not in rendered.lower()
    assert "<script" not in rendered.lower()
    assert "http://" not in rendered.lower()
    assert "https://" not in rendered.lower()
    assert json.loads((out / "report.json").read_text(encoding="utf-8"))["run_id"]


def test_verify_writes_passing_receipt(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verify", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((tmp_path / "verification-receipt.json").read_text(encoding="utf-8"))
    assert receipt["overall"] == "PASS"
    assert receipt["network_used"] is False
    assert receipt["external_effects"] is False
    assert len(receipt["cases"]) >= 9


def test_unsupported_command_fails_closed() -> None:
    result = runner.invoke(app, ["apply"])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload["status"] == "NOT_IMPLEMENTED"
    assert payload["external_effects"] is False


def test_unsupported_command_with_future_options_still_fails_closed() -> None:
    result = runner.invoke(app, ["apply", "--posting", "example", "--force"])
    assert result.exit_code == 3
    payload = json.loads(result.stderr)
    assert payload["status"] == "NOT_IMPLEMENTED"
    assert payload["command"] == "apply"
