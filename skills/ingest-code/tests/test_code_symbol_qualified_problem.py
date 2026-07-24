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
        start_line=10,
        end_line=12,
        signature="def run(self):",
        content_hash="hash",
        tags=["codebase", "symbol", "method", symbol_name, "app"],
    )


def test_nested_symbol_problem_uses_qualified_name() -> None:
    record = _record(qualified_name="Service.run")

    assert record.problem == "What is Service.run in app.py?"


def test_same_bare_names_in_different_ancestries_have_distinct_problems() -> None:
    alpha = _record(qualified_name="Alpha.run")
    beta = _record(qualified_name="Beta.run")

    assert alpha.symbol_name == beta.symbol_name == "run"
    assert alpha.problem == "What is Alpha.run in app.py?"
    assert beta.problem == "What is Beta.run in app.py?"
    assert alpha.problem != beta.problem


def test_top_level_symbol_problem_remains_unchanged() -> None:
    record = _record(symbol_name="run", qualified_name="run")

    assert record.problem == "What is run in app.py?"


def test_blank_qualified_name_falls_back_to_symbol_name() -> None:
    record = _record(symbol_name="run", qualified_name="  ")

    assert record.problem == "What is run in app.py?"


def test_structured_and_legacy_documents_share_qualified_problem() -> None:
    record = _record(qualified_name="Service.run")

    structured = record.to_document()
    legacy = record.to_legacy_lesson_document()

    assert structured["problem"] == "What is Service.run in app.py?"
    assert legacy["problem"] == "What is Service.run in app.py?"
    assert structured["symbol_name"] == "run"
    assert structured["qualified_name"] == "Service.run"
    assert "symbol:run" in structured["lexical_terms"]
    assert "qualified:Service.run" in structured["lexical_terms"]


def test_verification_sample_carries_qualified_problem() -> None:
    record = _record(qualified_name="Service.run")

    sample = ingest_code._code_symbol_verification_sample(record)

    assert sample["name"] == "run"
    assert sample["qualified_name"] == "Service.run"
    assert sample["problem"] == "What is Service.run in app.py?"
