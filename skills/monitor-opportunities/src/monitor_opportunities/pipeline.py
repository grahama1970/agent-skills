"""Single local Stage 0 run transaction composed from read-only phase artifacts."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

from .application_packets import build_application_packets
from .contact_changes import (
    bind_relationship_signals_to_opportunities,
    relationship_signals_from_linkedin_contact_evidence,
    relationship_signals_from_candidates,
    relationship_signals_from_memory,
)
from .contracts import CONTRACT_VERSION, IMMUTABLE_GOAL, STAGE, ContractError, ResultStatus
from .discovery import sweep
from .memory_sync import attach_memory_recall_provenance, governed_memory_recall
from .outreach import build_outreach_packets
from .ranking import rank
from .report import load_manifest, render_report
from .tailoring import tailor_candidate
from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json

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
PUBLICATION_EFFECT_CLASSES = (
    "LOCAL_ARTIFACT_WRITTEN",
    "INTERNAL_DESTINATION_WRITTEN",
    "HUMAN_TRANSMITTED",
    "EXTERNAL_SITE_MUTATED",
)

GENERATED_RUN_DIRS = (
    "application-packets",
    "discovery",
    "ranking",
    "report",
    "tailoring",
)
GENERATED_RUN_FILES = (
    "claim-snapshot.json",
    "consulting-research.json",
    "contact-changes.json",
    "decision-projection.json",
    "morning-digest.json",
    "prepublish-contract.json",
    "prospect-queue.json",
    "report-manifest.json",
    "memory-recall-receipt.json",
    "receipt-consistency.json",
    "report-acceptance-receipt.json",
    "run-receipt.json",
    "stage-ledger.json",
    "trigger-receipt.json",
    "zero-effect-replay-receipt.json",
)


def prepare_run_output(out_dir: Path, *, include_browser_capture: bool = False) -> None:
    """Remove prior generated children so a reused run dir cannot expose stale artifacts."""

    generated_dirs = (*GENERATED_RUN_DIRS, "browser-capture") if include_browser_capture else GENERATED_RUN_DIRS
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in generated_dirs:
        child = out_dir / name
        if child.exists():
            shutil.rmtree(child)
    for name in GENERATED_RUN_FILES:
        child = out_dir / name
        if child.exists():
            child.unlink()


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
    admitted_opportunities_by_lane: dict[str, int] = {}
    admitted_source_intel_by_lane: dict[str, int] = {}
    for candidate in shortlist:
        lane = candidate["lane"]
        admitted_by_lane[lane] = admitted_by_lane.get(lane, 0) + 1
        if _is_report_opportunity(candidate):
            admitted_opportunities_by_lane[lane] = admitted_opportunities_by_lane.get(lane, 0) + 1
        else:
            admitted_source_intel_by_lane[lane] = admitted_source_intel_by_lane.get(lane, 0) + 1
    return [
        {
            "lane": row["lane"],
            "searched": row["searched"],
            "result_status": row["result_status"],
            "candidates_observed": row["candidates_observed"],
            "candidates_admitted": admitted_by_lane.get(row["lane"], 0),
            "candidates_admitted_opportunities": admitted_opportunities_by_lane.get(row["lane"], 0),
            "candidates_admitted_source_intel": admitted_source_intel_by_lane.get(row["lane"], 0),
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


def _is_github_intelligence(candidate: dict[str, Any]) -> bool:
    return candidate.get("source_provider") == "github_repo_intelligence"


def _brave_workday_search(query: str) -> list[str]:
    """Return result URLs for a query via the brave-search skill, for Workday
    coordinate resolution. Best-effort and bounded: any failure returns []."""
    import re as _re
    import subprocess as _sp

    run_sh = Path(__file__).resolve().parents[4] / "skills" / "brave-search" / "run.sh"
    if not run_sh.exists():
        return []
    try:
        out = _sp.run(
            [str(run_sh), "web", query, "--count", "5"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, _sp.SubprocessError):
        return []
    return _re.findall(r"https?://[^\s\"'\\]+", out.stdout or "")


def _is_report_opportunity(candidate: dict[str, Any]) -> bool:
    return (
        not _is_linkedin_locator(candidate)
        and not _is_networking_signal(candidate)
        and not _is_github_intelligence(candidate)
    )


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _source_intel_refs(candidate: dict[str, Any], evidence_url: str | None) -> list[str]:
    refs = [
        *_string_list(candidate.get("github_evidence_refs")),
        *_string_list(candidate.get("source_evidence_refs")),
    ]
    if evidence_url:
        refs.append(str(evidence_url))
    return list(dict.fromkeys(refs))


def _source_intel_summary(candidate: dict[str, Any], *, contacts: list[Any] | None = None) -> str:
    title = str(candidate.get("title") or "Source intelligence").strip()
    organization = str(candidate.get("organization") or "unknown organization").strip()
    if _is_github_intelligence(candidate):
        repo = str(candidate.get("github_repo") or title).strip()
        analysis = candidate.get("github_repository_analysis") or {}
        terms = _string_list(analysis.get("matched_terms"))
        term_text = ", ".join(terms[:8]) if terms else "no configured relevance terms"
        relevance_status = str(
            candidate.get("github_relevance_quality_status")
            or analysis.get("relevance_quality_status")
            or "MISSING_RELEVANCE_QUALITY"
        )
        return (
            f"{repo} GitHub repository intelligence for {organization}; "
            f"{len(contacts or [])} contact or adjacent-contact hypotheses observed; "
            f"relevance quality: {relevance_status}; matched terms: {term_text}."
        )
    if _is_networking_signal(candidate):
        decision = str(candidate.get("networking_decision") or "WATCH").upper()
        return f"{title} at {organization} is Meetup source intelligence with recommended decision {decision}."
    if _is_linkedin_locator(candidate):
        return (
            f"{title} at {organization} is LinkedIn locator source intelligence; "
            "primary employer or client readback is still required before opportunity admission."
        )
    return f"{title} at {organization} is source intelligence."


def _bind_source_intel_evidence(
    source_intel: list[dict[str, Any]],
    source_receipts: list[dict[str, Any]],
) -> None:
    refs_by_receipt = {
        str(receipt.get("receipt_id")): _string_list(receipt.get("evidence_refs"))
        for receipt in source_receipts
    }
    for item in source_intel:
        accepted_refs = list(
            dict.fromkeys(
                ref
                for receipt_id in item.get("source_receipt_ids", [])
                for ref in refs_by_receipt.get(str(receipt_id), [])
            )
        )
        current_refs = _string_list(item.get("evidence_refs"))
        receipt_backed_refs = [ref for ref in current_refs if ref in accepted_refs]
        if not receipt_backed_refs and accepted_refs:
            receipt_backed_refs = accepted_refs[:1]
        item["evidence_refs"] = receipt_backed_refs


def _bind_relationship_evidence(
    relationship_signals: list[dict[str, Any]],
    source_receipts: list[dict[str, Any]],
) -> None:
    refs_by_receipt = {
        str(receipt.get("receipt_id")): _string_list(receipt.get("evidence_refs"))
        for receipt in source_receipts
    }
    for signal in relationship_signals:
        signal_receipt_ids = _string_list(signal.get("source_receipt_ids"))
        signal_accepted_refs = list(
            dict.fromkeys(
                ref
                for receipt_id in signal_receipt_ids
                for ref in refs_by_receipt.get(str(receipt_id), [])
            )
        )
        retained_signal_refs = [
            ref for ref in _string_list(signal.get("evidence_refs")) if ref in signal_accepted_refs
        ]
        retained_edge_refs: list[str] = []
        for edge in signal.get("contact_path") or []:
            if not isinstance(edge, dict):
                continue
            edge_receipt_ids = _string_list(edge.get("source_receipt_ids"))
            edge_accepted_refs = list(
                dict.fromkeys(
                    ref
                    for receipt_id in edge_receipt_ids
                    for ref in refs_by_receipt.get(str(receipt_id), [])
                )
            )
            edge_refs = [ref for ref in _string_list(edge.get("evidence_refs")) if ref in edge_accepted_refs]
            if not edge_refs and edge_accepted_refs:
                edge_refs = edge_accepted_refs[:1]
            edge["evidence_refs"] = edge_refs
            retained_edge_refs.extend(edge_refs)
        combined_signal_refs = list(dict.fromkeys([*retained_signal_refs, *retained_edge_refs]))
        if not combined_signal_refs and signal_accepted_refs:
            combined_signal_refs = signal_accepted_refs[:1]
        signal["evidence_refs"] = combined_signal_refs


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
            "summary": _source_intel_summary(candidate),
            "source_receipt_ids": [source_id],
            "primary_evidence_url": evidence_url,
            "evidence_refs": _source_intel_refs(candidate, evidence_url),
            "decision": f"{decision}_MEETUP",
            "reasons": [
                *(candidate.get("networking_reasons") or []),
                "Meetup source-intel only; no RSVP, join, message, attendee scrape, or GraphQL action.",
            ],
            "action_worthy": decision in {"ATTEND", "WATCH"},
            "visible_in_report": True,
        }
    if _is_linkedin_locator(candidate):
        # A WNY-priority locator that primary-source readback could not confirm
        # this run is surfaced as pending verification rather than buried. It is
        # still not action-worthy until a primary source and Graham's exact
        # post-report authorization are both present.
        pending = bool(candidate.get("pending_primary_verification"))
        return {
            "signal_id": stable_id("source-intel", candidate["candidate_id"]),
            "lane": candidate["lane"],
            "signal_type": "LINKEDIN_LOCATOR",
            "title": candidate["title"],
            "organization": candidate["organization"],
            "summary": _source_intel_summary(candidate),
            "source_receipt_ids": [source_id],
            "primary_evidence_url": evidence_url,
            "evidence_refs": _source_intel_refs(candidate, evidence_url),
            "decision": "PENDING_PRIMARY_VERIFICATION" if pending else "LOCATOR_ONLY",
            "reasons": [
                "LinkedIn row is profile/recommendation source intelligence only.",
                "Primary employer/client source readback is required before opportunity admission."
                if not pending else
                "WNY priority: no primary ATS source corroborated this run; verify the employer posting and require Graham's exact post-report authorization before any application.",
            ],
            "action_worthy": False,
            "visible_in_report": True,
        }
    if _is_github_intelligence(candidate):
        contacts = candidate.get("github_contact_hypotheses") or []
        analysis = candidate.get("github_repository_analysis") or {}
        relevance_status = str(
            candidate.get("github_relevance_quality_status")
            or analysis.get("relevance_quality_status")
            or "MISSING_RELEVANCE_QUALITY"
        )
        relevance_reasons = _string_list(
            candidate.get("github_relevance_quality_reasons")
            or analysis.get("relevance_quality_reasons")
        )
        relevance_warnings = _string_list(
            candidate.get("github_relevance_quality_warnings")
            or analysis.get("relevance_quality_warnings")
        )
        return {
            "signal_id": stable_id("source-intel", candidate["candidate_id"]),
            "lane": candidate["lane"],
            "signal_type": "GITHUB_REPO_INTELLIGENCE",
            "title": candidate["title"],
            "organization": candidate["organization"],
            "summary": _source_intel_summary(candidate, contacts=contacts),
            "source_receipt_ids": [source_id],
            "primary_evidence_url": evidence_url,
            "evidence_refs": _source_intel_refs(candidate, evidence_url),
            "decision": "CONTACT_INTELLIGENCE_ONLY",
            "reasons": [
                f"GitHub repository analyzed for contact and adjacent-contact intelligence; contacts observed: {len(contacts)}.",
                f"Repository relevance quality: {relevance_status}.",
                *relevance_reasons[:4],
                *[f"Repository relevance warning: {warning}" for warning in relevance_warnings[:4]],
                "Repository ownership, commits, issues, PRs, docs, and mentions are source-intel signals only.",
                "No GitHub mutation, LinkedIn connection, email, application, or outreach is authorized.",
            ],
            "action_worthy": bool(contacts) and relevance_status == "STRONG_RELEVANCE",
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


def _operational_readiness(
    source_receipts: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    resume_variants: list[dict[str, Any]],
    degraded_contracts: list[dict[str, str]] | None = None,
) -> str:
    degraded = {status.value for status in ResultStatus if status not in {ResultStatus.MATCHES, ResultStatus.NO_MATCHES}}
    if degraded_contracts:
        return "DEGRADED"
    if any(row["result_status"] in degraded for row in source_receipts):
        return "DEGRADED"
    if opportunities and len(resume_variants) != len(opportunities):
        return "DEGRADED"
    return "STAGE_0_READY"


def _memory_recall_source_receipt(
    run_dir: Path,
    recall_receipt: dict[str, Any],
    relationship_signals: list[dict[str, Any]],
) -> dict[str, Any] | None:
    memory_signals = [
        signal
        for signal in relationship_signals
        if str(signal.get("source_opportunity_id") or "").startswith("memory:")
        and signal.get("visible_in_report") is True
    ]
    if not memory_signals:
        return None
    evidence_refs = list(
        dict.fromkeys(
            str(ref)
            for signal in memory_signals
            for ref in signal.get("evidence_refs", [])
            if str(ref).strip()
        )
    )
    if not evidence_refs:
        return None
    receipt_id = "src:c:memory-recall:" + sha256_json(
        {
            "schema": recall_receipt.get("schema"),
            "signals": [signal.get("signal_id") for signal in memory_signals],
            "evidence_refs": evidence_refs,
        }
    )[:16]
    recall_path = run_dir / "memory-recall-receipt.json"
    if recall_path.exists():
        evidence_refs.append(recall_path.as_uri())
        evidence_refs = list(dict.fromkeys(evidence_refs))
    limitations = list(recall_receipt.get("degradation_reasons") or [])
    if recall_receipt.get("degraded") and not limitations:
        limitations.append("Governed Memory recall degraded; no raw database fallback attempted.")
    payload_bytes = json.dumps(recall_receipt, sort_keys=True).encode("utf-8")
    return {
        "receipt_id": receipt_id,
        "lane": "C",
        "provider": "memory",
        "target": "monitor-contacts relationship recall",
        "source_class": "governed_memory_recall",
        "result_status": ResultStatus.MATCHES.value,
        "observed_at": utc_now(),
        "request_summary": (
            "Bounded Memory /recall plus approved ARCOS contact source file; "
            "no /list, raw Arango/Qdrant, outreach, or mutation."
        ),
        "response_status": 200 if int(recall_receipt.get("attempted") or 0) else None,
        "content_type": "application/json",
        "response_bytes": len(payload_bytes),
        "content_sha256": sha256_json(recall_receipt),
        "evidence_refs": evidence_refs,
        "limitations": limitations,
        "automation_policy": "READ_ONLY_RECALL_NO_OUTREACH",
        "required_source_id": "memory_contact_recall",
        "channel": "relationship_memory",
    }


def _linkedin_contact_source_receipt(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return None
    rows = payload.get("contacts")
    required_source_id = "linkedin_actively_hiring_contacts"
    if not isinstance(rows, list):
        rows = payload.get("viewers")
        required_source_id = "linkedin_who_viewed_contacts"
    if not isinstance(rows, list) or not rows:
        return None
    evidence_refs = [path.as_uri()]
    for row in rows:
        if isinstance(row, dict) and row.get("profile"):
            evidence_refs.append(str(row["profile"]))
    evidence_refs = list(dict.fromkeys(evidence_refs))
    receipt_id = "src:c:linkedin-contacts:" + sha256_json(
        {
            "path": str(path),
            "schema": payload.get("schema_version"),
            "contacts": [
                {
                    "name": row.get("name"),
                    "org": row.get("org") or row.get("organization"),
                    "degree": row.get("degree"),
                    "profile": row.get("profile"),
                }
                for row in rows
                if isinstance(row, dict)
            ],
        }
    )[:16]
    return {
        "receipt_id": receipt_id,
        "lane": "C",
        "provider": "linkedin",
        "target": "LinkedIn 1st/2nd/3rd-degree contact evidence",
        "source_class": "ops_linkedin_authorized_read_only_contacts",
        "result_status": ResultStatus.MATCHES.value,
        "observed_at": payload.get("observed_at") or utc_now(),
        "request_summary": (
            "Local read-only LinkedIn people evidence captured through the human-authorized browser; "
            "no connect, message, follow, InMail, email, or application action."
        ),
        "response_status": 200,
        "content_type": "application/json",
        "response_bytes": path.stat().st_size,
        "content_sha256": sha256_json(payload),
        "evidence_refs": evidence_refs,
        "limitations": [
            "LinkedIn relationship degree and mutual text are screen evidence for human review, not outreach authority.",
            "The human must verify identity/current role before connecting or messaging.",
        ],
        "automation_policy": "linkedin_authorized_read_only_no_actions",
        "required_source_id": required_source_id,
        "channel": "linkedin_contact_graph",
    }


def _attach_source_receipt_to_memory_relationship_signals(
    relationship_signals: list[dict[str, Any]],
    receipt_id: str,
) -> None:
    for signal in relationship_signals:
        if not str(signal.get("source_opportunity_id") or "").startswith("memory:"):
            continue
        signal["source_receipt_ids"] = list(
            dict.fromkeys([*(signal.get("source_receipt_ids") or []), receipt_id])
        )
        for edge in signal.get("contact_path") or []:
            edge["source_receipt_ids"] = list(
                dict.fromkeys([*(edge.get("source_receipt_ids") or []), receipt_id])
            )


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
    linkedin_contact_evidence: Path | None = None,
    memory_url: str = "http://127.0.0.1:8601",
    degraded_contracts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    shortlist = read_json(ranking_dir / "shortlist.json")
    source_intel_shortlist_path = ranking_dir / "source-intel-shortlist.json"
    source_intel_shortlist = read_json(source_intel_shortlist_path) if source_intel_shortlist_path.exists() else []
    rejections = read_json(ranking_dir / "rejections.json")
    opportunity_candidates = [candidate for candidate in shortlist if _is_report_opportunity(candidate)]
    opportunities = [_opportunity(candidate) for candidate in opportunity_candidates[:REPORT_DIGEST_LIMIT]]
    source_intel = [
        item
        for item in (_source_intel(candidate) for candidate in [*source_intel_shortlist, *shortlist])
        if item is not None
    ]
    relationship_signals = relationship_signals_from_candidates(
        [*shortlist[:REPORT_DIGEST_LIMIT], *source_intel_shortlist[:REPORT_DIGEST_LIMIT]]
    )
    for signal in relationship_signals_from_memory(memory_url):
        if signal["signal_id"] not in {row["signal_id"] for row in relationship_signals}:
            relationship_signals.append(signal)
    linkedin_contact_receipt = _linkedin_contact_source_receipt(linkedin_contact_evidence)
    if linkedin_contact_receipt is not None and linkedin_contact_evidence is not None:
        existing_signal_ids = {row["signal_id"] for row in relationship_signals}
        for signal in relationship_signals_from_linkedin_contact_evidence(
            linkedin_contact_evidence,
            source_receipt_id=str(linkedin_contact_receipt["receipt_id"]),
        ):
            if signal["signal_id"] not in existing_signal_ids:
                relationship_signals.append(signal)
                existing_signal_ids.add(signal["signal_id"])
    memory_recall_receipt = governed_memory_recall(
        memory_url,
        opportunities=opportunities,
        relationship_signals=relationship_signals,
    )
    write_json(run_dir / "memory-recall-receipt.json", memory_recall_receipt)
    attach_memory_recall_provenance(opportunities, relationship_signals, memory_recall_receipt)
    source_receipts = _source_receipts(discovery_dir)
    if linkedin_contact_receipt is not None:
        source_receipts.append(linkedin_contact_receipt)
    memory_source_receipt = _memory_recall_source_receipt(
        run_dir,
        memory_recall_receipt,
        relationship_signals,
    )
    if memory_source_receipt is not None:
        _attach_source_receipt_to_memory_relationship_signals(
            relationship_signals,
            str(memory_source_receipt["receipt_id"]),
        )
        source_receipts.append(memory_source_receipt)
    _bind_source_intel_evidence(source_intel, source_receipts)
    _bind_relationship_evidence(relationship_signals, source_receipts)
    relationship_binding_diagnostics = bind_relationship_signals_to_opportunities(
        opportunities, relationship_signals
    )
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
        + len(relationship_signals)
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
        "operational_readiness": _operational_readiness(
            source_receipts,
            opportunities,
            resume_variants,
            degraded_contracts,
        ),
        "capability_authority": _capability_authority(),
        "lane_coverage": _lane_coverage(discovery_dir, [*shortlist, *source_intel_shortlist]),
        "source_receipts": source_receipts,
        "eligibility_rejections": [_rejection(candidate) for candidate in rejections],
        "opportunities": opportunities,
        "source_intel": source_intel,
        "resume_variants": resume_variants,
        "outreach_packets": outreach_packets,
        "applications": applications,
        "application_packets": application_packets,
        "relationship_signals": relationship_signals,
        "relationship_binding_diagnostics": relationship_binding_diagnostics,
        "interview_prep": interview_prep,
        "decision_actions": [
            {"action": "KEEP", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "REJECT", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "DEFER", "target_type": "opportunity", "enabled": True, "effects_external": False},
            {"action": "ATTEND_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
            {"action": "WATCH_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
            {"action": "SKIP_MEETUP", "target_type": "source_intel", "enabled": True, "effects_external": False},
            {"action": "RECONNECT_CONTACT", "target_type": "relationship_signal", "enabled": True, "effects_external": False},
            {"action": "DEFER_CONTACT", "target_type": "relationship_signal", "enabled": True, "effects_external": False},
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
    def _receipt_violations(required: dict[str, Any], receipt: dict[str, Any]) -> list[str]:
        rid = str(required["id"])
        accepted = set(required.get("accepted_statuses") or accepted_default)
        allowed_classes = set(required.get("source_classes") or [])
        channel = required.get("channel")
        allowed_channels = {"api", "browser_or_api"} if channel == "browser_or_api" else {channel}
        problems: list[str] = []
        status = str(receipt.get("result_status", ""))
        if status in forbidden or status not in accepted:
            problems.append(f"{rid}:{receipt['receipt_id']}:status={status}")
        if channel and receipt.get("channel") not in allowed_channels:
            problems.append(f"{rid}:{receipt['receipt_id']}:channel={receipt.get('channel')}")
        if allowed_classes and receipt.get("source_class") not in allowed_classes:
            problems.append(f"{rid}:{receipt['receipt_id']}:source_class={receipt.get('source_class')}")
        return problems

    for required in config.get("required", []):
        rid = str(required["id"])
        matches = by_required.get(rid, [])
        if not matches:
            missing.append(rid)
            continue
        per_receipt = [_receipt_violations(required, receipt) for receipt in matches]
        if all(problems for problems in per_receipt):
            invalid.extend(problem for problems in per_receipt for problem in problems)
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
    indeed_evidence: Path | None = None,
    hiddenjobs_evidence: Path | None = None,
    roundtable_receipts_path: Path | None = None,
    outreach_effects_path: Path | None = None,
    federal_evidence: Path | None = None,
    meetup_evidence: Path | None = None,
    github_evidence: Path | None = None,
    linkedin_contact_evidence: Path | None = None,
    degrade_required_source_failures: bool = False,
    memory_url: str = "http://127.0.0.1:8601",
) -> dict[str, Any]:
    prepare_run_output(out_dir)
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
        indeed_evidence=indeed_evidence,
        hiddenjobs_evidence=hiddenjobs_evidence,
        federal_evidence=federal_evidence,
        meetup_evidence=meetup_evidence,
        github_evidence=github_evidence,
    )
    phases.append({"phase": "DISCOVERY_COMPLETE", "artifact": str(discovery_dir / "run-manifest.json")})
    degraded_contracts: list[dict[str, str]] = []
    if fixture_dir is None:
        # Enforcement is for live runs; fixtures are deterministic test scaffolding.
        try:
            required_sources = _enforce_required_sources(skill_dir, discovery_dir)
        except ContractError as exc:
            if not degrade_required_source_failures:
                raise
            degraded_contracts.append({"code": exc.code, "message": exc.message})
            phases.append({"phase": "REQUIRED_SOURCES_DEGRADED", "code": exc.code, "message": exc.message})
        else:
            phases.append({"phase": "REQUIRED_SOURCES_ENFORCED", "checked": required_sources["checked"]})
        try:
            _enforce_api_website_fallback(skill_dir, discovery_dir)
        except ContractError as exc:
            if not degrade_required_source_failures:
                raise
            degraded_contracts.append({"code": exc.code, "message": exc.message})
            phases.append({"phase": "API_WEBSITE_FALLBACK_DEGRADED", "code": exc.code, "message": exc.message})
        else:
            phases.append({"phase": "API_WEBSITE_FALLBACK_ENFORCED"})
        from .application_history import annotate_candidates_with_prior_applications

        application_history_receipt = annotate_candidates_with_prior_applications(discovery_dir, memory_url)
        write_json(discovery_dir / "application-history-receipt.json", application_history_receipt)
        phases.append(
            {
                "phase": "APPLICATION_HISTORY_READ",
                "artifact": str(discovery_dir / "application-history-receipt.json"),
                "status": application_history_receipt["status"],
                "marked_already_applied": application_history_receipt["marked_already_applied"],
            }
        )
        if application_history_receipt["status"] != "OK":
            degraded_contracts.append(
                {
                    "code": "APPLICATION_HISTORY_UNKNOWN",
                    "message": "; ".join(application_history_receipt.get("limitations", []))
                    or "Prior application history was not available.",
                }
            )
    # Live primary-source readback (opt-in): when enabled, WNY LinkedIn locators
    # get their employer ATS board fetched and are promoted into the ranked pool.
    # Off by default so offline/deterministic runs make no network calls.
    ranking_probe = None
    if os.environ.get("MONITOR_READBACK_LIVE", "").lower() in {"1", "true", "yes"}:
        import httpx

        from .readback import live_ats_probe

        _readback_client = httpx.Client(timeout=httpx.Timeout(8.0), follow_redirects=True)
        try:
            ranking_probe = live_ats_probe(_readback_client, search_fn=_brave_workday_search)
            ranking_receipt = rank(discovery_dir, SHORTLIST_LIMIT, ranking_dir, ats_probe=ranking_probe)
        finally:
            _readback_client.close()
    else:
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
        linkedin_contact_evidence,
        memory_url if fixture_dir is None else "",
        degraded_contracts,
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
        "degraded_contracts": degraded_contracts,
        "discovery_receipt": discovery_receipt,
        "ranking_receipt": ranking_receipt,
        "tailoring_receipt": tailoring_receipt,
        "report_manifest_sha256": sha256_json(report_manifest),
        "report_html": render_artifacts["report_html"],
        "report_json": render_artifacts["report_json"],
    }
    write_json(out_dir / "run-receipt.json", receipt)
    write_json(
        out_dir / "receipt-consistency.json",
        build_receipt_consistency(
            run_dir=out_dir,
            receipt=receipt,
            manifest=report_manifest,
        ),
    )
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
    artifact_reconciliation = _artifact_reconciliation(manifest or {})
    publication = _publication_status(run_dir, receipt)
    receipt_consistency = build_receipt_consistency(
        run_dir=run_dir,
        receipt=receipt,
        manifest=manifest or {},
        publication=publication,
    )
    action_worthy_total = int(accounting.get("action_worthy_total", 0))
    decided_total = len(projection.get("items", {}))
    source_receipts = (manifest or {}).get("source_receipts", [])
    degraded_statuses = {
        status.value
        for status in ResultStatus
        if status not in {ResultStatus.MATCHES, ResultStatus.NO_MATCHES}
    }
    degraded_receipts = [
        {
            "receipt_id": row.get("receipt_id"),
            "required_source_id": row.get("required_source_id"),
            "lane": row.get("lane"),
            "provider": row.get("provider"),
            "channel": row.get("channel"),
            "result_status": row.get("result_status"),
            "response_status": row.get("response_status"),
        }
        for row in source_receipts
        if row.get("result_status") in degraded_statuses
    ]
    return {
        "schema": "monitor_opportunities.run_status.v1",
        "run_dir": str(run_dir),
        "run_id": receipt["run_id"],
        "state": receipt["terminal_state"],
        "operational_readiness": (manifest or {}).get("operational_readiness", "UNKNOWN"),
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
        "artifact_reconciliation": artifact_reconciliation,
        "artifact_counts": {
            "opportunities": len((manifest or {}).get("opportunities", [])),
            "source_intel": len((manifest or {}).get("source_intel", [])),
            "resume_variants": len((manifest or {}).get("resume_variants", [])),
            "outreach_packets": len((manifest or {}).get("outreach_packets", [])),
            "applications": len((manifest or {}).get("applications", [])),
            "application_packets": len((manifest or {}).get("application_packets", [])),
            "relationship_signals": len((manifest or {}).get("relationship_signals", [])),
        },
        "source_health": {
            "total_receipts": len(source_receipts),
            "degraded_count": len(degraded_receipts),
            "degraded_receipts": degraded_receipts,
        },
        "unresolved_decisions": max(action_worthy_total - decided_total, 0),
        "indeterminate_effect_state": False,
        "publication": publication,
        "receipt_consistency": receipt_consistency,
        "receipt_consistency_path": str(run_dir / "receipt-consistency.json")
        if (run_dir / "receipt-consistency.json").exists()
        else None,
        "report_html": receipt["report_html"],
        "external_effects": receipt["external_effects"],
    }


def build_zero_effect_replay_receipt(run_dir: Path, projection: dict[str, Any]) -> dict[str, Any]:
    """Bind replayed local decisions to the run's no-effect receipts."""
    rows = read_jsonl(run_dir / "decision-ledger.jsonl")
    manifest_path = run_dir / "report-manifest.json"
    projection_path = run_dir / "decision-projection.json"
    run_receipt_path = run_dir / "run-receipt.json"
    consistency_path = run_dir / "receipt-consistency.json"
    effect_policy_path = run_dir / "effect-policy-receipt.json"
    attestation_path = run_dir / "run-attestation.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {}
    run_receipt = read_json(run_receipt_path) if run_receipt_path.exists() else {}
    consistency = read_json(consistency_path) if consistency_path.exists() else {}
    effect_policy = read_json(effect_policy_path) if effect_policy_path.exists() else {}
    attestation = read_json(attestation_path) if attestation_path.exists() else {}
    attestation_code = attestation.get("code") or {}
    projection_for_hash = read_json(projection_path) if projection_path.exists() else projection
    event_effect_violations = [
        str(row.get("event_id") or row.get("idempotency_key") or index)
        for index, row in enumerate(rows)
        if row.get("external_effects") is not False
    ]
    checks = {
        "projection_external_effects_false": projection.get("external_effects") is False,
        "decision_events_external_effects_false": not event_effect_violations,
        "run_receipt_external_effects_false": (
            run_receipt.get("external_effects") is False if run_receipt else True
        ),
        "receipt_consistency_pass": (
            consistency.get("status") == "PASS" if consistency else True
        ),
        "effect_policy_external_effects_false": (
            effect_policy.get("external_effects") is False if effect_policy else True
        ),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema": "monitor_opportunities.zero_effect_replay_receipt.v1",
        "status": status,
        "run_dir": str(run_dir),
        "mode": effect_policy.get("mode", "UNAVAILABLE"),
        "event_count": len(rows),
        "projection_digest": projection.get("projection_digest"),
        "binding": {
            "run_id": run_receipt.get("run_id"),
            "manifest_run_id": manifest.get("run_id"),
            "report_manifest_sha256": sha256_json(manifest) if manifest else None,
            "run_receipt_report_manifest_sha256": run_receipt.get("report_manifest_sha256"),
            "run_receipt_sha256": sha256_json(run_receipt) if run_receipt else None,
            "decision_projection_sha256": sha256_json(projection_for_hash)
            if projection_for_hash
            else None,
            "projection_digest": projection.get("projection_digest"),
            "receipt_consistency_sha256": sha256_json(consistency) if consistency else None,
            "receipt_consistency_status": consistency.get("status") if consistency else None,
            "effect_policy_sha256": sha256_json(effect_policy) if effect_policy else None,
            "effect_policy_mode": effect_policy.get("mode") if effect_policy else None,
            "run_attestation_sha256": sha256_json(attestation) if attestation else None,
            "source_revision": attestation_code.get("git_revision") if attestation else None,
            "source_revision_full": attestation_code.get("git_revision_full")
            if attestation
            else None,
        },
        "external_effects": False,
        "checks": checks,
        "violations": {
            "decision_event_external_effects": event_effect_violations,
        },
        "artifacts": {
            "decision_projection": str(projection_path),
            "decision_ledger": str(run_dir / "decision-ledger.jsonl")
            if (run_dir / "decision-ledger.jsonl").exists()
            else None,
            "run_receipt": str(run_receipt_path) if run_receipt_path.exists() else None,
            "receipt_consistency": str(consistency_path) if consistency_path.exists() else None,
            "effect_policy": str(effect_policy_path) if effect_policy_path.exists() else None,
            "run_attestation": str(attestation_path) if attestation_path.exists() else None,
        },
        "mocked": False,
        "live": bool(run_receipt.get("live", False)),
    }


