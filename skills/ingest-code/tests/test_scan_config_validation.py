"""Regression tests for ingest-code scan configuration validation."""

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


def _write_config(repo: Path, payload) -> None:
    (repo / ".monitor-codebase.json").write_text(json.dumps(payload))


def test_nonempty_missing_include_dirs_returns_empty_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_config(repo, {"include_dirs": ["missing"]})

    assert ingest_code._extract_configured_scan_roots(repo) == []


def test_mixed_existing_and_missing_include_dirs_keeps_existing_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _write_config(repo, {"include_dirs": ["src", "missing"]})

    assert ingest_code._extract_configured_scan_roots(repo) == [repo.resolve() / "src"]


def test_empty_include_dirs_preserves_repository_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_config(repo, {"include_dirs": []})

    assert ingest_code._extract_configured_scan_roots(repo) == [repo.resolve()]


@pytest.mark.parametrize(
    "include_dirs",
    [
        "src",
        42,
        {"src": True},
        ["src", 42],
        ["src", ""],
        ["src", "   "],
    ],
)
def test_invalid_include_dirs_shape_is_rejected(include_dirs, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_config(repo, {"include_dirs": include_dirs})

    with pytest.raises(ingest_code.ScanConfigError):
        ingest_code._extract_configured_scan_roots(repo)


def test_scan_rejects_malformed_config_before_external_work(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".monitor-codebase.json").write_text("{not-json")
    called = {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "collect_files": False,
    }

    def fail_find_memory_skill():
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run for invalid scan config")

    def fail_load_taxonomy_module():
        called["load_taxonomy_module"] = True
        raise AssertionError("taxonomy loading should not run for invalid scan config")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("file discovery should not run for invalid scan config")

    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy_module)
    monkeypatch.setattr(ingest_code, "collect_files", fail_collect_files)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(
            path=repo,
            glob=[],
            cwe_only=False,
            validate=False,
            treesitter=False,
            code_index=True,
            dry_run=False,
            scope="code",
            batch_size=50,
        )

    assert exc_info.value.code == 2
    assert called == {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "collect_files": False,
    }
    error = json.loads(capsys.readouterr().err.strip())
    assert error["error"] == "Invalid ingest scan configuration"
    assert error["codebase"] == str(repo.resolve())
    assert error["config"] == str(repo.resolve() / ".monitor-codebase.json")


def test_rescan_prevalidates_all_configs_before_processing(monkeypatch, tmp_path: Path) -> None:
    valid_repo = tmp_path / "valid"
    invalid_repo = tmp_path / "invalid"
    valid_repo.mkdir()
    invalid_repo.mkdir()
    _write_config(valid_repo, {"include_dirs": []})
    (invalid_repo / ".monitor-codebase.json").write_text("{not-json")
    called = {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "collect_files": False,
    }

    def fail_find_memory_skill():
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run before all configs validate")

    def fail_load_taxonomy_module():
        called["load_taxonomy_module"] = True
        raise AssertionError("taxonomy loading should not run before all configs validate")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("no repository should be processed after a later invalid config")

    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy_module)
    monkeypatch.setattr(ingest_code, "collect_files", fail_collect_files)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(
            since=None,
            validate=False,
            treesitter=False,
            code_index=True,
            verify_embeddings=False,
            scope="code",
            codebase=[str(valid_repo), str(invalid_repo)],
        )

    assert exc_info.value.code == 2
    assert called == {
        "find_memory_skill": False,
        "load_taxonomy_module": False,
        "collect_files": False,
    }


def test_nonblank_environment_override_supersedes_include_dirs_schema(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _write_config(repo, {"include_dirs": "not-an-array"})
    monkeypatch.setenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, "src")

    assert ingest_code._extract_configured_scan_roots(repo) == [repo.resolve() / "src"]


def test_non_object_monitor_config_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_config(repo, ["src"])

    with pytest.raises(ingest_code.ScanConfigError):
        ingest_code._preflight_scan_config(repo)
