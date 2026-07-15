#!/usr/bin/env python3
"""Independently validate and optionally persist the canonical Phase 11 boundary."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from phase11_canonical_common import (
    DEFAULT_COLLECTION,
    DEFAULT_MEMORY_URL,
    DEFAULT_OUTPUT_RELATIVE,
    Phase11Blocked,
    canonical_json_bytes,
    canonical_path_violations,
    compile_bundle,
    load_inputs,
    memory_document,
    now_from_argument,
    output_paths,
    persist_phase11_boundary,
    read_object,
    sha256_file,
    validate_request_body,
    validate_schema,
    write_json,
)
from prepare_revision_qualification import GateBlocked


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", help="Optional assertion; must equal active_revision.json")
    value.add_argument("--phase10-payload", type=Path)
    value.add_argument("--candidate-binding", type=Path)
    value.add_argument("--media-lock", type=Path)
    value.add_argument("--provider-snapshot", type=Path)
    value.add_argument("--media-transition-manifest", type=Path)
    value.add_argument("--approval-root", type=Path)
    value.add_argument("--output-root", type=Path)
    value.add_argument("--now", help="ISO-8601 clock override used by both compiler and validator")
    value.add_argument("--persist-memory", action="store_true")
    value.add_argument("--memory-url")
    value.add_argument("--collection")
    value.add_argument("--connect-timeout", type=float, default=5.0)
    value.add_argument("--read-timeout", type=float, default=60.0)
    value.add_argument("--test-fixture", action="store_true", help=argparse.SUPPRESS)
    value.add_argument("--json", action="store_true")
    return value


def command_metadata() -> dict[str, Any]:
    path = Path(__file__).resolve()
    return {
        "argv": list(sys.argv),
        "cwd": str(Path.cwd()),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "script_path": str(path),
        "script_sha256": sha256_file(path),
    }


def same_json(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        current = now_from_argument(args.now)
        inputs = load_inputs(
            args.run_root,
            revision_override=args.revision_id,
            phase10_payload=args.phase10_payload,
            candidate_binding=args.candidate_binding,
            media_lock=args.media_lock,
            provider_snapshot=args.provider_snapshot,
            transition_manifest=args.media_transition_manifest,
            approval_root=args.approval_root,
            current=current,
        )
        output_root = (
            args.output_root.expanduser().resolve()
            if args.output_root
            else (inputs.context.revision_root / DEFAULT_OUTPUT_RELATIVE).resolve()
        )
        paths = output_paths(output_root)
        expected_media, expected_approvals, expected_request = compile_bundle(inputs)
        actual_media = read_object(paths["media_manifest"])
        actual_approvals = read_object(paths["approval_requirements"])
        actual_request = read_object(paths["live_request"])

        deterministic_errors: list[str] = []
        if not same_json(actual_media, expected_media):
            deterministic_errors.append("BLOCKED_PHASE11_MEDIA_MANIFEST_NONDETERMINISTIC")
        if not same_json(actual_approvals, expected_approvals):
            deterministic_errors.append("BLOCKED_PHASE11_APPROVAL_REQUIREMENTS_NONDETERMINISTIC")
        if not same_json(actual_request, expected_request):
            deterministic_errors.append("BLOCKED_PHASE11_LIVE_REQUEST_NONDETERMINISTIC")
        for name, value in (
            ("media_binding_manifest", actual_media),
            ("approval_requirements", actual_approvals),
            ("live_request", actual_request),
        ):
            deterministic_errors.extend(
                f"BLOCKED_PHASE11_CANONICAL_PATH_NONPORTABLE:{name}:{pointer}"
                for pointer in canonical_path_violations(value)
            )
        deterministic_errors.extend(
            f"BLOCKED_PHASE11_LIVE_REQUEST_SCHEMA:{message}"
            for message in validate_schema(actual_request, "phase11_live_request.v1.schema.json")
        )
        deterministic_errors.extend(
            f"BLOCKED_PHASE11_MEDIA_MANIFEST_SCHEMA:{message}"
            for message in validate_schema(actual_media, "phase11_media_binding_manifest.v2.schema.json")
        )
        deterministic_errors.extend(
            validate_request_body(
                actual_request.get("provider_request_body") if isinstance(actual_request.get("provider_request_body"), Mapping) else {},
                endpoint=str(actual_request.get("endpoint") or ""),
                mode=str(actual_request.get("mode") or ""),
            )
        )
        request_body_sha256 = str(actual_request.get("request_body_sha256") or "")
        from phase11_canonical_common import canonical_sha256  # local import avoids a second canonical implementation
        observed_body_sha = canonical_sha256(actual_request.get("provider_request_body"))
        if observed_body_sha != request_body_sha256:
            deterministic_errors.append("BLOCKED_PHASE11_REQUEST_BODY_HASH_MISMATCH")

        file_hashes = {
            "media_binding_manifest": sha256_file(paths["media_manifest"]),
            "approval_requirements": sha256_file(paths["approval_requirements"]),
            "live_request": sha256_file(paths["live_request"]),
            "provider_source_snapshot": inputs.provider_snapshot.sha256,
            "activation_receipt": sha256_file(inputs.context.activation_receipt_path),
        }
        technical_blockers = sorted(set(list(actual_request.get("technical_blockers") or []) + deterministic_errors))
        missing_approvals = sorted(set(actual_request.get("missing_approval_types") or []))
        gate_status = "BLOCKED_PROVIDER_GATE" if technical_blockers else "BLOCKED_AWAITING_HUMAN_APPROVAL"

        memory_evidence: dict[str, Any]
        if args.persist_memory:
            document = memory_document(
                inputs,
                gate_status=gate_status,
                media_file_sha256=file_hashes["media_binding_manifest"],
                approval_file_sha256=file_hashes["approval_requirements"],
                request_file_sha256=file_hashes["live_request"],
                request_body_sha256=request_body_sha256,
                technical_blockers=technical_blockers,
                missing_approvals=missing_approvals,
            )
            memory_evidence = persist_phase11_boundary(
                inputs,
                document,
                memory_url=(args.memory_url or inputs.context.memory_url or DEFAULT_MEMORY_URL),
                collection=(args.collection or inputs.context.collection or DEFAULT_COLLECTION),
                connect_timeout=args.connect_timeout,
                read_timeout=args.read_timeout,
            )
        else:
            technical_blockers = sorted(set(technical_blockers + ["BLOCKED_PHASE11_MEMORY_PERSISTENCE_REQUIRED"]))
            gate_status = "BLOCKED_PROVIDER_GATE"
            memory_evidence = {
                "persisted": False,
                "status": "BLOCKED_PHASE11_MEMORY_PERSISTENCE_REQUIRED",
            }

        receipt = {
            "schema": "persona_dream.phase11_validation_receipt.v1",
            "validator_status": "PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED",
            "gate_status": gate_status,
            "run_id": inputs.context.run_id,
            "revision_id": inputs.context.revision_id,
            "source_revision_id": inputs.context.source_revision_id,
            "source_commit": inputs.context.source_commit,
            "runtime_release_id": inputs.context.runtime_release_id,
            "activation_transaction_id": inputs.context.activation_transaction_id,
            "validated_at": current.isoformat(),
            "files": {
                "media_binding_manifest": {"path": str(paths["media_manifest"]), "sha256": file_hashes["media_binding_manifest"]},
                "approval_requirements": {"path": str(paths["approval_requirements"]), "sha256": file_hashes["approval_requirements"]},
                "live_request": {"path": str(paths["live_request"]), "sha256": file_hashes["live_request"]},
                "provider_source_snapshot": {"path": str(inputs.provider_snapshot.path), "sha256": file_hashes["provider_source_snapshot"]},
                "activation_receipt": {"path": str(inputs.context.activation_receipt_path), "sha256": file_hashes["activation_receipt"]},
            },
            "request_body_sha256": request_body_sha256,
            "request_output_file_sha256": file_hashes["live_request"],
            "technical_blockers": technical_blockers,
            "missing_approval_types": missing_approvals,
            "memory": memory_evidence,
            "command": command_metadata(),
            "mocked": bool(args.test_fixture or inputs.context.mocked),
            "live": bool(args.persist_memory and not (args.test_fixture or inputs.context.mocked)),
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "actual_provider_call_attempts": 0,
            "claims": {
                "proves": [
                    "the canonical Phase 11 request and every recorded hash were independently recomputed",
                    "the ACTIVE_CONSISTENT activation chain was revalidated",
                ] + (["Memory exactly reread and semantically recalled the Phase 11 boundary record"] if memory_evidence.get("persisted") else []),
                "does_not_prove": ["provider readiness", "provider submission", "provider acceptance", "returned video"],
            },
        }
        schema_errors = validate_schema(receipt, "phase11_validation_receipt.v1.schema.json")
        if schema_errors:
            raise Phase11Blocked("BLOCKED_PHASE11_VALIDATION_RECEIPT_SCHEMA", details={"errors": schema_errors})
        write_json(paths["validation_receipt"], receipt)
    except (Phase11Blocked, GateBlocked) as exc:
        output = {
            "schema": "persona_dream.phase11_validation_error.v1",
            "validator_status": exc.code,
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": exc.details,
            "mocked": bool(args.test_fixture),
            "live": False,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "actual_provider_call_attempts": 0,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return exc.exit_code
    except Exception as exc:  # no producer PASS can hide an unclassified validator failure
        output = {
            "schema": "persona_dream.phase11_validation_error.v1",
            "validator_status": "BLOCKED_PHASE11_VALIDATOR_EXCEPTION",
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": {"error": str(exc)},
            "mocked": bool(args.test_fixture),
            "live": False,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "actual_provider_call_attempts": 0,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 2

    print(json.dumps(receipt, indent=2, sort_keys=True) if args.json else receipt["gate_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
