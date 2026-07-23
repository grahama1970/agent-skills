"""Regression tests for Python declaration-header binding isolation."""

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


def test_root_function_default_and_decorator_walrus_are_not_locals(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator(header_decorator := factory('decorator literal'))\n"
        "def root(value=(header_default := default_factory('default literal'))):\n"
        "    body_local = body_factory('body literal')\n"
        "    return body_local\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "root", 1)

    assert "body_local" in details["local_variables"]
    assert "header_decorator" not in details["local_variables"]
    assert "header_default" not in details["local_variables"]


def test_root_async_function_header_walrus_is_not_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "async def root(value=(async_header := default_factory('async literal'))):\n"
        "    body_local = body_factory('body literal')\n"
        "    return body_local\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "root", 1)

    assert "body_local" in details["local_variables"]
    assert "async_header" not in details["local_variables"]


def test_root_class_base_metaclass_and_decorator_walrus_are_not_locals(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@class_decorator(header_decorator := factory('decorator literal'))\n"
        "class Root((header_base := Base), metaclass=(header_meta := type)):\n"
        "    body_local = body_factory('body literal')\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "class", "Root", 1)

    assert "body_local" in details["local_variables"]
    assert "header_decorator" not in details["local_variables"]
    assert "header_base" not in details["local_variables"]
    assert "header_meta" not in details["local_variables"]


def test_nested_function_header_walrus_binds_in_enclosing_scope_only(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def inner(value=(inner_default := default_factory('default literal'))):\n"
        "        return value\n"
        "    return inner_default\n",
    )

    outer_details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)
    inner_details = ingest_code._extract_python_symbol_details(source, "function", "inner", 2)

    assert "inner" in outer_details["local_variables"]
    assert "inner_default" in outer_details["local_variables"]
    assert "inner_default" not in inner_details["local_variables"]


def test_nested_class_header_walrus_binds_in_enclosing_scope_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    class Nested((nested_base := Base), metaclass=(nested_meta := type)):\n"
        "        body_local = body_factory('body literal')\n"
        "    return nested_base, nested_meta\n",
    )

    outer_details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)
    nested_details = ingest_code._extract_python_symbol_details(source, "class", "Nested", 2)

    assert "Nested" in outer_details["local_variables"]
    assert "nested_base" in outer_details["local_variables"]
    assert "nested_meta" in outer_details["local_variables"]
    assert "nested_base" not in nested_details["local_variables"]
    assert "nested_meta" not in nested_details["local_variables"]
    assert "body_local" in nested_details["local_variables"]


def test_header_calls_literals_and_body_bindings_remain_lexical_terms(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator(header_decorator := factory('decorator literal'))\n"
        "def root(value=(header_default := default_factory('default literal'))):\n"
        "    body_local = body_factory('body literal')\n"
        "    return body_local\n",
    )

    record = ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": "root",
            "start_line": 1,
            "end_line": 4,
            "signature": "def root(...): ...",
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
    assert "var:body_local" in record.lexical_terms
    assert "var:header_decorator" not in record.lexical_terms
    assert "var:header_default" not in record.lexical_terms
    for term in [
        "call:decorator",
        "call:factory",
        "call:default_factory",
        "call:body_factory",
        "literal:decorator literal",
        "literal:default literal",
        "literal:body literal",
    ]:
        assert term in record.lexical_terms
