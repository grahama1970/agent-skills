"""Regression tests for discrete Python declaration-marker matching."""

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


def _record(
    source: Path,
    repo: Path,
    *,
    kind: str,
    name: str,
    start_line: int,
    end_line: int,
    signature: str = "treesitter signature",
    docstring: str = "treesitter doc",
    parent: str = "TreeParent",
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": signature,
            "docstring": docstring,
            "parent": parent,
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_multiline_decorator_interior_line_is_not_exact_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorate(\n"
        "    value,\n"
        ")\n"
        "def run():\n"
        "    return 1\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 2)

    assert details == {}


def test_blank_line_between_decorator_and_definition_is_not_exact_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorate\n"
        "\n"
        "def run():\n"
        "    return 1\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 2)

    assert details == {}


def test_comment_line_between_decorator_and_definition_is_not_exact_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorate\n"
        "# comment\n"
        "def run():\n"
        "    return 1\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 2)

    assert details == {}


def test_each_decorator_start_and_definition_line_match_same_declaration(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@first\n"
        "@second(value)\n"
        "def run(arg):\n"
        "    return arg\n",
    )

    for line in (1, 2, 3):
        details = ingest_code._extract_python_symbol_details(
            source,
            "function",
            "run",
            line,
        )
        assert details["start_line"] == 1
        assert details["signature"] == "def run(arg):"


def test_undecorated_declaration_matches_only_definition_line(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(arg):\n"
        "    return arg\n",
    )

    matched = ingest_code._extract_python_symbol_details(source, "function", "run", 1)
    unmatched = ingest_code._extract_python_symbol_details(source, "function", "run", 2)

    assert matched["signature"] == "def run(arg):"
    assert unmatched == {}


def test_nonmarker_fallback_preserves_treesitter_fields_slice_and_hash(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorate(\n"
        "    value,\n"
        ")\n"
        "def run(arg):\n"
        "    \"\"\"Canonical doc.\"\"\"\n"
        "    return arg\n",
    )

    record = _record(
        source,
        repo,
        kind="method",
        name="run",
        start_line=2,
        end_line=2,
    )

    assert record is not None
    assert record.symbol_kind == "method"
    assert record.qualified_name == "TreeParent.run"
    assert record.start_line == 2
    assert record.end_line == 2
    assert record.signature == "treesitter signature"
    assert record.docstring == "treesitter doc"
    assert record.code == "    value,"
    assert record.content_hash == ingest_code._content_hash(record.code)
