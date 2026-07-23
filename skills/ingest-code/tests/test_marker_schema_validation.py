"""Regression tests for completed ingest marker schema validation."""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
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


def _write_marker(repo: Path, marker: dict) -> dict:
    (repo / ".ingest-code.json").write_text(json.dumps(marker))
    return ingest_code.build_marker_status(repo)


def _valid_legacy_marker(repo: Path) -> dict:
    return {
        "ingested_at": "2026-05-01T08:00:00",
        "path": str(repo.resolve()),
        "stem": repo.name,
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


def _valid_complete_marker(repo: Path) -> dict:
    marker = _valid_legacy_marker(repo)
    marker.update({
        "run_status": "complete",
        "started_at": "2026-05-01T07:59:00",
        "completed": True,
        "scan_roots": [str(repo.resolve()), "src"],
        "completed_scan_roots": ["src"],
    })
    return marker


def test_empty_object_marker_is_invalid_not_fresh(tmp_path: Path) -> None:
    status = _write_marker(tmp_path, {})

    assert status["status"] == "invalid"
    assert status["completed"] is False
    assert status["code_index"]["enabled"] is False
    assert "validation_errors" in status


@pytest.mark.parametrize(
    "field",
    [
        "ingested_at",
        "path",
        "stem",
        "files_scanned",
        "knowledge_stored",
        "cwe_stored",
        "edges_stored",
        "code_index",
        "scope",
    ],
)
def test_completed_marker_requires_stable_fields(tmp_path: Path, field: str) -> None:
    marker = _valid_legacy_marker(tmp_path)
    marker.pop(field)

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any(field in error for error in status["validation_errors"])


def test_valid_legacy_marker_without_run_status_remains_fresh(tmp_path: Path) -> None:
    status = _write_marker(tmp_path, _valid_legacy_marker(tmp_path))

    assert status["status"] == "fresh"
    assert status["run_status"] == "complete"
    assert status["completed"] is True
    assert status["scope"] == "legacy-scope"
    assert status["code_index"]["symbols_stored"] == 4
    assert status["scan_roots"] == []
    assert status["completed_scan_roots"] == []


@pytest.mark.parametrize("completed", [None, False, "true", 1])
def test_new_complete_marker_requires_completed_true(tmp_path: Path, completed: object) -> None:
    marker = _valid_complete_marker(tmp_path)
    if completed is None:
        marker.pop("completed")
    else:
        marker["completed"] = completed

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any("completed" in error for error in status["validation_errors"])


@pytest.mark.parametrize("field", ["files_scanned", "knowledge_stored", "cwe_stored", "edges_stored"])
@pytest.mark.parametrize("value", [-1, True, "1", 1.5])
def test_marker_rejects_invalid_counts(tmp_path: Path, field: str, value: object) -> None:
    marker = _valid_complete_marker(tmp_path)
    marker[field] = value

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any(field in error for error in status["validation_errors"])


@pytest.mark.parametrize("value", [-1, True, "1", 1.5])
def test_marker_rejects_invalid_symbols_stored(tmp_path: Path, value: object) -> None:
    marker = _valid_complete_marker(tmp_path)
    marker["code_index"]["symbols_stored"] = value

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any("symbols_stored" in error for error in status["validation_errors"])


def test_marker_rejects_path_and_stem_mismatch(tmp_path: Path) -> None:
    wrong_path = _valid_complete_marker(tmp_path)
    wrong_path["path"] = str(tmp_path.parent)
    wrong_stem = _valid_complete_marker(tmp_path)
    wrong_stem["stem"] = "wrong"

    path_status = _write_marker(tmp_path, wrong_path)
    stem_status = _write_marker(tmp_path, wrong_stem)

    assert path_status["status"] == "invalid"
    assert any("path" in error for error in path_status["validation_errors"])
    assert stem_status["status"] == "invalid"
    assert any("stem" in error for error in stem_status["validation_errors"])


@pytest.mark.parametrize(
    "mutator",
    [
        lambda marker: marker["code_index"].update({"enabled": True, "symbols_stored": 0}),
        lambda marker: marker["code_index"].update({"enabled": False, "symbols_stored": 3}),
        lambda marker: marker["code_index"].update({"backend": "other"}),
        lambda marker: marker["code_index"].update({"collection": "other"}),
    ],
)
def test_marker_rejects_inconsistent_code_index_state(tmp_path: Path, mutator) -> None:
    marker = _valid_complete_marker(tmp_path)
    mutator(marker)

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any("code_index" in error for error in status["validation_errors"])


@pytest.mark.parametrize(
    "scan_roots,completed_roots,expected_field",
    [
        ("src", [], "scan_roots"),
        ([""], [], "scan_roots"),
        (["../outside"], [], "scan_roots"),
        (["src"], ["../outside"], "completed_scan_roots"),
        (["src"], ["other"], "completed_scan_roots"),
    ],
)
def test_marker_rejects_invalid_root_lists(
    tmp_path: Path,
    scan_roots: object,
    completed_roots: object,
    expected_field: str,
) -> None:
    marker = _valid_complete_marker(tmp_path)
    marker["scan_roots"] = scan_roots
    marker["completed_scan_roots"] = completed_roots

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    assert any(expected_field in error for error in status["validation_errors"])


def test_running_marker_remains_partial_and_status_authoritative(tmp_path: Path) -> None:
    marker = {
        "run_status": "running",
        "completed": True,
        "scan_roots": ["src"],
    }

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "running"
    assert status["run_status"] == "running"
    assert status["completed"] is False
    assert status["scan_roots"] == ["src"]


def test_failed_marker_remains_partial_and_status_authoritative(tmp_path: Path) -> None:
    marker = {
        "run_status": "failed",
        "completed": True,
        "completed_scan_roots": ["src"],
    }

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "failed"
    assert status["run_status"] == "failed"
    assert status["completed"] is False
    assert status["completed_scan_roots"] == ["src"]


def test_generated_marker_round_trips_as_fresh(tmp_path: Path) -> None:
    ingest_code._write_ingest_marker(
        tmp_path,
        files_scanned=2,
        knowledge_stored=1,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=3,
        treesitter=True,
        scope="roundtrip",
        scan_roots=[tmp_path, tmp_path / "src"],
        completed_scan_roots=[tmp_path / "src"],
    )

    status = ingest_code.build_marker_status(tmp_path)

    assert status["status"] == "fresh"
    assert status["run_status"] == "complete"
    assert status["completed"] is True
    assert "validation_errors" not in status


def test_invalid_marker_exposes_bounded_validation_errors(tmp_path: Path) -> None:
    marker = deepcopy(_valid_complete_marker(tmp_path))
    marker["files_scanned"] = -1
    marker["knowledge_stored"] = True
    marker["raw_payload"] = {"secret": "do not echo"}

    status = _write_marker(tmp_path, marker)

    assert status["status"] == "invalid"
    errors = status["validation_errors"]
    assert 0 < len(errors) <= 20
    joined = "\n".join(errors)
    assert "files_scanned" in joined
    assert "knowledge_stored" in joined
    assert "do not echo" not in joined


def test_skill_docs_describe_completed_marker_schema_gate() -> None:
    text = SKILL_PATH.read_text()

    assert "structurally valid" in text
    assert "legacy marker" in text
    assert "code-index metadata" in text
