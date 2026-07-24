"""Regression tests for repository-relative CWE lesson identities."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

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


def _source(repo: Path, relative_path: str = "src/app.py") -> Path:
    source = repo / relative_path
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


def test_cwe_payload_uses_repository_relative_problem_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo, "src/security/app.py")

    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": "InputValidation"},
        [],
        codebase_root=repo,
    )

    assert payload["problem"] == "What CWEs are relevant to src/security/app.py?"


def test_same_named_cwe_files_have_distinct_repository_relative_questions(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src_payload = ingest_code._build_cwe_lesson_payload(
        _source(repo, "src/app.py"),
        {"cwe_id": "CWE-78", "name": "", "category": "InputValidation"},
        [],
        codebase_root=repo,
    )
    tools_payload = ingest_code._build_cwe_lesson_payload(
        _source(repo, "tools/app.py"),
        {"cwe_id": "CWE-78", "name": "", "category": "InputValidation"},
        [],
        codebase_root=repo,
    )

    assert src_payload["problem"] == "What CWEs are relevant to src/app.py?"
    assert tools_payload["problem"] == "What CWEs are relevant to tools/app.py?"


def test_repository_aware_cwe_solution_omits_checkout_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": "InputValidation"},
        [],
        codebase_root=repo,
    )

    assert "File: src/app.py" in payload["solution"]
    assert str(repo) not in payload["solution"]


def test_repository_identity_change_preserves_cwe_content_and_tags(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": "InputValidation"},
        ["sparta", "security"],
        codebase_root=repo,
    )

    assert payload["solution"].startswith("CWE-78 (OS Command Injection) - Category: InputValidation.")
    assert payload["tags"] == [
        "ingest-code",
        "cwe",
        "CWE-78",
        "InputValidation",
        "py",
        "sparta",
        "security",
    ]


def test_direct_cwe_payload_preserves_legacy_output(tmp_path: Path) -> None:
    source = tmp_path / "repo" / "src" / "app.py"

    payload = ingest_code._build_cwe_lesson_payload(
        source,
        {"cwe_id": "CWE-78", "name": "OS Command Injection", "category": "InputValidation"},
        [],
    )

    assert payload["problem"] == "What CWEs are relevant to app.py?"
    assert payload["solution"] == (
        f"CWE-78 (OS Command Injection) - Category: InputValidation. File: {source}"
    )


def test_scan_and_rescan_pass_repository_root_to_cwe_payload(
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

    assert scan_calls
    assert rescan_calls
    for call in [scan_calls[0], rescan_calls[0]]:
        assert call[1] == "What CWEs are relevant to src/app.py?"
        assert "File: src/app.py" in call[2]
        assert str(repo) not in call[2]


def test_skill_docs_describe_cwe_repository_identity() -> None:
    text = SKILL_PATH.read_text()

    assert "CWE compatibility lessons use repository-relative file identities" in text
    assert "do not include checkout-local absolute paths" in text
    assert "Direct helper calls without a repository root retain their legacy output" in text
