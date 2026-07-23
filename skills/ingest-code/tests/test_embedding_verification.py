"""Regression tests for embedding recall verification identity matching."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _sample(**overrides: str) -> dict[str, str]:
    sample = {
        "name": "parse",
        "problem": "What is parse in parser.py?",
        "repo": "repo",
        "path": "src/parser.py",
        "qualified_name": "Parser.parse",
        "start_line": "10",
        "end_line": "24",
    }
    sample.update(overrides)
    return sample


def test_correct_item_after_same_name_collision(monkeypatch) -> None:
    calls = []

    def fake_recall(query: str, k: int = 1):
        calls.append((query, k))
        return {
            "items": [
                {
                    "repo": "repo",
                    "path": "tests/parser.py",
                    "qualified_name": "Parser.parse",
                    "start_line": 10,
                    "end_line": 24,
                    "solution": "File: tests/parser.py:10-24\nQualified name: Parser.parse",
                },
                {
                    "repo": "repo",
                    "path": "src/parser.py",
                    "qualified_name": "Parser.parse",
                    "start_line": 10,
                    "end_line": 24,
                    "solution": "File: src/parser.py:10-24\nQualified name: Parser.parse",
                },
            ]
        }

    monkeypatch.setattr(ingest_code, "_recall_http", fake_recall)

    result = ingest_code.verify_embedding_recall([_sample()], sample_size=1)

    assert result["passed"] == 1
    assert result["failed"] == 0
    assert calls == [("Parser.parse src/parser.py:10-24 repo", 5)]


def test_wrong_path_same_name_item_does_not_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest_code,
        "_recall_http",
        lambda query, k=1: {
            "items": [
                {
                    "repo": "repo",
                    "path": "tests/parser.py",
                    "qualified_name": "Parser.parse",
                    "start_line": 10,
                    "end_line": 24,
                }
            ]
        },
    )

    result = ingest_code.verify_embedding_recall([_sample()], sample_size=1)

    assert result["passed"] == 0
    assert result["failed"] == 1
    assert result["failures"][0]["query"] == "Parser.parse src/parser.py:10-24 repo"


@pytest.mark.parametrize(
    "item",
    [
        {
            "path": "src/parser.py",
            "qualified_name": "Parser.parse",
            "start_line": 10,
            "end_line": 24,
        },
        {
            "metadata": {
                "path": "src/parser.py",
                "qualified_name": "Parser.parse",
                "start_line": 10,
                "end_line": 24,
            }
        },
        {
            "solution": "File: src/parser.py:10-24\nQualified name: Parser.parse",
        },
    ],
)
def test_structured_and_legacy_response_shapes_match(monkeypatch, item: dict) -> None:
    monkeypatch.setattr(ingest_code, "_recall_http", lambda query, k=1: {"items": [item]})

    result = ingest_code.verify_embedding_recall([_sample()], sample_size=1)

    assert result["passed"] == 1
    assert result["failed"] == 0


def test_same_path_and_name_with_wrong_line_range_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest_code,
        "_recall_http",
        lambda query, k=1: {
            "items": [
                {
                    "path": "src/parser.py",
                    "qualified_name": "Parser.parse",
                    "start_line": 11,
                    "end_line": 24,
                }
            ]
        },
    )

    result = ingest_code.verify_embedding_recall([_sample()], sample_size=1)

    assert result["passed"] == 0
    assert result["failed"] == 1


def test_generic_lesson_verification_remains_name_only(monkeypatch) -> None:
    calls = []

    def fake_recall(query: str, k: int = 1):
        calls.append((query, k))
        return {"items": [{"solution": "The parse helper reads input."}]}

    monkeypatch.setattr(ingest_code, "_recall_http", fake_recall)

    result = ingest_code.verify_embedding_recall(
        [{"name": "parse", "problem": "What does parse do?"}],
        sample_size=1,
    )

    assert result["passed"] == 1
    assert result["failed"] == 0
    assert calls == [("parse", 1)]


def test_code_symbol_sample_preserves_exact_record_identity() -> None:
    record = ingest_code.CodeSymbolRecord(
        scope="test",
        repo="repo",
        root="/repo",
        branch="main",
        commit="abc",
        path="src/parser.py",
        language="python",
        symbol_kind="method",
        symbol_name="parse",
        qualified_name="Parser.parse",
        start_line=10,
        end_line=24,
    )

    assert ingest_code._code_symbol_verification_sample(record) == {
        "name": record.symbol_name,
        "problem": record.problem,
        "repo": record.repo,
        "path": record.path,
        "qualified_name": record.qualified_name,
        "start_line": str(record.start_line),
        "end_line": str(record.end_line),
    }
