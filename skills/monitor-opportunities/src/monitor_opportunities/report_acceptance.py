"""Acceptance gate for a completed monitor-opportunities report run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ContractError, ResultStatus, validate_manifest
from .pipeline import build_receipt_consistency
from .util import read_json, write_json


def validate_report_acceptance(
    run_dir: Path, *, require_zero_effect_replay: bool = True
) -> dict[str, Any]:
    """Validate report-visible claims, provenance, degradation, and zero effects."""

    run_receipt_path = run_dir / "run-receipt.json"
    manifest_path = run_dir / "report-manifest.json"
    report_json_path = run_dir / "report" / "report.json"
    report_html_path = run_dir / "report" / "index.html"
    zero_effect_path = run_dir / "zero-effect-replay-receipt.json"
    failures: list[dict[str, Any]] = []

    def fail(check: str, detail: str) -> None:
        failures.append({"check": check, "detail": detail})

    run_receipt = read_json(run_receipt_path) if run_receipt_path.exists() else {}
    manifest_raw = read_json(manifest_path) if manifest_path.exists() else {}

    if not run_receipt_path.exists():
        fail("run_receipt_present", "run-receipt.json is missing")
    if not manifest_path.exists():
        fail("manifest_present", "report-manifest.json is missing")
    if not report_json_path.exists():
        fail("report_json_present", "report/report.json is missing")
    if not report_html_path.exists():
        fail("report_html_present", "report/index.html is missing")

    manifest = None
    if manifest_raw:
        try:
            manifest = validate_manifest(manifest_raw)
        except ContractError as exc:
            fail("manifest_contract", f"{exc.code}: {exc.message}")

    consistency = build_receipt_consistency(
        run_dir=run_dir,
        receipt=run_receipt,
        manifest=manifest_raw,
    )
    if consistency["status"] != "PASS":
        fail("receipt_consistency", "receipt consistency status is not PASS")

    zero_effect = read_json(zero_effect_path) if zero_effect_path.exists() else None
    if require_zero_effect_replay and zero_effect is None:
        fail("zero_effect_replay_present", "zero-effect-replay-receipt.json is missing")
    if zero_effect is not None and zero_effect.get("status") != "PASS":
        fail("zero_effect_replay", "zero-effect replay status is not PASS")

    if run_receipt and run_receipt.get("external_effects") is not False:
        fail("run_external_effects", "run receipt external_effects is not false")

    source_receipts = manifest_raw.get("source_receipts") or []
    degraded_statuses = {
        status.value
        for status in ResultStatus
        if status not in {ResultStatus.MATCHES, ResultStatus.NO_MATCHES}
    }
    degraded_receipts = [
        row for row in source_receipts if row.get("result_status") in degraded_statuses
    ]
    degraded_without_limitations = [
        str(row.get("receipt_id") or row.get("provider") or "unknown")
        for row in degraded_receipts
        if not row.get("limitations")
    ]
    if degraded_without_limitations:
        fail(
            "degraded_source_limitations",
            "degraded source receipts lack limitations: "
            + ", ".join(degraded_without_limitations[:12]),
        )

    application_packets = manifest_raw.get("application_packets") or []
    authorized_packets = [
        str(row.get("packet_id") or row.get("application_id") or "unknown")
        for row in application_packets
        if row.get("approval_status") != "NOT_AUTHORIZED"
        or row.get("external_effects") is not False
    ]
    if authorized_packets:
        fail(
            "application_packets_human_authorized_only",
            "application packets are authorized or externally effectful: "
            + ", ".join(authorized_packets[:12]),
        )

    opportunity_count = len(manifest_raw.get("opportunities") or [])
    if opportunity_count > 8:
        fail("shortlist_bound", f"{opportunity_count} opportunities exceeds max 8")

    status = "PASS" if not failures else "FAIL"
    receipt = {
        "schema": "monitor_opportunities.report_acceptance_receipt.v1",
        "status": status,
        "run_dir": str(run_dir),
        "checks": {
            "run_receipt_present": run_receipt_path.exists(),
            "manifest_present": manifest_path.exists(),
            "report_json_present": report_json_path.exists(),
            "report_html_present": report_html_path.exists(),
            "manifest_contract_pass": manifest is not None,
            "receipt_consistency_pass": consistency["status"] == "PASS",
            "zero_effect_replay_required": require_zero_effect_replay,
            "zero_effect_replay_present": zero_effect is not None,
            "zero_effect_replay_pass": (
                zero_effect.get("status") == "PASS" if zero_effect is not None else False
            ),
            "run_external_effects_false": run_receipt.get("external_effects") is False,
            "shortlist_bound": opportunity_count <= 8,
            "application_packets_human_authorized_only": not authorized_packets,
            "degraded_source_limitations_present": not degraded_without_limitations,
        },
        "counts": {
            "opportunities": opportunity_count,
            "source_intel": len(manifest_raw.get("source_intel") or []),
            "relationship_signals": len(manifest_raw.get("relationship_signals") or []),
            "source_receipts": len(source_receipts),
            "degraded_source_receipts": len(degraded_receipts),
            "application_packets": len(application_packets),
        },
        "receipt_consistency": consistency,
        "failures": failures,
        "external_effects": False,
        "mocked": False,
        "live": bool(run_receipt.get("live", False)),
    }
    write_json(run_dir / "report-acceptance-receipt.json", receipt)
    return receipt
