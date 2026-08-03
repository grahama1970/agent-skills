from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _make_repo(path: Path) -> tuple[Path, Path]:
    (path / "src").mkdir(parents=True)
    a = path / "src" / "a.py"
    b = path / "src" / "b.py"
    a.write_text("def a():\n    return 1\n")
    b.write_text("def b():\n    return 2\n")
    _git(path, "init")
    _git(path, "config", "user.email", "ingest-code@example.invalid")
    _git(path, "config", "user.name", "ingest-code fixture")
    _git(path, "remote", "add", "origin", "https://github.com/example/freshness.git")
    _git(path, "add", "src/a.py", "src/b.py")
    _git(path, "commit", "-m", "fixture")
    return a, b


def _symbol(repo: Path, source: Path, name: str) -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="code",
        repo="github.com/example/freshness",
        repository_id="github.com/example/freshness",
        root=str(repo.resolve()),
        branch=ingest_code._current_branch(repo),
        commit=ingest_code._current_commit(repo),
        path=source.relative_to(repo).as_posix(),
        language="python",
        symbol_kind="function",
        symbol_name=name,
        qualified_name=name,
        start_line=1,
        end_line=2,
        code=source.read_text(),
        content_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
    )


def _outcome(paths: list[str]) -> dict:
    return {
        "root": ".",
        "status": "succeeded",
        "reason": "",
        "extractor": "treesitter",
        "extractor_version": "test",
        "command": ["test-treesitter"],
        "declared_languages": ["python"],
        "discovered_file_count": len(paths),
        "reported_file_count": len(paths),
        "reported_paths": paths,
        "stderr": "",
    }


def _write_full_bundle_marker(repo: Path, files: list[Path], symbols: list[CodeSymbolRecord]) -> dict:
    patterns = ["*.py"]
    artifact = code_graph_artifact.write_code_graph_bundle(
        codebase_root=repo,
        repo="github.com/example/freshness",
        branch=ingest_code._current_branch(repo),
        commit=ingest_code._current_commit(repo),
        scan_roots=ingest_code._extract_configured_scan_roots(repo),
        files=files,
        symbols=symbols,
        edges=[],
        extractor_outcomes=[_outcome([source.relative_to(repo).as_posix() for source in files])],
        repository_id_authoritative=True,
        repository_id_source="git_remote_origin",
        scan_config=ingest_code._code_graph_scan_config(
            repo,
            patterns=patterns,
            treesitter=True,
            code_index=True,
            dry_run=False,
            cwe_only=False,
        ),
    )
    ingest_code._write_ingest_marker(
        repo,
        files_scanned=len(files),
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=len(symbols),
        treesitter=True,
        scope="code",
        scan_roots=ingest_code._extract_configured_scan_roots(repo),
        completed_scan_roots=ingest_code._extract_configured_scan_roots(repo),
        local_code_symbols_written=len(symbols),
        code_graph_artifact=artifact,
        coverage_scope="full",
        reconciliation_eligible=artifact["reconciliation_eligible"],
    )
    return artifact


def test_full_marker_freshness_blocks_source_edit_delete_and_recovers_after_full_scan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    a, b = _make_repo(repo)
    _write_full_bundle_marker(repo, [a, b], [_symbol(repo, a, "a"), _symbol(repo, b, "b")])

    first = ingest_code.build_marker_status(repo)
    assert first["status"] == "fresh"
    assert first["coverage_scope"] == "full"
    assert first["reconciliation_eligible"] is True
    assert first["local_artifacts"]["code_graph_freshness"]["blocks_negative_claims"] is False

    a.write_text("def a():\n    return 10\n")
    b.unlink()
    stale = ingest_code.build_marker_status(repo)
    assert stale["status"] == "stale"
    assert stale["reconciliation_eligible"] is False
    assert "source_hash_mismatch" in stale["local_artifacts"]["code_graph_freshness"]["reasons"]
    assert "src/b.py" in stale["local_artifacts"]["code_graph_freshness"]["source_mismatches"]

    _git(repo, "add", "src/a.py")
    _git(repo, "rm", "src/b.py")
    _git(repo, "commit", "-m", "refresh")
    _write_full_bundle_marker(repo, [a], [_symbol(repo, a, "a")])
    refreshed = ingest_code.build_marker_status(repo)
    assert refreshed["status"] == "fresh"
    assert refreshed["reconciliation_eligible"] is True


