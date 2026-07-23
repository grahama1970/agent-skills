"""Regression tests for memory-write completeness gates."""

from __future__ import annotations

import importlib.util
import json
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


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": False,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "dry_run": False,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _rescan_args(repos: list[Path], **overrides) -> dict:
    options = {
        "since": None,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(repo) for repo in repos],
    }
    options.update(overrides)
    return options


def _common_scan_mocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)


def _stderr_json(capsys) -> dict:
    stderr = capsys.readouterr().err.strip().splitlines()
    assert stderr
    return json.loads(stderr[-1])


def test_scan_knowledge_write_failure_exits_before_later_phases(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    edge_calls = []
    treesitter_calls = []
    marker_calls = []
    discoverability_calls = []
    learn_results = iter([True, False])
    _common_scan_mocks(monkeypatch, tmp_path)
    monkeypatch.setenv("INGEST_WORKERS", "1")

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [
            {"problem": "one", "solution": "One", "tags": ["one"]},
            {"problem": "two", "solution": "Two", "tags": ["two"]},
        ],
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: next(learn_results))
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edge_calls.append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: treesitter_calls.append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: discoverability_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert edge_calls == []
    assert treesitter_calls == []
    assert marker_calls == []
    assert discoverability_calls == []
    error = _stderr_json(capsys)
    assert error["phase"] == "knowledge"
    assert error["attempted"] == 2
    assert error["stored"] == 1
    assert error["failed"] == 1


def test_scan_cwe_write_failure_exits_before_edges_and_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    edge_calls = []
    treesitter_calls = []
    marker_calls = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: object())
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingest_code,
        "scan_file_cwe",
        lambda *args, **kwargs: {"cwe_mappings": [{"cwe_id": "CWE-20", "name": "Input"}]},
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: False)
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edge_calls.append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: treesitter_calls.append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert edge_calls == []
    assert treesitter_calls == []
    assert marker_calls == []


def test_scan_edge_write_shortfall_exits_before_treesitter_and_marker(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    treesitter_calls = []
    marker_calls = []
    _common_scan_mocks(monkeypatch, tmp_path)

    edges = [
        {"from_file": "a.py", "to_file": "b.py", "edge_type": "depends_on", "module": "b"},
        {"from_file": "a.py", "to_file": "c.py", "edge_type": "depends_on", "module": "c"},
    ]
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edges)
    monkeypatch.setattr(ingest_code, "store_edges", lambda *args, **kwargs: 1)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: treesitter_calls.append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert treesitter_calls == []
    assert marker_calls == []
    error = _stderr_json(capsys)
    assert error["phase"] == "edges"
    assert error["attempted"] == 2
    assert error["stored"] == 1


def test_rescan_late_codebase_write_failure_writes_no_pending_markers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    file_a = repo_a / "a.py"
    file_b = repo_b / "b.py"
    file_a.write_text("def a():\n    return 1\n")
    file_b.write_text("def b():\n    return 2\n")
    marker_calls = []
    learn_results = iter([True, False])
    _common_scan_mocks(monkeypatch, tmp_path)

    def fake_collect_files(path: Path, patterns, mtime_after=None):
        return [file_a] if path == repo_a.resolve() else [file_b]

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect_files)
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [{"problem": "item", "solution": "Item", "tags": ["item"]}],
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: next(learn_results))
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo_a, repo_b]))

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo_a / ".ingest-code.json").exists()
    assert not (repo_b / ".ingest-code.json").exists()


def test_zero_attempt_phases_do_not_abort(tmp_path: Path) -> None:
    ingest_code._abort_if_memory_writes_incomplete(
        phase="knowledge",
        attempted=0,
        stored=0,
        codebase=tmp_path,
    )


def test_scan_dry_run_does_not_apply_live_write_completeness_gate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    memory_calls = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [{"problem": "item", "solution": "Item", "tags": ["item"]}],
    )
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: memory_calls.append(args))
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert memory_calls == []
    assert marker_calls == []
