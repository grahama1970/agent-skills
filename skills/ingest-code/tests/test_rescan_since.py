"""Regression tests for rescan --since filtering."""

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
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _set_mtime(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_parse_since_relative_values_from_fixed_now() -> None:
    fixed = datetime(2026, 7, 23, 12, 0, 0)

    assert ingest_code._parse_since_threshold("1d", now=fixed) == datetime(2026, 7, 22, 12, 0, 0)
    assert ingest_code._parse_since_threshold("12h", now=fixed) == datetime(2026, 7, 23, 0, 0, 0)


@pytest.mark.parametrize(
    "raw",
    [
        "2026-07-23",
        "2026-07-23T12:00:00",
        "2026-07-23T12:00:00+00:00",
        "2026-07-23T12:00:00Z",
    ],
)
def test_parse_since_accepts_iso_forms(raw: str) -> None:
    assert ingest_code._parse_since_threshold(raw) is not None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "d",
        "h",
        "0d",
        "0h",
        "-1d",
        "1.5d",
        "1w",
        "yesterday",
        "999999999999999999999d",
    ],
)
def test_parse_since_rejects_invalid_relative_values(raw: str) -> None:
    with pytest.raises(ingest_code.RescanSinceError):
        ingest_code._parse_since_threshold(raw)


def test_invalid_since_exits_before_external_work(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    called = {
        "resolve": False,
        "preflight": False,
        "find_memory_skill": False,
        "collect_files": False,
        "learn": False,
        "marker": False,
    }

    def fail_resolve(*args, **kwargs):
        called["resolve"] = True
        raise AssertionError("codebase resolution should not run for invalid --since")

    def fail_preflight(*args, **kwargs):
        called["preflight"] = True
        raise AssertionError("config preflight should not run for invalid --since")

    def fail_find_memory_skill(*args, **kwargs):
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run for invalid --since")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("file discovery should not run for invalid --since")

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory writes should not run for invalid --since")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker writes should not run for invalid --since")

    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", fail_resolve)
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", fail_preflight)
    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "collect_files", fail_collect_files)
    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(
            since="-1d",
            validate=False,
            treesitter=False,
            code_index=True,
            verify_embeddings=False,
            scope="code",
            codebase=[str(repo)],
        )

    assert exc_info.value.code == 2
    assert called == {
        "resolve": False,
        "preflight": False,
        "find_memory_skill": False,
        "collect_files": False,
        "learn": False,
        "marker": False,
    }


def test_invalid_since_cannot_write_zero_result_marker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(
            since="-1d",
            validate=False,
            treesitter=False,
            code_index=True,
            verify_embeddings=False,
            scope="code",
            codebase=[str(repo)],
        )

    assert exc_info.value.code == 2
    assert not (repo / ".ingest-code.json").exists()


def test_skill_docs_describe_since_formats_and_exit_status() -> None:
    text = SKILL_PATH.read_text()

    assert "12h" in text
    assert "7d" in text
    assert "ISO-8601" in text
    assert "status 2" in text


def test_collect_files_applies_since_to_explicit_markdown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "local" / "docs").mkdir(parents=True)
    (repo / "docs").mkdir()
    repo.mkdir(exist_ok=True)
    threshold = datetime.now() - timedelta(days=1)
    old_ts = threshold.timestamp() - 100
    recent_ts = threshold.timestamp() + 100

    old_readme = repo / "README.md"
    old_local_doc = repo / "local" / "docs" / "old.md"
    recent_doc = repo / "docs" / "new.md"
    recent_source = repo / "recent.py"
    for path in [old_readme, old_local_doc, recent_doc, recent_source]:
        path.write_text("content\n")
    _set_mtime(old_readme, old_ts)
    _set_mtime(old_local_doc, old_ts)
    _set_mtime(recent_doc, recent_ts)
    _set_mtime(recent_source, recent_ts)

    files = ingest_code.collect_files(repo, ["*.py"], mtime_after=threshold)
    rel = {path.relative_to(repo).as_posix() for path in files}

    assert rel == {"docs/new.md", "recent.py"}


def test_treesitter_store_filters_results_by_since_threshold(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    old_file = src / "old.py"
    new_file = src / "new.py"
    old_file.write_text("def old():\n    return 1\n")
    new_file.write_text("def new():\n    return 2\n")
    threshold = datetime.now() - timedelta(days=1)
    _set_mtime(old_file, threshold.timestamp() - 100)
    _set_mtime(new_file, threshold.timestamp() + 100)
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    captured_records = []
    context_paths = []

    class FakeClient:
        def upsert_code_symbols(self, records):
            captured_records.extend(records)
            return SimpleNamespace(stored=len(records), attempted=len(records), errors=[])

    def symbol(name: str) -> dict:
        return {
            "kind": "function",
            "name": name,
            "start_line": 1,
            "end_line": 2,
            "signature": f"def {name}(): ...",
        }

    def fake_run(cmd, **kwargs):
        class Result:
            stderr = ""

        result = Result()
        if cmd[0] == "git":
            result.returncode = 1
            result.stdout = ""
            return result

        result.returncode = 0
        result.stdout = json.dumps([
            {"path": str(old_file.resolve()), "language": "python", "symbols": [symbol("old")]},
            {"path": str(new_file.resolve()), "language": "python", "symbols": [symbol("new")]},
        ])
        return result

    def fake_extract_symbol_context(filepath: Path):
        context_paths.append(filepath)
        return {"imports": [], "import_summary": "", "class_hierarchies": {}}

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())
    monkeypatch.setattr(ingest_code, "_extract_symbol_context", fake_extract_symbol_context)

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "test",
        allowed_files=frozenset({old_file.resolve(), new_file.resolve()}),
        mtime_after=threshold,
    )

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/new.py"]
    assert context_paths == [new_file.resolve()]


def test_rescan_passes_since_threshold_to_treesitter(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    collect_thresholds = []
    treesitter_thresholds = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])

    def fake_collect_files(path: Path, patterns, mtime_after=None):
        collect_thresholds.append(mtime_after)
        return []

    def fake_store(
        scan_root: Path,
        codebase_root: Path,
        scope: str,
        verification_samples=None,
        *,
        allowed_files,
        mtime_after=None,
    ):
        treesitter_thresholds.append(mtime_after)
        return 0

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect_files)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [src])
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fake_store)

    ingest_code.rescan(
        since="1d",
        validate=False,
        treesitter=True,
        code_index=True,
        verify_embeddings=False,
        scope="code",
        codebase=[str(repo)],
    )

    assert len(collect_thresholds) == 1
    assert len(treesitter_thresholds) == 1
    assert collect_thresholds[0] is not None
    assert treesitter_thresholds[0] is collect_thresholds[0]


def test_mtime_filter_accepts_timezone_aware_threshold(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("def source():\n    return 1\n")
    threshold = datetime.fromisoformat("2026-07-23T12:00:00+00:00")

    _set_mtime(source, threshold.timestamp() + 1)
    assert ingest_code._path_modified_at_or_after(source, threshold) is True

    _set_mtime(source, threshold.timestamp() - 1)
    assert ingest_code._path_modified_at_or_after(source, threshold) is False
