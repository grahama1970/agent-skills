from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def _sweep(tmp_path: Path) -> Path:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    out = tmp_path / "discovery"
    result = runner.invoke(app, ["sweep", "--fixture-dir", str(fixture_dir), "--lane", "A,B,C", "--out", str(out)])
    assert result.exit_code == 0, result.output
    return out


def test_rank_rejects_relocation_before_score(tmp_path: Path) -> None:
    discovery = _sweep(tmp_path)
    out = tmp_path / "ranking"
    result = runner.invoke(app, ["rank", "--input", str(discovery), "--limit", "8", "--out", str(out)])
    assert result.exit_code == 0, result.output
    shortlist = json.loads((out / "shortlist.json").read_text(encoding="utf-8"))
    rejected = json.loads((out / "rejections.json").read_text(encoding="utf-8"))
    assert all(item["candidate_id"] != "candidate:a:relocation" for item in shortlist)
    assert any(item["eligibility_state"] == "REJECT_RELOCATION_REQUIRED" for item in rejected)


def test_rank_is_stable_and_caps_shortlist(tmp_path: Path) -> None:
    discovery = _sweep(tmp_path)
    out = tmp_path / "ranking"
    result = runner.invoke(app, ["rank", "--input", str(discovery), "--limit", "1", "--out", str(out)])
    assert result.exit_code == 0, result.output
    shortlist = json.loads((out / "shortlist.json").read_text(encoding="utf-8"))
    assert len(shortlist) == 1
    assert shortlist[0]["eligibility_state"].startswith("ELIGIBLE_")
