"""Regression tests for rescan marker emission."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _run_rescan(codebases: list[Path], **overrides) -> None:
    options = {
        "since": None,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(path) for path in codebases],
    }
    options.update(overrides)
    ingest_code.rescan(**options)


def _mock_common(monkeypatch, tmp_path: Path, *, taxonomy=None) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: taxonomy)


def test_rescan_writes_distinct_marker_for_each_codebase(monkeypatch, tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    file_a = repo_a / "a.py"
    file_b = repo_b / "b.py"
    file_a.write_text("def a():\n    return 1\n")
    file_b.write_text("def b():\n    return 2\n")
    _mock_common(monkeypatch, tmp_path)

    def fake_collect_files(path: Path, patterns, mtime_after=None):
        return [file_a] if path == repo_a.resolve() else [file_b]

    def fake_extract_knowledge(filepath: Path):
        if filepath == file_a:
            return [{"problem": "a1", "solution": "A1", "tags": []}]
        return [
            {"problem": "b1", "solution": "B1", "tags": []},
            {"problem": "b2", "solution": "B2", "tags": []},
        ]

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect_files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", fake_extract_knowledge)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)

    _run_rescan([repo_a, repo_b])

    status_a = ingest_code.build_marker_status(repo_a)
    status_b = ingest_code.build_marker_status(repo_b)
    assert status_a["status"] == "fresh"
    assert status_a["files_scanned"] == 1
    assert status_a["knowledge_stored"] == 1
    assert status_b["status"] == "fresh"
    assert status_b["files_scanned"] == 1
    assert status_b["knowledge_stored"] == 2


def test_rescan_marker_records_treesitter_results(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "src"
    lib = repo / "lib"
    src.mkdir()
    lib.mkdir()
    _mock_common(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [src, lib])
    monkeypatch.setattr(
        ingest_code,
        "_store_treesitter_symbols_for_directory",
        lambda scan_root, *args, **kwargs: 2 if scan_root == src else 3,
    )

    _run_rescan([repo], treesitter=True)

    status = ingest_code.build_marker_status(repo)
    expected_roots = [str(src), str(lib)]
    assert status["code_index"]["enabled"] is True
    assert status["code_index"]["symbols_stored"] == 5
    assert status["scan_roots"] == expected_roots
    assert status["completed_scan_roots"] == expected_roots


def test_rescan_does_not_write_markers_when_verification_fails(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    _mock_common(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [
            {"problem": "app", "solution": "App", "tags": ["function", "app"]},
        ],
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "verify_embedding_recall",
        lambda *args, **kwargs: {"requested": 10, "checked": 1, "passed": 0, "failed": 1, "failures": []},
    )
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        _run_rescan([repo], verify_embeddings=True)

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_zero_result_still_writes_complete_marker(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _mock_common(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)

    _run_rescan([repo])

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["run_status"] == "complete"
    assert status["completed"] is True
    assert status["files_scanned"] == 0
    assert status["knowledge_stored"] == 0
    assert status["cwe_stored"] == 0
    assert status["code_index"]["enabled"] is False
