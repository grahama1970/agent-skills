"""Regression tests for required ingest marker writes."""

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


def _common_command_mocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)


def test_scan_marker_failure_exits_before_discoverability(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    discoverability_calls = []
    _common_command_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingest_code,
        "_write_ingest_marker",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("permission denied")),
    )
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: discoverability_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert discoverability_calls == []
    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert error["error"] == "Could not write ingest marker"
    assert error["codebase"] == str(repo.resolve())
    assert error["marker"] == str(repo.resolve() / ".ingest-code.json")


def test_rescan_marker_failure_exits_nonzero(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _common_command_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingest_code,
        "_write_ingest_marker",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo]))

    assert exc_info.value.code == 1
    assert not (repo / ".ingest-code.json").exists()
    assert '"codebases_scanned"' not in capsys.readouterr().out


def test_rescan_stops_marker_loop_after_first_failure(monkeypatch, tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    marker_write_paths = []
    _common_command_mocks(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])

    def fake_write_marker(path: Path, **kwargs):
        marker_write_paths.append(path.resolve())
        if path.resolve() == repo_a.resolve():
            raise OSError("first marker failed")
        return path / ".ingest-code.json"

    monkeypatch.setattr(ingest_code, "_write_ingest_marker", fake_write_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo_a, repo_b]))

    assert exc_info.value.code == 1
    assert marker_write_paths == [repo_a.resolve()]


def test_marker_temp_file_is_removed_when_replace_fails(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker_path = repo / ".ingest-code.json"
    temp_path = marker_path.with_suffix(marker_path.suffix + ".tmp")
    original_replace = Path.replace

    def fail_replace(self: Path, target: Path):
        if self == temp_path:
            raise OSError("replace failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError):
        ingest_code._write_ingest_marker(
            repo,
            files_scanned=0,
            knowledge_stored=0,
            cwe_stored=0,
            edges_stored=0,
            code_symbols_stored=0,
            treesitter=False,
            scope="code",
        )

    assert not marker_path.exists()
    assert not temp_path.exists()


def test_successful_required_marker_write_preserves_existing_schema(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    ingest_code._write_required_ingest_marker(
        repo,
        files_scanned=0,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=0,
        treesitter=False,
        scope="code",
    )

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["run_status"] == "complete"
    assert status["completed"] is True


def test_dry_run_does_not_call_required_marker_writer(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker_calls = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert marker_calls == []
