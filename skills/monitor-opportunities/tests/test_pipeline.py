from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_run_creates_one_report_and_receipt(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "nightly"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "run-receipt.json").read_text(encoding="utf-8"))
    assert receipt["terminal_state"] == "AWAITING_HUMAN"
    assert receipt["external_effects"] is False
    assert (out / "report" / "index.html").exists()
    status = runner.invoke(app, ["resume", "--run", str(out)])
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["state"] == "AWAITING_HUMAN"
