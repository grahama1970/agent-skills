"""Single local Stage 0 run transaction composed from read-only phase artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from .application_packets import build_application_packets
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError
from .discovery import sweep
from .outreach import build_outreach_packets
from .ranking import rank
from .report import load_manifest, render_report
from .tailoring import tailor, tailor_candidate
from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json


import os

from dotenv import load_dotenv

load_dotenv(override=False)

# The funnel is a volume game: ~42 applications per interview, 100-200+ cold
# applications per offer (brave-search 2026-08-07, memory
# job-application-funnel-metrics-2026), and tailoring is the biggest lever. So
# surface HUNDREDS of relevant jobs and tailor many, not a top-5 shortlist.
# Tailoring is local + cheap, so it scales wide; both are env-overridable.
def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "")))
    except (TypeError, ValueError):
        return default


SHORTLIST_LIMIT = _int_env("MONITOR_SHORTLIST_LIMIT", 150)
# The rendered human-facing report is a digest; Stage-0 contract caps it at 8.
REPORT_DIGEST_LIMIT = 8
# How many top jobs get a custom targeted resume + apply-prep packet per run.
APPLY_PREP_TOP_N = _int_env("MONITOR_APPLY_PREP_TOP_N", 100)


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


def _load_receipt_map(path: Path | None, *, key_field: str) -> dict[str, dict[str, Any]]:
    """Read a JSON receipt map or list keyed by a stable receipt field."""

    if path is None:
        return {}
    raw = read_json(path)
    rows: list[dict[str, Any]]
    if isinstance(raw, dict) and all(isinstance(value, dict) for value in raw.values()):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, dict):
        candidate_rows = raw.get("receipts") or raw.get("effects")
        rows = candidate_rows if isinstance(candidate_rows, list) else [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []
    return {
        str(row[key_field]): row
        for row in rows
        if isinstance(row, dict) and row.get(key_field) is not None
    }


def _apply_outreach_effects(
    packets: list[dict[str, Any]],
    effects_by_packet_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach read-back effect receipts to matching report-visible outreach packets."""

    if not effects_by_packet_id:
        return packets
    updated: list[dict[str, Any]] = []
    for packet in packets:
        effect = effects_by_packet_id.get(packet["packet_id"])
        if effect is None:
            updated.append(packet)
            continue
        if effect.get("packet_id") != packet["packet_id"]:
            raise ValueError(f"outreach effect packet mismatch: {packet['packet_id']}")
        if effect.get("channel") != packet["channel"]:
            raise ValueError(f"outreach effect channel mismatch: {packet['packet_id']}")
        if effect.get("gmail_sent") is not False or effect.get("linkedin_automated") is not False:
            raise ValueError(f"outreach effect violates no-send/no-automation policy: {packet['packet_id']}")
        state = effect.get("state")
        if state == "DRAFT_CREATED_NOT_SENT":
            if packet["channel"] != "GMAIL":
                raise ValueError(f"non-Gmail packet cannot carry Gmail draft effect: {packet['packet_id']}")
            if packet.get("roundtable_status") != "PASS" or packet.get("readiness_state") != "REVIEW_PERMITTED":
                raise ValueError(f"Gmail draft effect requires reviewed packet: {packet['packet_id']}")
            draft_id = str(effect.get("draft_id") or "")
            if not draft_id:
                raise ValueError(f"Gmail draft effect missing draft_id: {packet['packet_id']}")
            if effect.get("subject_digest") != sha256_json(packet.get("subject") or ""):
                raise ValueError(f"Gmail draft subject digest mismatch: {packet['packet_id']}")
            if effect.get("body_digest") != sha256_json(packet.get("body") or ""):
                raise ValueError(f"Gmail draft body digest mismatch: {packet['packet_id']}")
            updated.append(
                {
                    **packet,
                    "effect_status": state,
                    "draft_id": draft_id,
                    "mailbox_draft_ref": f"gmail:draft:{draft_id}",
                    "effect_receipt_digest": effect.get("receipt_digest"),
                }
            )
            continue
        if state == "INDETERMINATE":
            updated.append(
                {
                    **packet,
                    "effect_status": state,
                    "effect_receipt_digest": effect.get("receipt_digest"),
                }
            )
            continue
        raise ValueError(f"unsupported outreach effect state: {state}")
    return updated


