"""Regression tests for isolating docstrings from Python string literals."""

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


def _details(
    source: Path,
    *,
    kind: str,
    name: str,
    start_line: int,
) -> dict:
    return ingest_code._extract_python_symbol_details(
        source,
        kind,
        name,
        start_line,
    )


def _record(
    source: Path,
    repo: Path,
    *,
    kind: str,
    name: str,
    start_line: int,
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": start_line,
            "signature": "treesitter signature",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_function_docstring_is_not_a_string_literal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"Run service.\"\"\"\n"
        "    value = 'body literal'\n"
        "    return value\n",
    )

    details = _details(source, kind="function", name="run", start_line=1)

    assert details["docstring"] == "Run service."
    assert "Run service." not in details["string_literals"]
    assert "body literal" in details["string_literals"]


def test_async_function_and_class_docstrings_are_not_literals(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "async def load():\n"
        "    \"\"\"Load service.\"\"\"\n"
        "    return 'async literal'\n"
        "\n"
        "class Service:\n"
        "    \"\"\"Service docs.\"\"\"\n"
        "    marker = 'class literal'\n",
    )

    async_details = _details(source, kind="function", name="load", start_line=1)
    class_details = _details(source, kind="class", name="Service", start_line=5)

    assert "Load service." not in async_details["string_literals"]
    assert "async literal" in async_details["string_literals"]
    assert "Service docs." not in class_details["string_literals"]
    assert "class literal" in class_details["string_literals"]


def test_nonleading_standalone_and_assigned_strings_remain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    value = 'assigned literal'\n"
        "    'standalone literal'\n"
        "    return value\n",
    )

    details = _details(source, kind="function", name="run", start_line=1)

    assert "assigned literal" in details["string_literals"]
    assert "standalone literal" in details["string_literals"]


def test_repeated_docstring_value_outside_docstring_remains_literal(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"shared literal\"\"\"\n"
        "    value = 'shared literal'\n"
        "    return value\n",
    )

    details = _details(source, kind="function", name="run", start_line=1)

    assert details["docstring"] == "shared literal"
    assert details["string_literals"] == ["shared literal"]


def test_multiline_docstring_emits_no_raw_or_cleaned_literal_duplicate(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"\n"
        "    Line one.\n"
        "\n"
        "        Line two.\n"
        "    \"\"\"\n"
        "    return 'body literal'\n",
    )

    details = _details(source, kind="function", name="run", start_line=1)

    assert "Line one." in details["docstring"]
    assert "Line two." in details["docstring"]
    assert all("Line one." not in literal for literal in details["string_literals"])
    assert all("Line two." not in literal for literal in details["string_literals"])
    assert "body literal" in details["string_literals"]


def test_document_keeps_docstring_but_omits_docstring_literal_term(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"Run service.\"\"\"\n"
        "    value = 'body literal'\n"
        "    return value\n",
    )

    record = _record(source, repo, kind="function", name="run", start_line=1)
    assert record is not None

    document = record.to_document()
    assert document["docstring"] == "Run service."
    assert "Run service." not in document["string_literals"]
    assert "literal:Run service." not in document["lexical_terms"]
    assert "Docstring:\nRun service." in document["solution"]
    assert "literal:body literal" in document["lexical_terms"]
