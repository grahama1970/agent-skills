"""Single local Stage 0 run transaction composed from read-only phase artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE
from .discovery import sweep
from .ranking import rank
from .report import load_manifest, render_report
from .tailoring import tailor
from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json


def _capability_authority() -> dict[str, str]:
    return {
        "local_report": "ALLOWED",
        "local_resume_variant": "ALLOWED",
        "gmail_mailbox_draft_create": "BLOCKED_STAGE_0",
        "linkedin_human_handoff_ready": "BLOCKED_STAGE_0",
        "ats_form_inspect": "BLOCKED_STAGE_0",
        "ats_form_prefill": "BLOCKED_STAGE_0",
        "ats_form_submit": "BLOCKED_STAGE_0",
    }


def _source_receipts(discovery_dir: Path) -> list[dict[str, Any]]:
    receipts = []
    for row in read_jsonl(discovery_dir / "source-receipts.jsonl"):
        receipts.append(
            {
                "receipt_id": row["receipt_id"],
                "lane": row["lane"],
                "provider": row["provider"],
                "target": row["target"],
                "source_class": row["source_class"],
                "result_status": row["result_status"],
                "observed_at": row["observed_at"],
                "request_summary": row["request_summary"],
                "response_status": row.get("response_status"),
                "content_type": row.get("content_type"),
                "response_bytes": row.get("response_bytes", 0),
                "content_sha256": row.get("content_sha256"),
                "evidence_refs": row.get("evidence_refs", []),
                "limitations": row.get("limitations", []),
            }
        )
    return receipts


def _lane_coverage(discovery_dir: Path, shortlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = read_json(discovery_dir / "lane-summaries.json")
    admitted_by_lane: dict[str, int] = {}
    for candidate in shortlist:
        admitted_by_lane[candidate["lane"]] = admitted_by_lane.get(candidate["lane"], 0) + 1
    return [
        {
            "lane": row["lane"],
            "searched": row["searched"],
            "result_status": row["result_status"],
            "candidates_observed": row["candidates_observed"],
            "candidates_admitted": admitted_by_lane.get(row["lane"], 0),
            "source_receipt_ids": row["source_receipt_ids"],
            "limitations": row.get("limitations", []),
        }
        for row in summaries
    ]


def _opportunity(candidate: dict[str, Any]) -> dict[str, Any]:
    source_id = candidate.get("source_receipt_id") or candidate.get("source_receipt_ids", ["unknown"])[0]
    if candidate["lane"] == "C":
        opportunity_type = "commercial_signal"
        observed = ["Primary-source need signal observed."]
        inferred = ["Use a capability profile; do not send outreach automatically."]
        claim_keys = ["claim:pdf-oxide:document-extraction"]
    else:
        opportunity_type = "employment_posting"
        observed = [f"{candidate.get('source_provider', 'ATS')} source observed."]
        inferred = ["Single-column ATS-readable resume is prudent."]
        claim_keys = ["claim:arcos:acert-architect"]
    return {
        "opportunity_id": candidate["candidate_id"],
        "lane": candidate["lane"],
        "opportunity_type": opportunity_type,
        "title": candidate["title"],
        "organization": candidate["organization"],
        "location": {
            "display": candidate.get("location_display", "Unknown"),
            "workplace_type": candidate.get("workplace_type", "UNKNOWN"),
            "relocation_required": bool(candidate.get("relocation_required", False)),
        },
        "source_receipt_ids": [source_id],
        "eligibility_state": candidate["eligibility_state"],
        "fit_score": float(candidate.get("fit_score", 0.0)),
        "claim_keys": claim_keys,
        "why_candidate": ["Ranked after deterministic eligibility gating and source receipt readback."],
        "screening_interface_profile": {
            "observed": observed,
            "inferred": inferred,
            "confidence": 0.6,
            "evidence_refs": [source_id],
            "unknowns": ["Employer/client ranking weights and workflow remain unknown."],
        },
        "status": "SHORTLISTED",
        "action_worthy": True,
        "visible_in_report": True,
    }


def _rejection(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "rejection_id": stable_id("reject", candidate["candidate_id"]),
        "lane": candidate["lane"],
        "title": candidate["title"],
        "organization": candidate["organization"],
        "reason_code": candidate["eligibility_state"],
        "source_receipt_id": candidate.get("source_receipt_id", "unknown"),
        "action_worthy": False,
        "visible_in_report": True,
    }


def _resume_variant(tailoring_dir: Path, fallback_opportunity_id: str | None) -> list[dict[str, Any]]:
    variant_path = tailoring_dir / "resume-variant.json"
    diff_path = tailoring_dir / "presentation-diff.json"
    if not variant_path.exists() or fallback_opportunity_id is None:
        return []
    variant = read_json(variant_path)
    diff = read_json(diff_path)
    return [
        {
            "variant_id": variant["variant_id"],
            "opportunity_id": fallback_opportunity_id,
            "claim_snapshot_sha256": variant["claim_snapshot_sha256"],
            "claim_keys": [ref["claim_key"] for ref in variant["claim_refs"]],
            "artifact_refs": variant["artifact_refs"],
            "presentation_diff": {
                "allowed_changes": diff["allowed_changes"],
                "prohibited_changes": diff["prohibited_changes"],
            },
            "status": variant["status"],
            "action_worthy": True,
            "visible_in_report": True,
        }
    ]


def _report_from_run(run_id: str, discovery_dir: Path, ranking_dir: Path, tailoring_dir: Path) -> dict[str, Any]:
    shortlist = read_json(ranking_dir / "shortlist.json")
    rejections = read_json(ranking_dir / "rejections.json")
    opportunities = [_opportunity(candidate) for candidate in shortlist]
    first_opportunity_id = opportunities[0]["opportunity_id"] if opportunities else None
    resume_variants = _resume_variant(tailoring_dir, first_opportunity_id)
    outreach_packets = [
        {
            "packet_id": stable_id("outreach", opportunity["opportunity_id"]),
            "opportunity_id": opportunity["opportunity_id"],
            "channel": "GMAIL",
            "subject": f"Human-transmitted follow-up for {opportunity['organization']}",
            "body": "Stage 0 local handoff text only. The human decides whether to transmit.",
            "claim_keys": opportunity["claim_keys"],
            "roundtable_status": "NOT_RUN",
            "effect_status": "WOULD_PRESENT_STAGE0",
            "sendable": False,
            "candidate_transmits": True,
            "action_worthy": True,
            "visible_in_report": True,
        }
        for opportunity in opportunities
    ]
    applications = [
        {
            "application_id": stable_id("application", opportunity["opportunity_id"]),
            "opportunity_id": opportunity["opportunity_id"],
            "ats_provider": "greenhouse" if opportunity["lane"] == "A" else None,
            "state": "BLOCKED_STAGE_0",
            "authorized": False,
            "form_schema_digest": sha256_json({"opportunity_id": opportunity["opportunity_id"], "stage": STAGE}),
            "fields": [
                {
                    "name": "Why this role?",
                    "field_type": "free_text",
                    "required": True,
                    "disposition": "human_required",
                    "automated_answer": None,
                }
            ],
            "action_worthy": True,
            "visible_in_report": True,
        }
        for opportunity in opportunities
        if opportunity["lane"] == "A"
    ]
    interview_prep = [
        {
            "opportunity_id": opportunity["opportunity_id"],
            "talking_points": [
                {
                    "text": "Explain receipt-gated, claim-bound work with explicit source boundaries.",
                    "claim_keys": opportunity["claim_keys"],
                    "source_refs": opportunity["source_receipt_ids"],
                }
            ],
        }
        for opportunity in opportunities
    ]
    action_worthy_total = len(opportunities) + len(resume_variants) + len(outreach_packets) + len(applications)
    return {
        "schema": "monitor_opportunities.report.v1",
        "run_id": run_id,
        "generated_at": utc_now(),
        "contract_version": CONTRACT_VERSION,
        "immutable_goal": {"text": IMMUTABLE_GOAL, "goal_hash": sha256_json(IMMUTABLE_GOAL)},
        "stage": STAGE,
        "operational_readiness": "STAGE_0_LOCAL_READY",
        "capability_authority": _capability_authority(),
        "lane_coverage": _lane_coverage(discovery_dir, shortlist),
        "source_receipts": _source_receipts(discovery_dir),
        "eligibility_rejections": [_rejection(candidate) for candidate in rejections],
        "opportunities": opportunities,
        "resume_variants": resume_variants,
        "outreach_packets": outreach_packets,
        "applications": applications,
        "interview_prep": interview_prep,
        "decision_actions": [
            {"action": action, "target_type": "local_report_item", "enabled": True, "effects_external": False}
            for action in [
                "KEEP",
                "REJECT",
                "DEFER",
                "ACCEPT_RESUME_VARIANT",
                "PROPOSE_CLAIM_AMENDMENT",
                "WITHHOLD_APPLICATION",
                "AUTHORIZE_APPLICATION_PAYLOAD",
                "MARK_HUMAN_SENT_GMAIL",
                "MARK_HUMAN_SENT_LINKEDIN",
            ]
        ],
        "artifact_accounting": {
            "action_worthy_total": action_worthy_total,
            "visible_total": action_worthy_total,
            "hidden_total": 0,
            "hidden_ids": [],
        },
        "non_claims": [
            "Stage 0 run proves local read-only artifacts for this invocation only.",
            "No Gmail, LinkedIn, ATS, Memory, or external application effect was executed.",
            "Employer/client ranking weights and workflows remain unknown.",
        ],
    }


def run_stage0(skill_dir: Path, out_dir: Path, fixture_dir: Path | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = stable_id("run", {"out": str(out_dir), "started": utc_now()})
    phases = []
    discovery_dir = out_dir / "discovery"
    ranking_dir = out_dir / "ranking"
    tailoring_dir = out_dir / "tailoring"
    report_dir = out_dir / "report"

    discovery_receipt = sweep(
        skill_dir=skill_dir,
        lanes={"A", "B", "C"},
        out_dir=discovery_dir,
        fixture_dir=fixture_dir,
    )
    phases.append({"phase": "DISCOVERY_COMPLETE", "artifact": str(discovery_dir / "run-manifest.json")})
    ranking_receipt = rank(discovery_dir, 8, ranking_dir)
    phases.append({"phase": "RANKING_COMPLETE", "artifact": str(ranking_dir / "ranking-receipt.json")})
    claims_path = skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json"
    tailoring_receipt = None
    if claims_path.exists():
        tailoring_receipt = tailor("fixture:eligible-ai-architect", claims_path, tailoring_dir)
        phases.append({"phase": "TAILORING_COMPLETE", "artifact": str(tailoring_dir / "tailoring-receipt.json")})

    manifest_path = out_dir / "report-manifest.json"
    report_manifest = _report_from_run(run_id, discovery_dir, ranking_dir, tailoring_dir)
    write_json(manifest_path, report_manifest)
    manifest = load_manifest(manifest_path)
    render_artifacts = render_report(manifest, report_dir)
    phases.append({"phase": "REPORT_READY", "artifact": render_artifacts["report_html"]})
    receipt = {
        "schema": "monitor_opportunities.run_receipt.v1",
        "run_id": run_id,
        "started_at": report_manifest["generated_at"],
        "completed_at": utc_now(),
        "terminal_state": "AWAITING_HUMAN",
        "mocked": False,
        "live": fixture_dir is None,
        "external_effects": False,
        "immutable_goal": IMMUTABLE_GOAL,
        "budget": {"currency": "USD", "max": 10.0, "estimated": 0.0, "actual": 0.0},
        "phase_artifacts": phases,
        "discovery_receipt": discovery_receipt,
        "ranking_receipt": ranking_receipt,
        "tailoring_receipt": tailoring_receipt,
        "report_manifest_sha256": sha256_json(report_manifest),
        "report_html": render_artifacts["report_html"],
        "report_json": render_artifacts["report_json"],
    }
    write_json(out_dir / "run-receipt.json", receipt)
    return receipt


def status_for_run(run_dir: Path) -> dict[str, Any]:
    receipt_path = run_dir / "run-receipt.json"
    if not receipt_path.exists():
        return {"schema": "monitor_opportunities.run_status.v1", "run_dir": str(run_dir), "state": "NOT_FOUND"}
    receipt = read_json(receipt_path)
    manifest_path = run_dir / "report-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else None
    projection_path = run_dir / "decision-projection.json"
    projection = read_json(projection_path) if projection_path.exists() else {"items": {}}
    completed_at = receipt.get("completed_at")
    current_stale = _is_stale(completed_at)
    accounting = manifest.get("artifact_accounting", {}) if manifest else {}
    action_worthy_total = int(accounting.get("action_worthy_total", 0))
    decided_total = len(projection.get("items", {}))
    return {
        "schema": "monitor_opportunities.run_status.v1",
        "run_dir": str(run_dir),
        "run_id": receipt["run_id"],
        "state": receipt["terminal_state"],
        "last_attempt": completed_at,
        "last_complete_report": receipt.get("report_html"),
        "current_stale": current_stale,
        "stale_policy": "stale when no completed report exists or completed_at is older than 24 hours",
        "lane_health": [
            {
                "lane": lane["lane"],
                "status": lane["result_status"],
                "observed": lane["candidates_observed"],
                "admitted": lane["candidates_admitted"],
            }
            for lane in (manifest or {}).get("lane_coverage", [])
        ],
        "dependency_readiness": {
            "discovery": "READY" if (run_dir / "discovery" / "run-manifest.json").exists() else "MISSING",
            "ranking": "READY" if (run_dir / "ranking" / "ranking-receipt.json").exists() else "MISSING",
            "tailoring": "READY" if (run_dir / "tailoring" / "tailoring-receipt.json").exists() else "MISSING",
            "report": "READY" if receipt.get("report_html") and Path(receipt["report_html"]).exists() else "MISSING",
        },
        "budget": receipt.get("budget", {}),
        "artifact_accounting": accounting,
        "unresolved_decisions": max(action_worthy_total - decided_total, 0),
        "indeterminate_effect_state": False,
        "report_html": receipt["report_html"],
        "external_effects": receipt["external_effects"],
    }


def _is_stale(completed_at: str | None) -> bool:
    if not completed_at:
        return True
    try:
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - completed).total_seconds() > 24 * 60 * 60
