from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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

from code_symbol_record import CodeSymbolRecord


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _symbol(repo: Path) -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="code",
        repo=repo.name,
        root=str(repo),
        branch="main",
        commit="abc123",
        path="pkg/good.py",
        language="python",
        symbol_kind="function",
        symbol_name="answer",
        qualified_name="answer",
        start_line=1,
        end_line=2,
        signature="def answer(): ...",
        code="def answer():\n    return 42",
        content_hash="hash-good",
    )


def test_code_graph_bundle_is_deterministic_and_self_describing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "good.py").write_text("def answer():\n    return 42\n")
    (repo / "pkg" / "consumer.py").write_text("from pkg.good import answer\n")
    (repo / "pkg" / "broken.py").write_text("def broken(:\n")
    (repo / ".gitignore").write_text("ignored.py\n")
    (repo / "ignored.py").write_text("def ignored():\n    return 0\n")
    _git(repo, "init")

    files = [
        repo / "pkg" / "good.py",
        repo / "pkg" / "consumer.py",
        repo / "pkg" / "broken.py",
    ]
    edge = {
        "from_file": str((repo / "pkg" / "consumer.py").resolve()),
        "to_file": str((repo / "pkg" / "good.py").resolve()),
        "edge_type": "depends_on",
        "module": "pkg.good",
        "names": ["answer"],
    }

    first = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=files,
        symbols=[_symbol(repo)],
        edges=[edge],
    )
    bundle = Path(first["path"])
    expected = {
        "manifest.json",
        "files.jsonl",
        "symbols.jsonl",
        "edges.jsonl",
        "diagnostics.jsonl",
        "coverage.json",
        "checksums.json",
    }
    assert {path.name for path in bundle.iterdir()} == expected

    before = {name: (bundle / name).read_bytes() for name in expected}
    second = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=list(reversed(files)),
        symbols=[_symbol(repo)],
        edges=[edge],
    )
    assert second["path"] == first["path"]
    after = {name: (bundle / name).read_bytes() for name in expected}
    assert after == before

    checksums = json.loads((bundle / "checksums.json").read_text())
    for filename, digest in checksums["files"].items():
        assert hashlib.sha256((bundle / filename).read_bytes()).hexdigest() == digest

    file_records = _jsonl(bundle / "files.jsonl")
    statuses = {record["path"]: record["status"] for record in file_records}
    assert statuses["pkg/good.py"] == "parsed"
    assert statuses["pkg/broken.py"] == "failed"
    assert statuses["ignored.py"] == "ignored"
    assert all(not record["path"].startswith("/") for record in file_records)

    diagnostics = _jsonl(bundle / "diagnostics.jsonl")
    reasons = {item["path"]: item["reason"] for item in diagnostics}
    assert reasons["pkg/broken.py"] == "parse_error"
    assert reasons["ignored.py"] == "gitignore"

    coverage = json.loads((bundle / "coverage.json").read_text())
    assert coverage["complete"] is False
    assert coverage["fail_closed"] is True
    assert coverage["counts"]["files_failed"] == 1
    assert coverage["counts"]["files_ignored"] == 1

    symbols = _jsonl(bundle / "symbols.jsonl")
    assert symbols[0]["symbol_id"] == _symbol(repo).symbol_id
    assert symbols[0]["symbol_version_id"] == _symbol(repo).symbol_version_id
    assert symbols[0]["legacy_key"] == _symbol(repo).legacy_key

    edges = _jsonl(bundle / "edges.jsonl")
    assert edges[0]["edge_type"] == "IMPORTS"
    assert edges[0]["status"] == "resolved"
    assert edges[0]["from_path"] == "pkg/consumer.py"
    assert edges[0]["to_path"] == "pkg/good.py"


def test_scan_dry_run_emits_code_graph_without_memory_upsert(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")

    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_with_outcome",
        lambda directory, codebase_root, scope, discovered_files: ingest_code.TreeSitterScanResult(
            records=[
                CodeSymbolRecord(
                    scope=scope,
                    repo=repo.name,
                    root=str(repo),
                    branch="main",
                    commit="abc123",
                    path="app.py",
                    language="python",
                    symbol_kind="function",
                    symbol_name="app",
                    qualified_name="app",
                    start_line=1,
                    end_line=2,
                    code=source.read_text(),
                    content_hash="hash-app",
                )
            ],
            outcome={
                "root": ".",
                "status": "succeeded",
                "reason": "",
                "extractor": "treesitter",
                "extractor_version": "test",
                "command": ["test-treesitter"],
                "declared_languages": ["python"],
                "discovered_file_count": 1,
                "reported_file_count": 1,
                "reported_paths": ["app.py"],
                "stderr": "",
            },
        ),
    )

    class ForbiddenMemoryClient:
        def __init__(self) -> None:
            raise AssertionError("dry-run must not construct CodeMemoryClient")

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", ForbiddenMemoryClient)

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=True,
        code_index=True,
        dry_run=True,
        scope="code",
        batch_size=50,
    )

    bundle = repo / "artifacts" / "ingest-code" / "code-graph"
    assert (bundle / "manifest.json").exists()
    assert (bundle / "coverage.json").exists()
    assert _jsonl(bundle / "symbols.jsonl")[0]["symbol_name"] == "app"
    assert not (repo / ".ingest-code.json").exists()
