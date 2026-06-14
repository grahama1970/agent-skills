from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_failed_checks(failed_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for check in failed_checks:
        normalized.append(
            {
                "id": str(check.get("id") or "unknown_check"),
                "detail": str(check.get("detail") or ""),
                "passed": bool(check.get("passed")),
            }
        )
    return normalized


def write_maintainer_ticket(
    *,
    skill_name: str,
    route: str,
    job_dir: Path | str,
    output_path: Path | str,
    verify_receipt_path: Path | str,
    failed_checks: list[dict[str, Any]],
    target_paths: list[str],
    repro_commands: list[str],
    issue_url: str | None = None,
) -> dict[str, Any]:
    """Write a deterministic maintainer packet without creating a GitHub issue."""
    job_dir = Path(job_dir).resolve()
    output_path = Path(output_path).resolve()
    verify_receipt_path = Path(verify_receipt_path).resolve()
    normalized_failed_checks = normalize_failed_checks(failed_checks)
    packet = {
        "schema_version": "skill-maintainer-ticket.v1",
        "created_at": utc_now(),
        "skill": skill_name,
        "route": route,
        "status": "needs_maintainer" if normalized_failed_checks else "no_failed_checks",
        "issue_url": issue_url,
        "job_dir": str(job_dir),
        "verify_receipt": str(verify_receipt_path),
        "target_paths": target_paths,
        "failed_checks": normalized_failed_checks,
        "repro_commands": repro_commands,
        "github_side_effects_performed": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    return packet
