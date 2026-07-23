"""Regression tests for relative Python imports in Tree-sitter symbol context."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _write(repo: Path, relative_path: str, content: str) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _symbol(name: str = "service") -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": 3,
        "end_line": 4,
        "signature": f"def {name}(): ...",
    }


def _tree_entry(path: Path, symbols: list[dict] | None = None) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": symbols if symbols is not None else [_symbol()],
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


def _extract_records(monkeypatch, tmp_path: Path, repo: Path, source: Path):
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source)])
    return ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )


def test_symbol_context_resolves_sibling_relative_import(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    service = _write(repo, "pkg/service.py", "from .helper import run\n\n")

    context = ingest_code._extract_symbol_context(service, repo)

    assert context["imports"] == [{
        "module": "pkg.helper",
        "names": ["run"],
        "line": 1,
    }]


def test_symbol_context_resolves_from_dot_import(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    service = _write(repo, "pkg/service.py", "from . import helper\n\n")

    context = ingest_code._extract_symbol_context(service, repo)

    assert context["imports"] == [{
        "module": "pkg.helper",
        "names": [],
        "line": 1,
    }]


def test_symbol_context_resolves_parent_relative_import(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    service = _write(repo, "pkg/sub/service.py", "from ..common import load\n\n")

    context = ingest_code._extract_symbol_context(service, repo)

    assert context["imports"] == [{
        "module": "pkg.common",
        "names": ["load"],
        "line": 1,
    }]


def test_symbol_context_preserves_absolute_imports(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    service = _write(repo, "pkg/service.py", "from utilities.config import load\n\n")

    context = ingest_code._extract_symbol_context(service, repo)

    assert context["imports"] == [{
        "module": "utilities.config",
        "names": ["load"],
        "line": 1,
    }]


def test_root_level_relative_import_is_omitted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = _write(repo, "app.py", "from . import helper\n\n")

    context = ingest_code._extract_symbol_context(app, repo)

    assert context["imports"] == []


def test_code_symbol_record_contains_normalized_relative_import_terms(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/service.py",
        "from .helper import run\n\n"
        "def service():\n"
        "    return run()\n",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source)

    assert len(records) == 1
    record = records[0]
    assert record.imports == ["pkg.helper", "pkg.helper.run", "run"]
    document = record.to_document()
    assert "import:pkg.helper" in document["lexical_terms"]
    assert "import:pkg.helper.run" in document["lexical_terms"]
    assert "import:run" in document["lexical_terms"]


def test_from_dot_import_reaches_code_symbol_document(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/service.py",
        "from . import helper\n\n"
        "def service():\n"
        "    return helper.run()\n",
    )

    records = _extract_records(monkeypatch, tmp_path, repo, source)

    assert len(records) == 1
    document = records[0].to_document()
    assert records[0].imports == ["pkg.helper"]
    assert "import:pkg.helper" in document["lexical_terms"]


def test_dry_run_and_live_use_identical_relative_import_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/service.py",
        "from .helper import run\n\n"
        "def service():\n"
        "    return run()\n",
    )
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source)])
    stored_records = []

    class FakeClient:
        def upsert_code_symbols(self, records):
            stored_records.extend(records)
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                stored_records=records,
            )

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    dry_records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )
    stored = ingest_code._store_treesitter_symbols_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert stored == 1
    assert len(dry_records) == 1
    assert len(stored_records) == 1
    dry_doc = dry_records[0].to_document()
    live_doc = stored_records[0].to_document()
    assert stored_records[0].imports == dry_records[0].imports
    assert stored_records[0].content_hash == dry_records[0].content_hash
    assert live_doc["lexical_terms"] == dry_doc["lexical_terms"]


def test_relative_import_context_is_deterministic(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/service.py",
        "from .helper import run\n\n"
        "def service():\n"
        "    return run()\n",
    )

    first = _extract_records(monkeypatch, tmp_path, repo, source)
    second = _extract_records(monkeypatch, tmp_path, repo, source)

    assert [record.to_document() for record in first] == [
        record.to_document() for record in second
    ]
