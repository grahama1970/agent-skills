"""Regression tests for Tree-sitter source range validation."""

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


def _symbol(name: str = "app", start_line: int = 1, end_line: int | None = 1) -> dict:
    symbol = {
        "kind": "function",
        "name": name,
        "start_line": start_line,
        "signature": f"def {name}(): ...",
    }
    if end_line is not None:
        symbol["end_line"] = end_line
    return symbol


def _entry(path: Path, symbols: list[dict]) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": symbols,
    }


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


def test_source_ranges_accept_first_and_last_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("first\nsecond\nthird\n")

    ingest_code._validate_treesitter_source_ranges(
        [_symbol("first", 1, 1), _symbol("third", 3, 3)],
        filepath=source,
        codebase_root=repo,
        file_index=0,
    )


def test_source_range_rejects_start_line_beyond_eof(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("first\nsecond\n")

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_source_ranges(
            [_symbol(start_line=3, end_line=3)],
            filepath=source,
            codebase_root=repo,
            file_index=0,
        )

    assert "files[0].symbols[0].start_line" in str(exc_info.value)


def test_source_range_rejects_end_line_beyond_eof(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("first\nsecond\n")

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._validate_treesitter_source_ranges(
            [_symbol(start_line=1, end_line=3)],
            filepath=source,
            codebase_root=repo,
            file_index=0,
        )

    assert "files[0].symbols[0].end_line" in str(exc_info.value)


def test_empty_source_file_cannot_claim_a_symbol(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("")

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._validate_treesitter_source_ranges(
            [_symbol(start_line=1, end_line=1)],
            filepath=source,
            codebase_root=repo,
            file_index=0,
        )


def test_source_without_trailing_newline_counts_final_line(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("line one\nline two")

    ingest_code._validate_treesitter_source_ranges(
        [_symbol(start_line=2, end_line=2)],
        filepath=source,
        codebase_root=repo,
        file_index=0,
    )


def test_symbol_free_file_entry_does_not_read_source(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("def app():\n    return 1\n")
    line_count_calls = []
    context_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(source, [])])
    monkeypatch.setattr(ingest_code, "_source_line_count", lambda *args, **kwargs: line_count_calls.append(args))
    monkeypatch.setattr(ingest_code, "_extract_symbol_context", lambda *args, **kwargs: context_calls.append(args))

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert records == ()
    assert line_count_calls == []
    assert context_calls == []


def test_range_validation_runs_after_manifest_filter(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("def app():\n    return 1\n")
    line_count_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(source, [_symbol(start_line=99, end_line=99)])])
    monkeypatch.setattr(ingest_code, "_source_line_count", lambda *args, **kwargs: line_count_calls.append(args))

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset(),
    )

    assert records == ()
    assert line_count_calls == []


def test_range_failure_occurs_before_context_and_memory(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "app.py"
    repo.mkdir()
    source.write_text("def app():\n    return 1\n")
    context_calls = []
    memory_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(source, [_symbol(start_line=99, end_line=99)])])
    monkeypatch.setattr(ingest_code, "_extract_symbol_context", lambda *args, **kwargs: context_calls.append(args))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._extract_treesitter_records_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )

    assert context_calls == []
    assert memory_calls == []


@pytest.mark.parametrize("dry_run", [False, True])
def test_dry_run_and_live_share_range_failure_behavior(
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
    _install_treesitter_output(monkeypatch, tmp_path, [_entry(source, [_symbol(start_line=99, end_line=99)])])
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


def test_skill_docs_describe_source_range_gate() -> None:
    text = SKILL_PATH.read_text()

    assert "Out-of-bounds" in text
    assert "status 1" in text
    assert "preview or persistence" in text
