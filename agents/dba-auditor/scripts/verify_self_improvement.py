#!/usr/bin/env python3
"""Verify DBA Auditor self-improvement receipts.

This script is intentionally narrow: it validates the steering-loop receipt
shape. It does not judge database health or approve memory writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


OPTIONAL_FIELDS = [
    "database_session_dir",
    "session_backup_receipt",
    "baseline_health_summary",
    "reverted",
]

REQUIRED_FIELDS = [
    "memory_recall_query",
    "memory_recall_summary",
    "monitor_memory_summary_or_not_needed",
    "monitor_sparta_summary_or_not_needed",
    "external_research_summary_or_not_needed",
    "github_ticket_contract_summary_or_not_needed",
    "completed_task_assessment",
    "what_i_learned",
    "changed_or_recommended_agent_contract_rules",
    "memory_upsert_candidates",
    "next_audit_checklist_delta",
    "brave_search_used_or_not_needed",
    "github_search_summary_or_not_needed",
]


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing receipt: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - CLI reports parse failure.
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "receipt must be a JSON object"
    return data, None


def verify(path: Path) -> dict[str, Any]:
    data, error = load_json(path)
    if error:
        return {
            "schema": "dba_auditor.self_improvement_verification.v1",
            "status": "BLOCKED",
            "receipt": str(path),
            "error": error,
            "missing_fields": REQUIRED_FIELDS,
            "verified": False,
        }

    assert data is not None
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    empty = [field for field in REQUIRED_FIELDS if field in data and is_empty(data[field])]
    status = "PASS" if not missing and not empty else "NEEDS_CHANGES"
    return {
        "schema": "dba_auditor.self_improvement_verification.v1",
        "status": status,
        "receipt": str(path),
        "required_field_count": len(REQUIRED_FIELDS),
        "missing_fields": missing,
        "empty_fields": empty,
        "verified": status == "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    result = verify(args.receipt)
    if args.print_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {args.receipt}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
