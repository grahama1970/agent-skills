"""Regression tests for built-in CWE scanning without taxonomy."""

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


def _unsafe_source(repo: Path) -> Path:
    source = repo / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("import os\n\ndef run(cmd):\n    os.system(cmd)\n")
    return source


def _safe_source(repo: Path) -> Path:
    source = repo / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def app():\n    return 1\n")
    return source


def _summary(stdout: str) -> dict:
    start = stdout.rfind("\n{")
    if start == -1:
        start = stdout.find("{")
    assert start != -1, stdout
    return json.loads(stdout[start:].strip())


def _mock_common(monkeypatch, tmp_path: Path, source: Path) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def test_cwe_only_dry_run_finds_builtin_pattern_without_taxonomy(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    source = _unsafe_source(repo)
    _mock_common(monkeypatch, tmp_path, source)

    ingest_code.scan(**_scan_args(repo, cwe_only=True, dry_run=True))

    out = capsys.readouterr().out
    summary = _summary(out)
    assert "[CWE] app.py: CWE-78" in out
    assert summary["total_cwe_mappings"] == 1
    assert summary["cwe_stored"] == 0
    assert not (repo / ".ingest-code.json").exists()


def test_live_cwe_only_stores_finding_without_taxonomy(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _unsafe_source(repo)
    learn_calls = []
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo, cwe_only=True))

    status = ingest_code.build_marker_status(repo)
    assert len(learn_calls) == 1
    assert "CWE-78" in learn_calls[0][4]
    assert status["status"] == "fresh"
    assert status["cwe_stored"] == 1


def test_rescan_stores_cwe_finding_without_taxonomy(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _unsafe_source(repo)
    learn_calls = []
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    ingest_code.rescan(**_rescan_args([repo]))

    status = ingest_code.build_marker_status(repo)
    assert len(learn_calls) == 1
    assert status["status"] == "fresh"
    assert status["cwe_stored"] == 1


def test_missing_taxonomy_does_not_call_knowledge_enrichment(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _unsafe_source(repo)
    learn_calls = []
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [{"problem": "p", "solution": "s", "tags": ["tag"]}],
    )
    monkeypatch.setattr(
        ingest_code,
        "enrich_with_taxonomy",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("taxonomy absent")),
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo))

    assert len(learn_calls) == 2
    assert ingest_code.build_marker_status(repo)["cwe_stored"] == 1


def test_malformed_cwe_result_without_taxonomy_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _safe_source(repo)
    calls = {"edges": [], "treesitter": [], "marker": []}
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": None})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: calls["edges"].append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda *args: calls["treesitter"].append(args) or [])
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert calls == {"edges": [], "treesitter": [], "marker": []}


def test_source_read_failure_without_taxonomy_remains_terminal(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    source = _safe_source(repo)
    marker_calls = []
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "scan_file_cwe",
        lambda *args, **kwargs: {"error": "permission denied", "cwe_mappings": []},
    )
    monkeypatch.setattr(ingest_code, "_write_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert marker_calls == []
    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert error["error"] == "Source file read failed"
    assert error["phase"] == "cwe"


def test_valid_empty_cwe_result_without_taxonomy_can_complete(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _safe_source(repo)
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})

    ingest_code.scan(**_scan_args(repo))

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["cwe_stored"] == 0


def test_cwe_only_without_taxonomy_does_not_run_phase_one(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _unsafe_source(repo)
    phase_one_calls = {"extract": [], "enrich": []}
    _mock_common(monkeypatch, tmp_path, source)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: phase_one_calls["extract"].append(args) or [],
    )
    monkeypatch.setattr(
        ingest_code,
        "enrich_with_taxonomy",
        lambda *args, **kwargs: phase_one_calls["enrich"].append(args) or [],
    )

    ingest_code.scan(**_scan_args(repo, cwe_only=True))

    assert phase_one_calls == {"extract": [], "enrich": []}
    assert ingest_code.build_marker_status(repo)["cwe_stored"] == 1


def test_skill_docs_define_taxonomy_optional_cwe_behavior() -> None:
    text = SKILL_PATH.read_text()

    assert "built-in CWE" in text
    assert "with or without" in text
    assert "bridge tags" in text
    assert "--cwe-only" in text
