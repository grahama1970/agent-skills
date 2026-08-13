"""Emit and verify ingest-code analysis handoff artifacts.

The handoff binds deterministic static code-graph artifacts to optional
downstream analysis without changing canonical code-graph identity. Verification
re-reads referenced artifacts, recomputes hashes and counts, and fails closed on
path escapes, stale source hashes, unsupported media, or projection provenance
drift.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_memory_client import (
    CODE_GRAPH_ARTIFACTS,
    code_graph_bundle_digest,
    code_graph_checksums_digest,
)


ANALYSIS_HANDOFF_SCHEMA = "ingest-code.analysis_handoff.v1"
ANALYSIS_HANDOFF_VERIFICATION_SCHEMA = "ingest-code.analysis_handoff_verification.v1"
MAX_REFERENCED_ARTIFACT_BYTES = 64 * 1024 * 1024
STATIC_ARTIFACT_MEDIA = {
    "manifest.json": "application/json",
    "files.jsonl": "application/x-jsonlines",
    "symbols.jsonl": "application/x-jsonlines",
    "edges.jsonl": "application/x-jsonlines",
    "debug_invocations.jsonl": "application/x-jsonlines",
    "diagnostics.jsonl": "application/x-jsonlines",
    "coverage.json": "application/json",
    "checksums.json": "application/json",
}
BLOCKED_CLAIM_CLASSES = (
    "repository_wide_absence",
    "exhaustive_impact",
    "complete_callgraph",
    "runtime_proof",
    "semantic_correctness",
)


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_digest(payload: dict[str, Any]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl_count(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _artifact_ref(bundle_path: Path, name: str) -> dict[str, Any]:
    path = (bundle_path / name).resolve()
    media_type = STATIC_ARTIFACT_MEDIA[name]
    ref: dict[str, Any] = {
        "name": name,
        "path": str(path),
        "relative_path": name,
        "media_type": media_type,
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "max_bytes": MAX_REFERENCED_ARTIFACT_BYTES,
        "content_role": "canonical_static_code_graph",
    }
    if media_type == "application/x-jsonlines":
        ref["record_count"] = _jsonl_count(path)
    else:
        payload = _load_json(path)
        ref["schema_version"] = payload.get("schema") or payload.get("schema_version")
    if name == "debug_invocations.jsonl":
        ref["content_role"] = "static_runtime_verification_candidates"
    return ref


def _external_artifact_ref(path_text: str | None, *, role: str) -> dict[str, Any] | None:
    if not path_text:
        return None
    path = Path(path_text).resolve()
    return {
        "path": str(path),
        "relative_path": path.name,
        "media_type": "application/json",
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "max_bytes": MAX_REFERENCED_ARTIFACT_BYTES,
        "content_role": role,
    }


def _source_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "repo": manifest.get("repo"),
        "root": manifest.get("root"),
        "branch": manifest.get("branch"),
        "commit": manifest.get("commit"),
        "tracked_worktree_dirty": bool(manifest.get("tracked_worktree_dirty")),
        "scan_roots": list(manifest.get("scan_roots") or []),
    }


def _claim_policy(coverage: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    complete = bool(coverage.get("complete")) and not bool(coverage.get("fail_closed"))
    return {
        "coverage_complete": complete,
        "reconciliation_eligible": complete and bool(manifest.get("coverage_complete")),
        "attempt_generation_readback": "permitted_not_asserted" if complete else "blocked_by_incomplete_static_coverage",
        "blocked_claim_classes": [] if complete else list(BLOCKED_CLAIM_CLASSES),
        "always_blocked_claim_classes": [
            "runtime_proof_without_debugger_receipt",
            "kernel_execution_success",
            "model_summary_truth",
            "host_call_effect_acceptance",
        ],
    }


def _generation_provenance(
    *,
    projection_mode: str,
    projection_request: dict[str, Any] | None,
    projection_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    generation = (projection_receipt or {}).get("generation") or {}
    generation_id = generation.get("generation_id")
    if projection_receipt and generation_id:
        reason = "memory_gmo_apply_receipt_verified"
    elif projection_mode == "emit":
        reason = "projection_request_emit_only"
    elif projection_mode == "none":
        reason = "projection_not_requested"
    else:
        reason = "projection_receipt_missing_generation"
    return {
        "projection_mode": projection_mode,
        "generation_id": generation_id if projection_receipt else None,
        "generation_id_reason": reason,
        "projection_request_digest": projection_request.get("sha256") if projection_request else None,
        "projection_request_status": projection_request.get("status") if projection_request else None,
        "apply_receipt_digest": _json_digest(projection_receipt) if projection_receipt else None,
        "apply_receipt_status": projection_receipt.get("status") if projection_receipt else None,
    }


def _identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": payload["schema"],
        "source_identity": payload["source_identity"],
        "code_graph_identity": payload["code_graph_identity"],
        "environment_identity": payload["environment_identity"],
        "generation_provenance": payload["generation_provenance"],
        "coverage": payload["coverage"],
        "artifact_inventory": [
            {
                key: value
                for key, value in artifact.items()
                if key not in {"path", "relative_path"}
            }
            for artifact in payload["artifact_inventory"]
        ],
        "analysis_profiles": payload["analysis_profiles"],
        "proof_scope": payload["proof_scope"],
        "non_claims": payload["non_claims"],
    }


def build_analysis_handoff(
    *,
    code_graph_artifact: dict[str, Any],
    environment_manifest: dict[str, Any] | None,
    projection_mode: str,
    projection_request: dict[str, Any] | None = None,
    projection_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one versioned analysis handoff over an existing code-graph bundle."""
    bundle_path = Path(str(code_graph_artifact["path"])).resolve()
    manifest = _load_json(bundle_path / "manifest.json")
    coverage = _load_json(bundle_path / "coverage.json")
    static_refs = [_artifact_ref(bundle_path, name) for name in CODE_GRAPH_ARTIFACTS]
    env_ref = _external_artifact_ref(
        (environment_manifest or {}).get("path"),
        role="environment_identity_manifest",
    )
    projection_request_ref = _external_artifact_ref(
        (projection_request or {}).get("path"),
        role="candidate_projection_request",
    )
    claim_policy = _claim_policy(coverage, manifest)
    payload: dict[str, Any] = {
        "schema": ANALYSIS_HANDOFF_SCHEMA,
        "skill": "ingest-code",
        "emitted_at": datetime.now(UTC).isoformat(),
        "source_identity": _source_identity(manifest),
        "code_graph_identity": {
            "schema_version": manifest.get("schema") or manifest.get("schema_version"),
            "bundle_path": str(bundle_path),
            "bundle_path_role": "transport_metadata_only",
            "canonical_bundle_digest": code_graph_bundle_digest(bundle_path),
            "checksums_digest": code_graph_checksums_digest(bundle_path),
            "environment_manifest_digest": manifest.get("environment_manifest_digest"),
            "canonical_identity_excludes": [
                "analysis_handoff_path",
                "analysis_handoff_emitted_at",
                "kernel_executions",
                "model_summaries",
                "host_call_receipts",
                "derived_claims",
                "projection_apply_generation_provenance",
            ],
        },
        "environment_identity": {
            "manifest": env_ref,
            "environment_manifest_digest": (environment_manifest or {}).get("environment_manifest_digest"),
        },
        "generation_provenance": _generation_provenance(
            projection_mode=projection_mode,
            projection_request=projection_request,
            projection_receipt=projection_receipt,
        ),
        "coverage": {
            "schema_version": coverage.get("schema") or coverage.get("schema_version"),
            "counts": coverage.get("counts") or {},
            **claim_policy,
        },
        "artifact_inventory": static_refs,
        "projection_artifacts": {
            "request": projection_request_ref,
            "apply_receipt_digest": _json_digest(projection_receipt) if projection_receipt else None,
        },
        "analysis_profiles": [
            {"name": "source-span-review", "max_source_bytes": 200_000, "requires_runtime": False},
            {"name": "symbol-neighborhood", "max_symbols": 200, "requires_runtime": False},
            {"name": "debug-candidate-review", "max_candidates": 100, "requires_runtime": False},
        ],
        "proof_scope": "deterministic_static_code_graph_analysis_handoff",
        "non_claims": [
            "analysis_handoff_does_not_change_canonical_code_graph_identity",
            "analysis_handoff_is_not_memory_projection_activation",
            "analysis_handoff_is_not_runtime_proof",
            "analysis_handoff_is_not_kernel_execution",
            "analysis_handoff_is_not_model_summary_or_derived_claim",
            "static_debug_candidates_require_later_tau_debugger_verification",
        ],
    }
    payload["handoff_identity_digest"] = _json_digest(_identity_payload(payload))
    return payload


