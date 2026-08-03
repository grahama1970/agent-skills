from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_fixture_sweep_writes_receipts_and_candidates(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "discovery"
    result = runner.invoke(app, ["sweep", "--fixture-dir", str(fixture_dir), "--lane", "A,B,C", "--out", str(out)])
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_effects"] is False
    receipts = (out / "source-receipts.jsonl").read_text(encoding="utf-8").splitlines()
    candidates = (out / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(receipts) == 3
    assert len(candidates) == 3
    lane_summaries = json.loads((out / "lane-summaries.json").read_text(encoding="utf-8"))
    assert {row["lane"]: row["result_status"] for row in lane_summaries}["B"] == "FEED_DOWN"


def test_unattempted_lane_is_not_searched(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "discovery"
    result = runner.invoke(app, ["sweep", "--fixture-dir", str(fixture_dir), "--lane", "A", "--out", str(out)])
    assert result.exit_code == 0, result.output
    lane_summaries = json.loads((out / "lane-summaries.json").read_text(encoding="utf-8"))
    assert {row["lane"]: row["result_status"] for row in lane_summaries}["B"] == "NOT_SEARCHED"
