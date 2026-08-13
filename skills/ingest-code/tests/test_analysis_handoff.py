"""Analysis handoff tests for ingest-code static code graph bundles."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import code_analysis_handoff
import code_memory_client
import environment_manifest
from code_graph_artifact import write_code_graph_bundle
from code_symbol_record import CodeSymbolRecord


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


def _fixture(repo: Path, *, bad_source: bool = False) -> dict[str, Any]:
    repo.mkdir(parents=True)
    source = repo / ("bad.py" if bad_source else "app.py")
    source.write_text("def broken(:\n" if bad_source else "def app():\n    return 1\n", encoding="utf-8")
    symbols = [] if bad_source else [_symbol(repo)]
    bundle = write_code_graph_bundle(
        codebase_root=repo,
        repo=repo.name,
        branch="main",
        commit="abc123",
        scan_roots=[repo],
        files=[source],
        symbols=symbols,
        edges=[],
    )
    env = environment_manifest.write_environment_manifest(
        repo / "artifacts" / "ingest-code" / "environment_manifest.json",
        skill_root=MODULE_DIR,
        source_root=repo,
        projection_mode="emit",
        argv=["ingest_code.py", "scan", str(repo), "--treesitter", "--projection-mode", "emit"],
        terminal_status="complete",
    )
    request_result = code_memory_client.write_code_projection_request(
        bundle_path=Path(bundle["path"]),
        scope="code",
        repo=repo.name,
        branch="main",
        root=str(repo.resolve()),
        source_commit="abc123",
        expected_counts={"files": 1, "symbols": len(symbols), "edges": 0},
        idempotency_key=f"fixture:{repo.name}",
        environment_manifest_digest=env["environment_manifest_digest"],
    )
    request = {
        "schema": "ingest-code.code_projection_request_artifact.v1",
        "projection_mode": "emit",
        "path": str(request_result.request_path),
        "sha256": request_result.request_digest,
        "submitted_bundle_digest": request_result.submitted_bundle_digest,
        "checksums_digest": request_result.checksums_digest,
        "status": "emitted_not_applied",
        "environment_manifest_digest": env["environment_manifest_digest"],
    }
    return {"repo": repo, "bundle": bundle, "env": env, "request": request}


def _write_emit_handoff(repo: Path, path: Path | None = None) -> dict[str, Any]:
    fixture = _fixture(repo)
    target = path or (repo / "artifacts" / "ingest-code" / "analysis_handoff.json")
    handoff_ref = code_analysis_handoff.write_analysis_handoff(
        target,
        code_graph_artifact=fixture["bundle"],
        environment_manifest=fixture["env"],
        projection_mode="emit",
        projection_request=fixture["request"],
    )
    return {"fixture": fixture, "handoff_ref": handoff_ref, "handoff_path": target}


def test_emit_handoff_has_stable_identity_and_no_generation_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    first = _write_emit_handoff(repo, tmp_path / "a" / "handoff.json")
    second_ref = code_analysis_handoff.write_analysis_handoff(
        tmp_path / "b" / "moved.json",
        code_graph_artifact=first["fixture"]["bundle"],
        environment_manifest=first["fixture"]["env"],
        projection_mode="emit",
        projection_request=first["fixture"]["request"],
    )

    handoff = json.loads(first["handoff_path"].read_text(encoding="utf-8"))
    assert handoff["schema"] == "ingest-code.analysis_handoff.v1"
    assert handoff["generation_provenance"]["generation_id"] is None
    assert handoff["generation_provenance"]["generation_id_reason"] == "projection_request_emit_only"
    assert first["handoff_ref"]["verification"]["status"] == "PASS"
    assert first["handoff_ref"]["handoff_identity_digest"] == second_ref["handoff_identity_digest"]


def test_apply_handoff_records_generation_and_receipt_digest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo")
    receipt = {
        "status": "applied",
        "submitted_bundle_digest": code_memory_client.code_graph_bundle_digest(Path(fixture["bundle"]["path"])),
        "checksums_digest": code_memory_client.code_graph_checksums_digest(Path(fixture["bundle"]["path"])),
        "generation": {"generation_id": "cg_fixture"},
    }
    ref = code_analysis_handoff.write_analysis_handoff(
        tmp_path / "repo" / "artifacts" / "ingest-code" / "analysis_handoff.json",
        code_graph_artifact=fixture["bundle"],
        environment_manifest=fixture["env"],
        projection_mode="apply",
        projection_request=fixture["request"],
        projection_receipt=receipt,
    )
    handoff = json.loads(Path(ref["path"]).read_text(encoding="utf-8"))

    assert ref["verification"]["status"] == "PASS"
    assert handoff["generation_provenance"]["generation_id"] == "cg_fixture"
    assert handoff["generation_provenance"]["apply_receipt_digest"].startswith("sha256:")


def test_incomplete_coverage_blocks_downstream_claim_classes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "repo", bad_source=True)
    handoff = code_analysis_handoff.build_analysis_handoff(
        code_graph_artifact=fixture["bundle"],
        environment_manifest=fixture["env"],
        projection_mode="emit",
        projection_request=fixture["request"],
    )

    assert handoff["coverage"]["coverage_complete"] is False
    assert "complete_callgraph" in handoff["coverage"]["blocked_claim_classes"]
    assert handoff["coverage"]["attempt_generation_readback"] == "blocked_by_incomplete_static_coverage"


def test_handoff_verifier_fails_closed_on_mutations(tmp_path: Path) -> None:
    artifact_case = _write_emit_handoff(tmp_path / "artifact-case")
    bundle_path = Path(artifact_case["fixture"]["bundle"]["path"])
    (bundle_path / "symbols.jsonl").write_text("", encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(artifact_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert any("symbols.jsonl" in error for error in receipt["errors"])

    source_case = _write_emit_handoff(tmp_path / "source-case")
    (source_case["fixture"]["repo"] / "app.py").write_text("def app():\n    return 2\n", encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(source_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert "source hash mismatch for app.py" in receipt["errors"]

    env_case = _write_emit_handoff(tmp_path / "env-case")
    env_path = Path(env_case["fixture"]["env"]["path"])
    env_path.write_text('{"schema":"changed"}\n', encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(env_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert "environment manifest sha mismatch" in receipt["errors"]

    request_case = _write_emit_handoff(tmp_path / "request-case")
    request_path = Path(request_case["fixture"]["request"]["path"])
    request_path.write_text('{"schema":"changed"}\n', encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(request_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert "projection request sha mismatch" in receipt["errors"]

    generation_case = _write_emit_handoff(tmp_path / "generation-case")
    handoff = json.loads(generation_case["handoff_path"].read_text(encoding="utf-8"))
    handoff["generation_provenance"]["generation_id"] = "forbidden"
    generation_case["handoff_path"].write_text(json.dumps(handoff, indent=2, sort_keys=True), encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(generation_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert "emit-only handoff must not claim a generation_id" in receipt["errors"]

    escape_case = _write_emit_handoff(tmp_path / "escape-case")
    handoff = json.loads(escape_case["handoff_path"].read_text(encoding="utf-8"))
    handoff["artifact_inventory"][0]["path"] = str(tmp_path / "outside.json")
    escape_case["handoff_path"].write_text(json.dumps(handoff, indent=2, sort_keys=True), encoding="utf-8")
    receipt = code_analysis_handoff.verify_analysis_handoff(escape_case["handoff_path"])
    assert receipt["status"] == "BLOCKED"
    assert any("path escapes" in error for error in receipt["errors"])
