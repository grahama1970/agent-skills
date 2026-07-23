"""Regression tests for Tree-sitter result schema validation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _symbol(**overrides) -> dict:
    symbol = {
        "kind": "function",
        "name": "app",
        "start_line": 1,
        "end_line": 2,
        "signature": "def app(): ...",
    }
    symbol.update(overrides)
    return symbol


def _entry(path: str = "app.py", symbols: list | None = None, **overrides) -> dict:
    entry = {
        "path": path,
        "language": "python",
        "symbols": [] if symbols is None else symbols,
    }
    entry.update(overrides)
    return entry


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": False,
        "validate": False,
        "treesitter": True,
        "code_index": True,
        "dry_run": False,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _install_treesitter_output(monkeypatch, tmp_path: Path, payload) -> None:
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    def fake_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stderr = ""
            stdout = json.dumps(payload)

        return Result()

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)


def _common_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path], scan_root: Path) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [scan_root])


def test_treesitter_schema_accepts_valid_empty_results() -> None:
    assert ingest_code._validate_treesitter_scan_results([]) == ()
    assert ingest_code._validate_treesitter_scan_results([_entry()]) == (_entry(),)


@pytest.mark.parametrize("file_entry", [None, "entry", 42, []])
def test_treesitter_schema_rejects_non_object_file_entries(file_entry) -> None:
    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([file_entry])

    assert "files[0]" in str(exc_info.value)


@pytest.mark.parametrize("path", [None, "", "   ", 42])
def test_treesitter_schema_rejects_missing_or_blank_file_path(path) -> None:
    entry = _entry()
    if path is None:
        entry.pop("path")
    else:
        entry["path"] = path

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([entry])

    assert "files[0].path" in str(exc_info.value)


@pytest.mark.parametrize("symbols", [None, "symbols", 42, {}])
def test_treesitter_schema_rejects_non_array_symbols(symbols) -> None:
    entry = _entry()
    if symbols is None:
        entry.pop("symbols")
    else:
        entry["symbols"] = symbols

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([entry])

    assert "files[0].symbols" in str(exc_info.value)


@pytest.mark.parametrize("symbol", [None, "symbol", 42, []])
def test_treesitter_schema_rejects_non_object_symbol_entries(symbol) -> None:
    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([_entry(symbols=[symbol])])

    assert "files[0].symbols[0]" in str(exc_info.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", None),
        ("kind", ""),
        ("kind", "   "),
        ("kind", 42),
        ("name", None),
        ("name", ""),
        ("name", "   "),
        ("name", 42),
    ],
)
def test_treesitter_schema_rejects_invalid_symbol_identity(field: str, value) -> None:
    symbol = _symbol()
    if value is None:
        symbol.pop(field)
    else:
        symbol[field] = value

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([_entry(symbols=[symbol])])

    assert f"files[0].symbols[0].{field}" in str(exc_info.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_line", True),
        ("start_line", 0),
        ("start_line", -1),
        ("start_line", 1.5),
        ("start_line", "10"),
        ("end_line", True),
        ("end_line", 0),
        ("end_line", -1),
        ("end_line", 1.5),
        ("end_line", "10"),
        ("end_line", 1),
    ],
)
def test_treesitter_schema_rejects_invalid_line_ranges(field: str, value) -> None:
    symbol = _symbol(start_line=2, end_line=3)
    symbol[field] = value

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([_entry(symbols=[symbol])])

    assert f"files[0].symbols[0].{field}" in str(exc_info.value)


def test_treesitter_schema_defaults_missing_end_line_to_start_line() -> None:
    symbol = _symbol(start_line=7)
    symbol.pop("end_line")

    result = ingest_code._validate_treesitter_scan_results([_entry(symbols=[symbol])])

    assert result[0]["symbols"][0]["end_line"] == 7


@pytest.mark.parametrize("field", ["signature", "docstring", "parent", "parent_symbol"])
def test_treesitter_schema_rejects_non_string_optional_text_fields(field: str) -> None:
    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_scan_results([_entry(symbols=[_symbol(**{field: 42})])])

    assert f"files[0].symbols[0].{field}" in str(exc_info.value)


def test_well_formed_unknown_symbol_kind_is_ignored(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _install_treesitter_output(monkeypatch, tmp_path, [
        _entry(path=str(source.resolve()), symbols=[_symbol(kind="new-kind")])
    ])

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert records == ()


def test_schema_failure_occurs_before_context_reads_or_memory(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(symbols=[_symbol(start_line=0)])])
    context_calls = []
    memory_calls = []

    monkeypatch.setattr(ingest_code, "_extract_symbol_context", lambda *args, **kwargs: context_calls.append(args))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._extract_treesitter_records_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset(),
        )

    assert context_calls == []
    assert memory_calls == []


@pytest.mark.parametrize("dry_run", [False, True])
def test_dry_run_and_live_share_schema_failure_behavior(
    dry_run: bool,
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    memory_calls = []
    _common_scan_mocks(monkeypatch, tmp_path, [source], repo)
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(path=str(source.resolve()), symbols=[_symbol(name="")])])
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=dry_run))

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "[CODE_SYMBOL]" not in captured.out
    assert memory_calls == []
    assert marker_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_skill_docs_describe_treesitter_schema_failure() -> None:
    text = SKILL_PATH.read_text()

    assert "Malformed Tree-sitter" in text
    assert "status 1" in text
    assert "preview or persistence" in text
