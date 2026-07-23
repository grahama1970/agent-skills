"""Regression tests for Tree-sitter record canonicalization."""

from __future__ import annotations

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


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": False,
        "validate": False,
        "treesitter": True,
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
        "treesitter": True,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(repo) for repo in repos],
    }
    options.update(overrides)
    return options


def _symbol(
    name: str,
    *,
    kind: str = "function",
    start_line: int = 1,
    end_line: int = 1,
    signature: str | None = None,
) -> dict:
    return {
        "kind": kind,
        "name": name,
        "start_line": start_line,
        "end_line": end_line,
        "signature": signature if signature is not None else f"function {name}()",
    }


def _tree_entry(path: Path, symbols: list[dict]) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "typescript",
        "symbols": symbols,
    }


def _install_treesitter_output(monkeypatch, tmp_path: Path, entries: list[dict]) -> None:
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")

    def fake_run(cmd, **kwargs):
        class Result:
            stderr = ""

        result = Result()
        if cmd[0] == "git":
            result.returncode = 1
            result.stdout = ""
            return result

        result.returncode = 0
        result.stdout = json.dumps(entries)
        return result

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)


def _summary_from_stdout(stdout: str) -> dict:
    lines = stdout.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "{":
            candidate = "\n".join(lines[index:])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"summary JSON not found in output:\n{stdout}")


def _common_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path]) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)


def test_exact_duplicate_symbols_collapse_to_one_record(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    symbol = _symbol("run")
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [symbol, dict(symbol)])])

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert len(records) == 1


def test_duplicate_file_entries_collapse_to_one_record(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    entry = _tree_entry(source, [_symbol("run")])
    _install_treesitter_output(monkeypatch, tmp_path, [entry, dict(entry)])

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert len(records) == 1
    assert [ingest_code._treesitter_record_identity(record) for record in records] == [
        ("widget.ts", "run", 1)
    ]


def test_conflicting_duplicate_signature_fails(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    _install_treesitter_output(
        monkeypatch,
        tmp_path,
        [_tree_entry(source, [_symbol("run", signature="a"), _symbol("run", signature="b")])],
    )

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._extract_treesitter_records_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )


@pytest.mark.parametrize(
    "left,right",
    [
        (_symbol("run", end_line=1), _symbol("run", end_line=2)),
        (_symbol("run", kind="function"), _symbol("run", kind="method")),
    ],
)
def test_conflicting_duplicate_range_or_kind_fails(
    left: dict,
    right: dict,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\nconsole.log(run());\n")
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [left, right])])

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._extract_treesitter_records_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )


def test_same_qualified_name_at_different_lines_remains_distinct(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\nexport function run() { return 2; }\n")
    _install_treesitter_output(
        monkeypatch,
        tmp_path,
        [_tree_entry(source, [_symbol("run", start_line=2, end_line=2), _symbol("run", start_line=1, end_line=1)])],
    )

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert [(record.qualified_name, record.start_line) for record in records] == [("run", 1), ("run", 2)]


def test_canonical_order_is_independent_of_subprocess_order(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function b() { return 2; }\nexport function a() { return 1; }\n")
    symbols = [_symbol("b", start_line=1, end_line=1), _symbol("a", start_line=2, end_line=2)]
    outputs = []
    for ordered in [symbols, list(reversed(symbols))]:
        _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, ordered)])
        records = ingest_code._extract_treesitter_records_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )
        outputs.append([ingest_code._treesitter_record_identity(record) for record in records])

    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("dry_run", [True, False])
def test_conflict_occurs_before_preview_or_memory(
    dry_run: bool,
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    marker_calls = []
    memory_calls = []
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    _install_treesitter_output(
        monkeypatch,
        tmp_path,
        [_tree_entry(source, [_symbol("run", signature="a"), _symbol("run", signature="b")])],
    )
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=dry_run))

    stdout = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "[CODE_SYMBOL]" not in stdout
    assert memory_calls == []
    assert marker_calls == []


def test_dry_run_duplicate_symbol_is_previewed_once(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    symbol = _symbol("run")
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [symbol, dict(symbol)])])

    ingest_code.scan(**_scan_args(repo, dry_run=True))

    stdout = capsys.readouterr().out
    summary = _summary_from_stdout(stdout)
    assert stdout.count("[CODE_SYMBOL]") == 1
    assert summary["code_symbols_extracted"] == 1
    assert summary["code_symbols_stored"] == 0


def test_live_duplicate_symbol_is_upserted_and_counted_once(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    captured_records = []
    symbol = _symbol("run")
    _common_scan_mocks(monkeypatch, tmp_path, [source])
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [symbol, dict(symbol)])])

    class FakeClient:
        def upsert_code_symbols(self, records):
            captured_records.extend(records)
            return SimpleNamespace(stored=len(records), attempted=len(records), errors=[], stored_records=tuple(records))

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    ingest_code.scan(**_scan_args(repo))

    status = ingest_code.build_marker_status(repo)
    assert len(captured_records) == 1
    assert status["code_index"]["symbols_stored"] == 1


def test_rescan_duplicate_symbol_does_not_inflate_marker(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    symbol = _symbol("run")
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, [symbol, dict(symbol)])])

    class FakeClient:
        def upsert_code_symbols(self, records):
            return SimpleNamespace(stored=len(records), attempted=len(records), errors=[], stored_records=tuple(records))

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    ingest_code.rescan(**_rescan_args([repo]))

    status = ingest_code.build_marker_status(repo)
    assert status["code_index"]["symbols_stored"] == 1


def test_skill_docs_describe_duplicate_and_conflict_behavior() -> None:
    text = SKILL_PATH.read_text()

    assert "duplicate" in text
    assert "Conflicting" in text
    assert "status 1" in text
    assert "completed marker" in text
