"""Regression tests for scan --batch-size validation."""

from __future__ import annotations

import importlib.util
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


def test_validate_scan_batch_size_accepts_positive_values() -> None:
    assert ingest_code._validate_scan_batch_size(1) == 1
    assert ingest_code._validate_scan_batch_size(50) == 50


@pytest.mark.parametrize("batch_size", [0, -1, -100, False])
def test_validate_scan_batch_size_rejects_nonpositive_values(batch_size: int) -> None:
    with pytest.raises(ingest_code.ScanBatchSizeError):
        ingest_code._validate_scan_batch_size(batch_size)


def test_invalid_batch_size_exits_before_external_work(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    called = {
        "resolve": False,
        "preflight": False,
        "load_taxonomy": False,
        "find_memory_skill": False,
        "collect_files": False,
        "learn": False,
        "marker": False,
    }

    def fail_resolve(*args, **kwargs):
        called["resolve"] = True
        raise AssertionError("codebase resolution should not run for invalid --batch-size")

    def fail_preflight(*args, **kwargs):
        called["preflight"] = True
        raise AssertionError("config preflight should not run for invalid --batch-size")

    def fail_load_taxonomy(*args, **kwargs):
        called["load_taxonomy"] = True
        raise AssertionError("taxonomy loading should not run for invalid --batch-size")

    def fail_find_memory_skill(*args, **kwargs):
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run for invalid --batch-size")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("file discovery should not run for invalid --batch-size")

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory writes should not run for invalid --batch-size")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker writes should not run for invalid --batch-size")

    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", fail_resolve)
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", fail_preflight)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy)
    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", fail_collect_files)
    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, batch_size=0))

    assert exc_info.value.code == 2
    assert called == {
        "resolve": False,
        "preflight": False,
        "load_taxonomy": False,
        "find_memory_skill": False,
        "collect_files": False,
        "learn": False,
        "marker": False,
    }


def test_negative_batch_size_cannot_write_completed_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, batch_size=-1))

    assert exc_info.value.code == 2
    assert not (repo / ".ingest-code.json").exists()


def test_positive_batch_size_processes_every_cwe_file(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = []
    for index in range(5):
        path = repo / f"file_{index}.py"
        path.write_text(f"def file_{index}():\n    return {index}\n")
        files.append(path)
    scanned_files = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: object())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: None)

    def fake_scan_file_cwe(filepath: Path, taxonomy, validate: bool) -> dict:
        scanned_files.append(filepath)
        return {"cwe_mappings": []}

    monkeypatch.setattr(ingest_code, "scan_file_cwe", fake_scan_file_cwe)

    ingest_code.scan(**_scan_args(repo, batch_size=2))

    assert scanned_files == files


def test_dry_run_still_rejects_invalid_batch_size(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=True, batch_size=0))

    assert exc_info.value.code == 2


def test_skill_docs_require_positive_batch_size() -> None:
    text = SKILL_PATH.read_text()

    assert "--batch-size" in text
    assert "positive" in text.lower()
    assert "status 2" in text
