"""Regression tests for exact Python AST enrichment of Tree-sitter records."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _symbol(
    name: str,
    *,
    start_line: int,
    end_line: int | None = None,
    signature: str | None = None,
    docstring: str = "",
    parent: str = "",
) -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": start_line,
        "end_line": end_line if end_line is not None else start_line,
        "signature": signature if signature is not None else f"def {name}(): ...",
        "docstring": docstring,
        "parent": parent,
    }


def _tree_entry(path: Path, symbols: list[dict]) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": symbols,
    }


def _install_treesitter_output(monkeypatch, tmp_path: Path, entries: list[dict]) -> None:
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps(entries), stderr="")

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)


def _extract_records(monkeypatch, tmp_path: Path, repo: Path, source: Path, symbols: list[dict]):
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, symbols)])
    return ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )


def test_duplicate_top_level_function_uses_exact_definition(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(first):\n"
        "    return alpha(first)\n"
        "\n"
        "def run(second):\n"
        "    value = beta(second)\n"
        "    return value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 4)

    assert details["end_line"] == 6
    assert details["parameters"] == ["second"]
    assert details["local_variables"] == ["value"]
    assert details["called_symbols"] == ["beta"]


def test_same_named_methods_use_correct_parent_class(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Alpha:\n"
        "    def run(self, alpha_value):\n"
        "        return alpha(alpha_value)\n"
        "\n"
        "class Beta:\n"
        "    def run(self, beta_value):\n"
        "        value = beta(beta_value)\n"
        "        return value\n",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source, [_symbol("run", start_line=6)])

    assert len(records) == 1
    record = records[0]
    assert record.qualified_name == "Beta.run"
    assert record.parameters == ["beta_value"]
    assert record.local_variables == ["value"]
    assert record.called_symbols == ["beta"]


def test_nested_class_method_uses_innermost_parent(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Outer:\n"
        "    class Inner:\n"
        "        def run(self):\n"
        "            return 1\n",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source, [_symbol("run", start_line=3)])

    assert len(records) == 1
    assert records[0].qualified_name == "Inner.run"


def test_decorated_function_matches_decorator_start_line(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "def run(value):\n"
        "    return value\n",
    )

    details = ingest_code._extract_python_symbol_details(source, "function", "run", 1)

    assert details["end_line"] == 3
    assert details["parameters"] == ["value"]


def test_nonmatching_start_line_does_not_use_nearest_definition(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(first):\n"
        "    return first\n"
        "# not a declaration\n"
        "def run(second):\n"
        "    return second\n",
    )

    assert ingest_code._extract_python_symbol_details(source, "function", "run", 3) == {}


def test_unmatched_ast_details_preserve_treesitter_fields(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(first):\n"
        "    return first\n"
        "# not a declaration\n"
        "def run(second):\n"
        "    return second\n",
    )
    symbol = _symbol(
        "run",
        start_line=3,
        end_line=3,
        signature="treesitter signature",
        docstring="treesitter doc",
        parent="TreeSitterParent",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source, [symbol])

    assert len(records) == 1
    record = records[0]
    assert record.end_line == 3
    assert record.signature == "treesitter signature"
    assert record.docstring == "treesitter doc"
    assert record.qualified_name == "TreeSitterParent.run"
    assert record.parameters == []
    assert record.called_symbols == []


def test_exact_match_controls_code_slice_and_content_hash(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(first):\n"
        "    return alpha(first)\n"
        "\n"
        "def run(second):\n"
        "    return beta(second)\n",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source, [_symbol("run", start_line=4)])

    assert len(records) == 1
    record = records[0]
    assert record.code == "def run(second):\n    return beta(second)"
    assert "alpha" not in record.code
    assert record.content_hash == ingest_code._content_hash(record.code)


def test_symbol_identity_is_independent_of_ast_walk_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    before = _write(
        repo,
        "before.py",
        "def run(first):\n"
        "    return first\n"
        "\n"
        "def run(selected):\n"
        "    return selected\n",
    )
    after = _write(
        repo,
        "after.py",
        "def run(selected):\n"
        "    return selected\n"
        "\n"
        "def run(later):\n"
        "    return later\n",
    )

    before_details = ingest_code._extract_python_symbol_details(before, "function", "run", 4)
    after_details = ingest_code._extract_python_symbol_details(after, "function", "run", 1)

    assert before_details["parameters"] == after_details["parameters"] == ["selected"]
    assert before_details["called_symbols"] == after_details["called_symbols"] == []
    assert before_details["local_variables"] == after_details["local_variables"] == []


def test_dry_run_and_live_share_exact_python_enrichment(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Alpha:\n"
        "    def run(self, alpha_value):\n"
        "        return alpha(alpha_value)\n"
        "\n"
        "class Beta:\n"
        "    def run(self, beta_value):\n"
        "        value = beta(beta_value)\n"
        "        return value\n",
    )
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [_symbol("run", start_line=6)])])
    stored_records = []

    class FakeClient:
        def upsert_code_symbols(self, records):
            stored_records.extend(records)
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                stored_records=records,
            )

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    extracted = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )
    stored = ingest_code._store_treesitter_symbols_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert stored == 1
    assert len(extracted) == 1
    assert len(stored_records) == 1
    assert stored_records[0].qualified_name == extracted[0].qualified_name == "Beta.run"
    assert stored_records[0].parameters == extracted[0].parameters == ["beta_value"]
    assert stored_records[0].code == extracted[0].code
    assert stored_records[0].content_hash == extracted[0].content_hash
