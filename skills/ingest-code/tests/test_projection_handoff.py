"""Projection handoff tests for ingest-code complete bundle application."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

for module_name in [
    "code_symbol_record",
    "code_edge_record",
    "code_graph_artifact",
    "code_memory_client",
    "incremental_index",
    "incremental_state",
    "ingest_code",
]:
    spec = importlib.util.spec_from_file_location(module_name, MODULE_DIR / f"{module_name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

import code_memory_client
import ingest_code
from code_symbol_record import CodeSymbolRecord


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class FakeProjectionHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, path: str, json: dict):
        self.requests.append({"path": path, "json": json})
        return self.response


def _symbol(repo: Path) -> CodeSymbolRecord:
    return CodeSymbolRecord(
        scope="code",
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
        code="def app():\n    return 1\n",
        content_hash="hash-app",
    )


def _write_bundle(repo: Path) -> dict[str, Any]:
    (repo / "app.py").write_text("def app():\n    return 1\n", encoding="utf-8")
    return ingest_code.write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[repo / "app.py"],
        symbols=[_symbol(repo)],
        edges=[],
    )


def test_client_submits_complete_bundle_and_requires_matching_receipt(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = _write_bundle(repo)
    bundle_path = Path(bundle["path"])
    submitted_digest = code_memory_client.code_graph_bundle_digest(bundle_path)
    checksums_digest = code_memory_client.code_graph_checksums_digest(bundle_path)
    fake = FakeProjectionHttpClient(
        FakeResponse(
            200,
            {
                "status": "applied",
                "submitted_bundle_digest": submitted_digest,
                "checksums_digest": checksums_digest,
                "generation": {"generation_id": "cg_fixture"},
            },
        )
    )
    client = code_memory_client.CodeMemoryClient()
    monkeypatch.setattr(client, "_client", lambda: fake)

    result = client.apply_code_projection_bundle(
        bundle_path=bundle_path,
        scope="code",
        repo=repo.name,
        branch="main",
        root=str(repo.resolve()),
        source_commit="abc123",
        expected_counts={"files": 1, "symbols": 1, "edges": 1},
        idempotency_key="idem-fixture",
    )

    assert result.errors == []
    assert result.stored == 1
    assert fake.requests[0]["path"] == "/code/projection/apply"
    request = fake.requests[0]["json"]
    assert request["submitted_bundle_digest"] == submitted_digest
    assert request["checksums_digest"] == checksums_digest
    assert request["idempotency_key"] == "idem-fixture"


def test_client_rejects_receipt_digest_mismatch(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = _write_bundle(repo)
    bundle_path = Path(bundle["path"])
    fake = FakeProjectionHttpClient(
        FakeResponse(
            200,
            {
                "status": "applied",
                "submitted_bundle_digest": "sha256:not-this-bundle",
                "checksums_digest": code_memory_client.code_graph_checksums_digest(bundle_path),
                "generation": {"generation_id": "cg_fixture"},
            },
        )
    )
    client = code_memory_client.CodeMemoryClient()
    monkeypatch.setattr(client, "_client", lambda: fake)

    result = client.apply_code_projection_bundle(
        bundle_path=bundle_path,
        scope="code",
        repo=repo.name,
        branch="main",
        root=str(repo.resolve()),
        source_commit="abc123",
        expected_counts={"files": 1, "symbols": 1, "edges": 1},
        idempotency_key="idem-fixture",
    )

    assert result.stored == 0
    assert "submitted_bundle_digest mismatch" in result.errors[0]


def test_scan_uses_projection_apply_instead_of_legacy_symbol_upsert(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: Path("/tmp/memory.sock"))
    monkeypatch.setattr(ingest_code, "_current_branch", lambda path: "main")
    monkeypatch.setattr(ingest_code, "_current_commit", lambda path: "abc123")
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_for_file",
        lambda filepath, codebase_root, scope: [_symbol(repo)],
    )

    class FakeClient:
        applied: list[dict[str, Any]] = []

        def apply_code_projection_bundle(self, **kwargs):
            self.applied.append(kwargs)
            bundle_path = Path(kwargs["bundle_path"])
            submitted_digest = code_memory_client.code_graph_bundle_digest(bundle_path)
            return code_memory_client.CodeProjectionApplyResult(
                stored=1,
                attempted=1,
                errors=[],
                receipt={
                    "status": "applied",
                    "submitted_bundle_digest": submitted_digest,
                    "checksums_digest": code_memory_client.code_graph_checksums_digest(bundle_path),
                    "generation": {"generation_id": "cg_scan"},
                },
                request={},
                submitted_bundle_digest=submitted_digest,
                checksums_digest=code_memory_client.code_graph_checksums_digest(bundle_path),
            )

        def upsert_code_symbols(self, *_args, **_kwargs):
            raise AssertionError("legacy per-symbol upsert must not run by default")

        def prune_code_symbols(self, *_args, **_kwargs):
            raise AssertionError("legacy per-symbol prune must not run by default")

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", FakeClient)

    ingest_code.scan(
        path=repo,
        glob=[],
        cwe_only=False,
        validate=False,
        treesitter=True,
        code_index=True,
        compat_symbol_upsert=False,
        dry_run=False,
        scope="code",
        batch_size=50,
    )

    marker = json.loads((repo / ".ingest-code.json").read_text(encoding="utf-8"))
    assert marker["code_index"]["projection_generation_id"] == "cg_scan"
    assert marker["local_artifacts"]["code_projection_receipt"]["generation"]["generation_id"] == "cg_scan"


def test_scan_fails_closed_when_projection_apply_is_rejected(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: Path("/tmp/memory.sock"))
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_for_file",
        lambda filepath, codebase_root, scope: [_symbol(repo)],
    )

    class RejectingClient:
        def apply_code_projection_bundle(self, **_kwargs):
            return code_memory_client.CodeProjectionApplyResult(
                stored=0,
                attempted=1,
                errors=["HTTP 422: rejected"],
                receipt=None,
                request={},
                submitted_bundle_digest="sha256:fixture",
                checksums_digest="sha256:fixture",
            )

        def upsert_code_symbols(self, *_args, **_kwargs):
            raise AssertionError("legacy per-symbol upsert must not run after projection rejection")

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", RejectingClient)

    with pytest.raises(SystemExit):
        ingest_code.scan(
            path=repo,
            glob=[],
            cwe_only=False,
            validate=False,
            treesitter=True,
            code_index=True,
            compat_symbol_upsert=False,
            dry_run=False,
            scope="code",
            batch_size=50,
        )

    assert not (repo / ".ingest-code.json").exists()


def test_rescan_applies_complete_projection_bundle(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: Path("/tmp/memory.sock"))
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "_store_lessons_threaded", lambda _script, items, _scope, *, label: len(items))
    monkeypatch.setattr(ingest_code, "_current_branch", lambda path: "main")
    monkeypatch.setattr(ingest_code, "_current_commit", lambda path: "abc123")
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: [repo])
    monkeypatch.setattr(
        ingest_code,
        "_scan_treesitter_symbol_records_for_directory",
        lambda directory, codebase_root, scope: [_symbol(repo)],
    )

    class FakeClient:
        def apply_code_projection_bundle(self, **kwargs):
            bundle_path = Path(kwargs["bundle_path"])
            submitted_digest = code_memory_client.code_graph_bundle_digest(bundle_path)
            return code_memory_client.CodeProjectionApplyResult(
                stored=1,
                attempted=1,
                errors=[],
                receipt={
                    "status": "applied",
                    "submitted_bundle_digest": submitted_digest,
                    "checksums_digest": code_memory_client.code_graph_checksums_digest(bundle_path),
                    "generation": {"generation_id": "cg_rescan"},
                },
                request={},
                submitted_bundle_digest=submitted_digest,
                checksums_digest=code_memory_client.code_graph_checksums_digest(bundle_path),
            )

        def upsert_code_symbols(self, *_args, **_kwargs):
            raise AssertionError("rescan must not use legacy per-symbol upsert")

    monkeypatch.setattr(ingest_code, "CodeMemoryClient", FakeClient)

    ingest_code.rescan(
        since=None,
        validate=False,
        treesitter=True,
        code_index=True,
        verify_embeddings=False,
        scope="code",
        codebase=[str(repo)],
    )

    marker = json.loads((repo / ".ingest-code.json").read_text(encoding="utf-8"))
    assert marker["code_index"]["projection_generation_id"] == "cg_rescan"
