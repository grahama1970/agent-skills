"""Regression tests for fail-closed CWE taxonomy bridge extraction."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
CWE_MODULE_PATH = MODULE_PATH.parent / "ingest_code_cwe.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))

cwe_spec = importlib.util.spec_from_file_location("ingest_code_cwe", CWE_MODULE_PATH)
assert cwe_spec and cwe_spec.loader
ingest_code_cwe = importlib.util.module_from_spec(cwe_spec)
sys.modules[cwe_spec.name] = ingest_code_cwe
cwe_spec.loader.exec_module(ingest_code_cwe)

spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


class _Taxonomy:
    def __init__(self, result: object = None, exc: Exception | None = None) -> None:
        self.result = {"bridge_tags": ["security"]} if result is None else result
        self.exc = exc
        self.calls: list[str] = []

    def extract_taxonomy(self, text: str, **kwargs) -> object:
        self.calls.append(text)
        if self.exc is not None:
            raise self.exc
        return self.result


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": True,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "dry_run": True,
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
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('eval("1")\n')
    return source


def _cwe_ids(result: dict) -> set[str]:
    return {mapping["cwe_id"] for mapping in result["cwe_mappings"]}


def _install_common(monkeypatch, tmp_path: Path, source: Path, taxonomy) -> dict:
    calls = {"learn": [], "marker": []}
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: taxonomy)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "_write_required_ingest_marker",
        lambda *args, **kwargs: calls["marker"].append(args),
    )
    return calls


def test_cwe_scanner_without_taxonomy_preserves_base_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    result = ingest_code_cwe.scan_file_cwe(source, None)

    assert "CWE-94" in _cwe_ids(result)
    assert result["bridge_tags"] == []


def test_cwe_scanner_accepts_valid_taxonomy_bridge_tags(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    result = ingest_code_cwe.scan_file_cwe(source, _Taxonomy({"bridge_tags": ["security"]}))

    assert "CWE-94" in _cwe_ids(result)
    assert result["bridge_tags"] == ["security"]


def test_cwe_scanner_rejects_missing_taxonomy_callable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    with pytest.raises(ingest_code_cwe.CweTaxonomyError, match="no callable"):
        ingest_code_cwe.scan_file_cwe(source, object())


def test_cwe_scanner_rejects_taxonomy_exception(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    with pytest.raises(ingest_code_cwe.CweTaxonomyError, match="RuntimeError: taxonomy failed"):
        ingest_code_cwe.scan_file_cwe(source, _Taxonomy(exc=RuntimeError("taxonomy failed")))


def test_cwe_scanner_rejects_non_object_taxonomy_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    with pytest.raises(ingest_code_cwe.CweTaxonomyError, match="expected object"):
        ingest_code_cwe.scan_file_cwe(source, _Taxonomy(["security"]))


def test_checked_cwe_path_reports_taxonomy_result_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)

    with pytest.raises(ingest_code.CweScanResultError) as exc_info:
        ingest_code._scan_file_cwe_checked(source, _Taxonomy(["security"]), validate=False)

    assert exc_info.value.location == "taxonomy"
    assert "taxonomy result expected object" in str(exc_info.value)


def test_cwe_only_scan_taxonomy_failure_writes_nothing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = _install_common(monkeypatch, tmp_path, source, _Taxonomy(exc=RuntimeError("taxonomy failed")))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    captured = capsys.readouterr()
    error = json.loads(captured.err.strip().splitlines()[-1])
    assert exc_info.value.code == 1
    assert error["phase"] == "cwe"
    assert error["location"] == "taxonomy"
    assert "[CWE]" not in captured.out
    assert calls["learn"] == []
    assert calls["marker"] == []


def test_rescan_taxonomy_failure_writes_no_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _source(repo)
    calls = _install_common(monkeypatch, tmp_path, source, _Taxonomy(exc=RuntimeError("taxonomy failed")))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo]))

    assert exc_info.value.code == 1
    assert calls["learn"] == []
    assert calls["marker"] == []


def test_skill_docs_describe_cwe_taxonomy_failure_boundary() -> None:
    text = SKILL_PATH.read_text()

    assert "Absence of the optional taxonomy module remains nonfatal" in text
    assert (
        "missing callable, raised exception, non-object result, or malformed bridge tags"
        in text
    )
    assert "before CWE preview, persistence, or marker creation" in text
