"""CLI contract tests for phart-dag-chart."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from phart_dag_chart.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_validate_ok():
    result = runner.invoke(app, ["validate", str(FIXTURES / "memory-fanout.dag.json"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["node_count"] == 3


def test_validate_duplicate_id(tmp_path: Path):
    bad = {
        "schema_version": "ask.dag.v1",
        "nodes": [
            {"id": "a", "type": "memory.recall", "depends_on": []},
            {"id": "a", "type": "memory.recall", "depends_on": []},
        ],
    }
    path = tmp_path / "bad.dag.json"
    path.write_text(json.dumps(bad))
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "duplicated" in result.stderr


def test_chart_renders_boxes():
    result = runner.invoke(app, ["chart", str(FIXTURES / "memory-fanout.dag.json")])
    assert result.exit_code == 0
    assert "┌" in result.stdout or "[" in result.stdout
    assert "memory_a" in result.stdout


def test_missing_file():
    result = runner.invoke(app, ["validate", "/nonexistent/dag.json"])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower()
