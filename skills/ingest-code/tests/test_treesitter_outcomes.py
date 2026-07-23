"""Regression tests for Tree-sitter scan failure atomicity."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _symbol(name: str) -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": 1,
        "end_line": 2,
        "signature": f"def {name}(): ...",
    }


def _common_scan_mocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)


def test_treesitter_parser_distinguishes_empty_success_from_invalid_output() -> None:
    assert ingest_code._parse_treesitter_scan_output("[]") == []
    assert ingest_code._parse_treesitter_scan_output("") is None
    assert ingest_code._parse_treesitter_scan_output("not-json") is None
    assert ingest_code._parse_treesitter_scan_output('{"items": []}') is None


def test_treesitter_valid_empty_output_completes_with_zero_symbols(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    class FailIfOpened:
        def upsert_code_symbols(self, records):
            raise AssertionError("valid empty Tree-sitter output should not open memory")

    def fake_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return Result()

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FailIfOpened())

    stored = ingest_code._store_treesitter_symbols_for_directory(
        repo,
        repo,
        "test",
        allowed_files=frozenset(),
    )

    assert stored == 0


@pytest.mark.parametrize("failure_mode", ["timeout", "nonzero", "malformed", "unavailable"])
def test_treesitter_operational_failures_raise(
    failure_mode: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    if failure_mode == "unavailable":
        monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: None)
    else:
        monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)

    def fake_run(cmd, **kwargs):
        if failure_mode == "timeout":
            raise subprocess.TimeoutExpired(cmd, 300)

        class Result:
            stderr = ""

        result = Result()
        if failure_mode == "nonzero":
            result.returncode = 2
            result.stdout = ""
            result.stderr = "scan failed"
        else:
            result.returncode = 0
            result.stdout = "not-json"
        return result

    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._store_treesitter_symbols_for_directory(
            repo,
            repo,
            "test",
            allowed_files=frozenset(),
        )


def test_treesitter_terminal_memory_error_raises(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    verification_samples: list[dict[str, str]] = []

    class FailingClient:
        def upsert_code_symbols(self, records):
            return SimpleNamespace(
                stored=1,
                attempted=2,
                errors=["terminal singleton failure"],
                stored_records=tuple(records[:1]),
            )

    def fake_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = json.dumps([
                {
                    "path": str(source.resolve()),
                    "language": "python",
                    "symbols": [_symbol("app")],
                }
            ])
            stderr = ""

        return Result()

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FailingClient())

    with pytest.raises(ingest_code.TreeSitterScanError) as exc_info:
        ingest_code._store_treesitter_symbols_for_directory(
            repo,
            repo,
            "test",
            verification_samples=verification_samples,
            allowed_files=frozenset({source.resolve()}),
        )

    detail = str(exc_info.value)
    assert "stored=1 attempted=2" in detail
    assert "terminal singleton failure" in detail
    assert verification_samples == []


def test_scan_treesitter_failure_writes_no_success_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    discoverability_lesson_calls = []
    _common_scan_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [src])
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: discoverability_lesson_calls.append(args))
    monkeypatch.setattr(
        ingest_code,
        "_store_treesitter_symbols_for_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(ingest_code.TreeSitterScanError("boom")),
    )

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(
            path=repo,
            glob=[],
            cwe_only=False,
            validate=False,
            treesitter=True,
            code_index=True,
            dry_run=False,
            scope="code",
            batch_size=50,
        )

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert discoverability_lesson_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_treesitter_failure_writes_no_pending_markers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    src_a = repo_a / "src"
    src_b = repo_b / "src"
    src_a.mkdir(parents=True)
    src_b.mkdir(parents=True)
    file_a = src_a / "a.py"
    file_b = src_b / "b.py"
    file_a.write_text("def a():\n    return 1\n")
    file_b.write_text("def b():\n    return 2\n")
    marker_calls = []
    _common_scan_mocks(monkeypatch, tmp_path)

    def fake_collect_files(path: Path, patterns, mtime_after=None):
        return [file_a] if path == repo_a.resolve() else [file_b]

    def fake_scan_roots(path: Path):
        return [src_a] if path == repo_a.resolve() else [src_b]

    def fake_store(scan_root: Path, *args, **kwargs):
        if scan_root == src_b:
            raise ingest_code.TreeSitterScanError("second failed")
        return 0

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect_files)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", fake_scan_roots)
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fake_store)
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(
            since=None,
            validate=False,
            treesitter=True,
            code_index=True,
            verify_embeddings=False,
            scope="code",
            codebase=[str(repo_a), str(repo_b)],
        )

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo_a / ".ingest-code.json").exists()
    assert not (repo_b / ".ingest-code.json").exists()


def test_zero_symbol_root_is_recorded_as_completed(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    _common_scan_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [src])
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: 0)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=True,
        code_index=True,
        dry_run=False,
        scope="code",
        batch_size=50,
    )

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["scan_roots"] == [str(src)]
    assert status["completed_scan_roots"] == [str(src)]
    assert status["code_index"]["enabled"] is False
