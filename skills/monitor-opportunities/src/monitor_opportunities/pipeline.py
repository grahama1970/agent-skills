"""Single local Stage 0 run transaction composed from read-only phase artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from .application_packets import build_application_packets
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError, ResultStatus
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


REPORT_DIGEST_LIMIT = 8
# The report manifest is the authoritative action registry; downstream prep
# cannot retain actionable opportunities that are hidden from the report.
SHORTLIST_LIMIT = min(_int_env("MONITOR_SHORTLIST_LIMIT", REPORT_DIGEST_LIMIT), REPORT_DIGEST_LIMIT)
# How many top jobs get a custom targeted resume + apply-prep packet per run.
APPLY_PREP_TOP_N = min(_int_env("MONITOR_APPLY_PREP_TOP_N", REPORT_DIGEST_LIMIT), REPORT_DIGEST_LIMIT)


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
        for optional in ("required_source_id", "channel", "fallback_for_receipt_id"):
            if row.get(optional):
                receipt[optional] = row[optional]
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


def _is_linkedin_locator(candidate: dict[str, Any]) -> bool:
    return candidate.get("source_provider") in {
        "human_supplied_linkedin",
        "ops_linkedin_authorized_read_only",
    }


def _is_networking_signal(candidate: dict[str, Any]) -> bool:
    return candidate.get("source_provider") == "meetup_surf"


def _is_report_opportunity(candidate: dict[str, Any]) -> bool:
    return not _is_linkedin_locator(candidate) and not _is_networking_signal(candidate)


def _source_intel(candidate: dict[str, Any]) -> dict[str, Any] | None:
    source_id = candidate.get("source_receipt_id") or candidate.get("source_receipt_ids", ["unknown"])[0]
    evidence_url = candidate.get("primary_evidence_url") or candidate.get("posting_url")
    if _is_networking_signal(candidate):
        decision = str(candidate.get("networking_decision") or "WATCH").upper()
        return {
            "signal_id": stable_id("source-intel", candidate["candidate_id"]),
            "lane": candidate["lane"],
            "signal_type": "MEETUP_NETWORKING",
            "title": candidate["title"],
            "organization": candidate["organization"],
            "source_receipt_ids": [source_id],
            "primary_evidence_url": evidence_url,
            "decision": f"{decision}_MEETUP",
            "reasons": [
                *(candidate.get("networking_reasons") or []),
                "Meetup source-intel only; no RSVP, join, message, attendee scrape, or GraphQL action.",
            ],
            "action_worthy": decision in {"ATTEND", "WATCH"},
            "visible_in_report": True,
        }
    if _is_linkedin_locator(candidate):
        return {
            "signal_id": stable_id("source-intel", candidate["candidate_id"]),
            "lane": candidate["lane"],
            "signal_type": "LINKEDIN_LOCATOR",
            "title": candidate["title"],
            "organization": candidate["organization"],
            "source_receipt_ids": [source_id],
            "primary_evidence_url": evidence_url,
            "decision": "LOCATOR_ONLY",
            "reasons": [
                "LinkedIn row is profile/recommendation source intelligence only.",
                "Primary employer/client source readback is required before opportunity admission.",
            ],
            "action_worthy": False,
            "visible_in_report": True,
        }
    return None


def _opportunity(candidate: dict[str, Any]) -> dict[str, Any]:
    source_id = candidate.get("source_receipt_id") or candidate.get("source_receipt_ids", ["unknown"])[0]
    evidence_url = candidate.get("primary_evidence_url") or candidate.get("posting_url")
    if _is_linkedin_locator(candidate) or _is_networking_signal(candidate):
        raise ContractError(
            "SOURCE_INTEL_NOT_OPPORTUNITY",
            f"{candidate['candidate_id']} must be rendered as source_intel, not opportunity",
        )
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
    else:
        opportunity_type = "employment_posting"
        observed = [
            f"{candidate.get('source_provider', 'ATS')} primary source observed: {evidence_url or source_id}"
        ]
        inferred = ["Single-column ATS-readable resume is prudent."]
        claim_keys = ["claim:arcos:acert-architect"]
    why_candidate = ["Ranked after deterministic eligibility gating and source receipt readback."]
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


def _resume_variants(tailoring_dir: Path, opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for opportunity in opportunities:
        candidate_dir = tailoring_dir / opportunity["opportunity_id"]
        variant_path = candidate_dir / "resume-variant.json"
        diff_path = candidate_dir / "presentation-diff.json"
        if not variant_path.exists() and (tailoring_dir / "resume-variant.json").exists():
            variant_path = tailoring_dir / "resume-variant.json"
            diff_path = tailoring_dir / "presentation-diff.json"
        if not variant_path.exists():
            continue
        variant = read_json(variant_path)
        diff = read_json(diff_path)
        if variant.get("opportunity_id") != opportunity["opportunity_id"]:
            continue
        variants.append({
            "variant_id": variant["variant_id"],
            "opportunity_id": variant["opportunity_id"],
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
        })
    return variants


def _resolve_claim_snapshot_path(skill_dir: Path, fixture_dir: Path | None, needs_claims: bool) -> Path | None:
    if not needs_claims:
        return None
    configured = os.environ.get("MONITOR_CLAIM_SNAPSHOT_PATH")
    if configured:
        path = Path(configured).expanduser().resolve()
    elif fixture_dir is not None:
        path = (skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json").resolve()
    else:
        raise ContractError(
            "CLAIM_SNAPSHOT_REQUIRED",
            "Live claim-bearing runs require MONITOR_CLAIM_SNAPSHOT_PATH pointing to an approved export.",
        )
    fixture_root = (skill_dir / "tests" / "fixtures").resolve()
    if fixture_dir is None and (path == fixture_root or fixture_root in path.parents):
        raise ContractError(
            "TEST_FIXTURE_AUTHORITY_FORBIDDEN",
            "Live runs cannot use tests/fixtures as claim authority.",
        )
    if not path.exists():
        raise ContractError("CLAIM_SNAPSHOT_MISSING", str(path))
    snapshot = read_json(path)
    if snapshot.get("schema") != "monitor_opportunities.claim_snapshot.v1" or snapshot.get("active") is not True:
        raise ContractError("CLAIM_SNAPSHOT_INVALID", "Exactly one active approved claim snapshot is required.")
    return path


def _application_ats_provider(opportunity: dict[str, Any]) -> str | None:
    profile = opportunity.get("screening_interface_profile") or {}
    observed = "\n".join(profile.get("observed", [])).lower()
    for provider in ("greenhouse", "ashby", "lever"):
        if provider in observed:
            return provider
    return None


def _operational_readiness(source_receipts: list[dict[str, Any]], opportunities: list[dict[str, Any]], resume_variants: list[dict[str, Any]]) -> str:
    degraded = {status.value for status in ResultStatus if status not in {ResultStatus.MATCHES, ResultStatus.NO_MATCHES}}
    if any(row["result_status"] in degraded for row in source_receipts):
        return "DEGRADED"
    if opportunities and len(resume_variants) != len(opportunities):
        return "DEGRADED"
    return "STAGE_0_READY"


def _report_from_run(
    run_id: str,
    run_dir: Path,
    discovery_dir: Path,
    ranking_dir: Path,
    tailoring_dir: Path,
    skill_dir: Path,
    claim_snapshot: dict[str, Any] | None,
    roundtable_receipts: dict[str, dict[str, Any]] | None = None,
    outreach_effects: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    shortlist = read_json(ranking_dir / "shortlist.json")
    rejections = read_json(ranking_dir / "rejections.json")
    opportunity_candidates = [candidate for candidate in shortlist if _is_report_opportunity(candidate)]
    opportunities = [_opportunity(candidate) for candidate in opportunity_candidates[:REPORT_DIGEST_LIMIT]]
    source_intel = [
        item
        for item in (_source_intel(candidate) for candidate in shortlist)
        if item is not None
    ]
    resume_variants = _resume_variants(tailoring_dir, opportunities)
    if len(resume_variants) != len(opportunities):
        missing = sorted(
            {row["opportunity_id"] for row in opportunities}
            - {row["opportunity_id"] for row in resume_variants}
        )
        raise ContractError(
            "RESUME_VARIANT_MISSING",
            f"Every report-admitted opportunity requires a visible claim-bound resume variant; missing={missing}",
        )
    claim_snapshot = claim_snapshot or {"claims": []}
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
            "ats_provider": _application_ats_provider(opportunity) if opportunity["lane"] == "A" else None,
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
        + sum(1 for item in source_intel if item["action_worthy"])
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
        "operational_readiness": _operational_readiness(_source_receipts(discovery_dir), opportunities, resume_variants),
        "capability_authority": _capability_authority(),
        "lane_coverage": _lane_coverage(discovery_dir, shortlist),
        "source_receipts": _source_receipts(discovery_dir),
        "eligibility_rejections": [_rejection(candidate) for candidate in rejections],
        "opportunities": opportunities,
        "source_intel": source_intel,
        "resume_variants": resume_variants,
        "outreach_packets": outreach_packets,
        "applications": applications,
        "application_packets": application_packets,
        "interview_prep": interview_prep,
        "decision_actions": [
            {"action": "KEEP", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "REJECT", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "DEFER", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "ATTEND_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
            {"action": "WATCH_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
            {"action": "SKIP_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
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
    missing: list[str] = []
    invalid: list[str] = []
    by_required: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        required_id = receipt.get("required_source_id")
        if required_id:
            by_required.setdefault(str(required_id), []).append(receipt)
    accepted_default = set(config.get("accepted_non_match_states", []))
    forbidden = set(config.get("forbidden_states", []))
    for required in config.get("required", []):
        rid = str(required["id"])
        matches = by_required.get(rid, [])
        if not matches:
            missing.append(rid)
            continue
        accepted = set(required.get("accepted_statuses") or accepted_default)
        allowed_classes = set(required.get("source_classes") or [])
        channel = required.get("channel")
        for receipt in matches:
            status = str(receipt.get("result_status", ""))
            if status in forbidden or status not in accepted:
                invalid.append(f"{rid}:{receipt['receipt_id']}:status={status}")
            if channel and receipt.get("channel") != channel:
                invalid.append(f"{rid}:{receipt['receipt_id']}:channel={receipt.get('channel')}")
            if allowed_classes and receipt.get("source_class") not in allowed_classes:
                invalid.append(f"{rid}:{receipt['receipt_id']}:source_class={receipt.get('source_class')}")
    if missing or invalid:
        raise ContractError(
            "REQUIRED_SOURCE_CONTRACT_VIOLATION",
            f"mandated sources missing={missing} invalid={invalid}; "
            "discovery must satisfy exact required_source_id/lane/channel/source_class/status",
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

    violations: list[str] = []
    for required in config.get("required", []):
        if not required.get("api_failure_requires_browser"):
            continue
        rid = str(required["id"])
        source_receipts = [row for row in receipts if row.get("required_source_id") == rid]
        if not source_receipts:
            continue
        failed_api_receipts = []
        for receipt in source_receipts:
            response_status = receipt.get("response_status")
            non_2xx = isinstance(response_status, int) and not (200 <= response_status <= 299)
            if receipt.get("channel") == "api" and (receipt.get("result_status") in api_failure or non_2xx):
                failed_api_receipts.append(receipt)
        for failed in failed_api_receipts:
            fallback = next(
                (
                    row
                    for row in source_receipts
                    if row.get("fallback_for_receipt_id") == failed["receipt_id"]
                    and (
                        str(row.get("source_class", "")).endswith("_website")
                        or str(row.get("source_class", "")).startswith("human_supplied")
                        or "authorized_read_only" in str(row.get("source_class", ""))
                    )
                    and row.get("content_sha256")
                    and row.get("evidence_refs")
                    and row.get("result_status") in {"MATCHES", "NO_MATCHES"}
                ),
                None,
            )
            if fallback is None:
                violations.append(f"{rid}:{failed['receipt_id']}")
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
    meetup_evidence: Path | None = None,
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
        meetup_evidence=meetup_evidence,
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
    tailoring_receipt = None
    apply_prep: list[dict[str, Any]] = []
    shortlist_path = ranking_dir / "shortlist.json"
    shortlist = read_json(shortlist_path) if shortlist_path.exists() else []
    opportunity_candidates = [candidate for candidate in shortlist if _is_report_opportunity(candidate)]
    claims_path = _resolve_claim_snapshot_path(skill_dir, fixture_dir, bool(opportunity_candidates))
    claim_snapshot = read_json(claims_path) if claims_path is not None else None
    if claims_path is not None and opportunity_candidates:
        # A custom targeted resume for each report-admitted top opportunity.
        # Source-intel records such as LinkedIn locators and Meetup networking
        # signals cannot enter apply-prep, resume, outreach, or application packets.
        top_jobs = opportunity_candidates[:APPLY_PREP_TOP_N]
        for candidate in top_jobs:
            cand_id = str(candidate.get("candidate_id") or sha256_json(candidate)[:16])
            cand_dir = tailoring_dir / cand_id
            try:
                receipt = tailor_candidate(candidate, claims_path, cand_dir)
            except ValueError as exc:
                logger.warning("apply-prep tailoring skipped for {}: {}", cand_id, exc)
                continue
            if tailoring_receipt is None:
                tailoring_receipt = receipt
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
        write_json(tailoring_dir / "apply-prep.json", apply_prep)
        if tailoring_receipt is not None:
            write_json(tailoring_dir / "tailoring-receipt.json", tailoring_receipt)
        write_json(out_dir / "claim-snapshot.json", claim_snapshot)
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
        claim_snapshot,
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
