from __future__ import annotations

import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from monitor_opportunities.cli import app

runner = CliRunner()


def test_tailor_writes_claim_bound_artifacts(tmp_path: Path) -> None:
    claims = Path(__file__).parent / "fixtures" / "claims" / "approved-claims.json"
    out = tmp_path / "tailor"
    result = runner.invoke(
        app,
        ["tailor", "--posting", "fixture:eligible-ai-architect", "--claims", str(claims), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    receipt = json.loads((out / "tailoring-receipt.json").read_text(encoding="utf-8"))
    variant = json.loads((out / "resume-variant.json").read_text(encoding="utf-8"))
    assert receipt["external_effects"] is False
    assert len(variant["claim_refs"]) == 3
    text = (out / "resume.txt").read_text(encoding="utf-8")
    assert "Target role: Principal AI Architect" in text
    with zipfile.ZipFile(out / "resume.docx") as docx:
        document = docx.read("word/document.xml").decode("utf-8")
    assert "Led ACERT architecture work" in document
    assert "<w:tbl" not in document


def test_tailor_rejects_missing_claim(tmp_path: Path) -> None:
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(json.dumps({"schema": "x", "active": True, "claims": []}), encoding="utf-8")
    result = runner.invoke(
        app,
        ["tailor", "--posting", "fixture:eligible-ai-architect", "--claims", str(claims_path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "missing approved claim" in result.stderr
