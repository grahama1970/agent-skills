#!/usr/bin/env python3
"""Require a minimum source age before accepting live no-write Memory recall."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_live_memory_revision_recall import _file_sha256, _load_json, _write_json


PASS_STATUS = "PASS_PCTOM_LIVE_MEMORY_AGED_RETENTION_RECALL"
BLOCKED_STATUS = "BLOCKED_PCTOM_LIVE_MEMORY_AGED_RETENTION_RECALL"
NESTED_PASS_STATUS = "PASS_PCTOM_LIVE_MEMORY_REVISION_DELAYED_RECALL"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _write_receipt(receipt_out: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    _write_json(receipt_out, receipt)
    receipt["receipt_sha256"] = _file_sha256(receipt_out)
    _write_json(receipt_out, receipt)
    return receipt


def _base_receipt(
    *,
    created_at: str,
    source_root: Path,
    source_receipt_path: Path,
    source_receipt_sha256: str | None,
    source_created_at: Any,
    output_root: Path,
    receipt_out: Path,
    min_age_s: int,
    elapsed_age_s: float | None,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.live_memory_aged_retention_recall_receipt.v1",
        "created_at": created_at,
        "status": BLOCKED_STATUS,
        "source_root": str(source_root),
        "source_receipt": str(source_receipt_path),
        "source_receipt_sha256": source_receipt_sha256,
        "source_created_at": source_created_at,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "min_age_s": min_age_s,
        "elapsed_age_s": elapsed_age_s,
        "minimum_age_satisfied": False,
        "nested_delayed_recall": {
            "executed": False,
            "status": "SKIPPED_MINIMUM_AGE_NOT_SATISFIED",
            "receipt_path": None,
            "receipt_sha256": None,
        },
        "errors": errors,
        "counts": {
            "nested_source_memory_documents": 0,
            "nested_source_semantic_documents": 0,
            "nested_delayed_exact_rereads": 0,
            "nested_delayed_semantic_exact_rereads": 0,
            "nested_delayed_recall_queries": 0,
            "nested_delayed_recall_hits": 0,
            "nested_write_violations": 0,
        },
        "checks": {
            "source_receipt_hash_recomputed": isinstance(source_receipt_sha256, str)
            and source_receipt_sha256.startswith("sha256:"),
            "minimum_age_satisfied": False,
            "nested_delayed_recall_passed": False,
            "nested_no_write_path": False,
            "nested_prior_and_posterior_distinguished": False,
            "nested_synthetic_literal_boundary_preserved": False,
            "unsupported_writes_absent": True,
            "human_content_judgment_absent": True,
        },
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "memory_write_attempts": 0,
        "tau_call_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "claims": {
            "proves": [
                "the aged-retention wrapper failed closed before accepting delayed recall evidence",
            ],
            "does_not_prove": [
                "live no-write recall after the requested minimum age",
                "multi-day wall-clock retention",
                "new live Tau execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }


def run(
    *,
    source_root: Path,
    output_root: Path,
    receipt_out: Path,
    memory_base_url: str,
    min_age_s: int,
    recall_attempts: int,
    recall_sleep_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    source_receipt_path = source_root / "live_memory_revision_recall_receipt.v1.json"
    source_receipt = _load_json(source_receipt_path, errors, "source_live_memory_revision_recall_receipt")
    source_receipt = source_receipt if isinstance(source_receipt, dict) else {}
    source_receipt_sha256 = _file_sha256(source_receipt_path) if source_receipt_path.exists() else None
    source_created_at = source_receipt.get("created_at")
    created_at = _now_iso()
    created_dt = _parse_iso(created_at)
    source_dt = _parse_iso(source_created_at)
    elapsed_age_s = round((created_dt - source_dt).total_seconds(), 3) if created_dt and source_dt else None

    if source_receipt.get("status") != "PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL":
        errors.append(f"source_status_not_pass:{source_receipt.get('status')}")
    if elapsed_age_s is None:
        errors.append(f"source_created_at_unparseable:{source_created_at}")
    elif elapsed_age_s < min_age_s:
        errors.append(f"minimum_age_not_satisfied:{elapsed_age_s}:{min_age_s}")

    nested_output_root = output_root / "nested_delayed_recall"
    nested_receipt_path = nested_output_root / "live_memory_revision_delayed_recall_receipt.v1.json"
    receipt = _base_receipt(
        created_at=created_at,
        source_root=source_root,
        source_receipt_path=source_receipt_path,
        source_receipt_sha256=source_receipt_sha256,
        source_created_at=source_created_at,
        output_root=output_root,
        receipt_out=receipt_out,
        min_age_s=min_age_s,
        elapsed_age_s=elapsed_age_s,
        errors=errors,
    )

    if errors:
        receipt["processing_time_s"] = round(time.monotonic() - started, 6)
        return _write_receipt(receipt_out, receipt)

    cmd = [
        sys.executable,
        str(Path(__file__).with_name("run_live_memory_revision_delayed_recall.py")),
        "--source-root",
        str(source_root),
        "--output-root",
        str(nested_output_root),
        "--receipt-out",
        str(nested_receipt_path),
        "--memory-base-url",
        memory_base_url,
        "--recall-attempts",
        str(recall_attempts),
        "--recall-sleep-s",
        str(recall_sleep_s),
        "--json",
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    nested_receipt = _load_json(nested_receipt_path, errors, "nested_delayed_recall_receipt")
    nested_receipt = nested_receipt if isinstance(nested_receipt, dict) else {}
    nested_counts = nested_receipt.get("counts") if isinstance(nested_receipt.get("counts"), dict) else {}
    nested_checks = nested_receipt.get("checks") if isinstance(nested_receipt.get("checks"), dict) else {}
    nested_status = nested_receipt.get("status")
    nested_write_violations = int(nested_counts.get("write_violations", 0) or 0)

    if completed.returncode != 0:
        errors.append(f"nested_delayed_recall_exit_nonzero:{completed.returncode}")
    if nested_status != NESTED_PASS_STATUS:
        errors.append(f"nested_delayed_recall_status_not_pass:{nested_status}")
    for key in (
        "fresh_process_no_write_path",
        "delayed_exact_reread_complete",
        "delayed_semantic_exact_reread_complete",
        "delayed_live_memory_recall_hits_per_condition",
        "prior_and_posterior_distinguished",
        "synthetic_literal_boundary_preserved",
        "unsupported_writes_absent",
        "human_content_judgment_absent",
    ):
        if nested_checks.get(key) is not True:
            errors.append(f"nested_check_not_true:{key}:{nested_checks.get(key)}")
    for key in (
        "memory_write_attempts",
        "tau_call_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if nested_receipt.get(key) != 0:
            errors.append(f"nested_{key}_nonzero:{nested_receipt.get(key)}")
    if nested_write_violations != 0:
        errors.append(f"nested_write_violations_nonzero:{nested_write_violations}")

    receipt["status"] = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt["minimum_age_satisfied"] = elapsed_age_s is not None and elapsed_age_s >= min_age_s
    receipt["nested_delayed_recall"] = {
        "executed": True,
        "command": cmd,
        "returncode": completed.returncode,
        "status": nested_status,
        "receipt_path": str(nested_receipt_path),
        "receipt_sha256": _file_sha256(nested_receipt_path) if nested_receipt_path.exists() else None,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    receipt["errors"] = errors
    receipt["counts"] = {
        "nested_source_memory_documents": int(nested_counts.get("source_memory_documents", 0) or 0),
        "nested_source_semantic_documents": int(nested_counts.get("source_semantic_documents", 0) or 0),
        "nested_delayed_exact_rereads": int(nested_counts.get("delayed_exact_rereads", 0) or 0),
        "nested_delayed_semantic_exact_rereads": int(nested_counts.get("delayed_semantic_exact_rereads", 0) or 0),
        "nested_delayed_recall_queries": int(nested_counts.get("delayed_recall_queries", 0) or 0),
        "nested_delayed_recall_hits": int(nested_counts.get("delayed_recall_hits", 0) or 0),
        "nested_delayed_recall_hits_per_condition": nested_counts.get("delayed_recall_hits_per_condition", {}),
        "nested_write_violations": nested_write_violations,
    }
    receipt["checks"] = {
        "source_receipt_hash_recomputed": isinstance(source_receipt_sha256, str)
        and source_receipt_sha256.startswith("sha256:"),
        "minimum_age_satisfied": receipt["minimum_age_satisfied"],
        "nested_delayed_recall_passed": nested_status == NESTED_PASS_STATUS,
        "nested_no_write_path": nested_checks.get("fresh_process_no_write_path") is True
        and nested_receipt.get("memory_write_attempts") == 0,
        "nested_prior_and_posterior_distinguished": nested_checks.get("prior_and_posterior_distinguished") is True,
        "nested_synthetic_literal_boundary_preserved": nested_checks.get("synthetic_literal_boundary_preserved") is True,
        "unsupported_writes_absent": nested_checks.get("unsupported_writes_absent") is True
        and nested_write_violations == 0,
        "human_content_judgment_absent": nested_checks.get("human_content_judgment_absent") is True,
    }
    receipt["claims"] = {
        "proves": [
            f"live no-write PCTOM-R Memory delayed recall was accepted only after elapsed_age_s >= min_age_s ({elapsed_age_s} >= {min_age_s})",
            "the nested delayed-recall checker exact-reread prior noncanonical research documents and searchable mirrors",
            "the nested delayed-recall checker retrieved condition-scoped revision context through live Memory /recall",
            "prior/posterior distinction and synthetic/literal separation survived aged delayed recall",
            "the aged-retention wrapper and nested checker used zero Memory writes, provider calls, Tau calls, canonical writes, identity writes, source-memory writes, LLM judges, or human content judgment",
        ]
        if not errors
        else [
            "the aged-retention wrapper failed closed before accepting aged delayed recall evidence",
        ],
        "does_not_prove": [
            "multi-day wall-clock retention",
            "internet-hosted or permanently deployed Memory service availability",
            "new live Tau execution",
            "paid provider execution",
            "video, audio, or semantic dream quality",
            "complete live Phase 01-16 runtime execution",
        ],
    }
    receipt["processing_time_s"] = round(time.monotonic() - started, 6)
    return _write_receipt(receipt_out, receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--min-age-s", type=int, required=True)
    parser.add_argument("--recall-attempts", type=int, default=3)
    parser.add_argument("--recall-sleep-s", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_memory_aged_retention_recall_receipt.v1.json")
    receipt = run(
        source_root=args.source_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        memory_base_url=args.memory_base_url,
        min_age_s=args.min_age_s,
        recall_attempts=args.recall_attempts,
        recall_sleep_s=args.recall_sleep_s,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
