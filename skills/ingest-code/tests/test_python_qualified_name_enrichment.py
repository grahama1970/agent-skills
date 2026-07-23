"""Regression tests for full structural Python qualified-name enrichment."""

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


def test_deep_nested_class_method_uses_full_lexical_qualified_name(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Outer:\n"
        "    class Inner:\n"
        "        def run(self):\n"
        "            return 1\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=3,
        end_line=4,
        parent="Inner",
    )

    assert record is not None
    assert record.qualified_name == "Outer.Inner.run"


def test_nested_function_inside_method_uses_full_lexical_qualified_name(
    tmp_path: Path,
) -> None:
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

    record = _record(
        source,
        repo,
        kind="function",
        name="helper",
        start_line=3,
        end_line=4,
        parent="method",
    )

    assert record is not None
    assert record.qualified_name == "Service.method.helper"


def test_same_immediate_parent_names_are_disambiguated_in_records(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Alpha:\n"
        "    def build(self):\n"
        "        def helper():\n"
        "            return 'alpha'\n"
        "        return helper\n"
        "\n"
        "class Beta:\n"
        "    def build(self):\n"
        "        def helper():\n"
        "            return 'beta'\n"
        "        return helper\n",
    )

    alpha = _record(
        source,
        repo,
        kind="function",
        name="helper",
        start_line=3,
        end_line=4,
        parent="build",
    )
    beta = _record(
        source,
        repo,
        kind="function",
        name="helper",
        start_line=9,
        end_line=10,
        parent="build",
    )

    assert alpha is not None
    assert beta is not None
    assert alpha.qualified_name == "Alpha.build.helper"
    assert beta.qualified_name == "Beta.build.helper"
    assert alpha.qualified_name != beta.qualified_name
    assert "qualified:Alpha.build.helper" in alpha.to_document()["lexical_terms"]
    assert "qualified:Beta.build.helper" in beta.to_document()["lexical_terms"]


def test_parent_symbol_remains_immediate_while_qualified_name_is_full(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def method(self):\n"
        "        def helper():\n"
        "            return 1\n",
    )

    details = ingest_code._extract_python_symbol_details(
        source,
        "function",
        "helper",
        3,
    )

    assert details["parent_symbol"] == "method"
    assert details["qualified_name"] == "Service.method.helper"


def test_top_level_exact_match_keeps_bare_qualified_name(tmp_path: Path) -> None:
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
        start_line=1,
        end_line=2,
        parent="TreeSitterParent",
    )

    assert record is not None
    assert record.qualified_name == "run"


def test_unmatched_ast_preserves_treesitter_qualification(tmp_path: Path) -> None:
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
