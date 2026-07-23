"""Regression tests for overlapping scan-root collapse."""

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


def _write_source_tree(repo: Path) -> None:
    (repo / "src" / "service").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "app.py").write_text("def app():\n    return 1\n")
    (repo / "src" / "service" / "worker.py").write_text("def worker():\n    return 1\n")
    (repo / "tests" / "test_app.py").write_text("def test_app():\n    pass\n")


def _scan_args(repo: Path, **overrides):
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


def _rescan_args(codebases: list[Path], **overrides):
    options = {
        "since": None,
        "validate": False,
        "treesitter": True,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(path) for path in codebases],
    }
    options.update(overrides)
    return options


def _install_noop_storage_mocks(monkeypatch, tmp_path: Path, calls: list[Path], stored: int) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    def fake_store_treesitter(scan_root: Path, *args, **kwargs) -> int:
        calls.append(scan_root.resolve())
        return stored

    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fake_store_treesitter)


@pytest.mark.parametrize(
    "entries",
    [
        ["src", "src/service"],
        ["src/service", "src"],
    ],
)
def test_nested_scan_roots_collapse_regardless_of_configuration_order(
    entries: list[str],
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_source_tree(repo)
    monkeypatch.delenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, raising=False)
    (repo / ".monitor-codebase.json").write_text(json.dumps({"include_dirs": entries}))

    assert ingest_code._extract_configured_scan_roots(repo) == [repo.resolve() / "src"]


def test_disjoint_scan_roots_are_preserved_in_configuration_order(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source_tree(repo)
    monkeypatch.delenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, raising=False)
    (repo / ".monitor-codebase.json").write_text(json.dumps({"include_dirs": ["src", "tests"]}))

    assert ingest_code._extract_configured_scan_roots(repo) == [
        repo.resolve() / "src",
        repo.resolve() / "tests",
    ]


def test_exact_and_symlink_alias_roots_are_deduplicated(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source_tree(repo)
    alias = repo / "src-alias"
    try:
        alias.symlink_to(repo / "src", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unsupported: {exc}")
    monkeypatch.delenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, raising=False)
    (repo / ".monitor-codebase.json").write_text(json.dumps({
        "include_dirs": ["src", "src", "src-alias"],
    }))

    assert ingest_code._extract_configured_scan_roots(repo) == [repo.resolve() / "src"]


def test_scan_overlapping_roots_invokes_treesitter_once(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source_tree(repo)
    calls: list[Path] = []
    monkeypatch.setenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, "src,src/service")
    _install_noop_storage_mocks(monkeypatch, tmp_path, calls, stored=3)

    ingest_code.scan(**_scan_args(repo))

    assert calls == [repo.resolve() / "src"]
    status = ingest_code.build_marker_status(repo)
    assert status["code_index"]["symbols_stored"] == 3
    assert status["scan_roots"] == [str(repo.resolve() / "src")]
    assert status["completed_scan_roots"] == [str(repo.resolve() / "src")]


def test_rescan_overlapping_roots_does_not_double_count_symbols(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source_tree(repo)
    calls: list[Path] = []
    monkeypatch.setenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, "src,src/service")
    _install_noop_storage_mocks(monkeypatch, tmp_path, calls, stored=3)

    ingest_code.rescan(**_rescan_args([repo]))

    assert calls == [repo.resolve() / "src"]
    status = ingest_code.build_marker_status(repo)
    assert status["code_index"]["symbols_stored"] == 3
    assert status["scan_roots"] == [str(repo.resolve() / "src")]
    assert status["completed_scan_roots"] == [str(repo.resolve() / "src")]
