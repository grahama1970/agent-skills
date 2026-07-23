"""Regression tests for Python bound-name lexical enrichment."""

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


def test_nested_function_async_function_and_class_names_are_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    async def async_inner():\n"
        "        return 2\n"
        "    class LocalClass:\n"
        "        pass\n"
        "    return inner, async_inner, LocalClass\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "inner" in details["local_variables"]
    assert "async_inner" in details["local_variables"]
    assert "LocalClass" in details["local_variables"]


def test_nested_declaration_names_do_not_reenable_body_leakage(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    def inner():\n"
        "        nested_only = nested_call('nested literal')\n"
        "        return nested_only\n"
        "    return inner\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "inner" in details["local_variables"]
    assert "nested_only" not in details["local_variables"]
    assert "nested_call" not in details["called_symbols"]
    assert "nested literal" not in details["string_literals"]


def test_import_bindings_follow_alias_and_dotted_import_rules(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def imports():\n"
        "    import os.path\n"
        "    import collections as cx\n"
        "    from pathlib import Path\n"
        "    from json import dumps as json_dumps\n"
        "    return os, cx, Path, json_dumps\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "imports", 1)

    assert "os" in details["local_variables"]
    assert "cx" in details["local_variables"]
    assert "Path" in details["local_variables"]
    assert "json_dumps" in details["local_variables"]
    assert "os.path" not in details["local_variables"]
    assert "collections" not in details["local_variables"]
    assert "dumps" not in details["local_variables"]


def test_except_handler_and_match_capture_names_are_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def capture(value):\n"
        "    try:\n"
        "        risky()\n"
        "    except Error as exc:\n"
        "        handled = exc\n"
        "    match value:\n"
        "        case {'key': mapped, **rest}:\n"
        "            pass\n"
        "        case [first, *tail]:\n"
        "            pass\n"
        "        case alias:\n"
        "            pass\n"
        "    return handled\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "capture", 1)

    for name in ["exc", "handled", "mapped", "rest", "first", "tail", "alias"]:
        assert name in details["local_variables"]


def test_global_and_nonlocal_assignments_are_excluded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def wrapper():\n"
        "    enclosed = 0\n"
        "    def inner():\n"
        "        nonlocal enclosed\n"
        "        global shared_global\n"
        "        enclosed = 1\n"
        "        shared_global = 2\n"
        "        kept_local = 3\n"
        "        return kept_local\n"
        "    return inner\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "inner", 3)

    assert "kept_local" in details["local_variables"]
    assert "enclosed" not in details["local_variables"]
    assert "shared_global" not in details["local_variables"]


def test_bound_names_emit_var_lexical_terms(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    import pathlib as pl\n"
        "    def inner():\n"
        "        return pl.Path()\n"
        "    return inner\n",
    )

    record = ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": "outer",
            "start_line": 1,
            "end_line": 5,
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
    assert "pl" in record.local_variables
    assert "inner" in record.local_variables
    assert "var:pl" in record.lexical_terms
    assert "var:inner" in record.lexical_terms
