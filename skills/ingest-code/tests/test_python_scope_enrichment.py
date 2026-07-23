"""Regression tests for declaration-scoped Python lexical enrichment."""

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


def test_outer_function_excludes_nested_function_body_lexicals(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(value):\n"
        "    outer_local = outer_call('outer literal')\n"
        "    def inner():\n"
        "        inner_local = inner_call('inner literal')\n"
        "        return inner_local\n"
        "    return outer_local\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "outer_local" in details["local_variables"]
    assert "outer_call" in details["called_symbols"]
    assert "outer literal" in details["string_literals"]
    assert "inner_local" not in details["local_variables"]
    assert "inner_call" not in details["called_symbols"]
    assert "inner literal" not in details["string_literals"]


def test_exact_nested_function_keeps_its_own_lexicals(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(value):\n"
        "    def inner():\n"
        "        inner_local = inner_call('inner literal')\n"
        "        return inner_local\n"
        "    return inner()\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "inner", 2)

    assert details["local_variables"] == ["inner_local"]
    assert details["called_symbols"] == ["inner_call"]
    assert details["string_literals"] == ["inner literal"]


def test_class_symbol_excludes_method_and_nested_class_bodies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Outer(Base):\n"
        "    class_value = class_call('class literal')\n"
        "    class Nested:\n"
        "        nested_value = nested_call('nested literal')\n"
        "    def method(self):\n"
        "        method_value = method_call('method literal')\n"
        "        return method_value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "class", "Outer", 1)

    assert "class_value" in details["local_variables"]
    assert "class_call" in details["called_symbols"]
    assert "class literal" in details["string_literals"]
    assert "nested_value" not in details["local_variables"]
    assert "nested_call" not in details["called_symbols"]
    assert "nested literal" not in details["string_literals"]
    assert "method_value" not in details["local_variables"]
    assert "method_call" not in details["called_symbols"]
    assert "method literal" not in details["string_literals"]


def test_nested_declaration_header_expressions_remain_in_enclosing_scope(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    @decorator_factory('decorator literal')\n"
        "    def inner(\n"
        "        arg: annotation_factory('annotation literal') = default_factory('default literal'),\n"
        "    ) -> return_factory('return literal'):\n"
        "        inner_call('inner body literal')\n"
        "    class Nested(base_factory('base literal'), keyword=keyword_factory('keyword literal')):\n"
        "        nested_call('nested body literal')\n"
        "    return done()\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    for call in [
        "decorator_factory",
        "annotation_factory",
        "default_factory",
        "return_factory",
        "base_factory",
        "keyword_factory",
        "done",
    ]:
        assert call in details["called_symbols"]
    assert "inner_call" not in details["called_symbols"]
    assert "nested_call" not in details["called_symbols"]

    for literal in [
        "decorator literal",
        "annotation literal",
        "default literal",
        "return literal",
        "base literal",
        "keyword literal",
    ]:
        assert literal in details["string_literals"]
    assert "inner body literal" not in details["string_literals"]
    assert "nested body literal" not in details["string_literals"]


def test_lambda_body_does_not_pollute_enclosing_function(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    callback = lambda value=default_call('default literal'): body_call('body literal')\n"
        "    return callback\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert details["local_variables"] == ["callback"]
    assert "default_call" in details["called_symbols"]
    assert "body_call" not in details["called_symbols"]
    assert "default literal" in details["string_literals"]
    assert "body literal" not in details["string_literals"]


def test_code_symbol_lexical_terms_omit_nested_body_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    outer_local = outer_call('outer literal')\n"
        "    def inner():\n"
        "        inner_local = inner_call('inner literal')\n"
        "        return inner_local\n"
        "    return outer_local\n",
    )

    record = ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": "outer",
            "start_line": 1,
            "end_line": 6,
            "signature": "def outer(): ...",
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
    assert "var:outer_local" in record.lexical_terms
    assert "call:outer_call" in record.lexical_terms
    assert "literal:outer literal" in record.lexical_terms
    assert "var:inner_local" not in record.lexical_terms
    assert "call:inner_call" not in record.lexical_terms
    assert "literal:inner literal" not in record.lexical_terms
