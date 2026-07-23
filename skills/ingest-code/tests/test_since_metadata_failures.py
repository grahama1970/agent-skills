"""Regression tests for fail-closed --since metadata checks."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
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
        "since": "1d",
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(path) for path in codebases],
    }
    options.update(overrides)
    return options


def _set_mtime(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def _symbol(name: str = "app") -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": 1,
        "end_line": 2,
        "signature": f"def {name}(): ...",
    }


def _mock_basic_scan_dependencies(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def _raise_metadata_failure(path: Path, threshold: datetime | None = None) -> bool:
    raise ingest_code.FileDiscoveryError(f"could not read modification time for {path}: boom")


def test_mtime_filter_accepts_recent_and_rejects_old_files(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n")
    threshold = datetime.now() - timedelta(days=1)

    _set_mtime(source, threshold.timestamp() + 1)
    assert ingest_code._path_modified_at_or_after(source, threshold) is True

    _set_mtime(source, threshold.timestamp() - 1)
    assert ingest_code._path_modified_at_or_after(source, threshold) is False


def test_mtime_filter_without_threshold_does_not_stat(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n")

    def fail_stat(self, *args, **kwargs):
        raise AssertionError("threshold=None must not read file metadata")

    monkeypatch.setattr(Path, "stat", fail_stat)

    assert ingest_code._path_modified_at_or_after(source, None) is True


def test_mtime_stat_failure_raises_path_qualified_discovery_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n")
    threshold = datetime.now() - timedelta(days=1)

    def fail_stat(self, *args, **kwargs):
        raise OSError("stat boom")

    monkeypatch.setattr(Path, "stat", fail_stat)

    with pytest.raises(ingest_code.FileDiscoveryError) as exc_info:
        ingest_code._path_modified_at_or_after(source, threshold)

    assert str(source) in str(exc_info.value)
    assert "could not read modification time" in str(exc_info.value)


def test_git_discovery_mtime_failure_exits_status_one(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _mock_basic_scan_dependencies(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", lambda path: repo.resolve())
    monkeypatch.setattr(ingest_code, "_is_git_repo", lambda path: True)
    monkeypatch.setattr(ingest_code, "_git_ls_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", _raise_metadata_failure)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"] == "File discovery failed"
    assert "could not read modification time" in payload["detail"]
    assert not (repo / ".ingest-code.json").exists()


def test_non_git_discovery_mtime_failure_exits_status_one(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _mock_basic_scan_dependencies(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", lambda path: repo.resolve())
    monkeypatch.setattr(ingest_code, "_is_git_repo", lambda path: False)
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", _raise_metadata_failure)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"] == "File discovery failed"
    assert "could not read modification time" in payload["detail"]
    assert not (repo / ".ingest-code.json").exists()


def test_explicit_mdx_mtime_failure_is_terminal(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readme = repo / "README.mdx"
    readme.write_text("# readme\n")

    monkeypatch.setattr(ingest_code, "_is_git_repo", lambda path: False)
    monkeypatch.setattr(ingest_code, "_resolve_in_repo_file", lambda *args, **kwargs: readme)
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", _raise_metadata_failure)

    with pytest.raises(ingest_code.FileDiscoveryError, match="could not read modification time"):
        ingest_code.collect_files(repo, ["*.py"], mtime_after=datetime.now() - timedelta(days=1))


def test_rescan_metadata_failure_writes_no_memory_or_markers(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    called = {
        "find_memory": False,
        "learn": False,
        "treesitter": False,
        "verify": False,
        "marker": False,
    }

    monkeypatch.setattr(ingest_code, "_is_git_repo", lambda path: True)
    monkeypatch.setattr(ingest_code, "_git_ls_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", _raise_metadata_failure)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: called.__setitem__("find_memory", True))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: called.__setitem__("learn", True))
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: called.__setitem__("treesitter", True))
    monkeypatch.setattr(ingest_code, "verify_embedding_recall", lambda *args, **kwargs: called.__setitem__("verify", True))
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: called.__setitem__("marker", True))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo], treesitter=True, verify_embeddings=True))

    assert exc_info.value.code == 1
    assert called == {
        "find_memory": False,
        "learn": False,
        "treesitter": False,
        "verify": False,
        "marker": False,
    }
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_second_codebase_metadata_failure_precedes_all_writes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    source_a = repo_a / "a.py"
    source_b = repo_b / "b.py"
    source_a.write_text("def a():\n    return 1\n")
    source_b.write_text("def b():\n    return 2\n")
    called = {
        "find_memory": False,
        "learn": False,
        "treesitter": False,
        "verify": False,
        "marker": False,
    }

    def fake_git_ls_files(path: Path, *args, **kwargs):
        return [source_a] if path == repo_a.resolve() else [source_b]

    def fake_mtime(path: Path, threshold: datetime | None) -> bool:
        if path == source_b:
            raise ingest_code.FileDiscoveryError(
                f"could not read modification time for {path}: boom"
            )
        return True

    monkeypatch.setattr(ingest_code, "_is_git_repo", lambda path: True)
    monkeypatch.setattr(ingest_code, "_git_ls_files", fake_git_ls_files)
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", fake_mtime)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: called.__setitem__("find_memory", True))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: called.__setitem__("learn", True))
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: called.__setitem__("treesitter", True))
    monkeypatch.setattr(ingest_code, "verify_embedding_recall", lambda *args, **kwargs: called.__setitem__("verify", True))
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: called.__setitem__("marker", True))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo_a, repo_b], treesitter=True, verify_embeddings=True))

    assert exc_info.value.code == 1
    assert called == {
        "find_memory": False,
        "learn": False,
        "treesitter": False,
        "verify": False,
        "marker": False,
    }
    assert not (repo_a / ".ingest-code.json").exists()
    assert not (repo_b / ".ingest-code.json").exists()


def test_treesitter_mtime_failure_precedes_context_and_memory(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    called = {
        "context": False,
        "memory": False,
    }

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"path": str(source.resolve()), "language": "python", "symbols": [_symbol()]},
            ]),
            stderr="",
        )

    def fail_context(filepath: Path):
        called["context"] = True
        raise AssertionError("symbol context should not be extracted after mtime failure")

    class FailMemory:
        def __init__(self):
            called["memory"] = True
            raise AssertionError("memory client should not open after mtime failure")

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "_path_modified_at_or_after", _raise_metadata_failure)
    monkeypatch.setattr(ingest_code, "_extract_symbol_context", fail_context)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", FailMemory)

    with pytest.raises(ingest_code.TreeSitterScanError, match="modification-time check failed"):
        ingest_code._store_treesitter_symbols_for_directory(
            src,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
            mtime_after=datetime.now() - timedelta(days=1),
        )

    assert called == {"context": False, "memory": False}


def test_treesitter_old_file_remains_normal_filtered_result(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    threshold = datetime.now() - timedelta(days=1)
    _set_mtime(source, threshold.timestamp() - 10)
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([
                {"path": str(source.resolve()), "language": "python", "symbols": [_symbol()]},
            ]),
            stderr="",
        )

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(
        ingest_code,
        "_extract_symbol_context",
        lambda filepath: (_ for _ in ()).throw(AssertionError("old file should be skipped")),
    )
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("old file should not open memory")),
    )

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
        mtime_after=threshold,
    )

    assert stored == 0


def test_skill_docs_describe_since_metadata_failure_boundary() -> None:
    skill_doc = (MODULE_PATH.parent / "SKILL.md").read_text()

    assert "Modification-time metadata must be readable" in skill_doc
    assert "status 1" in skill_doc
    assert "unchanged file" in skill_doc
    assert "completed markers" in skill_doc
