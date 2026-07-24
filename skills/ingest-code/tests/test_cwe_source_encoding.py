"""Regression tests for CWE scanner source encoding handling."""

from __future__ import annotations

import codecs
import importlib.util
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
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_taxonomy(self, text: str, **kwargs) -> dict:
        self.calls.append(text)
        return {"bridge_tags": ["security"]}


def _write_bytes(repo: Path, relative_path: str, data: bytes) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _cwe_ids(result: dict) -> set[str]:
    return {mapping["cwe_id"] for mapping in result["cwe_mappings"]}


def test_cwe_scanner_decodes_latin1_python_cookie_before_taxonomy(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(
        repo,
        "app.py",
        (
            "# coding: latin-1\n"
            "password = \"cafésecret\"\n"
            "note = \"olé\"\n"
        ).encode("latin-1"),
    )
    taxonomy = _Taxonomy()

    result = ingest_code_cwe.scan_file_cwe(source, taxonomy)

    assert "CWE-259" in _cwe_ids(result)
    assert taxonomy.calls == ['# coding: latin-1\npassword = "cafésecret"\nnote = "olé"\n']


def test_cwe_scanner_strips_utf8_bom_before_taxonomy(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "app.py", codecs.BOM_UTF8 + b'eval("1")\n')
    taxonomy = _Taxonomy()

    result = ingest_code_cwe.scan_file_cwe(source, taxonomy)

    assert "CWE-94" in _cwe_ids(result)
    assert taxonomy.calls
    assert not taxonomy.calls[0].startswith("\ufeff")


def test_cwe_scanner_returns_error_for_unknown_python_encoding(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "app.py", b"# coding: made-up\npassword = \"secret\"\n")
    taxonomy = _Taxonomy()

    result = ingest_code_cwe.scan_file_cwe(source, taxonomy)

    assert result["error"]
    assert result["cwe_mappings"] == []
    assert taxonomy.calls == []


def test_cwe_scanner_returns_error_for_conflicting_bom_and_cookie(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(
        repo,
        "app.py",
        codecs.BOM_UTF8 + b"# coding: latin-1\npassword = \"secret\"\n",
    )
    taxonomy = _Taxonomy()

    result = ingest_code_cwe.scan_file_cwe(source, taxonomy)

    assert result["error"]
    assert result["cwe_mappings"] == []
    assert taxonomy.calls == []


def test_checked_cwe_path_promotes_encoding_error_to_source_read_error(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "app.py", b"# coding: made-up\npassword = \"secret\"\n")

    with pytest.raises(ingest_code.SourceReadError):
        ingest_code._scan_file_cwe_checked(source, _Taxonomy(), validate=False)


def test_cwe_scanner_preserves_non_python_tolerant_decoding(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "app.js", b"\xffeval(\"1\")\n")
    taxonomy = _Taxonomy()

    result = ingest_code_cwe.scan_file_cwe(source, taxonomy)

    assert "error" not in result
    assert "CWE-94" in _cwe_ids(result)
    assert taxonomy.calls == ['eval("1")\n']


def test_skill_docs_describe_cwe_python_decoding_parity() -> None:
    text = SKILL_PATH.read_text()

    assert (
        "Built-in CWE scanning uses Python encoding-cookie and UTF-8 BOM decoding"
        in text
    )
    assert "full, CWE-only, and rescan workflows" in text
    assert "fail closed before CWE preview, persistence, or marker creation" in text
