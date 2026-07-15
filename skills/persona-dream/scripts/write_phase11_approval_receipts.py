#!/usr/bin/env python3
"""Write the five Phase 11 approval receipts from one explicit human packet.

Invoking this command is not itself authorization.  The command writes approval
receipts only when a schema-valid machine-readable packet explicitly approves
the exact current request, media contract, provider snapshot, pricing snapshot,
endpoint, and ACTIVE_CONSISTENT activation transaction.  ``--dry-run`` performs
all checks and writes no approval receipt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase11_canonical_common import Phase11Blocked, load_inputs, now_from_argument, read_object
from phase11_execution_common import write_approval_receipts


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", help="Optional assertion; must equal active_revision.json")
    value.add_argument("--authorization-packet", type=Path, required=True)
    value.add_argument("--phase10-payload", type=Path)
    value.add_argument("--candidate-binding", type=Path)
    value.add_argument("--media-lock", type=Path)
    value.add_argument("--provider-snapshot", type=Path)
    value.add_argument("--media-transition-manifest", type=Path)
    value.add_argument("--approval-root", type=Path)
    value.add_argument("--now", help="ISO-8601 clock override")
    value.add_argument("--dry-run", action="store_true")
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
        packet_path = args.authorization_packet.expanduser().resolve(strict=True)
        packet = read_object(packet_path)
        result = write_approval_receipts(
            inputs,
            packet,
            packet_path=packet_path,
            current=current,
            dry_run=args.dry_run,
        )
    except Phase11Blocked as exc:
        result = {
            "schema": "persona_dream.phase11_approval_write_error.v1",
            "status": exc.code,
            "details": exc.details,
            "dry_run": bool(args.dry_run),
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "submitted": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
