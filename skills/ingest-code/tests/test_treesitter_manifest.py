"""Regression tests for Tree-sitter result manifest filtering."""

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


def _symbol(name: str) -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": 1,
        "end_line": 2,
        "signature": f"def {name}(): ...",
    }


def _tree_entry(path: Path, name: str) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": [_symbol(name)],
    }


def _install_mock_treesitter(
    monkeypatch,
    tmp_path: Path,
    entries: list[dict],
    captured_records: list,
) -> None:
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    class FakeClient:
        def upsert_code_symbols(self, records):
            captured_records.extend(records)
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                stored_records=tuple(records),
            )

    def fake_run(cmd, **kwargs):
        class Result:
            stderr = ""

        result = Result()
        if cmd[0] == "git":
            result.returncode = 1
            result.stdout = ""
            return result

        result.returncode = 0
        result.stdout = json.dumps(entries)
        return result

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())


def test_treesitter_rejects_result_missing_from_discovered_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    keep = src / "keep.py"
    reject = src / "reject.py"
    keep.write_text("def keep():\n    return 1\n")
    reject.write_text("def reject():\n    return 2\n")
    captured_records = []
    context_paths = []

    _install_mock_treesitter(
        monkeypatch,
        tmp_path,
        [_tree_entry(keep, "keep"), _tree_entry(reject, "reject")],
        captured_records,
    )

    def fake_extract_symbol_context(filepath: Path):
        context_paths.append(filepath)
        return {"imports": [], "import_summary": "", "class_hierarchies": {}}

    monkeypatch.setattr(ingest_code, "_extract_symbol_context", fake_extract_symbol_context)

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "test",
        allowed_files=frozenset({keep.resolve()}),
    )

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/keep.py"]
    assert context_paths == [keep.resolve()]


def test_gitignored_file_cannot_become_treesitter_record(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    generated = src / "generated"
    generated.mkdir(parents=True)
    keep = src / "keep.py"
    ignored = generated / "ignored.py"
    keep.write_text("def keep():\n    return 1\n")
    ignored.write_text("def ignored():\n    return 2\n")
    (repo / ".gitignore").write_text("src/generated/\n")
    _git(repo, "init")
    allowed_files = ingest_code._resolved_file_manifest(
        ingest_code.collect_files(repo, ["*.py"]),
        repo,
    )
    captured_records = []

    _install_mock_treesitter(
        monkeypatch,
        tmp_path,
        [_tree_entry(keep, "keep"), _tree_entry(ignored, "ignored")],
        captured_records,
    )

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "test",
        allowed_files=allowed_files,
    )

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/keep.py"]


def test_custom_scan_glob_limits_treesitter_records(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    py_file = src / "app.py"
    js_file = src / "app.js"
    py_file.write_text("def app():\n    return 1\n")
    js_file.write_text("export function app() { return 1; }\n")
    allowed_files = ingest_code._resolved_file_manifest(
        ingest_code.collect_files(repo, ["src/**/*.py"]),
        repo,
    )
    captured_records = []

    _install_mock_treesitter(
        monkeypatch,
        tmp_path,
        [_tree_entry(py_file, "app"), _tree_entry(js_file, "app")],
        captured_records,
    )

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "test",
        allowed_files=allowed_files,
    )

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/app.py"]


@pytest.mark.parametrize("command_name", ["scan", "rescan"])
def test_scan_and_rescan_pass_discovered_manifest_to_treesitter(
    command_name: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    known_file = src / "known.py"
    known_file.write_text("def known():\n    return 1\n")
    captured_manifests = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [known_file])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [src])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    def fake_store(
        scan_root: Path,
        codebase_root: Path,
        scope: str,
        verification_samples=None,
        *,
        allowed_files,
        mtime_after=None,
    ):
        captured_manifests.append(allowed_files)
        return 0

    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fake_store)

    if command_name == "scan":
        ingest_code.scan(
            path=repo,
            glob=[],
            cwe_only=False,
            validate=False,
            treesitter=True,
            code_index=True,
            dry_run=False,
            scope="code",
            batch_size=50,
        )
    else:
        ingest_code.rescan(
            since=None,
            validate=False,
            treesitter=True,
            code_index=True,
            verify_embeddings=False,
            scope="code",
            codebase=[str(repo)],
        )

    assert captured_manifests == [frozenset({known_file.resolve()})]


def test_empty_manifest_produces_no_code_symbol_records(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    captured_records = []
    context_paths = []

    _install_mock_treesitter(
        monkeypatch,
        tmp_path,
        [_tree_entry(source, "app")],
        captured_records,
    )

    def fake_extract_symbol_context(filepath: Path):
        context_paths.append(filepath)
        return {"imports": [], "import_summary": "", "class_hierarchies": {}}

    monkeypatch.setattr(ingest_code, "_extract_symbol_context", fake_extract_symbol_context)

    stored = ingest_code._store_treesitter_symbols_for_directory(
        src,
        repo,
        "test",
        allowed_files=frozenset(),
    )

    assert stored == 0
    assert captured_records == []
    assert context_paths == []
