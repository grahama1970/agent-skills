"""Regression tests for canonical Python declaration start enrichment."""

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


def _record(source: Path, repo: Path, name: str, start_line: int, end_line: int):
    return ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": f"def {name}(...): ...",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_decorated_function_definition_start_canonicalizes_to_decorator(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "def run(value):\n"
        "    return value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 2)

    assert details["start_line"] == 1


def test_multiple_decorators_canonicalize_to_first_decorator(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@first\n"
        "@second\n"
        "def run(value):\n"
        "    return value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 3)

    assert details["start_line"] == 1


def test_decorated_async_function_and_class_are_canonicalized(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@async_decorator\n"
        "async def fetch(value):\n"
        "    return value\n"
        "\n"
        "@class_decorator\n"
        "class Service:\n"
        "    pass\n",
    )

    async_details = ingest_code._extract_python_symbol_details(source, "function", "fetch", 2)
    class_details = ingest_code._extract_python_symbol_details(source, "class", "Service", 6)

    assert async_details["start_line"] == 1
    assert class_details["start_line"] == 5


def test_decorator_and_definition_inputs_produce_identical_record_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "def run(value):\n"
        "    return value\n",
    )

    decorator_record = _record(source, repo, "run", 1, 3)
    definition_record = _record(source, repo, "run", 2, 3)

    assert decorator_record is not None
    assert definition_record is not None
    assert decorator_record.start_line == definition_record.start_line == 1
    assert decorator_record.code == definition_record.code
    assert decorator_record.content_hash == definition_record.content_hash
    assert decorator_record.key == definition_record.key


def test_undecorated_declaration_start_is_unchanged(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value):\n"
        "    return value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 1)

    assert details["start_line"] == 1


def test_unmatched_ast_start_preserves_treesitter_range(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value):\n"
        "    return value\n"
        "def run(other):\n"
        "    return other\n",
    )

    record = _record(source, repo, "run", 2, 2)

    assert record is not None
    assert record.start_line == 2
    assert record.end_line == 2
    assert record.code == "    return value"
