"""Acceptance gate for a completed monitor-opportunities report run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ContractError, ResultStatus, validate_manifest
from .pipeline import build_receipt_consistency
from .util import read_json, sha256_json, write_json

REQUIRED_ZERO_EFFECT_CHECKS = (
    "projection_external_effects_false",
    "decision_events_external_effects_false",
    "run_receipt_external_effects_false",
    "receipt_consistency_pass",
    "effect_policy_external_effects_false",
)


def _same_path(value: object, expected: Path) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return Path(value).resolve() == expected.resolve()
    except OSError:
        return False


def _json_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return sha256_json(read_json(path))


def _validate_zero_effect_replay_binding(
    *,
    run_dir: Path,
    zero_effect: dict[str, Any],
    run_receipt: dict[str, Any],
    manifest: dict[str, Any],
    fail: Any,
) -> dict[str, bool]:
    projection_path = run_dir / "decision-projection.json"
    ledger_path = run_dir / "decision-ledger.jsonl"
    run_receipt_path = run_dir / "run-receipt.json"
    consistency_path = run_dir / "receipt-consistency.json"
    effect_policy_path = run_dir / "effect-policy-receipt.json"
    attestation_path = run_dir / "run-attestation.json"

    checks: dict[str, bool] = {
        "zero_effect_replay_schema": zero_effect.get("schema")
        == "monitor_opportunities.zero_effect_replay_receipt.v1",
        "zero_effect_replay_external_effects_false": zero_effect.get("external_effects")
        is False,
        "zero_effect_replay_run_dir_bound": _same_path(zero_effect.get("run_dir"), run_dir),
    }
    for key, ok in checks.items():
        if not ok:
            fail(key, f"zero-effect replay receipt failed {key}")

    replay_checks = zero_effect.get("checks") or {}
    failed_replay_checks = [
        key for key in REQUIRED_ZERO_EFFECT_CHECKS if replay_checks.get(key) is not True
    ]
    if failed_replay_checks:
        checks["zero_effect_replay_required_checks_true"] = False
        fail(
            "zero_effect_replay_required_checks_true",
            "zero-effect replay checks are not true: "
            + ", ".join(failed_replay_checks),
        )
    else:
        checks["zero_effect_replay_required_checks_true"] = True

    artifacts = zero_effect.get("artifacts") or {}
    expected_artifacts = {
        "decision_projection": projection_path,
        "run_receipt": run_receipt_path,
        "receipt_consistency": consistency_path,
    }
    if ledger_path.exists():
        expected_artifacts["decision_ledger"] = ledger_path
    if effect_policy_path.exists():
        expected_artifacts["effect_policy"] = effect_policy_path
    if attestation_path.exists():
        expected_artifacts["run_attestation"] = attestation_path

    bad_artifacts = [
        key
        for key, path in expected_artifacts.items()
        if not path.exists() or not _same_path(artifacts.get(key), path)
    ]
    if bad_artifacts:
        checks["zero_effect_replay_artifacts_bound"] = False
        fail(
            "zero_effect_replay_artifacts_bound",
            "zero-effect replay artifacts are missing or stale: "
            + ", ".join(bad_artifacts),
        )
    else:
        checks["zero_effect_replay_artifacts_bound"] = True

    manifest_sha = sha256_json(manifest) if manifest else None
    projection = read_json(projection_path) if projection_path.exists() else {}
    consistency = read_json(consistency_path) if consistency_path.exists() else {}
    effect_policy = read_json(effect_policy_path) if effect_policy_path.exists() else {}
    attestation = read_json(attestation_path) if attestation_path.exists() else {}
    attestation_code = attestation.get("code") or {}
    binding = zero_effect.get("binding") or {}
    expected_binding = {
        "run_id": run_receipt.get("run_id"),
        "manifest_run_id": manifest.get("run_id"),
        "report_manifest_sha256": manifest_sha,
        "run_receipt_report_manifest_sha256": run_receipt.get("report_manifest_sha256"),
        "run_receipt_sha256": _json_sha256(run_receipt_path),
        "decision_projection_sha256": _json_sha256(projection_path),
        "projection_digest": projection.get("projection_digest"),
        "receipt_consistency_sha256": _json_sha256(consistency_path),
        "receipt_consistency_status": consistency.get("status"),
        "effect_policy_sha256": _json_sha256(effect_policy_path),
        "effect_policy_mode": effect_policy.get("mode") if effect_policy else None,
        "run_attestation_sha256": _json_sha256(attestation_path),
        "source_revision": attestation_code.get("git_revision") if attestation else None,
        "source_revision_full": attestation_code.get("git_revision_full")
        if attestation
        else None,
    }
    mismatches = [
        key
        for key, expected in expected_binding.items()
        if expected is not None and binding.get(key) != expected
    ]
    if mismatches:
        checks["zero_effect_replay_binding_current"] = False
        fail(
            "zero_effect_replay_binding_current",
            "zero-effect replay binding does not match current run artifacts: "
            + ", ".join(mismatches),
        )
    else:
        checks["zero_effect_replay_binding_current"] = True

    if (
        run_receipt.get("run_id")
        and manifest.get("run_id")
        and run_receipt.get("run_id") != manifest.get("run_id")
    ):
        checks["run_manifest_ids_match"] = False
        fail("run_manifest_ids_match", "run receipt and manifest run_id differ")
    else:
        checks["run_manifest_ids_match"] = True

    if run_receipt.get("report_manifest_sha256") != manifest_sha:
        checks["run_manifest_hash_bound"] = False
        fail("run_manifest_hash_bound", "run receipt manifest hash differs from manifest")
    else:
        checks["run_manifest_hash_bound"] = True

    return checks


def validate_report_acceptance(
    run_dir: Path,
    *,
    require_zero_effect_replay: bool = True,
    require_stage_ledger: bool = False,
) -> dict[str, Any]:
    """Validate report-visible claims, provenance, degradation, and zero effects."""

    run_receipt_path = run_dir / "run-receipt.json"
    manifest_path = run_dir / "report-manifest.json"
    report_json_path = run_dir / "report" / "report.json"
    report_html_path = run_dir / "report" / "index.html"
    zero_effect_path = run_dir / "zero-effect-replay-receipt.json"
    stage_ledger_path = run_dir / "stage-ledger.json"
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
    if require_stage_ledger and not stage_ledger_path.exists():
        fail("stage_ledger_present", "stage-ledger.json is missing")

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
    replay_binding_checks: dict[str, bool] = {}
    if zero_effect is not None and zero_effect.get("status") != "PASS":
        fail("zero_effect_replay", "zero-effect replay status is not PASS")
    if zero_effect is not None:
        replay_binding_checks = _validate_zero_effect_replay_binding(
            run_dir=run_dir,
            zero_effect=zero_effect,
            run_receipt=run_receipt,
            manifest=manifest_raw,
            fail=fail,
        )

    if run_receipt and run_receipt.get("external_effects") is not False:
        fail("run_external_effects", "run receipt external_effects is not false")

    stage_ledger = read_json(stage_ledger_path) if stage_ledger_path.exists() else None
    stage_ledger_schema_ok = (
        stage_ledger.get("schema") == "monitor_opportunities.stage_ledger.v1"
        if stage_ledger is not None
        else False
    )
    stage_ledger_pass = (
        stage_ledger.get("ok") is True
        if stage_ledger is not None
        else False
    )
    stage_ledger_violations = (
        len(stage_ledger.get("violations") or []) if stage_ledger is not None else 0
    )
    if stage_ledger is not None and not stage_ledger_schema_ok:
        fail("stage_ledger_schema", "stage-ledger.json has an unexpected schema")
    if require_stage_ledger and stage_ledger is not None and not stage_ledger_pass:
        fail(
            "stage_ledger_pass",
            f"stage-ledger.json is not ok; violations={stage_ledger_violations}",
        )

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
    if opportunity_count == 0:
        fail("shortlist_nonempty", "0 opportunities surfaced; promoted monitor report failed")
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
            **replay_binding_checks,
            "stage_ledger_required": require_stage_ledger,
            "stage_ledger_present": stage_ledger is not None,
            "stage_ledger_schema": stage_ledger_schema_ok,
            "stage_ledger_pass": stage_ledger_pass,
            "run_external_effects_false": run_receipt.get("external_effects") is False,
            "shortlist_nonempty": opportunity_count > 0,
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
            "stage_ledger_violations": stage_ledger_violations,
        },
        "receipt_consistency": consistency,
        "failures": failures,
        "external_effects": False,
        "mocked": False,
        "live": bool(run_receipt.get("live", False)),
    }
    write_json(run_dir / "report-acceptance-receipt.json", receipt)
    return receipt
