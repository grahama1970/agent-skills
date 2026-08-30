"""Deterministic truth-status compiler for human-facing run claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ResultStatus
from .util import read_json, sha256_json, utc_now, write_json

DEGRADED_SOURCE_STATUSES = {
    status.value
    for status in ResultStatus
    if status not in {ResultStatus.MATCHES, ResultStatus.NO_MATCHES}
}


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _input_ref(kind: str, path: Path, authoritative_for: list[str]) -> dict[str, Any] | None:
    payload = _read_optional_json(path)
    if payload is None:
        return None
    return {
        "kind": kind,
        "receipt_ref": path.name,
        "sha256": "sha256:" + sha256_json(payload),
        "run_id": payload.get("run_id"),
        "authoritative_for": authoritative_for,
    }


def _opportunity_type(value: object) -> str:
    text = str(value or "").lower()
    if "employment" in text:
        return "employment"
    if "consult" in text or "federal" in text or "commercial" in text:
        return "consulting"
    return "other"


def _source_statuses(source_receipts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for receipt in source_receipts:
        provider = str(receipt.get("provider") or receipt.get("source") or "unknown")
        status = str(receipt.get("result_status") or receipt.get("status") or "UNKNOWN")
        row = sources.setdefault(
            provider,
            {
                "discovery_status": "NO_MATCHES",
                "match_count": 0,
                "receipt_count": 0,
                "degraded_count": 0,
            },
        )
        row["receipt_count"] += 1
        if status == ResultStatus.MATCHES.value:
            row["match_count"] += 1
        if status in DEGRADED_SOURCE_STATUSES or status == "UNKNOWN":
            row["degraded_count"] += 1
            row["discovery_status"] = status
        elif row["discovery_status"] not in DEGRADED_SOURCE_STATUSES:
            row["discovery_status"] = (
                ResultStatus.MATCHES.value
                if int(row["match_count"]) > 0
                else ResultStatus.NO_MATCHES.value
            )
    return sources


def _provider_receipts(run_dir: Path) -> list[dict[str, Any]]:
    provider_root = run_dir / "tau-semantic" / "providers"
    if not provider_root.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for path in sorted(provider_root.glob("*/tau-semantic-provider-receipt.json")):
        payload = _read_optional_json(path)
        if payload is not None:
            payload["_receipt_ref"] = path.relative_to(run_dir).as_posix()
            receipts.append(payload)
    return receipts


def compile_truth_status(run_dir: Path, *, write: bool = True) -> dict[str, Any]:
    """Compile one receipt-derived status artifact for human-facing claims."""

    run_receipt_path = run_dir / "run-receipt.json"
    nightly_receipt_path = run_dir / "nightly-receipt.json"
    manifest_path = run_dir / "report-manifest.json"
    report_path = run_dir / "report" / "report.json"
    stage_ledger_path = run_dir / "stage-ledger.json"
    replay_path = run_dir / "zero-effect-replay-receipt.json"
    discord_path = run_dir / "discord-handoff" / "morning-discord-receipt.json"
    tau_prepare_path = run_dir / "tau-semantic" / "tau-semantic-prepare-receipt.json"

    run_receipt = _read_optional_json(run_receipt_path) or {}
    nightly_receipt = _read_optional_json(nightly_receipt_path) or {}
    manifest = _read_optional_json(manifest_path) or {}
    report = _read_optional_json(report_path) or {}
    stage_ledger = _read_optional_json(stage_ledger_path) or {}
    replay = _read_optional_json(replay_path) or {}
    discord = _read_optional_json(discord_path) or {}
    tau_prepare = _read_optional_json(tau_prepare_path) or {}
    tau_providers = _provider_receipts(run_dir)

    blocking_codes: list[str] = []
    degradation_codes: list[str] = []
    suppressed_claims: list[dict[str, Any]] = []

    if not run_receipt:
        blocking_codes.append("RUN_RECEIPT_MISSING")
    if not manifest:
        blocking_codes.append("MANIFEST_MISSING")
    if not report:
        blocking_codes.append("REPORT_JSON_MISSING")

    run_id = str(manifest.get("run_id") or run_receipt.get("run_id") or run_dir.name)
    source_receipts = [
        row for row in manifest.get("source_receipts", []) if isinstance(row, dict)
    ]
    sources = _source_statuses(source_receipts)
    degraded_sources = {
        name: row
        for name, row in sources.items()
        if row.get("discovery_status") in DEGRADED_SOURCE_STATUSES
        or int(row.get("degraded_count") or 0) > 0
    }
    if degraded_sources:
        degradation_codes.append("SOURCE_COVERAGE_DEGRADED")

    opportunities = [row for row in manifest.get("opportunities", []) if isinstance(row, dict)]
    rendered = [row for row in report.get("opportunities", []) if isinstance(row, dict)]
    employment = sum(1 for row in opportunities if _opportunity_type(row.get("opportunity_type")) == "employment")
    consulting = sum(1 for row in opportunities if _opportunity_type(row.get("opportunity_type")) == "consulting")
    other = len(opportunities) - employment - consulting
    if len(rendered) != len(opportunities):
        blocking_codes.append("REPORT_COUNT_MISMATCH")

    ledger_counts = stage_ledger.get("counts") if isinstance(stage_ledger.get("counts"), dict) else {}
    discovered = int(ledger_counts.get("discovered") or 0)
    accepted = int(ledger_counts.get("accepted") or 0)
    deduplicated = int(ledger_counts.get("deduplicated") or 0)
    eligible_not_shortlisted = int(ledger_counts.get("eligible_not_shortlisted") or 0)
    rejected = int(ledger_counts.get("rejected") or 0)
    unaccounted = int(ledger_counts.get("unaccounted") or 0)
    ledger_equation_ok = True
    if stage_ledger:
        ledger_equation_ok = (
            stage_ledger.get("ok") is True
            and unaccounted == 0
            and (
                discovered == 0
                or discovered == accepted + deduplicated + eligible_not_shortlisted + rejected
                or discovered == accepted + rejected
            )
        )
    if stage_ledger and not ledger_equation_ok:
        blocking_codes.append("LEDGER_ACCOUNTING_MISMATCH")

    provider_statuses = [str(receipt.get("status") or "UNKNOWN") for receipt in tau_providers]
    provider_live_receipts = [
        receipt for receipt in tau_providers
        if receipt.get("status") == "PASS" and receipt.get("provider_live") is True
    ]
    provider_live = bool(provider_live_receipts)
    tau_step = (nightly_receipt.get("steps") or {}).get("tau_semantic") or {}
    tau_claims_provider_live = tau_step.get("provider_live") is True
    tau_prepare_has_legacy_provider_live = "provider_live" in tau_prepare
    tau_provider_unproven = tau_claims_provider_live and not provider_live
    if tau_provider_unproven:
        blocking_codes.append("TAU_PROVIDER_LIVE_UNPROVEN")
        suppressed_claims.append(
            {
                "claim_id": "tau.provider.live",
                "status": "SUPPRESSED",
                "reason_code": "TAU_PROVIDER_LIVE_UNPROVEN",
                "evidence_refs": [nightly_receipt_path.name],
            }
        )
    elif provider_live:
        suppressed_claims.append(
            {
                "claim_id": "tau.provider.live",
                "status": "VERIFIED",
                "reason_code": "TAU_PROVIDER_RECEIPT_BOUND",
                "evidence_refs": [
                    str(receipt.get("_receipt_ref")) for receipt in provider_live_receipts
                ],
            }
        )

    tau_status = "NOT_RUN"
    if tau_prepare:
        tau_status = "PASS" if tau_prepare.get("status") == "PASS" else "FAILED"
    if tau_provider_unproven:
        tau_status = "CONFLICT"
    elif tau_providers:
        tau_status = "LIVE" if provider_live and all(status == "PASS" for status in provider_statuses) else "FAILED"

    discord_handoff = {
        "status": "NOT_ATTEMPTED",
        "http_status": None,
        "message_id": None,
        "message_url": None,
    }
    if discord:
        ops_receipt = discord.get("ops_discord_receipt") if isinstance(discord.get("ops_discord_receipt"), dict) else {}
        http_status = ops_receipt.get("http_status")
        message_id = ops_receipt.get("message_id") or discord.get("message_id")
        sent = (
            discord.get("status") == "PASS"
            and discord.get("ops_discord_status") == "SENT"
            and isinstance(http_status, int)
            and 200 <= http_status < 300
            and bool(message_id)
        )
        discord_handoff = {
            "status": "SENT" if sent else "FAILED",
            "http_status": http_status,
            "message_id": message_id,
            "message_url": discord.get("message_url"),
        }
        if not sent:
            degradation_codes.append("HANDOFF_SENT_UNPROVEN")

    trigger = str(run_receipt.get("trigger") or "MANUAL_SCHEDULER_EQUIVALENCE")
    scheduler_execution = (
        "SCHEDULER_PASS"
        if trigger == "SCHEDULER"
        else "MANUAL_EQUIVALENCE_PASS"
        if run_receipt.get("live") is True
        else "UNPROVEN"
    )
    nightly_reliability = "PROVEN" if trigger == "SCHEDULER" else "UNPROVEN"
    if nightly_reliability == "UNPROVEN":
        degradation_codes.append("SCHEDULER_RELIABILITY_UNPROVEN")

    eval_mode = "UNKNOWN"
    if (run_dir / "agentic-eval-report.json").exists():
        eval_report = _read_optional_json(run_dir / "agentic-eval-report.json") or {}
        if eval_report.get("live") is True:
            eval_mode = "LIVE"
        elif eval_report.get("fixture_backed") is True:
            eval_mode = "FIXTURE_BACKED"
            degradation_codes.append("FIXTURE_ASSURANCE_ESCALATION")

    core_verified = (
        run_receipt.get("live") is True
        and run_receipt.get("mocked") is False
        and run_receipt.get("external_effects") is False
        and replay.get("status") in {None, "PASS"}
        and len(blocking_codes) == 0
        and ledger_equation_ok
    )

    disposition = "WITHHOLD" if blocking_codes else "EMIT_DEGRADED" if degradation_codes else "EMIT_VERIFIED"
    overall = "FAILED" if blocking_codes else "DEGRADED" if degradation_codes else "VERIFIED"

    inputs = [
        item
        for item in [
            _input_ref("execution", run_receipt_path, ["execution.live", "execution.mocked", "execution.external_effects"]),
            _input_ref("nightly", nightly_receipt_path, ["tau.steps", "truth_status.binding"]),
            _input_ref("manifest", manifest_path, ["opportunities", "sources", "relationship_signals"]),
            _input_ref("report", report_path, ["rendered_row_count"]),
            _input_ref("stage_ledger", stage_ledger_path, ["ledger.counts"]),
            _input_ref("zero_effect_replay", replay_path, ["effects.zero_replay"]),
            _input_ref("discord_handoff", discord_path, ["delivery.discord_handoff"]),
            _input_ref("tau_prepare", tau_prepare_path, ["tau.prepare"]),
        ]
        if item is not None
    ]

    receipt = {
        "schema": "monitor_opportunities.truth_status.v1",
        "generated_at": utc_now(),
        "run_id": run_id,
        "compiler_version": "truth_status.v1",
        "inputs": inputs,
        "report_disposition": disposition,
        "overall_status": overall,
        "blocking_codes": sorted(set(blocking_codes)),
        "degradation_codes": sorted(set(degradation_codes)),
        "execution": {
            "status": "VERIFIED" if core_verified else "FAILED" if blocking_codes else "DEGRADED",
            "trigger": trigger,
            "live": run_receipt.get("live"),
            "mocked": run_receipt.get("mocked"),
            "external_effects": run_receipt.get("external_effects"),
            "exit_code": run_receipt.get("exit_code"),
        },
        "integrity": {
            "ledger_equation_ok": ledger_equation_ok,
            "unaccounted": unaccounted,
            "report_count_match": len(rendered) == len(opportunities),
        },
        "opportunities": {
            "total": len(opportunities),
            "employment": employment,
            "consulting": consulting,
            "other": other,
            "rendered_row_count": len(rendered),
        },
        "sources": sources,
        "tau": {
            "policy": "EVIDENCE_GATE",
            "status": tau_status,
            "prepare_status": tau_prepare.get("status"),
            "prepare_provider_live_legacy": tau_prepare.get("provider_live") if tau_prepare_has_legacy_provider_live else None,
            "provider_statuses": provider_statuses,
            "provider_live": None if tau_provider_unproven else provider_live,
            "consistency": "FAIL" if tau_provider_unproven else "PASS",
        },
        "delivery": {"discord_handoff": discord_handoff},
        "assurance": {
            "scheduler_execution": scheduler_execution,
            "nightly_reliability": nightly_reliability,
            "agentic_eval_mode": eval_mode,
        },
        "claims": suppressed_claims,
        "external_effects": False,
        "mocked": False,
        "live": bool(run_receipt.get("live", False)),
    }
    if write:
        write_json(run_dir / "truth-status.json", receipt)
    return receipt
