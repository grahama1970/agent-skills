"""Static runtime-verification request artifacts for ingest-code.

These requests package `debugger.invocation_candidate.v1` rows for a later Tau
or debugger workflow. They are freshness-bound static requests only: this module
does not execute target code, observe runtime behavior, or promote Memory state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from code_analysis_handoff import verify_analysis_handoff
from code_memory_client import code_graph_bundle_digest, code_graph_checksums_digest


REQUEST_SCHEMA = "ingest-code.runtime_verification_request.v1"
REQUESTS_ARTIFACT_SCHEMA = "ingest-code.runtime_verification_requests_artifact.v1"
REQUEST_VERIFICATION_SCHEMA = "ingest-code.runtime_verification_request_verification.v1"
READY = "READY_FOR_VERIFICATION"
NEEDS_INPUT = "NEEDS_INPUT"
NEEDS_HUMAN_DECISION = "NEEDS_HUMAN_DECISION"
UNSUPPORTED_PROFILE = "UNSUPPORTED_PROFILE"
AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
DYNAMIC_TARGET = "DYNAMIC_TARGET"
STALE_SOURCE_BINDING = "STALE_SOURCE_BINDING"
INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"
BLOCKED_POLICY = "BLOCKED_POLICY"
SUPPORTED_PROFILES = {
    "tau-python-workspace-v1": {
        "adapter_family": "python",
        "limits": {
            "timeout_seconds": 30,
            "memory_mb": 512,
            "max_processes": 2,
            "max_output_bytes": 200_000,
        },
    }
}
RUNTIME_RESULT_FIELDS = {
    "runtime_result",
    "runtime_observation",
    "observations",
    "exit_code",
    "stdout",
    "stderr",
    "accepted",
    "verified_runtime",
    "debugger_receipt",
}


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_digest(payload: dict[str, Any]) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _request_identity_payload(request: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in request.items()
        if key not in {"request_identity_digest", "verification"}
    }


def _relative_contained(root: Path, rel_path: str) -> Path | None:
    if not rel_path or Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
        return None
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _artifact_ref(root: Path, rel_path: str, *, role: str) -> dict[str, Any] | None:
    path = _relative_contained(root, rel_path)
    if path is None or not path.is_file():
        return None
    return {
        "path": str(path),
        "relative_path": rel_path,
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
        "content_role": role,
    }


def _disposition(
    *,
    candidate: dict[str, Any],
    symbol: dict[str, Any] | None,
    source_file: dict[str, Any] | None,
    root: Path,
    coverage_complete: bool,
    profile: str,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    reasons: list[str] = []
    input_refs: list[dict[str, Any]] = []
    if profile not in SUPPORTED_PROFILES:
        return UNSUPPORTED_PROFILE, ["unsupported_downstream_profile"], input_refs
    if not coverage_complete:
        return INCOMPLETE_COVERAGE, ["coverage_incomplete_blocks_unique_or_exhaustive_claims"], input_refs
    if symbol is None:
        return STALE_SOURCE_BINDING, ["symbol_id_not_found_in_current_bundle"], input_refs
    if source_file is None:
        return STALE_SOURCE_BINDING, ["source_file_not_found_in_current_bundle"], input_refs
    if candidate.get("symbol_version_id") != symbol.get("symbol_version_id"):
        return STALE_SOURCE_BINDING, ["symbol_version_id_mismatch"], input_refs
    if candidate.get("symbol_content_hash") != symbol.get("content_hash"):
        return STALE_SOURCE_BINDING, ["symbol_content_hash_mismatch"], input_refs
    if candidate.get("status") == "unsafe_direct":
        return BLOCKED_POLICY, ["candidate_has_unsafe_direct_side_effects"], input_refs
    if candidate.get("invocation_kind") in {"attach_runtime", "http"}:
        return DYNAMIC_TARGET, ["candidate_requires_live_runtime_or_service_context"], input_refs
    if any("ambiguous" in str(item) for item in candidate.get("limitations") or []):
        return AMBIGUOUS_TARGET, ["candidate_limitations_are_ambiguous"], input_refs
    if candidate.get("status") == "needs_fixture":
        return NEEDS_INPUT, ["candidate_requires_exact_fixture_or_adapter_input"], input_refs
    if candidate.get("status") != "candidate_static":
        return NEEDS_HUMAN_DECISION, [f"unsupported_candidate_status:{candidate.get('status')}"], input_refs
    for rel_path in candidate.get("fixture_refs") or []:
        ref = _artifact_ref(root, str(rel_path), role="required_fixture")
        if ref is None:
            reasons.append(f"fixture_ref_unresolved:{rel_path}")
        else:
            input_refs.append(ref)
    if reasons:
        return NEEDS_INPUT, reasons, input_refs
    if not candidate.get("command"):
        return NEEDS_INPUT, ["candidate_has_no_static_command_or_fixture"], input_refs
    return READY, [], input_refs


def build_runtime_verification_requests(
    *,
    code_graph_artifact: dict[str, Any],
    analysis_handoff: dict[str, Any],
    environment_manifest: dict[str, Any],
    scope: str = "code",
    profile: str = "tau-python-workspace-v1",
) -> list[dict[str, Any]]:
    """Build deterministic static verification requests for every candidate row."""
    bundle_path = Path(str(code_graph_artifact["path"])).resolve()
    manifest = _load_json(bundle_path / "manifest.json")
    coverage = _load_json(bundle_path / "coverage.json")
    root = Path(str(manifest["root"])).resolve()
    symbols = {row["symbol_id"]: row for row in _jsonl(bundle_path / "symbols.jsonl")}
    files = {row["path"]: row for row in _jsonl(bundle_path / "files.jsonl")}
    handoff_path = Path(str(analysis_handoff["path"])).resolve()
    handoff_payload = _load_json(handoff_path)
    handoff_verification = verify_analysis_handoff(handoff_path)
    profile_config = SUPPORTED_PROFILES.get(profile)
    requests: list[dict[str, Any]] = []
    for candidate in _jsonl(bundle_path / "debug_invocations.jsonl"):
        source = candidate.get("source") or {}
        symbol = symbols.get(str(candidate.get("symbol_id")))
        source_file = files.get(str(source.get("path")))
        disposition, reasons, input_refs = _disposition(
            candidate=candidate,
            symbol=symbol,
            source_file=source_file,
            root=root,
            coverage_complete=bool(coverage.get("complete")) and not bool(coverage.get("fail_closed")),
            profile=profile,
        )
        candidate_digest = _json_digest(candidate)
        request = {
            "schema": REQUEST_SCHEMA,
            "disposition": disposition,
            "non_ready_reasons": reasons,
            "candidate": {
                "candidate_id": candidate.get("recipe_id"),
                "candidate_digest": candidate_digest,
                "candidate_status": candidate.get("status"),
                "candidate_limitations": candidate.get("limitations") or [],
            },
            "repository": manifest.get("repo"),
            "branch": manifest.get("branch"),
            "commit": manifest.get("commit"),
            "worktree_disposition": "dirty" if manifest.get("tracked_worktree_dirty") else "clean",
            "scope": scope,
            "code_index_identity": {
                "canonical_bundle_digest": code_graph_bundle_digest(bundle_path),
                "checksums_digest": code_graph_checksums_digest(bundle_path),
                "generation_id": (handoff_payload.get("generation_provenance") or {}).get("generation_id"),
            },
            "symbol": {
                "symbol_id": candidate.get("symbol_id"),
                "symbol_version_id": candidate.get("symbol_version_id"),
                "content_hash": candidate.get("symbol_content_hash"),
                "qualified_name": source.get("qualified_name"),
            },
            "source": {
                "path": source.get("path"),
                "start_line": source.get("start_line"),
                "end_line": source.get("end_line"),
                "source_hash": (source_file or {}).get("source_hash"),
                "entry_breakpoint": candidate.get("entry_breakpoint"),
            },
            "invocation": {
                "kind": candidate.get("invocation_kind"),
                "exact_target_identity": candidate.get("symbol_ref"),
                "command": candidate.get("command") or [],
            },
            "inputs": {
                "required_input_refs": input_refs,
                "unresolved_input_reason": reasons if disposition == NEEDS_INPUT else [],
            },
            "downstream": {
                "profile": profile,
                "adapter_family": (profile_config or {}).get("adapter_family"),
            },
            "containment": {
                "working_root": str(root),
                "declared_file_grants": sorted(
                    str(item)
                    for item in {source.get("path"), *(candidate.get("fixture_refs") or [])}
                    if item
                ),
            },
            "limits": (profile_config or {}).get("limits", {}),
            "environment_manifest_ref": {
                "path": environment_manifest.get("path"),
                "sha256": environment_manifest.get("sha256"),
                "environment_manifest_digest": environment_manifest.get("environment_manifest_digest"),
            },
            "analysis_handoff_ref": {
                "path": str(handoff_path),
                "sha256": analysis_handoff.get("sha256"),
                "handoff_identity_digest": analysis_handoff.get("handoff_identity_digest"),
                "verification_status": handoff_verification.get("status"),
            },
            "proof_scope": "static_freshness_bound_runtime_verification_request",
            "non_claims": [
                "request_is_not_runtime_execution",
                "request_is_not_debugger_observation",
                "request_is_not_memory_promotion",
                "request_is_not_tau_node_acceptance",
            ],
        }
        request["request_identity_digest"] = _json_digest(_request_identity_payload(request))
        requests.append(request)
    return sorted(requests, key=lambda item: (item["source"]["path"], item["symbol"]["qualified_name"], item["invocation"]["kind"], item["candidate"]["candidate_id"]))


def write_runtime_verification_requests(
    path: Path,
    *,
    code_graph_artifact: dict[str, Any],
    analysis_handoff: dict[str, Any],
    environment_manifest: dict[str, Any],
    scope: str = "code",
    profile: str = "tau-python-workspace-v1",
) -> dict[str, Any]:
    """Write request rows and verify each one without executing target code."""
    requests = build_runtime_verification_requests(
        code_graph_artifact=code_graph_artifact,
        analysis_handoff=analysis_handoff,
        environment_manifest=environment_manifest,
        scope=scope,
        profile=profile,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in requests),
        encoding="utf-8",
    )
    verifications = [verify_runtime_verification_request(row) for row in requests]
    status = "PASS" if all(item["status"] == "PASS" for item in verifications) else "BLOCKED"
    return {
        "schema": REQUESTS_ARTIFACT_SCHEMA,
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "record_count": len(requests),
        "status": status,
        "disposition_counts": {
            value: sum(1 for row in requests if row["disposition"] == value)
            for value in sorted({row["disposition"] for row in requests})
        },
        "verification_errors": [error for item in verifications for error in item["errors"]],
    }


def _reject_runtime_fields(value: Any, errors: list[str], prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            if key in RUNTIME_RESULT_FIELDS:
                errors.append(f"runtime result field is forbidden: {dotted}")
            _reject_runtime_fields(item, errors, dotted)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _reject_runtime_fields(item, errors, f"{prefix}[{idx}]")


def verify_runtime_verification_request(request: dict[str, Any]) -> dict[str, Any]:
    """Verify one static runtime-verification request without executing code."""
    errors: list[str] = []
    if request.get("schema") != REQUEST_SCHEMA:
        errors.append(f"unsupported schema: {request.get('schema')}")
    _reject_runtime_fields(request, errors)
    expected_identity = _json_digest(_request_identity_payload(request))
    if request.get("request_identity_digest") != expected_identity:
        errors.append("request identity digest mismatch")
    root = Path(str((request.get("containment") or {}).get("working_root", ""))).resolve()
    if not root.is_dir():
        errors.append("working root missing")
    for grant in (request.get("containment") or {}).get("declared_file_grants") or []:
        if _relative_contained(root, str(grant)) is None:
            errors.append(f"declared file grant escapes root: {grant}")
    source_path = _relative_contained(root, str((request.get("source") or {}).get("path", "")))
    if source_path is None or not source_path.is_file():
        errors.append("source path is not contained or missing")
    handoff_ref = request.get("analysis_handoff_ref") or {}
    handoff_path = Path(str(handoff_ref.get("path", ""))).resolve()
    if not handoff_path.exists():
        errors.append("analysis handoff missing")
    elif _sha256_file(handoff_path) != handoff_ref.get("sha256"):
        errors.append("analysis handoff sha mismatch")
    else:
        handoff_receipt = verify_analysis_handoff(handoff_path)
        if handoff_receipt["status"] != "PASS":
            errors.append("analysis handoff verification failed")
        if handoff_receipt.get("handoff_identity_digest") != handoff_ref.get("handoff_identity_digest"):
            errors.append("analysis handoff identity mismatch")
        bundle_path = Path(str((_load_json(handoff_path).get("code_graph_identity") or {}).get("bundle_path", ""))).resolve()
        if bundle_path.is_dir():
            candidate_rows = _jsonl(bundle_path / "debug_invocations.jsonl")
            matches = [
                row
                for row in candidate_rows
                if row.get("recipe_id") == (request.get("candidate") or {}).get("candidate_id")
            ]
            if len(matches) != 1:
                errors.append("candidate id does not resolve uniquely")
            elif _json_digest(matches[0]) != (request.get("candidate") or {}).get("candidate_digest"):
                errors.append("candidate digest mismatch")
            symbol_rows = {
                row["symbol_id"]: row
                for row in _jsonl(bundle_path / "symbols.jsonl")
            }
            symbol = symbol_rows.get(str((request.get("symbol") or {}).get("symbol_id")))
            if symbol is None:
                errors.append("symbol id missing from bundle")
            else:
                if symbol.get("symbol_version_id") != (request.get("symbol") or {}).get("symbol_version_id"):
                    errors.append("symbol version mismatch")
                if symbol.get("content_hash") != (request.get("symbol") or {}).get("content_hash"):
                    errors.append("symbol content hash mismatch")
            if source_path and source_path.is_file():
                actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if actual != (request.get("source") or {}).get("source_hash"):
                    errors.append("bound source file changed")
            if code_graph_bundle_digest(bundle_path) != (request.get("code_index_identity") or {}).get("canonical_bundle_digest"):
                errors.append("canonical bundle digest mismatch")
            if code_graph_checksums_digest(bundle_path) != (request.get("code_index_identity") or {}).get("checksums_digest"):
                errors.append("checksums digest mismatch")
    env_ref = request.get("environment_manifest_ref") or {}
    env_path = Path(str(env_ref.get("path", ""))).resolve()
    if not env_path.exists():
        errors.append("environment manifest missing")
    elif _sha256_file(env_path) != env_ref.get("sha256"):
        errors.append("environment manifest sha mismatch")
    else:
        env_payload = _load_json(env_path)
        if env_payload.get("environment_manifest_digest") != env_ref.get("environment_manifest_digest"):
            errors.append("environment manifest digest mismatch")
    if request.get("disposition") == READY and (request.get("inputs") or {}).get("unresolved_input_reason"):
        errors.append("ready request must not have unresolved input reason")
    return {
        "schema": REQUEST_VERIFICATION_SCHEMA,
        "status": "PASS" if not errors else "BLOCKED",
        "errors": errors,
        "mocked": False,
        "live": False,
        "proof_scope": "static_request_readback_without_runtime_execution",
        "claims": {
            "proves": "request freshness and containment bindings match current static artifacts",
            "does_not_prove": "target code execution, debugger observations, Memory promotion, or Tau acceptance",
        },
    }
