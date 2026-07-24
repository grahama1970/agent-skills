"""Regression tests for qualified code-symbol compatibility questions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _record(
    *,
    symbol_name: str = "run",
    qualified_name: str = "Service.run",
    path: str = "pkg/app.py",
    start_line: int = 10,
    end_line: int = 12,
) -> ingest_code.CodeSymbolRecord:
    return ingest_code.CodeSymbolRecord(
        scope="code",
        repo="repo",
        root="/repo",
        branch="main",
        commit="commit",
        path=path,
        language="python",
        symbol_kind="method",
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        start_line=start_line,
        end_line=end_line,
        signature="def run(self):",
        content_hash="hash",
        tags=["codebase", "symbol", "method", symbol_name, "app"],
    )


def test_problem_includes_canonical_source_range() -> None:
    record = _record(qualified_name="Service.run")

    assert record.source_locator == "pkg/app.py:10-12"
    assert record.problem == "What is Service.run in pkg/app.py:10-12?"


def test_same_qualified_symbol_same_path_different_ranges_has_distinct_problems() -> None:
    first = _record(qualified_name="Service.run", start_line=10, end_line=12)
    second = _record(qualified_name="Service.run", start_line=30, end_line=32)

    assert first.problem == "What is Service.run in pkg/app.py:10-12?"
    assert second.problem == "What is Service.run in pkg/app.py:30-32?"
    assert first.problem != second.problem


def test_single_line_symbol_uses_explicit_start_end_range() -> None:
    record = _record(
        symbol_name="run",
        qualified_name="run",
        path="app.py",
        start_line=3,
        end_line=3,
    )

    assert record.problem == "What is run in app.py:3-3?"


def test_invalid_or_nonpositive_range_falls_back_to_path_only() -> None:
    nonpositive = _record(start_line=0, end_line=12)
    inverted = _record(start_line=12, end_line=10)

    assert nonpositive.source_locator == "pkg/app.py"
    assert inverted.source_locator == "pkg/app.py"
    assert nonpositive.problem == "What is Service.run in pkg/app.py?"
    assert inverted.problem == "What is Service.run in pkg/app.py?"


def test_problem_and_solution_share_source_locator() -> None:
    record = _record(qualified_name="Service.run")

    assert record.problem == "What is Service.run in pkg/app.py:10-12?"
    assert record.solution.splitlines()[0] == "File: pkg/app.py:10-12"


def test_structured_legacy_and_verification_use_range_qualified_problem() -> None:
    record = _record(qualified_name="Service.run")

    structured = record.to_document()
    legacy = record.to_legacy_lesson_document()
    sample = ingest_code._code_symbol_verification_sample(record)

    assert structured["problem"] == "What is Service.run in pkg/app.py:10-12?"
    assert legacy["problem"] == "What is Service.run in pkg/app.py:10-12?"
    assert sample["problem"] == "What is Service.run in pkg/app.py:10-12?"
    assert structured["symbol_name"] == "run"
    assert structured["qualified_name"] == "Service.run"
    assert "symbol:run" in structured["lexical_terms"]
    assert "qualified:Service.run" in structured["lexical_terms"]
    assert sample["name"] == "run"
    assert sample["qualified_name"] == "Service.run"
