"""Regression tests for scan --dry-run --treesitter previews."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
        "dry_run": True,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _symbol(name: str, start_line: int = 1, end_line: int = 2) -> dict:
    return {
        "kind": "function",
        "name": name,
        "start_line": start_line,
        "end_line": end_line,
        "signature": f"def {name}(): ...",
    }


def _tree_entry(path: Path, name: str, start_line: int = 1, end_line: int = 2) -> dict:
    return {
        "path": str(path.resolve()),
        "language": "python",
        "symbols": [_symbol(name, start_line=start_line, end_line=end_line)],
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


def _common_scan_mocks(monkeypatch, tmp_path: Path, files: list[Path], scan_root: Path) -> None:
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: files)
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [scan_root])


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


def test_treesitter_extraction_helper_returns_records_without_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, "app")])
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("extraction helper must not open memory")),
    )

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert len(records) == 1
    assert records[0].path == "app.py"
    assert records[0].qualified_name == "app"


def test_scan_treesitter_dry_run_previews_symbols_without_writes(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "service.py"
    source.write_text("def run():\n    return 1\n")
    marker_calls = []
    discoverability_calls = []
    _common_scan_mocks(monkeypatch, tmp_path, [source], src)
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, "run")])
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run must not open memory")),
    )
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: discoverability_calls.append(args))

    ingest_code.scan(**_scan_args(repo))

    stdout = capsys.readouterr().out
    summary = _summary_from_stdout(stdout)
    assert "  [CODE_SYMBOL] src/service.py:1-2 function run" in stdout
    assert summary["code_symbols_extracted"] == 1
    assert summary["code_symbols_stored"] == 0
    assert summary["dry_run"] is True
    assert marker_calls == []
    assert discoverability_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_treesitter_dry_run_uses_discovered_manifest(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    keep = src / "keep.py"
    skip = src / "skip.py"
    keep.write_text("def keep():\n    return 1\n")
    skip.write_text("def skip():\n    return 2\n")
    _common_scan_mocks(monkeypatch, tmp_path, [keep], src)
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(keep, "keep"), _tree_entry(skip, "skip")])

    ingest_code.scan(**_scan_args(repo))

    stdout = capsys.readouterr().out
    summary = _summary_from_stdout(stdout)
    assert "[CODE_SYMBOL] src/keep.py:1-2 function keep" in stdout
    assert "skip.py" not in stdout
    assert summary["code_symbols_extracted"] == 1


def test_treesitter_dry_run_valid_empty_output_reports_zero(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    _common_scan_mocks(monkeypatch, tmp_path, [], src)
    _install_treesitter_output(monkeypatch, tmp_path, [])
    monkeypatch.setattr(
        ingest_code,
        "CodeMemoryClient",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run empty output must not open memory")),
    )

    ingest_code.scan(**_scan_args(repo))

    summary = _summary_from_stdout(capsys.readouterr().out)
    assert summary["code_symbols_extracted"] == 0
    assert summary["code_symbols_stored"] == 0


@pytest.mark.parametrize("failure_mode", ["timeout", "nonzero", "malformed"])
def test_treesitter_dry_run_failure_exits_one_without_marker(
    failure_mode: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    run_sh = tmp_path / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\n")
    _common_scan_mocks(monkeypatch, tmp_path, [source], src)
    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    def fake_run(cmd, **kwargs):
        if failure_mode == "timeout":
            raise subprocess.TimeoutExpired(cmd, 300)

        class Result:
            stderr = ""

        result = Result()
        if failure_mode == "nonzero":
            result.returncode = 2
            result.stdout = ""
            result.stderr = "scan failed"
        else:
            result.returncode = 0
            result.stdout = "not-json"
        return result

    monkeypatch.setattr(ingest_code.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo))

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo / ".ingest-code.json").exists()


def test_live_store_wrapper_uses_shared_extraction_helper(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    stored_records = []

    record = ingest_code._build_code_symbol_record(
        symbol=_symbol("app"),
        filepath=source,
        codebase_root=repo,
        scope="code",
        repo="repo",
        branch="main",
        commit="abc123",
        imports=[],
    )
    assert record is not None

    class FakeClient:
        def upsert_code_symbols(self, records):
            stored_records.extend(records)
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                stored_records=tuple(records),
            )

    monkeypatch.setattr(ingest_code, "_extract_treesitter_records_for_directory", lambda *args, **kwargs: (record,))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    stored = ingest_code._store_treesitter_symbols_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset({source.resolve()}),
    )

    assert stored == 1
    assert stored_records == [record]


def test_treesitter_dry_run_preview_order_is_deterministic(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    b_file = repo / "b.py"
    a_file = repo / "a.py"
    b_file.write_text("def b():\n    return 2\n")
    a_file.write_text("def a():\n    return 1\n")
    _common_scan_mocks(monkeypatch, tmp_path, [b_file, a_file], repo)
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(b_file, "b"), _tree_entry(a_file, "a")])

    ingest_code.scan(**_scan_args(repo))

    preview_lines = [
        line.strip()
        for line in capsys.readouterr().out.splitlines()
        if "[CODE_SYMBOL]" in line
    ]
    assert preview_lines == [
        "[CODE_SYMBOL] a.py:1-2 function a",
        "[CODE_SYMBOL] b.py:1-2 function b",
    ]


def test_no_code_index_disables_dry_run_symbol_extraction(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    source = src / "app.py"
    source.write_text("def app():\n    return 1\n")
    tree_calls = []
    _common_scan_mocks(monkeypatch, tmp_path, [source], src)
    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: tree_calls.append("called"))

    ingest_code.scan(**_scan_args(repo, code_index=False))

    assert tree_calls == []


def test_skill_docs_describe_treesitter_dry_run_preview() -> None:
    text = SKILL_PATH.read_text()

    assert "--dry-run" in text
    assert "--treesitter" in text
    assert "no memory writes" in text
    assert "no `.ingest-code.json` marker" in text
