"""Regression tests for .monitor-codebase.json exclude_dirs validation."""

from __future__ import annotations

import importlib.util
import json
import sys
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


def _write_config(repo: Path, payload) -> None:
    (repo / ".monitor-codebase.json").write_text(json.dumps(payload))


def _scan_args(repo: Path, **overrides) -> dict:
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


def test_exclude_entries_accept_missing_empty_and_safe_values() -> None:
    assert ingest_code._configured_exclude_entries({}) == ()
    assert ingest_code._configured_exclude_entries({"exclude_dirs": []}) == ()
    assert ingest_code._configured_exclude_entries({
        "exclude_dirs": [
            "generated",
            r"src\generated",
            "./src/generated/",
            "generated",
        ]
    }) == (
        "generated",
        "src/generated",
    )


def test_exclude_entries_do_not_require_existing_directories() -> None:
    assert ingest_code._configured_exclude_entries({"exclude_dirs": ["future-generated"]}) == (
        "future-generated",
    )


@pytest.mark.parametrize("exclude_dirs", ["generated", 42, {"generated": True}, None])
def test_exclude_dirs_rejects_invalid_container_shapes(exclude_dirs) -> None:
    with pytest.raises(ingest_code.ScanConfigError):
        ingest_code._configured_exclude_entries({"exclude_dirs": exclude_dirs})


@pytest.mark.parametrize(
    "entry",
    [
        "",
        "   ",
        ".",
        "../outside",
        "src/../../outside",
        "/tmp/generated",
        "C:\\tmp\\generated",
        "src/**/generated",
        "generated?",
        "\x00generated",
        42,
        None,
    ],
)
def test_exclude_dirs_rejects_invalid_entries(entry) -> None:
    with pytest.raises(ingest_code.ScanConfigError):
        ingest_code._configured_exclude_entries({"exclude_dirs": [entry]})


def test_scan_rejects_invalid_excludes_before_external_work(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_config(repo, {"exclude_dirs": ["../outside"]})
    called = {
        "find_memory_skill": False,
        "load_taxonomy": False,
        "collect_files": False,
        "treesitter_roots": False,
        "treesitter_store": False,
        "learn": False,
        "marker": False,
    }

    def fail_find_memory_skill():
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run for invalid exclude_dirs")

    def fail_load_taxonomy(*args, **kwargs):
        called["load_taxonomy"] = True
        raise AssertionError("taxonomy loading should not run for invalid exclude_dirs")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("file discovery should not run for invalid exclude_dirs")

    def fail_treesitter_roots(*args, **kwargs):
        called["treesitter_roots"] = True
        raise AssertionError("Tree-sitter roots should not resolve for invalid exclude_dirs")

    def fail_treesitter_store(*args, **kwargs):
        called["treesitter_store"] = True
        raise AssertionError("Tree-sitter storage should not run for invalid exclude_dirs")

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory writes should not run for invalid exclude_dirs")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker writes should not run for invalid exclude_dirs")

    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", fail_collect_files)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", fail_treesitter_roots)
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", fail_treesitter_store)
    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 2
    assert called == {
        "find_memory_skill": False,
        "load_taxonomy": False,
        "collect_files": False,
        "treesitter_roots": False,
        "treesitter_store": False,
        "learn": False,
        "marker": False,
    }


def test_environment_include_override_does_not_bypass_exclude_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _write_config(repo, {"include_dirs": "not-an-array", "exclude_dirs": ["/tmp/generated"]})
    monkeypatch.setenv(ingest_code.SCAN_INCLUDE_DIRS_ENV, "src")

    with pytest.raises(ingest_code.ScanConfigError):
        ingest_code._preflight_scan_config(repo)


def test_rescan_prevalidates_all_exclude_configs_before_processing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    valid_repo = tmp_path / "valid"
    invalid_repo = tmp_path / "invalid"
    valid_repo.mkdir()
    invalid_repo.mkdir()
    _write_config(valid_repo, {"exclude_dirs": ["generated"]})
    _write_config(invalid_repo, {"exclude_dirs": ["../outside"]})
    called = {
        "find_memory_skill": False,
        "load_taxonomy": False,
        "collect_files": False,
        "marker": False,
    }

    def fail_find_memory_skill():
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run before all exclude configs validate")

    def fail_load_taxonomy(*args, **kwargs):
        called["load_taxonomy"] = True
        raise AssertionError("taxonomy loading should not run before all exclude configs validate")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("no repository should be processed after a later invalid exclude config")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker writes should not run after invalid exclude config")

    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy)
    monkeypatch.setattr(ingest_code, "collect_files", fail_collect_files)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([valid_repo, invalid_repo]))

    assert exc_info.value.code == 2
    assert called == {
        "find_memory_skill": False,
        "load_taxonomy": False,
        "collect_files": False,
        "marker": False,
    }


def test_valid_excludes_retain_existing_normal_and_treesitter_semantics(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    keep = repo / "src" / "keep.py"
    generated = repo / "src" / "generated" / "skip.py"
    other_generated = repo / "generated" / "skip.py"
    generated.parent.mkdir(parents=True)
    other_generated.parent.mkdir(parents=True)
    keep.write_text("def keep():\n    return 1\n")
    generated.write_text("def skip():\n    return 2\n")
    other_generated.write_text("def skip_root():\n    return 3\n")
    _write_config(repo, {"exclude_dirs": ["generated", "src/generated"]})
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    captured_records = []

    files = ingest_code.collect_files(repo, ["*.py"])
    assert files == [keep]

    class FakeClient:
        def upsert_code_symbols(self, records):
            captured_records.extend(records)
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                stored_records=tuple(records),
            )

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
            returncode = 0
            stderr = ""
            stdout = json.dumps([
                {"path": str(keep.resolve()), "language": "python", "symbols": [symbol("keep")]},
                {"path": str(generated.resolve()), "language": "python", "symbols": [symbol("skip")]},
                {"path": str(other_generated.resolve()), "language": "python", "symbols": [symbol("skip_root")]},
            ])

        return Result()

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    stored = ingest_code._store_treesitter_symbols_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({keep.resolve(), generated.resolve(), other_generated.resolve()}),
    )

    assert stored == 1
    assert [record.path for record in captured_records] == ["src/keep.py"]


def test_skill_docs_describe_exclude_dirs_validation() -> None:
    text = SKILL_PATH.read_text()

    assert "exclude_dirs" in text
    assert "repository-relative" in text
    assert "status 2" in text
