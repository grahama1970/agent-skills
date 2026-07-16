#!/usr/bin/env python3
"""Create the active-revision Phase 11 Standard payload binding without provider calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase11_canonical_common import (
    DEFAULT_CANDIDATE_RELATIVE,
    DEFAULT_MEDIA_LOCK_RELATIVE,
    DEFAULT_PHASE10_RELATIVE,
    Phase11Blocked,
    resolve_active_context,
    sha256_file,
)
from phase11_payload_binding import (
    DEFAULT_REPOSITORY,
    PayloadBindingBlocked,
    build_payload_binding,
    discover_git_commit,
    load_and_validate_payload_binding,
    write_payload_binding,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--run-root", type=Path, required=True)
    value.add_argument("--revision-id", help="Optional assertion; must equal active_revision.json")
    value.add_argument("--publication-commit", help="Commit containing the active revision media; defaults to git HEAD")
    value.add_argument("--repository", default=DEFAULT_REPOSITORY)
    value.add_argument("--phase10-payload", type=Path)
    value.add_argument("--media-lock", type=Path)
    value.add_argument("--output", type=Path)
    value.add_argument("--json", action="store_true")
    return value


def bootstrap(args: argparse.Namespace) -> dict[str, object]:
    context = resolve_active_context(args.run_root, args.revision_id)
    phase10_path = (
        args.phase10_payload.expanduser().resolve()
        if args.phase10_payload
        else (context.revision_root / DEFAULT_PHASE10_RELATIVE).resolve()
    )
    media_lock_path = (
        args.media_lock.expanduser().resolve()
        if args.media_lock
        else (context.revision_root / DEFAULT_MEDIA_LOCK_RELATIVE).resolve()
    )
    output_path = (
        args.output.expanduser().resolve()
        if args.output
        else (context.revision_root / DEFAULT_CANDIDATE_RELATIVE).resolve()
    )
    publication_commit = (args.publication_commit or discover_git_commit(context.run_root)).lower()

    created = False
    if output_path.is_file():
        binding = load_and_validate_payload_binding(
            output_path,
            context=context,
            phase10_payload_path=phase10_path,
            media_lock_path=media_lock_path,
        )
        if binding["publication"]["commit"] != publication_commit:
            raise PayloadBindingBlocked(
                "BLOCKED_PHASE11_PAYLOAD_BINDING_ALREADY_EXISTS_DIFFERENT",
                details={
                    "path": str(output_path),
                    "existing_publication_commit": binding["publication"]["commit"],
                    "requested_publication_commit": publication_commit,
                },
            )
    else:
        binding = build_payload_binding(
            context=context,
            phase10_payload_path=phase10_path,
            media_lock_path=media_lock_path,
            publication_commit=publication_commit,
            repository=args.repository,
        )
        write_payload_binding(output_path, binding)
        created = True

    return {
        "schema": "persona_dream.phase11_payload_binding_bootstrap_receipt.v1",
        "status": "PASS_PHASE11_PAYLOAD_BINDING_BOOTSTRAP",
        "gate_status": binding["gate_status"],
        "binding_status": binding["status"],
        "run_id": context.run_id,
        "revision_id": context.revision_id,
        "activation_transaction_id": context.activation_transaction_id,
        "binding_path": str(output_path),
        "binding_sha256": sha256_file(output_path),
        "created": created,
        "role_counts": binding["media_roles"]["role_counts"],
        "next_command": binding["publication"]["next_command"],
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = bootstrap(args)
    except (PayloadBindingBlocked, Phase11Blocked) as exc:
        result = {
            "schema": "persona_dream.phase11_payload_binding_bootstrap_receipt.v1",
            "status": exc.code,
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": exc.details,
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return exc.exit_code
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "persona_dream.phase11_payload_binding_bootstrap_receipt.v1",
            "status": "BLOCKED_PHASE11_PAYLOAD_BINDING_BOOTSTRAP_ERROR",
            "gate_status": "BLOCKED_PROVIDER_GATE",
            "details": {"error": str(exc)},
            "actual_provider_call_attempts": 0,
            "provider_live": False,
            "paid_call_authorized": False,
            "submitted": False,
            "provider_ready": False,
            "live_submit_ready": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