def _source_receipts(discovery_dir: Path) -> list[dict[str, Any]]:
    receipts = []
    for row in read_jsonl(discovery_dir / "source-receipts.jsonl"):
        receipt = {
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
        if row.get("automation_policy"):
            receipt["automation_policy"] = row["automation_policy"]
        receipts.append(receipt)
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
    evidence_url = candidate.get("primary_evidence_url") or candidate.get("posting_url")
    if candidate["lane"] == "B":
        opportunity_type = "federal_notice"
        observed = [f"Federal primary source observed: {evidence_url or source_id}"]
        inferred = ["Treat as a federal notice/signal; do not coerce into an employment application."]
        claim_keys = ["claim:pdf-oxide:document-extraction"]
    elif candidate["lane"] == "C":
        opportunity_type = "commercial_signal"
        observed = [f"Primary-source need signal observed: {evidence_url or source_id}"]
        inferred = ["Use a capability profile; do not send outreach automatically."]
        claim_keys = ["claim:pdf-oxide:document-extraction"]
    elif candidate.get("source_provider") in {"human_supplied_linkedin", "ops_linkedin_authorized_read_only"}:
        opportunity_type = "employment_posting"
        source_label = (
            "ops-linkedin authorized read-only LinkedIn evidence"
            if candidate.get("source_provider") == "ops_linkedin_authorized_read_only"
            else "Human-supplied LinkedIn evidence"
        )
        observed = [
            f"{source_label} observed: {evidence_url or source_id}",
            f"Automation policy: {candidate.get('automation_policy', 'linkedin_no_automation')}",
        ]
        if candidate.get("top_candidate_evidence"):
            observed.append("LinkedIn evidence marks this as a profile/recommendation-based relevance signal.")
        inferred = [
            "Use this as a relevance signal only; leave LinkedIn and inspect primary employer/client sources separately.",
            "Do not connect, message, click apply, scrape, or otherwise automate LinkedIn.",
        ]
        claim_keys = ["claim:arcos:acert-architect"]
    else:
        opportunity_type = "employment_posting"
        observed = [
            f"{candidate.get('source_provider', 'ATS')} primary source observed: {evidence_url or source_id}"
        ]
        inferred = ["Single-column ATS-readable resume is prudent."]
        claim_keys = ["claim:arcos:acert-architect"]
    why_candidate = ["Ranked after deterministic eligibility gating and source receipt readback."]
    if candidate.get("top_candidate_evidence"):
        why_candidate.append("Ranking includes LinkedIn profile/recommendation-based relevance evidence.")
    return {
        "opportunity_id": candidate["candidate_id"],
        "lane": candidate["lane"],
        "opportunity_type": opportunity_type,
        "title": candidate["title"],
        "organization": candidate["organization"],
        "posting_url": candidate.get("posting_url"),
        "apply_url": candidate.get("apply_url"),
        "primary_evidence_url": candidate.get("primary_evidence_url") or candidate.get("posting_url"),
        "location": {
            "display": candidate.get("location_display", "Unknown"),
            "workplace_type": candidate.get("workplace_type", "UNKNOWN"),
            "relocation_required": bool(candidate.get("relocation_required", False)),
        },
        "source_receipt_ids": [source_id],
        "eligibility_state": candidate["eligibility_state"],
        "fit_score": float(candidate.get("fit_score", 0.0)),
        "claim_keys": claim_keys,
        "why_candidate": why_candidate,
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
            "opportunity_id": variant.get("opportunity_id") or fallback_opportunity_id,
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


def _report_from_run(
    run_id: str,
    run_dir: Path,
    discovery_dir: Path,
    ranking_dir: Path,
    tailoring_dir: Path,
    skill_dir: Path,
    roundtable_receipts: dict[str, dict[str, Any]] | None = None,
    outreach_effects: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    shortlist = read_json(ranking_dir / "shortlist.json")
    rejections = read_json(ranking_dir / "rejections.json")
    # The rendered report is a human digest (Stage-0 contract caps it at 8). The
    # full shortlist stays available for apply-prep + memory at volume; only the
    # report is truncated to the top REPORT_DIGEST_LIMIT.
    opportunities = [_opportunity(candidate) for candidate in shortlist[:REPORT_DIGEST_LIMIT]]
    first_opportunity_id = opportunities[0]["opportunity_id"] if opportunities else None
    resume_variants = _resume_variant(tailoring_dir, first_opportunity_id)
    claim_snapshot = read_json(skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json")
    outreach_packets = build_outreach_packets(
        opportunities=opportunities,
        claim_snapshot=claim_snapshot,
        roundtable_receipts=roundtable_receipts,
    )
    outreach_packets = _apply_outreach_effects(outreach_packets, outreach_effects or {})
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
    application_packets = build_application_packets(
        run_dir=run_dir,
        opportunities=opportunities,
        resume_variants=resume_variants,
        outreach_packets=outreach_packets,
        applications=applications,
    )
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
    action_worthy_total = (
        len(opportunities)
        + len(resume_variants)
        + len(outreach_packets)
        + len(applications)
        + len(application_packets)
    )
    gmail_draft_effects = any(packet["effect_status"] == "DRAFT_CREATED_NOT_SENT" for packet in outreach_packets)
    non_claims = [
        "Stage 0 run proves local read-only artifacts for this invocation only.",
        "No Gmail send, LinkedIn platform access, ATS, Memory, or external application effect was executed.",
        "Outreach packets are local human-transmit text until a permitting Ask roundtable and capability-specific promotion exist.",
        "Employer/client ranking weights and workflows remain unknown.",
    ]
    if gmail_draft_effects:
        non_claims[0] = "This report consumed a promoted Gmail draft readback receipt for this invocation only."
        non_claims[2] = "Gmail draft creation remains draft-only; THE HUMAN TRANSMITS and the skill never sends Gmail."

    return {
        "schema": "monitor_opportunities.report.v1",
        "run_id": run_id,
        "generated_at": utc_now(),
        "contract_version": CONTRACT_VERSION,
        "immutable_goal": {"text": IMMUTABLE_GOAL, "goal_hash": sha256_json(IMMUTABLE_GOAL)},
        "stage": STAGE,
        "operational_readiness": "STAGE_0_READY",
        "capability_authority": _capability_authority(),
        "lane_coverage": _lane_coverage(discovery_dir, shortlist),
        "source_receipts": _source_receipts(discovery_dir),
        "eligibility_rejections": [_rejection(candidate) for candidate in rejections],
        "opportunities": opportunities,
        "resume_variants": resume_variants,
        "outreach_packets": outreach_packets,
        "applications": applications,
        "application_packets": application_packets,
        "interview_prep": interview_prep,
        "decision_actions": [
            {"action": "KEEP", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "REJECT", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "DEFER", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {
                "action": "ACCEPT_RESUME_VARIANT",
                "target_type": "resume_variant",
                "enabled": True,
                "effects_external": False,
            },
            {
                "action": "PROPOSE_CLAIM_AMENDMENT",
                "target_type": "resume_variant",
                "enabled": True,
                "effects_external": False,
            },
            {
                "action": "WITHHOLD_APPLICATION",
                "target_type": "application",
                "enabled": True,
                "effects_external": False,
            },
            {
                "action": "AUTHORIZE_APPLICATION_PAYLOAD",
                "target_type": "application",
                "enabled": False,
                "effects_external": False,
            },
            {
                "action": "MARK_HUMAN_SENT_GMAIL",
                "target_type": "outreach_packet",
                "enabled": False,
                "effects_external": False,
            },
            {
                "action": "MARK_HUMAN_SENT_LINKEDIN",
                "target_type": "outreach_packet",
                "enabled": False,
                "effects_external": False,
            },
        ],
        "artifact_accounting": {
            "action_worthy_total": action_worthy_total,
            "visible_total": action_worthy_total,
            "hidden_total": 0,
            "hidden_ids": [],
        },
        "non_claims": non_claims,
    }


def _enforce_required_sources(skill_dir: Path, discovery_dir: Path) -> dict[str, Any]:
    """Fail the run if any mandated source produced no receipt or NOT_SEARCHED.

    Discovery is enforced in code, not prose: a source listed in
    config/required_sources.json MUST appear in the run's source receipts with
    an honest terminal status. Absence or NOT_SEARCHED is a defect and stops
    the run. An honest FEED_DOWN/AUTH_REQUIRED receipt is allowed.
    """
    config_path = skill_dir / "config" / "required_sources.json"
    if not config_path.exists():
        raise ContractError("REQUIRED_SOURCES_CONFIG_MISSING", str(config_path))
    config = read_json(config_path)
    receipts = _source_receipts(discovery_dir)
    def _norm(value: str) -> str:
        return value.lower().replace("-", "").replace("_", "").replace(".", "")

    seen: dict[str, str] = {}
    for r in receipts:
        provider = _norm(str(r.get("provider", "")))
        seen[provider] = str(r.get("result_status", ""))
    missing: list[str] = []
    not_searched: list[str] = []
    for required in config.get("required", []):
        rid = _norm(str(required["id"]))
        # match by normalized provider substring (linkedin/indeed/sam.gov/etc)
        match = next((s for p, s in seen.items() if rid in p or p in rid), None)
        if match is None:
            missing.append(required["id"])
        elif match == "NOT_SEARCHED":
            not_searched.append(required["id"])
    if missing or not_searched:
        raise ContractError(
            "REQUIRED_SOURCE_NOT_SEARCHED",
            f"mandated sources missing={missing} not_searched={not_searched}; "
            "discovery must attempt every required source (config/required_sources.json)",
        )
    return {"required_sources_enforced": True, "checked": [r["id"] for r in config.get("required", [])]}


def _enforce_api_website_fallback(skill_dir: Path, discovery_dir: Path) -> dict[str, Any]:
    """API break must fall back to the website (Graham 2026-08-06, unignorable rule).

    A required source flagged api_failure_requires_browser whose receipt reports
    an API-failure status (FEED_DOWN/AUTH_FAILED/INVALID_RESPONSE) must have a
    companion browser-capture receipt (source_class ending _website or a
    human_supplied capture). Otherwise the run FAILS: a bare API failure is a
    defect, not an acceptable answer.
    """
    config = read_json(skill_dir / "config" / "required_sources.json")
    receipts = _source_receipts(discovery_dir)
    api_failure = {"FEED_DOWN", "AUTH_FAILED", "INVALID_RESPONSE", "INVALID_REQUEST"}

    def _norm(v: str) -> str:
        return v.lower().replace("-", "").replace("_", "").replace(".", "")

    by_provider: dict[str, list[str]] = {}
    browser_captured: set[str] = set()
    for r in receipts:
        prov = _norm(str(r.get("provider", "")))
        by_provider.setdefault(prov, []).append(str(r.get("result_status", "")))
        src_class = str(r.get("source_class", ""))
        if src_class.endswith("_website") or src_class.startswith("human_supplied") or "authorized_read_only" in src_class:
            browser_captured.add(prov)

    violations: list[str] = []
    for required in config.get("required", []):
        if not required.get("api_failure_requires_browser"):
            continue
        rid = _norm(str(required["id"]))
        statuses = next((s for p, s in by_provider.items() if rid in p or p in rid), None)
        if statuses is None:
            continue
        had_api_failure = any(s in api_failure for s in statuses)
        had_success = any(s == "MATCHES" for s in statuses)
        has_browser = any(rid in p or p in rid for p in browser_captured)
        if had_api_failure and not had_success and not has_browser:
            violations.append(required["id"])
    if violations:
        raise ContractError(
            "API_BREAK_REQUIRES_WEBSITE",
            f"sources with failed API and no website/browser fallback: {violations}; "
            "if the API breaks the skill must use the website (config/required_sources.json)",
        )
    return {"api_website_fallback_enforced": True, "checked": violations == []}


def run_stage0(
    skill_dir: Path,
    out_dir: Path,
    fixture_dir: Path | None = None,
    linkedin_evidence: Path | None = None,
    roundtable_receipts_path: Path | None = None,
    outreach_effects_path: Path | None = None,
    federal_evidence: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = "mo_" + stable_id("run", {"out": str(out_dir), "started": utc_now()}).split(":", 1)[1]
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
        linkedin_evidence=linkedin_evidence,
        federal_evidence=federal_evidence,
    )
    phases.append({"phase": "DISCOVERY_COMPLETE", "artifact": str(discovery_dir / "run-manifest.json")})
    if fixture_dir is None:
        # Enforcement is for live runs; fixtures are deterministic test scaffolding.
        required_sources = _enforce_required_sources(skill_dir, discovery_dir)
        phases.append({"phase": "REQUIRED_SOURCES_ENFORCED", "checked": required_sources["checked"]})
        _enforce_api_website_fallback(skill_dir, discovery_dir)
        phases.append({"phase": "API_WEBSITE_FALLBACK_ENFORCED"})
    ranking_receipt = rank(discovery_dir, SHORTLIST_LIMIT, ranking_dir)
    phases.append({"phase": "RANKING_COMPLETE", "artifact": str(ranking_dir / "ranking-receipt.json")})
    claims_path = skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json"
    tailoring_receipt = None
    apply_prep: list[dict[str, Any]] = []
    if claims_path.exists():
        shortlist_path = ranking_dir / "shortlist.json"
        shortlist = read_json(shortlist_path) if shortlist_path.exists() else []
        if shortlist:
            # A custom targeted resume for each of the top jobs (goal: "custom
            # targeted resume" for top opportunities), not just the single top
            # one. Submit stays human-gated: each packet carries the apply_url
            # and flags the ATS form-inspect/submit as the next human stage.
            top_jobs = [c for c in shortlist if c.get("lane") == "A"][:APPLY_PREP_TOP_N] or shortlist[:APPLY_PREP_TOP_N]
            for candidate in top_jobs:
                cand_id = str(candidate.get("candidate_id") or sha256_json(candidate)[:16])
                cand_dir = tailoring_dir / cand_id
                try:
                    receipt = tailor_candidate(candidate, claims_path, cand_dir)
                except ValueError as exc:
                    logger.warning("apply-prep tailoring skipped for {}: {}", cand_id, exc)
                    continue
                apply_prep.append(
                    {
                        "candidate_id": cand_id,
                        "title": candidate.get("title"),
                        "organization": candidate.get("organization"),
                        "apply_url": candidate.get("apply_url") or candidate.get("posting_url"),
                        "ats_provider": candidate.get("source_provider") or "not-established",
                        "resume_variant_id": receipt.get("variant_id"),
                        "resume_dir": str(cand_dir),
                        "next_stage": "human_review_then_ats_form_inspect",
                        "external_effects": False,
                        "automation_policy": "submit_requires_human_authorization",
                    }
                )
            # Preserve the single primary tailoring_receipt for the report.
            primary = next((c for c in shortlist if c.get("lane") == "A"), shortlist[0])
            tailoring_receipt = tailor_candidate(primary, claims_path, tailoring_dir)
        else:
            tailoring_receipt = tailor("fixture:eligible-ai-architect", claims_path, tailoring_dir)
        write_json(tailoring_dir / "apply-prep.json", apply_prep)
        phases.append({"phase": "TAILORING_COMPLETE", "artifact": str(tailoring_dir / "tailoring-receipt.json")})
        phases.append({"phase": "APPLY_PREP_COMPLETE", "prepared": len(apply_prep), "artifact": str(tailoring_dir / "apply-prep.json")})

    manifest_path = out_dir / "report-manifest.json"
    report_manifest = _report_from_run(
        run_id,
        out_dir,
        discovery_dir,
        ranking_dir,
        tailoring_dir,
        skill_dir,
        _load_receipt_map(roundtable_receipts_path, key_field="receipt_key"),
        _load_receipt_map(outreach_effects_path, key_field="packet_id"),
    )
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
