"""Regression tests for Python source encoding-cookie handling."""

from __future__ import annotations

import codecs
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _write_bytes(repo: Path, relative_path: str, data: bytes) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _symbol(name: str, *, start_line: int, end_line: int | None = None) -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": start_line,
        "end_line": end_line if end_line is not None else start_line,
        "signature": f"def {name}(): ...",
    }


def _tree_entry(path: Path, symbols: list[dict]) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": symbols,
    }


def _install_treesitter_output(monkeypatch, tmp_path: Path, entries: list[dict]) -> None:
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps(entries), stderr="")

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)


def _extract_records(monkeypatch, tmp_path: Path, repo: Path, source: Path, symbols: list[dict]):
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, symbols)])
    return ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )


def test_latin1_cookie_preserves_docstring_and_string_literal(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(
        repo,
        "pkg/app.py",
        (
            "# coding: latin-1\n"
            "def cafe():\n"
            "    \"\"\"café function docstring\"\"\"\n"
            "    value = \"olé\"\n"
            "    return value\n"
        ).encode("latin-1"),
    )

    items = ingest_code.extract_python_knowledge(source, ingest_code._read_source_text(source), repo)
    details = ingest_code._extract_python_symbol_details(source, "function", "cafe", 2)

    assert any("café function docstring" in item["solution"] for item in items)
    assert details["docstring"] == "café function docstring"
    assert "olé" in details["string_literals"]


def test_latin1_exact_symbol_code_and_hash_are_canonical(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = _write_bytes(
        repo,
        "app.py",
        (
            "# coding: latin-1\n"
            "def cafe():\n"
            "    return \"olé\"\n"
        ).encode("latin-1"),
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source, [_symbol("cafe", start_line=2)])

    assert len(records) == 1
    assert records[0].code == 'def cafe():\n    return "olé"'
    assert records[0].content_hash == ingest_code._content_hash(records[0].code)


def test_utf8_bom_python_source_parses_without_bom_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(
        repo,
        "app.py",
        codecs.BOM_UTF8 + b'def run():\n    return "ok"\n',
    )

    content = ingest_code._read_source_text(source)
    items = ingest_code.extract_python_knowledge(source, content)

    assert not content.startswith("\ufeff")
    assert any(item["problem"] == "What does run() do in app.py?" for item in items)


def test_unknown_encoding_cookie_raises_source_read_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "app.py", b"# coding: made-up\nx = 1\n")

    with pytest.raises(ingest_code.SourceReadError):
        ingest_code._read_source_text(source)


def test_conflicting_bom_and_cookie_raises_source_read_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(
        repo,
        "app.py",
        codecs.BOM_UTF8 + b"# coding: latin-1\nx = 1\n",
    )

    with pytest.raises(ingest_code.SourceReadError):
        ingest_code._read_source_text(source)


def test_non_python_invalid_bytes_keep_existing_tolerant_behavior(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write_bytes(repo, "notes.txt", b"abc\xffdef")

    assert ingest_code._read_source_text(source) == "abcdef"


def test_skill_docs_describe_python_source_decoding() -> None:
    text = SKILL_PATH.read_text()

    assert "Python source decoding honors encoding cookies and UTF-8 BOMs" in text
    assert "fails closed" in text
