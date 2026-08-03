from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_empty_candidate_run_exits_zero(tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    (discovery / "candidates.jsonl").write_text("", encoding="utf-8")
    out = tmp_path / "ranking"
    result = runner.invoke(app, ["rank", "--input", str(discovery), "--limit", "8", "--out", str(out)])
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "ranking-receipt.json").read_text(encoding="utf-8"))
    assert receipt["shortlisted"] == 0
    assert json.loads((out / "shortlist.json").read_text(encoding="utf-8")) == []
