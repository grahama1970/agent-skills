"""Report-visible artifact accounting is authoritative."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_authoritative_shortlist_cap_prevents_hidden_downstream_ids(tmp_path: Path) -> None:
    source = Path(__file__).parent / "fixtures" / "discovery" / "discovery-run.json"
    payload = json.loads(source.read_text())
    base = payload["candidates"][0]
    payload["candidates"] = [
        {
            **base,
            "candidate_id": f"candidate:a:visible-{i}",
            "title": f"Principal AI Architect {i}",
            "organization": f"Acme Aerospace {i}",
            "fit_score": 0.99 - (i * 0.01),
        }
        for i in range(10)
    ] + payload["candidates"][1:]
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    (fixture_dir / "discovery-run.json").write_text(json.dumps(payload), encoding="utf-8")

    out = tmp_path / "run"
    result = runner.invoke(app, ["run", "--fixture-dir", str(fixture_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "report-manifest.json").read_text())
    assert len(manifest["opportunities"]) == 8
    downstream_ids = {
        row["opportunity_id"]
        for section in ("resume_variants", "outreach_packets", "applications", "application_packets")
        for row in manifest[section]
    }
    visible_ids = {row["opportunity_id"] for row in manifest["opportunities"]}
    assert downstream_ids <= visible_ids
    assert manifest["artifact_accounting"]["hidden_total"] == 0
    assert manifest["artifact_accounting"]["action_worthy_total"] == manifest["artifact_accounting"]["visible_total"]
