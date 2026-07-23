"""Regression tests for complete Python parameter enrichment."""

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


def _write(repo: Path, relative_path: str, content: str) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_python_parameters_include_all_argument_kinds_in_source_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def collect(pos_only, /, standard, *extras, keyword_only, **options):\n"
        "    return pos_only, standard, extras, keyword_only, options\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "collect", 1)

    assert details["parameters"] == [
        "pos_only",
        "standard",
        "extras",
        "keyword_only",
        "options",
    ]


def test_async_python_parameters_use_the_same_ordering(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "async def fetch(pos_only, /, standard, *extras, keyword_only, **options):\n"
        "    return pos_only, standard, extras, keyword_only, options\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "fetch", 1)

    assert details["parameters"] == [
        "pos_only",
        "standard",
        "extras",
        "keyword_only",
        "options",
    ]


def test_positional_only_self_preserves_existing_receiver_omission(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Collector:\n"
        "    def collect(self, pos_only, /, standard, *, keyword_only):\n"
        "        return pos_only, standard, keyword_only\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "collect", 2)

    assert details["parameters"] == ["pos_only", "standard", "keyword_only"]


def test_absent_vararg_and_kwarg_do_not_emit_empty_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def configure(pos_only, /, standard, *, keyword_only):\n"
        "    return pos_only, standard, keyword_only\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "configure", 1)

    assert details["parameters"] == ["pos_only", "standard", "keyword_only"]
    assert "" not in details["parameters"]


def test_code_symbol_record_contains_all_param_lexical_terms(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def collect(pos_only, /, standard, *extras, keyword_only, **options):\n"
        "    return pos_only, standard, extras, keyword_only, options\n",
    )

    record = ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": "collect",
            "start_line": 1,
            "end_line": 2,
            "signature": "def collect(...): ...",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )

    assert record is not None
    assert record.parameters == [
        "pos_only",
        "standard",
        "extras",
        "keyword_only",
        "options",
    ]
    for parameter in record.parameters:
        assert f"param:{parameter}" in record.lexical_terms
