"""Regression tests for canonical CWE memory payloads."""

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
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def app():\n    return 1\n")
    return source


def _cwe_result(*, bridge_tags=None) -> dict:
    return {
        "cwe_mappings": [
            {
                "cwe_id": "CWE-78",
                "name": "OS Command Injection",
                "category": "InputValidation",
            }
        ],
        "bridge_tags": [] if bridge_tags is None else bridge_tags,
    }


def _mock_common(monkeypatch, tmp_path: Path, source: Path, cwe_result: dict) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: deepcopy(cwe_result))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def test_cwe_payload_contains_canonical_problem_solution_and_tags(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": "InputValidation"},
        [],
    )

    assert payload == {
        "problem": "What CWEs are relevant to app.py?",
        "solution": f"CWE-78 (OS Command Injection) - Category: InputValidation. File: {source}",
        "tags": ["ingest-code", "cwe", "CWE-78", "InputValidation", "py"],
    }


def test_cwe_payload_omits_blank_category_tag_and_text(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": ""},
        [],
    )

    assert "Category" not in payload["solution"]
    assert payload["tags"] == ["ingest-code", "cwe", "CWE-78", "py"]


def test_cwe_payload_appends_bridge_tags_in_order(tmp_path: Path) -> None:
    payload = ingest_code._build_cwe_lesson_payload(
        tmp_path / "app.py",
        {"cwe_id": "CWE-78", "name": "", "category": "InputValidation"},
        ["sparta", "security", "runtime"],
    )

    assert payload["tags"] == [
        "ingest-code",
        "cwe",
        "CWE-78",
        "InputValidation",
        "py",
        "sparta",
        "security",
        "runtime",
    ]


def test_cwe_payload_deduplicates_bridge_tags_by_first_occurrence(tmp_path: Path) -> None:
    payload = ingest_code._build_cwe_lesson_payload(
        tmp_path / "app.py",
        {"cwe_id": "CWE-78", "name": "", "category": "InputValidation"},
        ["cwe", "CWE-78", "security", "security", "py"],
    )

    assert payload["tags"] == ["ingest-code", "cwe", "CWE-78", "InputValidation", "py", "security"]


def test_cwe_payload_without_taxonomy_preserves_base_tags(tmp_path: Path) -> None:
    payload = ingest_code._build_cwe_lesson_payload(
        tmp_path / "app.py",
        {"cwe_id": "CWE-78", "name": "", "category": "InputValidation"},
        [],
    )

    assert payload["tags"] == ["ingest-code", "cwe", "CWE-78", "InputValidation", "py"]


def test_scan_and_rescan_emit_identical_cwe_memory_arguments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    cwe_result = _cwe_result(bridge_tags=["security"])
    scan_calls = []
    rescan_calls = []
    _mock_common(monkeypatch, tmp_path, source, cwe_result)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: scan_calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo))

    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: rescan_calls.append(args) or True)
    ingest_code.rescan(**_rescan_args([repo]))

    assert scan_calls == rescan_calls


def test_rescan_preserves_cwe_category_metadata(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = []
    _mock_common(monkeypatch, tmp_path, source, _cwe_result())
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append(args) or True)

    ingest_code.rescan(**_rescan_args([repo]))

    assert "Category: InputValidation" in calls[0][2]
    assert "InputValidation" in calls[0][4]


def test_scan_and_rescan_propagate_validated_bridge_tags(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = []
    _mock_common(monkeypatch, tmp_path, source, _cwe_result(bridge_tags=["security", "sparta"]))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo))
    ingest_code.rescan(**_rescan_args([repo]))

    assert calls[0][4][-2:] == ["security", "sparta"]
    assert calls[1][4][-2:] == ["security", "sparta"]


def test_multiple_mappings_share_bridge_tags_without_cross_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = []
    result = {
        "cwe_mappings": [
            {"cwe_id": "CWE-78", "name": "Command", "category": "InputValidation"},
            {"cwe_id": "CWE-79", "name": "XSS", "category": "InputValidation"},
        ],
        "bridge_tags": ["security"],
    }
    _mock_common(monkeypatch, tmp_path, source, result)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls.append(args) or True)

    ingest_code.scan(**_scan_args(repo))

    assert len(calls) == 2
    assert calls[0][4] == ["ingest-code", "cwe", "CWE-78", "InputValidation", "py", "security"]
    assert calls[1][4] == ["ingest-code", "cwe", "CWE-79", "InputValidation", "py", "security"]


def test_payload_builder_does_not_mutate_cwe_or_bridge_tag_inputs(tmp_path: Path) -> None:
    cwe = {"cwe_id": "CWE-78", "name": "Command", "category": "InputValidation"}
    bridge_tags = ["security"]
    original_cwe = dict(cwe)
    original_tags = list(bridge_tags)

    payload = ingest_code._build_cwe_lesson_payload(tmp_path / "app.py", cwe, bridge_tags)
    payload["tags"].append("mutated")

    assert cwe == original_cwe
    assert bridge_tags == original_tags


def test_cwe_attempted_and_stored_counts_are_unchanged(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    learn_results = iter([True, False])
    result = {
        "cwe_mappings": [
            {"cwe_id": "CWE-78", "name": "Command", "category": "InputValidation"},
            {"cwe_id": "CWE-79", "name": "XSS", "category": "InputValidation"},
        ],
        "bridge_tags": ["security"],
    }
    _mock_common(monkeypatch, tmp_path, source, result)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: next(learn_results))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    error = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert error["phase"] == "cwe"
    assert error["attempted"] == 2
    assert error["stored"] == 1


def test_malformed_bridge_tags_still_fail_before_payload_or_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = {"payload": [], "learn": []}
    _mock_common(monkeypatch, tmp_path, source, _cwe_result(bridge_tags=["ok", 1]))
    monkeypatch.setattr(
        ingest_code,
        "_build_cwe_lesson_payload",
        lambda *args, **kwargs: calls["payload"].append(args) or {},
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert calls == {"payload": [], "learn": []}


def test_skill_docs_describe_canonical_cwe_payload() -> None:
    text = SKILL_PATH.read_text()

    assert "same CWE compatibility payload" in text
    assert "bridge tags" in text
    assert "scan" in text and "rescan" in text
