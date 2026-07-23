"""Regression tests for monitor exclude_dirs semantics."""

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


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _write_exclude_fixture(repo: Path, exclude_entry) -> tuple[Path, Path]:
    keep = repo / "src" / "keep.py"
    skip = repo / "src" / "generated" / "skip.py"
    skip.parent.mkdir(parents=True)
    keep.write_text("def keep():\n    return 1\n")
    skip.write_text("def skip():\n    return 2\n")
    (repo / ".monitor-codebase.json").write_text(json.dumps({"exclude_dirs": [exclude_entry]}))
    return keep, skip


def _run_mocked_treesitter(monkeypatch, tmp_path: Path, repo: Path, keep: Path, skip: Path):
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
            {"path": str(keep.resolve()), "language": "python", "symbols": [symbol("keep")]},
            {"path": str(skip.resolve()), "language": "python", "symbols": [symbol("skip")]},
        ])
        return result

    def fake_extract_symbol_context(filepath: Path):
        context_paths.append(filepath)
        return {"imports": [], "import_summary": "", "class_hierarchies": {}}

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())
    monkeypatch.setattr(ingest_code, "_extract_symbol_context", fake_extract_symbol_context)

    stored = ingest_code._store_treesitter_symbols_for_directory(repo / "src", repo, "test")
    return stored, captured_records, context_paths


@pytest.mark.parametrize("exclude_entry", ["generated", "src/generated"])
def test_treesitter_results_respect_monitor_exclude_dirs(
    exclude_entry: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    keep, skip = _write_exclude_fixture(repo, exclude_entry)

    stored, captured_records, context_paths = _run_mocked_treesitter(monkeypatch, tmp_path, repo, keep, skip)

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/keep.py"]
    assert context_paths == [keep.resolve()]


@pytest.mark.parametrize("git_repo", [False, True])
def test_discovery_and_treesitter_share_exclude_semantics(
    git_repo: bool,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / ("git-repo" if git_repo else "plain-repo")
    repo.mkdir()
    keep, skip = _write_exclude_fixture(repo, "src/generated")
    if git_repo:
        _git(repo, "init")

    files = ingest_code.collect_files(repo, ["*.py"])
    assert files == [keep]

    stored, captured_records, context_paths = _run_mocked_treesitter(monkeypatch, tmp_path, repo, keep, skip)
    assert stored == 1
    assert [record.path for record in captured_records] == ["src/keep.py"]
    assert context_paths == [keep.resolve()]


def test_absolute_parent_directories_do_not_trigger_repository_exclusions(tmp_path: Path) -> None:
    repo = tmp_path / "build" / "repo"
    keep = repo / "src" / "keep.py"
    keep.parent.mkdir(parents=True)
    keep.write_text("def keep():\n    return 1\n")

    files = ingest_code.collect_files(repo, ["*.py"])

    assert files == [keep]


def test_unsafe_configured_exclude_entries_are_ignored(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    keep = repo / "src" / "keep.py"
    keep.parent.mkdir(parents=True)
    keep.write_text("def keep():\n    return 1\n")
    (repo / ".monitor-codebase.json").write_text(json.dumps({
        "exclude_dirs": [
            "",
            "../outside",
            "/absolute/path",
            None,
            42,
        ],
    }))

    files = ingest_code.collect_files(repo, ["*.py"])

    assert files == [keep]