def test_incremental_rescan_marker_cannot_refresh_prior_full_bundle(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    a, b = _make_repo(repo)
    _write_full_bundle_marker(repo, [a, b], [_symbol(repo, a, "a"), _symbol(repo, b, "b")])
    a.write_text("def a():\n    return 10\n")
    b.unlink()

    record = _symbol(repo, a, "a")
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.sock")
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_with_outcome",
        lambda scan_root, codebase_root, scope, discovered_files: ingest_code.TreeSitterScanResult(
            records=[record],
            outcome=_outcome(["src/a.py"]),
        ),
    )

    class FakeClient:
        def upsert_code_symbols(self, records):
            return SimpleNamespace(
                stored=len(records),
                attempted=len(records),
                errors=[],
                structured_upsert_stored=len(records),
                legacy_fallback_stored=0,
                structured_verified=len(records),
                failed=0,
                write_status="complete",
                structured_records=tuple(records),
                record_results=(),
            )

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", lambda: FakeClient())

    ingest_code.rescan(
        since=None,
        validate=False,
        treesitter=True,
        code_index=True,
        verify_embeddings=False,
        scope="code",
        codebase=[str(repo)],
    )

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "incremental"
    assert status["coverage_scope"] == "incremental"
    assert status["reconciliation_eligible"] is False
    assert status["local_artifacts"]["code_graph_freshness"]["status"] == "not_present"


def test_marker_binding_and_checksum_tampering_block_freshness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    a, b = _make_repo(repo)
    _write_full_bundle_marker(repo, [a, b], [_symbol(repo, a, "a"), _symbol(repo, b, "b")])

    marker_path = repo / ".ingest-code.json"
    marker = json.loads(marker_path.read_text())
    marker["local_artifacts"]["code_graph_binding"]["manifest_hash"] = "bad"
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")
    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "stale"
    assert "marker_manifest_hash_mismatch" in status["local_artifacts"]["code_graph_freshness"]["reasons"]

    _write_full_bundle_marker(repo, [a, b], [_symbol(repo, a, "a"), _symbol(repo, b, "b")])
    (repo / "artifacts" / "ingest-code" / "code-graph" / "coverage.json").write_text("{}\n")
    tampered = ingest_code.build_marker_status(repo)
    assert tampered["status"] == "stale"
    assert tampered["local_artifacts"]["code_graph_freshness"]["status"] == "invalid"


def test_configuration_change_after_indexing_blocks_freshness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    a, b = _make_repo(repo)
    _write_full_bundle_marker(repo, [a, b], [_symbol(repo, a, "a"), _symbol(repo, b, "b")])

    (repo / ".monitor-codebase.json").write_text(json.dumps({"include_dirs": ["src"]}))
    status = ingest_code.build_marker_status(repo)

    assert status["status"] == "stale"
    assert "configuration_digest_mismatch" in status["local_artifacts"]["code_graph_freshness"]["reasons"]
    assert status["reconciliation_eligible"] is False


def test_stale_local_code_symbols_jsonl_is_compatibility_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact = repo / "artifacts" / "ingest-code" / "code-symbols.jsonl"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"symbol_name": "old"}\n')

    ingest_code._write_ingest_marker(
        repo,
        files_scanned=1,
        knowledge_stored=0,
        cwe_stored=0,
        edges_stored=0,
        code_symbols_stored=0,
        treesitter=True,
        scope="code",
        local_code_symbols_artifact=artifact,
        local_code_symbols_written=1,
        coverage_scope="incremental",
        reconciliation_eligible=False,
    )

    status = ingest_code.build_marker_status(repo)

    assert status["status"] == "incremental"
    assert status["reconciliation_eligible"] is False
    assert status["local_artifacts"]["code_graph_freshness"]["status"] == "not_present"
    assert status["local_artifacts"]["code_symbols_jsonl_freshness"] == {
        "status": "compatibility_only",
        "authoritative_for_modification": False,
        "path": str(artifact),
        "line_count": 1,
    }


def test_scan_treesitter_no_code_index_emits_bundle_without_memory_upsert(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source, _ = _make_repo(repo)
    monkeypatch.setenv("INGEST_CODE_REPOSITORY_ID", "github.com/example/freshness")
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.sock")
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_with_outcome",
        lambda scan_root, codebase_root, scope, discovered_files: ingest_code.TreeSitterScanResult(
            records=[_symbol(repo, source, "a")],
            outcome=_outcome(["src/a.py"]),
        ),
    )

    class ForbiddenMemoryClient:
        def __init__(self) -> None:
            raise AssertionError("--no-code-index must not construct CodeMemoryClient")

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", ForbiddenMemoryClient)

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=True,
        code_index=False,
        dry_run=False,
        scope="code",
        batch_size=50,
    )

    status = ingest_code.build_marker_status(repo)
    bundle = repo / "artifacts" / "ingest-code" / "code-graph"
    assert (bundle / "manifest.json").exists()
    assert status["coverage_scope"] == "full"
    assert status["status"] == "fresh"
    assert status["code_index"]["enabled"] is False
    assert status["local_artifacts"]["code_graph_freshness"]["status"] == "fresh"
