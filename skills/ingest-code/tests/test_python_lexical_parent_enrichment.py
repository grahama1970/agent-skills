"""Regression tests for structural Python lexical parent enrichment."""

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


def test_nested_function_uses_enclosing_function_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "inner", 2)

    assert details["parent_symbol"] == "outer"


def test_nested_async_function_uses_enclosing_function_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    async def inner():\n"
        "        return 1\n"
        "    return inner\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "inner", 2)

    assert details["parent_symbol"] == "outer"


def test_function_inside_method_uses_method_not_class_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def method(self):\n"
        "        def helper():\n"
        "            return 1\n"
        "        return helper\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "helper", 3)

    assert details["parent_symbol"] == "method"


def test_function_local_class_uses_enclosing_function_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def factory():\n"
        "    class Product:\n"
        "        pass\n"
        "    return Product\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "class", "Product", 2)

    assert details["parent_symbol"] == "factory"


def test_exact_ast_parent_overrides_conflicting_treesitter_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="inner",
        start_line=2,
        end_line=3,
        parent="WrongParent",
    )

    assert record is not None
    assert record.qualified_name == "outer.inner"


def test_unmatched_ast_record_preserves_treesitter_parent(tmp_path: Path) -> None:
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
        kind="function",
        name="run",
        start_line=2,
        end_line=2,
        parent="TreeSitterParent",
    )

    assert record is not None
    assert record.qualified_name == "TreeSitterParent.run"
