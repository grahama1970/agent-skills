"""Regression tests for fail-closed CWE scanner result validation."""

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


def _source(repo: Path) -> Path:
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    return source


def _install_scan_mocks(monkeypatch, tmp_path: Path, source: Path, cwe_result) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: object())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: cwe_result)


def test_cwe_validator_accepts_valid_empty_result(tmp_path: Path) -> None:
    source = tmp_path / "app.py"

    assert ingest_code._validate_cwe_scan_result(source, {"cwe_mappings": []}) == {
        "cwe_mappings": []
    }


def test_cwe_validator_accepts_and_normalizes_valid_mapping(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    result = ingest_code._validate_cwe_scan_result(
        source,
        {
            "cwe_mappings": [
                {
                    "cwe_id": " CWE-20 ",
                    "name": " Input Validation ",
                    "category": " input ",
                    "matches": [{"line": 1}],
                }
            ],
            "bridge_tags": ["security"],
            "worth_remembering": True,
        },
    )

    assert result["cwe_mappings"][0] == {
        "cwe_id": "CWE-20",
        "name": "Input Validation",
        "category": "input",
        "matches": [{"line": 1}],
    }


def test_cwe_validator_rejects_non_object_result(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(tmp_path / "app.py", [])


@pytest.mark.parametrize("result", [{}, {"cwe_mappings": None}, {"cwe_mappings": "CWE-20"}])
def test_cwe_validator_rejects_missing_or_non_array_mappings(tmp_path: Path, result: object) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(tmp_path / "app.py", result)


def test_cwe_validator_rejects_non_object_mapping(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(tmp_path / "app.py", {"cwe_mappings": ["CWE-20"]})


@pytest.mark.parametrize("cwe_id", [None, "", " ", 20, "CWE-0", "CWE-x", "CWE-"])
def test_cwe_validator_rejects_invalid_cwe_id(tmp_path: Path, cwe_id: object) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(
            tmp_path / "app.py",
            {"cwe_mappings": [{"cwe_id": cwe_id}]},
        )


@pytest.mark.parametrize("field", ["name", "category"])
def test_cwe_validator_rejects_non_string_name_or_category(tmp_path: Path, field: str) -> None:
    mapping = {"cwe_id": "CWE-20", field: 42}

    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(tmp_path / "app.py", {"cwe_mappings": [mapping]})


@pytest.mark.parametrize("bridge_tags", ["security", [1], ["security", 2]])
def test_cwe_validator_rejects_invalid_bridge_tags(tmp_path: Path, bridge_tags: object) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(
            tmp_path / "app.py",
            {"cwe_mappings": [], "bridge_tags": bridge_tags},
        )


def test_cwe_validator_rejects_non_boolean_worth_remembering(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.CweScanResultError):
        ingest_code._validate_cwe_scan_result(
            tmp_path / "app.py",
            {"cwe_mappings": [], "worth_remembering": "yes"},
        )


def test_cwe_validator_preserves_unknown_fields(tmp_path: Path) -> None:
    result = ingest_code._validate_cwe_scan_result(
        tmp_path / "app.py",
        {"cwe_mappings": [{"cwe_id": "CWE-79", "custom": 1}], "extra": {"x": True}},
    )

    assert result["extra"] == {"x": True}
    assert result["cwe_mappings"][0]["custom"] == 1


def test_scanner_error_remains_source_read_failure(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.SourceReadError):
        ingest_code._validate_cwe_scan_result(
            tmp_path / "app.py",
            {"error": "permission denied", "cwe_mappings": []},
        )


def test_scan_invalid_cwe_result_stops_before_edges_and_marker(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _source(repo)
    edge_calls = []
    marker_calls = []
    _install_scan_mocks(monkeypatch, tmp_path, source, {"cwe_mappings": [{"cwe_id": ""}]})
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edge_calls.append(args) or [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert edge_calls == []
    assert marker_calls == []
    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert error["error"] == "CWE scan result invalid"
    assert error["location"] == "cwe_mappings[0].cwe_id"


def test_rescan_invalid_cwe_result_writes_no_pending_markers(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _source(repo)
    marker_calls = []
    _install_scan_mocks(monkeypatch, tmp_path, source, {"cwe_mappings": None})
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo]))

    assert exc_info.value.code == 1
    assert marker_calls == []


def test_dry_run_invalid_cwe_result_emits_no_cwe_preview(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _source(repo)
    _install_scan_mocks(monkeypatch, tmp_path, source, {"cwe_mappings": [{"cwe_id": "bad"}]})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert exc_info.value.code == 1
    assert "[CWE]" not in capsys.readouterr().out


def test_valid_empty_cwe_result_still_allows_completed_marker(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _source(repo)
    marker_calls = []
    _install_scan_mocks(monkeypatch, tmp_path, source, {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: marker_calls.append(kwargs) or repo / ".ingest-code.json",
    )
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(**_scan_args(repo))

    assert marker_calls
    assert marker_calls[0]["cwe_stored"] == 0


def test_skill_docs_describe_cwe_result_failure_boundary() -> None:
    text = SKILL_PATH.read_text()

    assert "Malformed CWE" in text
    assert "status 1" in text
    assert "zero-finding" in text
    assert "completed marker" in text
