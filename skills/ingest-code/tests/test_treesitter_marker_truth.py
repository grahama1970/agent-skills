"""Regression tests for Tree-sitter marker truthfulness."""

from __future__ import annotations

import importlib.util
import json
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
        "treesitter": True,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(repo) for repo in repos],
    }
    options.update(overrides)
    return options


def _source(repo: Path, name: str = "app.py") -> Path:
    source = repo / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def app():\n    return 1\n")
    return source


def _mock_scan_common(monkeypatch, tmp_path: Path, source: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def _mock_rescan_common(monkeypatch, tmp_path: Path, files_by_repo: dict[Path, Path]) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)

    def fake_collect_files(path: Path, patterns, mtime_after=None):
        return [files_by_repo[path]]

    monkeypatch.setattr(ingest_code, "collect_files", fake_collect_files)


def _code_index(repo: Path) -> dict:
    return ingest_code.build_marker_status(repo)["code_index"]


def test_scan_no_code_index_does_not_claim_treesitter_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    tree_calls = []
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(
        ingest_code,
        "_extract_configured_scan_roots",
        lambda *args, **kwargs: tree_calls.append(args) or [repo],
    )

    ingest_code.scan(**_scan_args(repo, code_index=False))

    assert tree_calls == []
    assert _code_index(repo)["treesitter"] is False


def test_scan_cwe_only_does_not_claim_treesitter_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    tree_calls = []
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(
        ingest_code,
        "_extract_configured_scan_roots",
        lambda *args, **kwargs: tree_calls.append(args) or [repo],
    )

    ingest_code.scan(**_scan_args(repo, cwe_only=True))

    assert tree_calls == []
    assert _code_index(repo)["treesitter"] is False


def test_scan_empty_root_scope_does_not_claim_treesitter_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: [])

    ingest_code.scan(**_scan_args(repo))

    assert _code_index(repo)["treesitter"] is False


def test_scan_zero_symbol_completed_root_records_treesitter_true(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo / "src")
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: [source.parent])
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: 0)

    ingest_code.scan(**_scan_args(repo))

    code_index = _code_index(repo)
    assert code_index["treesitter"] is True
    assert code_index["enabled"] is False
    assert code_index["symbols_stored"] == 0


def test_scan_symbol_result_records_treesitter_and_enabled_true(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo / "src")
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: [source.parent])
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: 2)

    ingest_code.scan(**_scan_args(repo))

    code_index = _code_index(repo)
    assert code_index["treesitter"] is True
    assert code_index["enabled"] is True
    assert code_index["symbols_stored"] == 2


def test_rescan_no_code_index_records_treesitter_false(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    _mock_rescan_common(monkeypatch, tmp_path, {repo.resolve(): source})
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: [repo])

    ingest_code.rescan(**_rescan_args([repo], code_index=False))

    assert _code_index(repo)["treesitter"] is False


def test_rescan_records_treesitter_execution_per_codebase(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    src_a = repo_a / "src"
    source_a = _source(src_a)
    source_b = _source(repo_b)
    _mock_rescan_common(
        monkeypatch,
        tmp_path,
        {repo_a.resolve(): source_a, repo_b.resolve(): source_b},
    )

    def fake_roots(path: Path) -> list[Path]:
        return [src_a] if path == repo_a.resolve() else []

    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", fake_roots)
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: 0)

    ingest_code.rescan(**_rescan_args([repo_a, repo_b]))

    assert _code_index(repo_a)["treesitter"] is True
    assert _code_index(repo_a)["enabled"] is False
    assert _code_index(repo_b)["treesitter"] is False


def test_marker_reader_rejects_non_boolean_treesitter_field(tmp_path: Path) -> None:
    ingest_code._write_ingest_marker(
        tmp_path,
        files_scanned=1,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=0,
        treesitter=False,
        scope="code",
    )
    marker_path = tmp_path / ".ingest-code.json"
    marker = json.loads(marker_path.read_text())
    marker["code_index"]["treesitter"] = "yes"
    marker_path.write_text(json.dumps(marker))

    status = ingest_code.build_marker_status(tmp_path)

    assert status["status"] == "invalid"
    assert "code_index.treesitter" in "\n".join(status["validation_errors"])


def test_legacy_code_index_without_treesitter_remains_valid(tmp_path: Path) -> None:
    marker = {
        "ingested_at": "2026-05-01T08:00:00",
        "path": str(tmp_path.resolve()),
        "stem": tmp_path.name,
        "files_scanned": 2,
        "knowledge_stored": 1,
        "cwe_stored": 0,
        "edges_stored": 0,
        "code_index": {
            "enabled": True,
            "backend": "memory",
            "collection": "code_symbols",
            "symbols_stored": 4,
        },
        "scope": "legacy-scope",
    }
    (tmp_path / ".ingest-code.json").write_text(json.dumps(marker))

    status = ingest_code.build_marker_status(tmp_path)

    assert status["status"] == "fresh"
    assert "treesitter" not in status["code_index"]


def test_treesitter_failure_still_writes_no_marker(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo / "src")
    marker_calls = []
    _mock_scan_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: [source.parent])
    monkeypatch.setattr(
        ingest_code,
        "_store_treesitter_symbols_for_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(ingest_code.TreeSitterScanError("boom")),
    )
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_skill_docs_describe_treesitter_marker_truth() -> None:
    text = SKILL_PATH.read_text()

    assert "code_index.treesitter" in text
    assert "completed successfully" in text
    assert "zero-symbol" in text
