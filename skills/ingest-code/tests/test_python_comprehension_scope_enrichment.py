"""Regression tests for Python comprehension-scope local enrichment."""

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


def test_list_set_dict_and_generator_targets_do_not_leak(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(values, pairs):\n"
        "    list_values = [item for item in values]\n"
        "    set_values = {entry for entry in values}\n"
        "    dict_values = {key: value for key, value in pairs}\n"
        "    gen_values = (node for node in values)\n"
        "    return list_values, set_values, dict_values, gen_values\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    for name in ["list_values", "set_values", "dict_values", "gen_values"]:
        assert name in details["local_variables"]
    for name in ["item", "entry", "key", "value", "node"]:
        assert name not in details["local_variables"]


def test_destructured_starred_and_nested_targets_do_not_leak(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(rows):\n"
        "    result = [left for (left, (middle, *tail)) in rows]\n"
        "    return result\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "result" in details["local_variables"]
    for name in ["left", "middle", "tail"]:
        assert name not in details["local_variables"]


def test_same_name_bound_outside_comprehension_is_preserved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(values):\n"
        "    item = None\n"
        "    result = [item for item in values]\n"
        "    return item, result\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "item" in details["local_variables"]
    assert "result" in details["local_variables"]


def test_comprehension_calls_and_literals_remain_enriched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer():\n"
        "    result = [\n"
        "        transform('elt literal', item)\n"
        "        for item in source_factory('iter literal')\n"
        "        if keep('if literal', item)\n"
        "    ]\n"
        "    return result\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    for call in ["transform", "source_factory", "keep"]:
        assert call in details["called_symbols"]
    for literal in ["elt literal", "iter literal", "if literal"]:
        assert literal in details["string_literals"]
    assert "item" not in details["local_variables"]


def test_comprehension_walrus_target_remains_containing_local(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(values):\n"
        "    result = [seen for item in values if (seen := normalize(item))]\n"
        "    return result, seen\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "outer", 1)

    assert "result" in details["local_variables"]
    assert "seen" in details["local_variables"]
    assert "item" not in details["local_variables"]
    assert "normalize" in details["called_symbols"]


def test_code_symbol_terms_omit_only_comprehension_target_vars(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def outer(source):\n"
        "    result = [transform(item) for item in source]\n"
        "    return result\n",
    )

    record = ingest_code._build_code_symbol_record(
        {
            "kind": "function",
            "name": "outer",
            "start_line": 1,
            "end_line": 3,
            "signature": "def outer(source): ...",
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
    assert "var:result" in record.lexical_terms
    assert "call:transform" in record.lexical_terms
    assert "var:item" not in record.lexical_terms
