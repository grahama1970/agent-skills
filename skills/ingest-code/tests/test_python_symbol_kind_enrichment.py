"""Regression tests for exact-AST Python symbol-kind canonicalization."""

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
    parent: str = "",
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": f"{kind} {name}(...): ...",
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


def test_class_method_reported_as_function_canonicalizes_to_method(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(self):\n"
        "        return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
        parent="Service",
    )

    assert record is not None
    assert record.symbol_kind == "method"
    assert "method" in record.tags
    assert "function" not in record.tags
    assert "kind:method" in record.to_document()["lexical_terms"]


def test_async_class_method_canonicalizes_to_method(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    async def run(self):\n"
        "        return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
        parent="Service",
    )

    assert record is not None
    assert record.symbol_kind == "method"


def test_nested_function_inside_method_canonicalizes_to_function(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(self):\n"
        "        def helper():\n"
        "            return 1\n"
        "        return helper\n",
    )

    record = _record(
        source,
        repo,
        kind="method",
        name="helper",
        start_line=3,
        end_line=4,
        parent="run",
    )

    assert record is not None
    assert record.symbol_kind == "function"
    assert "function" in record.tags
    assert "method" not in record.tags
    assert "kind:function" in record.to_document()["lexical_terms"]


def test_top_level_function_reported_as_method_canonicalizes_to_function(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value):\n"
        "    return value\n",
    )

    record = _record(
        source,
        repo,
        kind="method",
        name="run",
        start_line=1,
        end_line=2,
    )

    assert record is not None
    assert record.symbol_kind == "function"


def test_class_reported_as_function_canonicalizes_to_class(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Product:\n"
        "    pass\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="Product",
        start_line=1,
        end_line=2,
    )

    assert record is not None
    assert record.symbol_kind == "class"


def test_unmatched_ast_preserves_treesitter_kind(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value):\n"
        "    return value\n",
    )

    record = _record(
        source,
        repo,
        kind="method",
        name="run",
        start_line=2,
        end_line=2,
        parent="TreeSitterParent",
    )

    assert record is not None
    assert record.symbol_kind == "method"
