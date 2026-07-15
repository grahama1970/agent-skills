#!/usr/bin/env python3
"""Write the canonical Phase 11 media-binding manifest v2 without provider calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from phase11_canonical_common import (
    DEFAULT_CANDIDATE_RELATIVE,
    DEFAULT_MEDIA_LOCK_RELATIVE,
    DEFAULT_TRANSITION_RELATIVE,
    build_media_binding_manifest,
    compile_request_body,
    load_inputs,
    now_from_argument,
    write_json,
)


def build_manifest(inputs: Any, request_body: Mapping[str, Any]) -> dict[str, Any]:
    """Public pure entry used by the compiler and focused tests."""
    return build_media_binding_manifest(inputs, request_body)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", help="Optional assertion; must equal active_revision.json")
    value.add_argument("--candidate-binding", type=Path)
    value.add_argument("--media-lock", type=Path)
    value.add_argument("--provider-snapshot", type=Path)
    value.add_argument("--media-transition-manifest", type=Path)
    value.add_argument("--approval-root", type=Path)
    value.add_argument("--phase10-payload", type=Path)
    value.add_argument("--now", help="ISO-8601 clock override for deterministic validation")
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--json", action="store_true")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        inputs = load_inputs(
            args.run_root,
            revision_override=args.revision_id,
            phase10_payload=args.phase10_payload,
            candidate_binding=args.candidate_binding,
            media_lock=args.media_lock,
            provider_snapshot=args.provider_snapshot,
            transition_manifest=args.media_transition_manifest,
            approval_root=args.approval_root,
            current=now_from_argument(args.now),
        )
        request_body, _blockers, _transformations = compile_request_body(inputs)
        manifest = build_manifest(inputs, request_body)
    except Exception as exc:  # fail closed with one machine-readable blocker
        code = getattr(exc, "code", "BLOCKED_PHASE11_MEDIA_BINDING_COMPILER")
        manifest = {
            "schema": "persona_dream.phase11_media_binding_manifest.v2",
            "status": "BLOCKED_PROVIDER_GATE",
            "run_id": None,
            "revision_id": None,
            "activation_transaction_id": None,
            "role_counts": {
                "global_start_anchor": 0,
                "global_end_anchor": 0,
                "continuity_only": 0,
                "element_packs": 0,
            },
            "storyboard_frames": [],
            "element_packs": [],
            "blockers": [str(code)],
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
    write_json(args.output, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True) if args.json else manifest["status"])
    # A blocked provider gate is an expected, successfully materialized state.
    return 0 if manifest["status"] in {"PASS_PHASE11_MEDIA_BINDING_TECHNICAL", "BLOCKED_PROVIDER_GATE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
