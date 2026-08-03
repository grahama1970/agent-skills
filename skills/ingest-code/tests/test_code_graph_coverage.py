from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

artifact_spec = importlib.util.spec_from_file_location("code_graph_artifact", MODULE_DIR / "code_graph_artifact.py")
assert artifact_spec and artifact_spec.loader
code_graph_artifact = importlib.util.module_from_spec(artifact_spec)
sys.modules[artifact_spec.name] = code_graph_artifact
artifact_spec.loader.exec_module(code_graph_artifact)

ingest_spec = importlib.util.spec_from_file_location("ingest_code", MODULE_DIR / "ingest_code.py")
assert ingest_spec and ingest_spec.loader
ingest_code = importlib.util.module_from_spec(ingest_spec)
sys.modules[ingest_spec.name] = ingest_code
ingest_spec.loader.exec_module(ingest_code)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _coverage(repo: Path) -> dict:
    return json.loads((repo / "artifacts" / "ingest-code" / "code-graph" / "coverage.json").read_text())


def _diagnostics(repo: Path) -> list[dict]:
    return _jsonl(repo / "artifacts" / "ingest-code" / "code-graph" / "diagnostics.jsonl")


def _files(repo: Path) -> list[dict]:
    return _jsonl(repo / "artifacts" / "ingest-code" / "code-graph" / "files.jsonl")


def _outcome(status: str, reason: str, reported_paths: list[str] | None = None) -> dict:
    return {
        "root": ".",
        "status": status,
        "reason": reason,
        "extractor": "treesitter",
        "extractor_version": "test",
        "command": ["test-treesitter"],
        "declared_languages": ["python", "typescript"],
        "discovered_file_count": 1,
        "reported_file_count": len(reported_paths or []),
        "reported_paths": reported_paths or [],
        "stderr": "",
    }


@pytest.mark.parametrize(
    ("status", "reason", "diagnostic_reason"),
    [
        ("unavailable", "treesitter_skill_not_found", "extractor_unavailable"),
        ("timed_out", "treesitter_scan_timeout", "extractor_timed_out"),
        ("failed", "treesitter_exit_2", "extractor_failed"),
        ("invalid_output", "malformed_json", "extractor_invalid_output"),
        ("partial", "unexpected_empty_output", "extractor_partial"),
    ],
)
def test_extractor_failures_make_coverage_fail_closed(
    tmp_path: Path,
    status: str,
    reason: str,
    diagnostic_reason: str,
) -> None:
    repo = tmp_path / status
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")

    result = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[],
        edges=[],
        extractor_outcomes=[_outcome(status, reason)],
    )

    coverage = _coverage(repo)
    assert result["complete"] is False
    assert result["reconciliation_eligible"] is False
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True
    assert coverage["reconciliation_eligible"] is False
    assert coverage["extractor_outcomes"][0]["status"] == status
    assert _files(repo)[0]["status"] == "failed"
    assert {item["reason"] for item in _diagnostics(repo)} == {diagnostic_reason}


