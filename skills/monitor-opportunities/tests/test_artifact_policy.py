"""Artifact policy keeps networking intelligence out of outbound/application builders."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_meetup_source_intel_produces_no_resume_outreach_or_application_artifacts(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "discovery"
    meetup = fixture_dir / "meetup-buffalo-capture.json"
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["run", "--fixture-dir", str(fixture_dir), "--meetup-evidence", str(meetup), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "report-manifest.json").read_text())
    meetup_titles = {
        (row["title"], row["organization"])
        for row in manifest["source_intel"]
        if row["signal_type"] == "MEETUP_NETWORKING"
    }
    assert meetup_titles
    artifact_titles = {
        (row.get("title"), row.get("organization"))
        for row in manifest["opportunities"]
    }
    assert meetup_titles.isdisjoint(artifact_titles)
    assert all(row["decision"].endswith("_MEETUP") for row in manifest["source_intel"] if row["signal_type"] == "MEETUP_NETWORKING")
