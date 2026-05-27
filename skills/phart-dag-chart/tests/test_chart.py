"""Chart graph identity and label tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from phart_dag_chart.chart import dag_to_nx, render_chart
from phart_dag_chart.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_dag_to_nx_keeps_distinct_long_ids():
    prefix = "a" * 50
    dag = {
        "schema_version": "ask.dag.v1",
        "nodes": [
            {"id": f"{prefix}_memory", "type": "memory.recall", "depends_on": [], "input": {}},
            {"id": f"{prefix}_dogpile", "type": "dogpile.search", "depends_on": [], "input": {}},
        ],
    }
    graph = dag_to_nx(dag)
    assert graph.number_of_nodes() == 2
    assert f"{prefix}_memory" in graph
    assert f"{prefix}_dogpile" in graph


def test_node_labels_include_skill_and_model():
    from phart_dag_chart.dag_validate import validate_dag
    import json

    fanout = json.loads((FIXTURES / "memory-fanout.dag.json").read_text())
    normalized, _ = validate_dag(fanout, chart_only=True)
    final = next(n for n in normalized["nodes"] if n["id"] == "final_report")
    from phart_dag_chart.chart import _node_label

    assert "create-report" in _node_label(final)

    scillm_raw = json.loads((FIXTURES / "scillm-llm-call.dag.json").read_text())
    scillm_norm, _ = validate_dag(scillm_raw, chart_only=True)
    review = scillm_norm["nodes"][0]
    assert review["type"] == "ask.oracle"
    assert "gpt-5.5" in _node_label(review)


def test_chart_plain_skips_markdown_fence():
    result = runner.invoke(app, ["chart", str(FIXTURES / "memory-fanout.dag.json"), "--plain"])
    assert result.exit_code == 0
    assert "```" not in result.stdout


def test_scillm_fixture_validates():
    result = runner.invoke(app, ["validate", str(FIXTURES / "scillm-llm-call.dag.json"), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["node_count"] == 1


def test_validate_json_error_no_traceback(tmp_path: Path):
    bad = {
        "schema_version": "ask.dag.v1",
        "nodes": [
            {"id": "a", "type": "memory.recall", "depends_on": []},
            {"id": "a", "type": "memory.recall", "depends_on": []},
        ],
    }
    path = tmp_path / "dup.dag.json"
    path.write_text(json.dumps(bad))
    result = runner.invoke(app, ["validate", str(path), "--json"])
    assert result.exit_code == 1
    assert "Traceback" not in result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"]
