#!/usr/bin/env python3
"""Compile the canonical zero-call Persona Dream Phase 11 pre-Kling bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase11_canonical_common import (
    DEFAULT_OUTPUT_RELATIVE,
    Phase11Blocked,
    compile_bundle,
    load_inputs,
    now_from_argument,
    output_paths,
    write_compiled_bundle,
)


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
    value.add_argument("--now", help="ISO-8601 clock override for deterministic compilation")
    value.add_argument("--json", action="store_true")
    return value


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
        media, approvals, request = compile_bundle(inputs)
        output_root = (
            args.output_root.expanduser().resolve()
            if args.output_root
            else (inputs.context.revision_root / DEFAULT_OUTPUT_RELATIVE).resolve()
        )
        paths = write_compiled_bundle(output_root, media, approvals, request)
        result = {
            "schema": "persona_dream.phase11_compile_receipt.v1",
            "status": "PASS_PHASE11_CANONICAL_COMPILER",
            "gate_status": request["status"],
            "run_id": inputs.context.run_id,
            "revision_id": inputs.context.revision_id,
            "activation_transaction_id": inputs.context.activation_transaction_id,
            "outputs": {name: str(path) for name, path in paths.items() if name != "validation_receipt"},
            "technical_blockers": request["technical_blockers"],
            "missing_approval_types": request["missing_approval_types"],
            "request_body_sha256": request["request_body_sha256"],
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "mocked": inputs.context.mocked,
            "live": False,
        }
    except Phase11Blocked as exc:
        result = {
            "schema": "persona_dream.phase11_compile_receipt.v1",
            "status": exc.code,
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": exc.details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
            "mocked": False,
            "live": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["gate_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
