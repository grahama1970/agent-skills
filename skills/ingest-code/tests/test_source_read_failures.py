"""Regression tests for source read failure handling."""

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


def _stderr_json(capsys) -> dict:
    stderr = capsys.readouterr().err.strip().splitlines()
    assert stderr
    return json.loads(stderr[-1])


def _tree_entry(path: Path, language: str = "python", name: str = "run") -> dict:
    return {
        "path": str(path.resolve()),
        "language": language,
        "symbols": [{
            "kind": "function",
            "name": name,
            "start_line": 1,
            "end_line": 1,
            "signature": f"def {name}(): ...",
        }],
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


def _fail_read_for(target: Path):
    resolved_target = target.resolve()

    def fail_read(filepath: Path) -> str:
        if filepath.resolve() == resolved_target:
            raise ingest_code.SourceReadError(filepath, "permission denied")
        return filepath.read_text(errors="ignore")

    return fail_read


def test_read_source_text_wraps_oserror_with_path(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n")
    original_tokenize_open = ingest_code.tokenize.open

    def fail_tokenize_open(filepath, *args, **kwargs):
        if Path(filepath) == source:
            raise PermissionError("permission denied")
        return original_tokenize_open(filepath, *args, **kwargs)

    monkeypatch.setattr(ingest_code.tokenize, "open", fail_tokenize_open)

    with pytest.raises(ingest_code.SourceReadError) as exc_info:
        ingest_code._read_source_text(source)

    assert exc_info.value.filepath == source
    assert "permission denied" in str(exc_info.value)


def test_extract_knowledge_does_not_convert_read_failure_to_empty_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "app.py"
    source.write_text("def app():\n    return 1\n")
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))

    with pytest.raises(ingest_code.SourceReadError):
        ingest_code.extract_knowledge(source)


def test_scan_knowledge_read_failure_exits_before_writes(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    calls = {
        "learn": [],
        "cwe": [],
        "edges": [],
        "treesitter": [],
        "marker": [],
        "discoverability": [],
    }
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: object())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: calls["cwe"].append(args) or {})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: calls["edges"].append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: calls["treesitter"].append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: calls["discoverability"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert all(not value for value in calls.values())
    error = _stderr_json(capsys)
    assert error["phase"] == "knowledge"
    assert error["file"] == str(source)


def test_scan_cwe_read_failure_exits_before_edges_and_marker(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    edge_calls = []
    treesitter_calls = []
    marker_calls = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: object())
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"error": "permission denied", "cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: edge_calls.append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: treesitter_calls.append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert edge_calls == []
    assert treesitter_calls == []
    assert marker_calls == []
    error = _stderr_json(capsys)
    assert error["phase"] == "cwe"
    assert error["file"] == str(source)


def test_rescan_read_failure_writes_no_pending_markers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    file_a = repo_a / "a.py"
    file_b = repo_b / "b.py"
    file_a.write_text("def a():\n    return 1\n")
    file_b.write_text("def b():\n    return 2\n")
    marker_calls = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(
        ingest_code,
        "_collect_files_or_exit",
        lambda path, *args, **kwargs: [file_a] if path == repo_a.resolve() else [file_b],
    )
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(file_b))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo_a, repo_b]))

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert not (repo_a / ".ingest-code.json").exists()
    assert not (repo_b / ".ingest-code.json").exists()


def test_import_read_failure_is_not_treated_as_zero_edges(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    dep = repo / "dep.py"
    source.write_text("import dep\n")
    dep.write_text("def dep():\n    return 1\n")
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))

    with pytest.raises(ingest_code.SourceReadError):
        ingest_code.extract_edges([source, dep], repo)


def test_python_syntax_error_remains_nonfatal(tmp_path: Path) -> None:
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n    pass\n")

    assert ingest_code.extract_python_imports(source) == []
    assert ingest_code.extract_knowledge(source) == []


def test_treesitter_python_context_read_failure_precedes_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def run():\n    return 1\n")
    memory_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source)])
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._store_treesitter_symbols_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )

    assert memory_calls == []


def test_treesitter_non_python_source_slice_failure_precedes_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "widget.ts"
    source.write_text("export function run() { return 1; }\n")
    memory_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, language="typescript")])
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))

    with pytest.raises(ingest_code.TreeSitterScanError):
        ingest_code._store_treesitter_symbols_for_directory(
            repo,
            repo,
            "code",
            allowed_files=frozenset({source.resolve()}),
        )

    assert memory_calls == []


def test_filtered_treesitter_result_is_not_read(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "skip.py"
    source.write_text("def skip():\n    return 1\n")
    read_calls = []
    _install_treesitter_output(monkeypatch, tmp_path, [_tree_entry(source, name="skip")])

    def record_read(filepath: Path) -> str:
        read_calls.append(filepath)
        return filepath.read_text(errors="ignore")

    monkeypatch.setattr(ingest_code, "_read_source_text", record_read)

    records = ingest_code._extract_treesitter_records_for_directory(
        repo,
        repo,
        "code",
        allowed_files=frozenset(),
    )

    assert records == ()
    assert read_calls == []


def test_dry_run_source_read_failure_writes_nothing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    marker_calls = []
    memory_calls = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: None)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_collect_files_or_exit", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "_read_source_text", _fail_read_for(source))
    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: memory_calls.append("memory"))
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: marker_calls.append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert exc_info.value.code == 1
    assert marker_calls == []
    assert memory_calls == []
    assert not (repo / ".ingest-code.json").exists()
    assert "\n{" not in capsys.readouterr().out


def test_skill_docs_describe_source_read_failure() -> None:
    text = SKILL_PATH.read_text()

    assert "read failure" in text
    assert "status 1" in text
    assert "completed marker" in text