def test_successful_empty_treesitter_output_is_partial_for_non_empty_root(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    run_sh = repo / "treesitter-run.sh"
    run_sh.write_text("#!/usr/bin/env bash\nprintf '[]\\n'\n")
    run_sh.chmod(0o755)

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    result = ingest_code._scan_treesitter_symbol_records_with_outcome(
        repo,
        repo,
        "code",
        discovered_files=[source],
    )

    assert result.records == []
    assert result.outcome["status"] == "partial"
    assert result.outcome["reason"] == "unexpected_empty_output"


def test_malformed_treesitter_output_is_invalid_output(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    run_sh = repo / "treesitter-run.sh"
    run_sh.write_text("#!/usr/bin/env bash\nprintf '[not json]\\n'\n")
    run_sh.chmod(0o755)

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    result = ingest_code._scan_treesitter_symbol_records_with_outcome(
        repo,
        repo,
        "code",
        discovered_files=[source],
    )

    assert result.records == []
    assert result.outcome["status"] == "invalid_output"
    assert result.outcome["reason"].startswith("malformed_json:")


def test_nonzero_treesitter_exit_is_failed(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    run_sh = repo / "treesitter-run.sh"
    run_sh.write_text("#!/usr/bin/env bash\nprintf 'boom' >&2\nexit 7\n")
    run_sh.chmod(0o755)

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    result = ingest_code._scan_treesitter_symbol_records_with_outcome(
        repo,
        repo,
        "code",
        discovered_files=[source],
    )

    assert result.records == []
    assert result.outcome["status"] == "failed"
    assert result.outcome["reason"] == "treesitter_exit_7"
    assert result.outcome["stderr"] == "boom"


def test_timeout_and_missing_treesitter_are_distinct(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: None)
    missing = ingest_code._scan_treesitter_symbol_records_with_outcome(repo, repo, "code", [source])
    assert missing.outcome["status"] == "unavailable"

    run_sh = repo / "treesitter-run.sh"
    run_sh.write_text("#!/usr/bin/env bash\nprintf 'unused\\n'\n")
    run_sh.chmod(0o755)

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    monkeypatch.setattr(ingest_code.subprocess, "run", timeout_run)
    timed_out = ingest_code._scan_treesitter_symbol_records_with_outcome(repo, repo, "code", [source])
    assert timed_out.outcome["status"] == "timed_out"


def test_treesitter_output_is_limited_to_discovered_files(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    included = repo / "app.py"
    included.write_text("def app():\n    return 1\n")
    ignored = repo / "ignored.py"
    ignored.write_text("def ignored():\n    return 0\n")
    run_sh = repo / "treesitter-run.sh"
    payload = [
        {
            "path": str(included),
            "symbols": [{"kind": "function", "name": "app", "start_line": 1, "end_line": 2}],
        },
        {
            "path": str(ignored),
            "symbols": [{"kind": "function", "name": "ignored", "start_line": 1, "end_line": 2}],
        },
    ]
    run_sh.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' '{json.dumps(payload)}'\n"
    )
    run_sh.chmod(0o755)

    monkeypatch.setattr(ingest_code, "find_treesitter_skill", lambda: run_sh)
    result = ingest_code._scan_treesitter_symbol_records_with_outcome(
        repo,
        repo,
        "code",
        discovered_files=[included],
    )

    assert [record.symbol_name for record in result.records] == ["app"]
    assert result.outcome["status"] == "succeeded"
    assert result.outcome["reported_paths"] == ["app.py"]


def test_python_syntax_failure_has_parse_diagnostic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    broken = repo / "broken.py"
    broken.write_text("def broken(:\n")

    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[broken],
        symbols=[],
        edges=[],
        extractor_outcomes=[_outcome("succeeded", "", ["broken.py"])],
    )

    coverage = _coverage(repo)
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True
    assert _files(repo)[0]["status"] == "failed"
    assert _diagnostics(repo)[0]["reason"] == "parse_error"


def test_symbols_for_failed_files_are_not_emitted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    broken = repo / "broken.py"
    broken.write_text("def broken(:\n")
    symbol = ingest_code.CodeSymbolRecord(
        scope="code",
        repo=repo.name,
        root=str(repo),
        branch="main",
        commit="abc123",
        path="broken.py",
        language="python",
        symbol_kind="function",
        symbol_name="broken",
        qualified_name="broken",
        start_line=1,
        end_line=1,
        code="def broken(:",
        content_hash="hash-broken",
    )

    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[broken],
        symbols=[symbol],
        edges=[],
        extractor_outcomes=[_outcome("succeeded", "", ["broken.py"])],
    )

    assert _files(repo)[0]["status"] == "failed"
    symbols = _jsonl(repo / "artifacts" / "ingest-code" / "code-graph" / "symbols.jsonl")
    assert symbols == []


def test_non_python_file_requires_parser_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "view.ts"
    source.write_text("export function view() { return 1; }\n")

    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[],
        edges=[],
        extractor_outcomes=[_outcome("succeeded", "", [])],
    )

    coverage = _coverage(repo)
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True
    assert _files(repo)[0]["status"] == "failed"
    assert _diagnostics(repo)[0]["reason"] == "parser_no_report"


def test_read_hash_failures_are_explicit(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")

    monkeypatch.setattr(
        code_graph_artifact,
        "_read_file_bytes",
        lambda path, max_source_bytes: (None, "read_failed:denied"),
    )
    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=[],
        edges=[],
        extractor_outcomes=[_outcome("succeeded", "", ["app.py"])],
    )

    record = _files(repo)[0]
    coverage = _coverage(repo)
    assert record["status"] == "unreadable"
    assert record["source_hash"] == ""
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True
    assert _diagnostics(repo)[0]["reason"] == "unreadable"


def test_ignored_binary_unsupported_and_too_large_statuses_are_distinct(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.py\n")
    ignored = repo / "ignored.py"
    ignored.write_text("def ignored():\n    return 0\n")
    binary = repo / "binary.py"
    binary.write_bytes(b"\0binary")
    too_large = repo / "huge.py"
    too_large.write_text("x = '" + ("a" * 80) + "'\n")
    unsupported = repo / "notes.txt"
    unsupported.write_text("not configured source\n")
    _git(repo, "init")

    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[binary, too_large, unsupported],
        symbols=[],
        edges=[],
        extractor_outcomes=[_outcome("succeeded", "", ["binary.py", "huge.py", "notes.txt"])],
        max_source_bytes=32,
    )

    statuses = {record["path"]: record["status"] for record in _files(repo)}
    assert statuses["ignored.py"] == "ignored"
    assert statuses["binary.py"] == "binary"
    assert statuses["huge.py"] == "too_large"
    assert statuses["notes.txt"] == "unsupported"
    coverage = _coverage(repo)
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True


def test_scoped_root_with_gitignored_file_is_accounted_for(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    (repo / ".gitignore").write_text("src/ignored.py\n")
    good = src / "good.py"
    good.write_text("def good():\n    return 1\n")
    ignored = src / "ignored.py"
    ignored.write_text("def ignored():\n    return 0\n")
    _git(repo, "init")

    code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[src],
        files=[good],
        symbols=[],
        edges=[],
        extractor_outcomes=[{
            **_outcome("succeeded", "", ["src/good.py"]),
            "root": "src",
            "discovered_file_count": 1,
        }],
    )

    statuses = {record["path"]: record["status"] for record in _files(repo)}
    assert statuses["src/good.py"] == "parsed"
    assert statuses["src/ignored.py"] == "ignored"
    coverage = _coverage(repo)
    assert coverage["complete"] is True
    assert coverage["fail_closed"] is False
    assert coverage["counts"]["files_ignored"] == 1
