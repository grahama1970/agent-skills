"""Regression tests for explicit scan --glob validation."""

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


def test_validate_explicit_scan_globs_normalizes_and_deduplicates() -> None:
    assert ingest_code._validate_explicit_scan_globs([
        "*.py",
        "./src/**/*.ts",
        r"src\**\*.tsx",
        "*.py",
    ]) == [
        "**/*.py",
        "src/**/*.ts",
        "src/**/*.tsx",
    ]


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "   ",
        ".",
        "../*.py",
        "src/../../*.py",
        "/tmp/*.py",
        "C:\\tmp\\*.py",
        "\x00*.py",
    ],
)
def test_validate_explicit_scan_globs_rejects_invalid_values(pattern: str) -> None:
    with pytest.raises(ingest_code.ScanGlobError):
        ingest_code._validate_explicit_scan_globs([pattern])


def test_invalid_glob_exits_before_external_work(monkeypatch, tmp_path: Path) -> None:
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
        raise AssertionError("codebase resolution should not run for invalid --glob")

    def fail_preflight(*args, **kwargs):
        called["preflight"] = True
        raise AssertionError("config preflight should not run for invalid --glob")

    def fail_load_taxonomy(*args, **kwargs):
        called["load_taxonomy"] = True
        raise AssertionError("taxonomy loading should not run for invalid --glob")

    def fail_find_memory_skill(*args, **kwargs):
        called["find_memory_skill"] = True
        raise AssertionError("memory lookup should not run for invalid --glob")

    def fail_collect_files(*args, **kwargs):
        called["collect_files"] = True
        raise AssertionError("file discovery should not run for invalid --glob")

    def fail_learn(*args, **kwargs):
        called["learn"] = True
        raise AssertionError("memory writes should not run for invalid --glob")

    def fail_marker(*args, **kwargs):
        called["marker"] = True
        raise AssertionError("marker writes should not run for invalid --glob")

    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", fail_resolve)
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", fail_preflight)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", fail_load_taxonomy)
    monkeypatch.setattr(ingest_code, "find_memory_skill", fail_find_memory_skill)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", fail_collect_files)
    monkeypatch.setattr(ingest_code, "_learn", fail_learn)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", fail_marker)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, glob=["../*.py"]))

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


def test_mixed_valid_and_invalid_globs_fail_entire_command(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    discovery_calls = []

    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: discovery_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, glob=["src/**/*.py", "../*.py"]))

    assert exc_info.value.code == 2
    assert discovery_calls == []


def test_valid_custom_globs_reach_discovery_normalized(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    captured_patterns = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: None)

    def fake_collect_files(path: Path, patterns: list[str]) -> list[Path]:
        captured_patterns.extend(patterns)
        return []

    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", fake_collect_files)

    ingest_code.scan(**_scan_args(repo, glob=["*.py", "./src/**/*.ts", "*.py"]))

    assert captured_patterns == ["**/*.py", "src/**/*.ts"]


def test_no_explicit_globs_preserves_default_patterns(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    captured_patterns = []

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: None)

    def fake_collect_files(path: Path, patterns: list[str]) -> list[Path]:
        captured_patterns.extend(patterns)
        return []

    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", fake_collect_files)

    ingest_code.scan(**_scan_args(repo, glob=[]))

    assert captured_patterns == list(ingest_code.DEFAULT_GLOB_PATTERNS)


def test_dry_run_does_not_bypass_invalid_glob_validation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, glob=["/tmp/*.py"], dry_run=True))

    assert exc_info.value.code == 2


def test_skill_docs_describe_glob_validation() -> None:
    text = SKILL_PATH.read_text()

    assert "--glob" in text
    assert "repository-relative" in text
    assert "Repeatable" in text or "repeatable" in text
    assert "status 2" in text