def _raw_artifact_rows(manifest: dict[str, Any]) -> list[tuple[str, bool, bool]]:
    rows: list[tuple[str, bool, bool]] = []
    sections = (
        ("opportunities", "opportunity_id"),
        ("source_intel", "signal_id"),
        ("resume_variants", "variant_id"),
        ("outreach_packets", "packet_id"),
        ("applications", "application_id"),
        ("application_packets", "packet_id"),
        ("relationship_signals", "signal_id"),
    )
    for section, id_field in sections:
        for item in manifest.get(section, []):
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    str(item.get(id_field, "unknown")),
                    bool(item.get("action_worthy", False)),
                    bool(item.get("visible_in_report", False)),
                )
            )
    return rows


def _artifact_reconciliation(manifest: dict[str, Any]) -> dict[str, Any]:
    accounting = manifest.get("artifact_accounting", {}) if manifest else {}
    rows = _raw_artifact_rows(manifest)
    action_worthy_rows = [row for row in rows if row[1]]
    visible_action_worthy_rows = [row for row in action_worthy_rows if row[2]]
    hidden_ids = [artifact_id for artifact_id, _, visible in action_worthy_rows if not visible]
    declared_action_worthy = int(accounting.get("action_worthy_total", 0))
    declared_visible = int(accounting.get("visible_total", 0))
    declared_hidden = int(accounting.get("hidden_total", 0))
    return {
        "semantics": (
            "visible_total counts action-worthy report-visible artifacts, not all visible rows"
        ),
        "declared_action_worthy_total": declared_action_worthy,
        "calculated_action_worthy_total": len(action_worthy_rows),
        "declared_visible_total": declared_visible,
        "calculated_visible_total": len(visible_action_worthy_rows),
        "declared_hidden_total": declared_hidden,
        "calculated_hidden_total": len(hidden_ids),
        "hidden_ids": hidden_ids,
        "ok": (
            declared_action_worthy == len(action_worthy_rows)
            and declared_visible == len(visible_action_worthy_rows)
            and declared_hidden == 0
            and not hidden_ids
        ),
    }


