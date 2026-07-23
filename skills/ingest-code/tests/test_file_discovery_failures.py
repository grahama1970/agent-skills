"""Regression tests for fail-closed file discovery."""

from __future__ import annotations

import importlib.util
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


def _scan_args(repo: Path, **overrides):
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


def _rescan_args(codebases: list[Path], **overrides):
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
    return options


def test_git_ls_files_timeout_raises_discovery_error(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=60)

    monkeypatch.setattr(ingest_code.subprocess, "run", timeout)

    with pytest.raises(ingest_code.FileDiscoveryError):
        ingest_code._git_ls_files(repo, ["*.py"])


def test_git_ls_files_nonzero_exit_raises_discovery_error(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        ingest_code.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout="", stderr="fatal: broken index"),
    )

    with pytest.raises(ingest_code.FileDiscoveryError, match="broken index"):
        ingest_code._git_ls_files(repo, ["*.py"])


def test_git_probe_failure_with_git_marker_does_not_fallback_to_non_git_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "ignored.py").write_text("def ignored():\n    return 1\n")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=5)

    monkeypatch.setattr(ingest_code.subprocess, "run", timeout)

    with pytest.raises(ingest_code.FileDiscoveryError):
        ingest_code.collect_files(repo, ["*.py"])


def test_plain_non_git_directory_still_scans_when_git_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")

    def git_unavailable(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(ingest_code.subprocess, "run", git_unavailable)

    assert ingest_code.collect_files(repo, ["*.py"]) == [source]


def test_non_git_glob_iteration_failure_raises_discovery_error(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def fail_glob(self, pattern):
        raise OSError("cannot enumerate")

    monkeypatch.setattr(ingest_code.Path, "glob", fail_glob)

    with pytest.raises(ingest_code.FileDiscoveryError, match="cannot enumerate"):
        ingest_code.collect_files(repo, ["*.py"])


def test_scan_discovery_failure_writes_no_marker_or_memory_records(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    called = {
        "learn": False,
        "marker": False,
    }

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(
        ingest_code,
        "collect_files",
        lambda *args, **kwargs: (_ for _ in ()).throw(ingest_code.FileDiscoveryError("boom")),
    )

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory write should not run after discovery failure")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker write should not run after discovery failure")

    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_learn_http", fail_learn)
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert called == {"learn": False, "marker": False}
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_precollects_all_codebases_before_any_memory_write(monkeypatch, tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    source = repo_a / "app.py"
    source.write_text("def app():\n    return 1\n")
    collect_paths = []
    called = {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "learn": False,
        "treesitter": False,
        "marker": False,
        "verify": False,
    }

    def fake_collect(path: Path, *args, **kwargs):
        collect_paths.append(path.resolve())
        if path.resolve() == repo_b.resolve():
            raise ingest_code.FileDiscoveryError("second repo failed")
        return [source]

    def fail_find_memory_skill():
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run before all discovery succeeds")

    def fail_load_taxonomy_module():
        called["load_taxonomy_module"] = True
        raise AssertionError("taxonomy loading should not run before all discovery succeeds")

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory write should not run after discovery failure")

    def fail_treesitter(*args, **kwargs):
        called["treesitter"] = True
        raise AssertionError("treesitter should not run after discovery failure")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker write should not run after discovery failure")

    def fail_verify(*args, **kwargs):
        called["verify"] = True
        raise AssertionError("embedding verification should not run after discovery failure")

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect)
    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy_module)
    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fail_treesitter)
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", fail_marker)
    monkeypatch.setattr(ingest_code, "verify_embedding_recall", fail_verify)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo_a, repo_b], treesitter=True, verify_embeddings=True))

    assert exc_info.value.code == 1
    assert collect_paths == [repo_a.resolve(), repo_b.resolve()]
    assert called == {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "learn": False,
        "treesitter": False,
        "marker": False,
        "verify": False,
    }
    assert not (repo_a / ".ingest-code.json").exists()


def test_valid_empty_git_listing_remains_successful_empty_discovery(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        ingest_code.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    assert ingest_code._git_ls_files(repo, ["*.py"]) == []