def write_analysis_handoff(
    path: Path,
    *,
    code_graph_artifact: dict[str, Any],
    environment_manifest: dict[str, Any] | None,
    projection_mode: str,
    projection_request: dict[str, Any] | None = None,
    projection_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write an analysis handoff and return its marker-friendly reference."""
    handoff = build_analysis_handoff(
        code_graph_artifact=code_graph_artifact,
        environment_manifest=environment_manifest,
        projection_mode=projection_mode,
        projection_request=projection_request,
        projection_receipt=projection_receipt,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verification = verify_analysis_handoff(path)
    if verification["status"] != "PASS":
        raise ValueError(f"analysis handoff verification failed: {verification['errors'][:3]}")
    return {
        "schema": "ingest-code.analysis_handoff_artifact.v1",
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "handoff_identity_digest": handoff["handoff_identity_digest"],
        "verification": verification,
    }


def _require_under(path: Path, root: Path, errors: list[str], label: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        errors.append(f"{label} path escapes expected root: {path}")


def _verify_source_hashes(bundle_path: Path, manifest: dict[str, Any], errors: list[str]) -> None:
    root_text = manifest.get("root")
    if not root_text:
        errors.append("manifest missing root for source freshness verification")
        return
    root = Path(str(root_text)).resolve()
    for line_number, line in enumerate((bundle_path / "files.jsonl").read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        source_hash = record.get("source_hash")
        rel_path = record.get("path")
        status = record.get("status")
        if status in {"ignored"}:
            continue
        source_path = (root / str(rel_path)).resolve()
        _require_under(source_path, root, errors, f"source:{line_number}")
        if not source_path.exists():
            errors.append(f"source file missing for {rel_path}")
            continue
        actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_hash and actual != source_hash:
            errors.append(f"source hash mismatch for {rel_path}")


def verify_analysis_handoff(path: Path) -> dict[str, Any]:
    """Verify an emitted analysis handoff by reading every referenced artifact."""
    errors: list[str] = []
    handoff_path = path.resolve()
    try:
        handoff = _load_json(handoff_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": ANALYSIS_HANDOFF_VERIFICATION_SCHEMA,
            "status": "BLOCKED",
            "errors": [f"handoff unreadable: {exc}"],
        }

    if handoff.get("schema") != ANALYSIS_HANDOFF_SCHEMA:
        errors.append(f"unsupported schema: {handoff.get('schema')}")

    bundle_path = Path(str((handoff.get("code_graph_identity") or {}).get("bundle_path", ""))).resolve()
    if not bundle_path.is_dir():
        errors.append(f"bundle path missing: {bundle_path}")
    artifact_refs = handoff.get("artifact_inventory") or []
    names = [item.get("name") for item in artifact_refs]
    if tuple(names) != CODE_GRAPH_ARTIFACTS:
        errors.append(f"artifact inventory must exactly match {CODE_GRAPH_ARTIFACTS}; got {names}")

    recomputed_counts: dict[str, int] = {}
    for artifact in artifact_refs:
        name = str(artifact.get("name", ""))
        media_type = artifact.get("media_type")
        if name not in STATIC_ARTIFACT_MEDIA:
            errors.append(f"unknown artifact: {name}")
            continue
        if media_type != STATIC_ARTIFACT_MEDIA[name]:
            errors.append(f"unsupported media for {name}: {media_type}")
        artifact_path = Path(str(artifact.get("path", ""))).resolve()
        _require_under(artifact_path, bundle_path, errors, name)
        if not artifact_path.exists():
            errors.append(f"artifact missing: {name}")
            continue
        if artifact_path.stat().st_size > int(artifact.get("max_bytes", MAX_REFERENCED_ARTIFACT_BYTES)):
            errors.append(f"artifact too large: {name}")
        digest = _sha256_file(artifact_path)
        if digest != artifact.get("sha256"):
            errors.append(f"artifact digest mismatch: {name}")
        if media_type == "application/x-jsonlines":
            count = _jsonl_count(artifact_path)
            recomputed_counts[name] = count
            if count != int(artifact.get("record_count", -1)):
                errors.append(f"record count mismatch: {name}")

    if bundle_path.is_dir():
        try:
            checksums = _load_json(bundle_path / "checksums.json")
            for name, digest in (checksums.get("files") or {}).items():
                actual = _sha256_file(bundle_path / name)
                expected = f"sha256:{digest}"
                if actual != expected:
                    errors.append(f"checksums.json mismatch for {name}")
            manifest = _load_json(bundle_path / "manifest.json")
            _verify_source_hashes(bundle_path, manifest, errors)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            errors.append(f"bundle readback failed: {exc}")
        canonical_digest = code_graph_bundle_digest(bundle_path)
        if canonical_digest != (handoff.get("code_graph_identity") or {}).get("canonical_bundle_digest"):
            errors.append("canonical bundle digest mismatch")
        checksums_digest = code_graph_checksums_digest(bundle_path)
        if checksums_digest != (handoff.get("code_graph_identity") or {}).get("checksums_digest"):
            errors.append("checksums digest mismatch")

    env_ref = ((handoff.get("environment_identity") or {}).get("manifest") or {})
    if env_ref:
        env_path = Path(str(env_ref.get("path", ""))).resolve()
        if not env_path.exists():
            errors.append("environment manifest missing")
        elif _sha256_file(env_path) != env_ref.get("sha256"):
            errors.append("environment manifest sha mismatch")
        else:
            env_payload = _load_json(env_path)
            expected_env_digest = (handoff.get("environment_identity") or {}).get("environment_manifest_digest")
            if env_payload.get("environment_manifest_digest") != expected_env_digest:
                errors.append("environment manifest digest mismatch")

    request_ref = ((handoff.get("projection_artifacts") or {}).get("request") or {})
    if request_ref:
        request_path = Path(str(request_ref.get("path", ""))).resolve()
        if not request_path.exists():
            errors.append("projection request missing")
        elif _sha256_file(request_path) != request_ref.get("sha256"):
            errors.append("projection request sha mismatch")

    provenance = handoff.get("generation_provenance") or {}
    if provenance.get("projection_mode") == "emit" and provenance.get("generation_id") is not None:
        errors.append("emit-only handoff must not claim a generation_id")
    if provenance.get("projection_mode") == "apply" and not provenance.get("generation_id"):
        errors.append("apply handoff must bind a generation_id")

    expected_identity = _json_digest(_identity_payload(handoff))
    if expected_identity != handoff.get("handoff_identity_digest"):
        errors.append("handoff identity digest mismatch")

    return {
        "schema": ANALYSIS_HANDOFF_VERIFICATION_SCHEMA,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "handoff_path": str(handoff_path),
        "handoff_sha256": _sha256_file(handoff_path) if handoff_path.exists() else None,
        "handoff_identity_digest": handoff.get("handoff_identity_digest"),
        "recomputed_jsonl_counts": recomputed_counts,
        "mocked": False,
        "live": False,
        "proof_scope": "deterministic_local_artifact_readback",
        "claims": {
            "proves": "referenced static artifacts, environment manifest, projection provenance, counts, and source hashes match the handoff",
            "does_not_prove": "Memory activation, runtime behavior, debugger proof, model summaries, or semantic correctness",
        },
    }
