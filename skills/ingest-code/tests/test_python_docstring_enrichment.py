"""Regression tests for exact-AST Python docstring canonicalization."""

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
    docstring: str = "",
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": f"{kind} {name}(...): ...",
            "docstring": docstring,
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_exact_function_docstring_overrides_conflicting_treesitter_value(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"Canonical doc.\"\"\"\n"
        "    return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=3,
        docstring="stale treesitter doc",
    )

    assert record is not None
    assert record.docstring == "Canonical doc."


def test_exact_match_without_docstring_clears_stale_treesitter_value(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=2,
        docstring="stale treesitter doc",
    )

    assert record is not None
    assert record.docstring == ""


def test_exact_async_function_and_class_docstrings_are_canonicalized(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    \"\"\"Service doc.\"\"\"\n"
        "\n"
        "async def run():\n"
        "    \"\"\"Async doc.\"\"\"\n"
        "    return 1\n",
    )

    cls = _record(
        source,
        repo,
        kind="class",
        name="Service",
        start_line=1,
        end_line=2,
        docstring="stale class doc",
    )
    function = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=4,
        end_line=6,
        docstring="stale async doc",
    )

    assert cls is not None
    assert function is not None
    assert cls.docstring == "Service doc."
    assert function.docstring == "Async doc."


def test_multiline_docstring_uses_ast_cleaning(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"\n"
        "    Summary.\n"
        "\n"
        "        Indented detail.\n"
        "    \"\"\"\n"
        "    return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=7,
        docstring='''"""raw stale"""''',
    )

    assert record is not None
    assert record.docstring == "Summary.\n\n    Indented detail."


def test_document_solution_and_text_use_only_canonical_docstring(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"Canonical doc.\"\"\"\n"
        "    return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=3,
        docstring="stale treesitter doc",
    )

    assert record is not None
    document = record.to_document()
    assert document["docstring"] == "Canonical doc."
    assert "Docstring:\nCanonical doc." in document["solution"]
    assert "Docstring:\nCanonical doc." in document["text"]
    assert "stale treesitter doc" not in document["solution"]
    assert "stale treesitter doc" not in document["text"]


def test_unmatched_ast_preserves_treesitter_docstring(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run():\n"
        "    \"\"\"Canonical doc.\"\"\"\n"
        "    return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
        docstring="treesitter doc",
    )

    assert record is not None
    assert record.docstring == "treesitter doc"
