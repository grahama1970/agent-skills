#!/usr/bin/env python3
"""Write a draft authorization template for provider-media publication.

The output is deliberately not an authorization receipt. It packages the exact
locked media facts and the validator's suggested authorization payload so a
human or external authority can approve, reject, or replace it explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_provider_media_publication_authorization import (
    validate_provider_media_publication_authorization,
)


TEMPLATE_SCHEMA = "persona_dream.provider_media_publication_authorization_template.v1"


def write_provider_media_publication_authorization_template(
    *,
    preflight_receipt_path: Path,
) -> dict[str, Any]:
    validation = validate_provider_media_publication_authorization(
        preflight_receipt_path=preflight_receipt_path,
    )
    approval_request = validation.get("approval_request")
    if not isinstance(approval_request, dict):
        raise ValueError("authorization validation did not emit an approval_request")

    target_record = approval_request.get("target_record")
    suggested_receipt = approval_request.get("authorization_receipt_template")
    if not isinstance(target_record, dict) or not isinstance(suggested_receipt, dict):
        raise ValueError("authorization validation emitted an incomplete approval_request")

    return {
        "schema": TEMPLATE_SCHEMA,
        "status": "DRAFT_NOT_AUTHORIZATION",
        "preflight_receipt": str(preflight_receipt_path.resolve()),
        "first_blocker": validation.get("first_blocker"),
        "target_record": target_record,
        "human_role": approval_request.get("human_role"),
        "agent_default_after_approval": approval_request.get("agent_default_after_approval", []),
        "suggested_authorization_receipt": suggested_receipt,
        "operator_instructions": [
            "Do not use this template file as the authorization receipt.",
            "If approved, copy suggested_authorization_receipt to a separate JSON file and replace approved_by and approved_at.",
            "Run validate-provider-media-publication-authorization with --authorization-receipt against that separate approval file.",
            "Only after PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION may the exact staged bytes be published.",
        ],
        "does_not_authorize": validation.get("does_not_authorize", []),
        "mocked": validation.get("mocked", "no"),
        "live": "no",
        "exercised": "preflight receipt parse, locked media fact extraction, draft approval packet rendering",
        "unverified": "human approval, public upload execution, public URL fetch, provider readiness, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = write_provider_media_publication_authorization_template(
            preflight_receipt_path=args.preflight_receipt,
        )
    except Exception as exc:
        result = {
            "schema": TEMPLATE_SCHEMA,
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_publication_authorization_template", "reason": str(exc)},
            "live": "no",
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {args.output}")
    return 0 if result["status"] == "DRAFT_NOT_AUTHORIZATION" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
