from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from monitor_opportunities.cli import app
from monitor_opportunities.tailoring import _validate_no_prohibited_delta

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
    assert all(row["claim_refs"] for row in variant["rendered_statements"] if row["kind"] == "approved_claim")
    text = (out / "resume.txt").read_text(encoding="utf-8")
    assert "Target role: Principal AI Architect" in text
    with zipfile.ZipFile(out / "resume.docx") as docx:
        document = docx.read("word/document.xml").decode("utf-8")
    assert "Led ACERT architecture work" in document
    assert "<w:tbl" not in document
    approved_texts = {row["text"] for row in variant["rendered_statements"] if row["kind"] == "approved_claim"}
    for approved_line in approved_texts:
        assert approved_line in document


def test_tailor_rejects_missing_claim(tmp_path: Path) -> None:
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(
        json.dumps({"schema": "monitor_opportunities.claim_snapshot.v1", "active": True, "claims": []}),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["tailor", "--posting", "fixture:eligible-ai-architect", "--claims", str(claims_path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "missing approved claim" in result.stderr


def test_tailor_rejects_schema_document_instead_of_active_snapshot(tmp_path: Path) -> None:
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(json.dumps({"schema": "json_schema", "active": False, "claims": []}), encoding="utf-8")
    result = runner.invoke(
        app,
        ["tailor", "--posting", "fixture:eligible-ai-architect", "--claims", str(claims_path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "active claim snapshot required" in result.stderr


def test_tailor_rejects_stale_or_unapproved_claim(tmp_path: Path) -> None:
    claims = json.loads((Path(__file__).parent / "fixtures" / "claims" / "approved-claims.json").read_text())
    claims["claims"][0]["stale"] = True
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(json.dumps(claims), encoding="utf-8")
    result = runner.invoke(
        app,
        ["tailor", "--posting", "fixture:eligible-ai-architect", "--claims", str(claims_path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "missing approved claim" in result.stderr


@pytest.mark.parametrize(
    "line",
    [
        "Increased pipeline throughput by 47 percent.",
        "Served as Chief AI Officer at Acme Aerospace from 2021 to 2024.",
        "Built production systems in COBOLQuantum.",
        "Holds active TS/SCI clearance and unrestricted work authorization.",
        "Principal AI Architect was a historical employment title.",
        "Immediately amended the canonical claim ledger.",
    ],
)
def test_prohibited_factual_deltas_are_not_accepted(line: str) -> None:
    approved = {"Built document extraction systems that preserve source evidence."}
    assert _validate_no_prohibited_delta([line], approved) == [line]