def _publication_status(run_dir: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    effect_policy_path = run_dir / "effect-policy-receipt.json"
    if effect_policy_path.exists():
        policy = read_json(effect_policy_path)
        return {
            "mode": policy.get("mode", "UNKNOWN"),
            "effect_policy_receipt": str(effect_policy_path),
            "external_effects": bool(
                policy.get("external_effects", receipt.get("external_effects", False))
            ),
            "publications": policy.get("publications", {}),
            "read_only_checks": policy.get("read_only_checks", {}),
            "separately_gated": policy.get("separately_gated", {}),
            "forbidden_effects": policy.get("forbidden_effects", {}),
        }
    return {
        "mode": "UNAVAILABLE",
        "effect_policy_receipt": None,
        "external_effects": bool(receipt.get("external_effects", False)),
        "publications": {
            "local_report": "ENABLED" if receipt.get("report_html") else "MISSING",
            "digest": None,
            "memory_summary": None,
            "relationship_graph": None,
            "buzz_summary": None,
            "discord_handoff": None,
        },
        "read_only_checks": {
            "prior_application_history": None,
        },
        "separately_gated": {
            "tracker": None,
            "ats_selector_memory_write": None,
        },
        "forbidden_effects": {
            "gmail_send": "FORBIDDEN",
            "gmail_schedule_send": "FORBIDDEN",
            "gmail_forward": "FORBIDDEN",
            "linkedin_action": "FORBIDDEN",
            "meetup_rsvp": "FORBIDDEN",
            "ats_submit": "FORBIDDEN",
        },
    }


def _publication_policy_value(publication: dict[str, Any], section: str, name: str) -> str:
    value = publication.get(section, {}).get(name)
    if value is None:
        return "UNAVAILABLE"
    return str(value)


def _publication_state(
    *,
    destination: str,
    policy: str,
    effect_class: str,
    status: str,
    evidence_path: str = "",
    evidence_field: str = "",
    note: str = "",
) -> dict[str, str]:
    if effect_class not in PUBLICATION_EFFECT_CLASSES:
        raise ValueError(f"invalid publication effect class: {effect_class}")
    return {
        "destination": destination,
        "policy": policy,
        "effect_class": effect_class,
        "status": status,
        "evidence_path": evidence_path,
        "evidence_field": evidence_field,
        "note": note,
    }


def _canonical_publication_states(
    run_dir: Path, receipt: dict[str, Any], publication: dict[str, Any]
) -> list[dict[str, str]]:
    report_value = str(receipt.get("report_html") or "")
    report_path = Path(report_value) if report_value else None
    digest_path = run_dir / "morning-digest.json"
    memory_path = run_dir / "memory-sync-receipt.json"
    buzz_path = run_dir / "buzz-summary" / "buzz-summary-receipt.json"
    discord_path = run_dir / "discord-handoff" / "morning-discord-receipt.json"
    tracker_policy = _publication_policy_value(publication, "separately_gated", "tracker")
    ats_policy = _publication_policy_value(
        publication, "separately_gated", "ats_selector_memory_write"
    )
    states = [
        _publication_state(
            destination="local_report",
            policy=_publication_policy_value(publication, "publications", "local_report"),
            effect_class="LOCAL_ARTIFACT_WRITTEN",
            status="WRITTEN" if report_path and report_path.exists() else "MISSING",
            evidence_path=str(report_path) if report_path and report_path.exists() else "",
            evidence_field="receipt.report_html",
            note="Local report artifact only; no external transmission.",
        ),
        _publication_state(
            destination="digest",
            policy=_publication_policy_value(publication, "publications", "digest"),
            effect_class="LOCAL_ARTIFACT_WRITTEN",
            status="WRITTEN" if digest_path.exists() else "NOT_ATTEMPTED",
            evidence_path=str(digest_path) if digest_path.exists() else "",
            evidence_field="morning-digest.json",
            note="Local digest artifact, not a send/apply effect.",
        ),
        _publication_state(
            destination="memory_summary",
            policy=_publication_policy_value(publication, "publications", "memory_summary"),
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="WRITTEN" if memory_path.exists() else "NOT_ATTEMPTED",
            evidence_path=str(memory_path) if memory_path.exists() else "",
            evidence_field="memory-sync-receipt.json",
            note="Internal Memory destination; external_effects remains false.",
        ),
        _publication_state(
            destination="relationship_graph",
            policy=_publication_policy_value(publication, "publications", "relationship_graph"),
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="WRITTEN" if memory_path.exists() else "NOT_ATTEMPTED",
            evidence_path=str(memory_path) if memory_path.exists() else "",
            evidence_field="memory-sync-receipt.relationship_readback_found",
            note="Relationship graph is an internal Memory projection.",
        ),
        _publication_state(
            destination="buzz_summary",
            policy=_publication_policy_value(publication, "publications", "buzz_summary"),
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="WRITTEN" if buzz_path.exists() else "NOT_ATTEMPTED",
            evidence_path=str(buzz_path) if buzz_path.exists() else "",
            evidence_field="buzz-summary-receipt.posted",
            note="Legacy Buzz summary path; Discord is the preferred morning handoff.",
        ),
        _publication_state(
            destination="discord_handoff",
            policy=_publication_policy_value(publication, "publications", "discord_handoff"),
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="WRITTEN" if discord_path.exists() else "NOT_ATTEMPTED",
            evidence_path=str(discord_path) if discord_path.exists() else "",
            evidence_field="morning-discord-receipt.status",
            note="Discord handoff is the preferred morning discussion surface; it is not application authority.",
        ),
        _publication_state(
            destination="prior_application_history",
            policy=_publication_policy_value(
                publication, "read_only_checks", "prior_application_history"
            ),
            effect_class="LOCAL_ARTIFACT_WRITTEN",
            status="READ_ONLY_CHECK" if (run_dir / "discovery" / "application-history-receipt.json").exists() else "NOT_ATTEMPTED",
            evidence_path=str(run_dir / "discovery" / "application-history-receipt.json")
            if (run_dir / "discovery" / "application-history-receipt.json").exists()
            else "",
            evidence_field="application-history-receipt.json",
            note="Read-only recall/check, not an application effect.",
        ),
        _publication_state(
            destination="tracker",
            policy=tracker_policy,
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="NOT_ATTEMPTED" if tracker_policy in {"SKIPPED", "UNAVAILABLE"} else "POLICY_ENABLED",
            note="Private tracker writes are separately gated and skipped in Stage 0 cron.",
        ),
        _publication_state(
            destination="ats_selector_memory_write",
            policy=ats_policy,
            effect_class="INTERNAL_DESTINATION_WRITTEN",
            status="NOT_ATTEMPTED" if ats_policy in {"SKIPPED", "UNAVAILABLE"} else "POLICY_ENABLED",
            note="Selector memory writes are separately gated and skipped in Stage 0 cron.",
        ),
    ]
    for destination in (
        "gmail_send",
        "gmail_schedule_send",
        "gmail_forward",
        "linkedin_action",
        "meetup_rsvp",
        "ats_submit",
    ):
        policy = _publication_policy_value(publication, "forbidden_effects", destination)
        states.append(
            _publication_state(
                destination=destination,
                policy=policy,
                effect_class=(
                    "HUMAN_TRANSMITTED"
                    if destination.startswith("gmail")
                    else "EXTERNAL_SITE_MUTATED"
                ),
                status="FORBIDDEN" if policy == "FORBIDDEN" else "POLICY_ENABLED",
                note="Forbidden or human-only effect; monitor-opportunities did not perform it.",
            )
        )
    return states


def _count_required_nulls(value: Any) -> int:
    if value is None:
        return 1
    if isinstance(value, dict):
        return sum(_count_required_nulls(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_required_nulls(item) for item in value)
    return 0


def _find_posted_fields(value: Any, *, path: str = "") -> list[str]:
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "posted":
                found.append(child_path)
            found.extend(_find_posted_fields(item, path=child_path))
        return found
    if isinstance(value, list):
        found = []
        for index, item in enumerate(value):
            found.extend(_find_posted_fields(item, path=f"{path}[{index}]"))
        return found
    return []


def build_receipt_consistency(
    *,
    run_dir: Path,
    receipt: dict[str, Any],
    manifest: dict[str, Any],
    publication: dict[str, Any] | None = None,
) -> dict[str, Any]:
    publication = publication or _publication_status(run_dir, receipt)
    artifact_reconciliation = _artifact_reconciliation(manifest)
    publication_states = _canonical_publication_states(run_dir, receipt, publication)
    count_mismatches: list[dict[str, Any]] = []
    if not artifact_reconciliation["ok"]:
        count_mismatches.append(
            {
                "kind": "artifact_accounting",
                "declared_action_worthy_total": artifact_reconciliation[
                    "declared_action_worthy_total"
                ],
                "calculated_action_worthy_total": artifact_reconciliation[
                    "calculated_action_worthy_total"
                ],
                "declared_visible_total": artifact_reconciliation["declared_visible_total"],
                "calculated_visible_total": artifact_reconciliation["calculated_visible_total"],
                "declared_hidden_total": artifact_reconciliation["declared_hidden_total"],
                "calculated_hidden_total": artifact_reconciliation["calculated_hidden_total"],
            }
        )
    required_payload = {
        "run_id": receipt.get("run_id"),
        "terminal_state": receipt.get("terminal_state"),
        "external_effects": receipt.get("external_effects"),
        "publication_mode": publication.get("mode"),
        "artifact_accounting": {
            "action_worthy_total": (manifest.get("artifact_accounting") or {}).get(
                "action_worthy_total"
            ),
            "visible_total": (manifest.get("artifact_accounting") or {}).get("visible_total"),
            "hidden_total": (manifest.get("artifact_accounting") or {}).get("hidden_total"),
        },
        "publication_states": publication_states,
    }
    required_nulls = _count_required_nulls(required_payload)
    classified_posted_fields = {
        "buzz-summary-receipt.posted",
    }
    ambiguous_posted_fields = sorted(
        set(_find_posted_fields(publication))
        - classified_posted_fields
    )
    stage0_external_site_mutations = [
        state["destination"]
        for state in publication_states
        if state["effect_class"] == "EXTERNAL_SITE_MUTATED"
        and state["status"] not in {"FORBIDDEN", "NOT_ATTEMPTED"}
    ]
    status = (
        "PASS"
        if required_nulls == 0
        and not count_mismatches
        and not ambiguous_posted_fields
        and not stage0_external_site_mutations
        else "FAIL"
    )
    return {
        "schema": "monitor_opportunities.receipt_consistency.v1",
        "status": status,
        "run_id": receipt.get("run_id", ""),
        "artifact_reconciliation": artifact_reconciliation,
        "required_nulls": required_nulls,
        "count_mismatches": len(count_mismatches),
        "count_mismatch_details": count_mismatches,
        "publication_state_vocabulary": list(PUBLICATION_EFFECT_CLASSES),
        "publication_states": publication_states,
        "ambiguous_posted_fields": ambiguous_posted_fields,
        "stage0_external_site_mutations": stage0_external_site_mutations,
        "external_effects": bool(receipt.get("external_effects", False)),
        "mocked": False,
        "live": bool(receipt.get("live", False)),
    }


def _is_stale(completed_at: str | None) -> bool:
    if not completed_at:
        return True
    try:
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - completed).total_seconds() > 24 * 60 * 60
