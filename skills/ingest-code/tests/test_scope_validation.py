"""Regression tests for ingest memory scope validation."""

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


class _EmptyTaxonomy:
    def extract_taxonomy(self, *args, **kwargs):
        return {"bridge_tags": [], "collection_tags": {}}


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


def test_validate_memory_scope_accepts_and_normalizes() -> None:
    assert ingest_code._validate_memory_scope("code") == "code"
    assert ingest_code._validate_memory_scope("  project-code  ") == "project-code"


@pytest.mark.parametrize("scope", ["", " ", "\t\n", None, 42, False])
def test_validate_memory_scope_rejects_invalid_values(scope: object) -> None:
    with pytest.raises(ingest_code.MemoryScopeError):
        ingest_code._validate_memory_scope(scope)


def test_scan_invalid_scope_exits_before_external_work(monkeypatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", lambda *args, **kwargs: calls.append("resolve"))
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", lambda *args, **kwargs: calls.append("config"))
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: calls.append("taxonomy"))
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: calls.append("collect"))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append("learn"))
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args, **kwargs: calls.append("treesitter"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls.append("marker"))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(tmp_path / "missing", scope="  "))

    assert exc_info.value.code == 2
    assert calls == []


def test_rescan_invalid_scope_exits_before_external_work(monkeypatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(ingest_code, "_resolve_codebase_directory", lambda *args, **kwargs: calls.append("resolve"))
    monkeypatch.setattr(ingest_code, "_preflight_scan_config", lambda *args, **kwargs: calls.append("config"))
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: calls.append("taxonomy"))
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: calls.append("collect"))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append("learn"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls.append("marker"))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([tmp_path / "repo"], scope=""))

    assert exc_info.value.code == 2
    assert calls == []


def test_scan_propagates_normalized_scope(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    scopes: list[tuple[str, str]] = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: _EmptyTaxonomy())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [{"problem": "p", "solution": "s", "tags": ["t"]}],
    )
    monkeypatch.setattr(
        ingest_code,
        "scan_file_cwe",
        lambda *args, **kwargs: {"cwe_mappings": [{"cwe_id": "CWE-20", "name": "Input", "category": "input"}]},
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: scopes.append(("learn", args[3])) or True)
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [{"from_file": str(source), "to_file": str(source), "edge_type": "depends_on", "module": "app"}])
    monkeypatch.setattr(ingest_code, "store_edges", lambda *args, **kwargs: scopes.append(("edges", kwargs["scope"])) or 1)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_store_treesitter_symbols_for_directory",
        lambda *args, **kwargs: scopes.append(("treesitter", args[2])) or 0,
    )
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: scopes.append(("marker", kwargs["scope"])) or (repo / ".ingest-code.json"),
    )
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(**_scan_args(repo, treesitter=True, scope=" team-code "))

    assert scopes
    assert all(scope == "team-code" for _, scope in scopes)
    assert {kind for kind, _ in scopes} >= {"learn", "edges", "treesitter", "marker"}


def test_rescan_propagates_normalized_scope(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    scopes: list[tuple[str, str]] = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: _EmptyTaxonomy())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [{"problem": "p", "solution": "s", "tags": ["t"]}],
    )
    monkeypatch.setattr(
        ingest_code,
        "scan_file_cwe",
        lambda *args, **kwargs: {"cwe_mappings": [{"cwe_id": "CWE-20", "name": "Input"}]},
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: scopes.append(("learn", args[3])) or True)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_store_treesitter_symbols_for_directory",
        lambda *args, **kwargs: scopes.append(("treesitter", args[2])) or 0,
    )
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: scopes.append(("marker", kwargs["scope"])) or (repo / ".ingest-code.json"),
    )

    ingest_code.rescan(**_rescan_args([repo], treesitter=True, scope=" team-code "))

    assert scopes
    assert all(scope == "team-code" for _, scope in scopes)
    assert {kind for kind, _ in scopes} >= {"learn", "treesitter", "marker"}


def test_write_ingest_marker_rejects_blank_scope(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.MemoryScopeError):
        ingest_code._write_ingest_marker(
            tmp_path,
            files_scanned=0,
            knowledge_stored=0,
            cwe_stored=0,
            edges_stored=0,
            code_symbols_stored=0,
            treesitter=False,
            scope=" ",
        )

    assert not (tmp_path / ".ingest-code.json").exists()
    assert not (tmp_path / ".ingest-code.json.tmp").exists()


def test_normalized_scope_marker_round_trips_as_fresh(tmp_path: Path) -> None:
    ingest_code._write_ingest_marker(
        tmp_path,
        files_scanned=0,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=0,
        treesitter=False,
        scope=" code ",
    )

    status = ingest_code.build_marker_status(tmp_path)

    assert status["status"] == "fresh"
    assert status["scope"] == "code"


def test_dry_run_still_rejects_invalid_scope(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(tmp_path / "missing", dry_run=True, scope="\t"))

    assert exc_info.value.code == 2


def test_skill_docs_define_scope_validation() -> None:
    text = SKILL_PATH.read_text()

    assert "--scope" in text
    assert "nonblank" in text
    assert "whitespace" in text
    assert "status 2" in text
