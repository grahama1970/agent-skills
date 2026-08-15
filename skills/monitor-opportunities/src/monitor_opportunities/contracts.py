"""Typed Stage 0 report contracts and fail-closed semantic validation."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

IMMUTABLE_GOAL = (
    "Daily top opportunities that are highly targeted, delivered in an interactive "
    "report/interview, with human-authorized application preparation using a custom targeted resume given the algorithm "
    "likely employed by the employer or client."
)
CONTRACT_VERSION = "0.2.0"
STAGE = "STAGE_0_RESEARCH_ONLY"
SENSITIVE_FIELD_TYPES = {
    "free_text",
    "self_identification",
    "salary",
    "clearance",
    "work_authorization",
    "legal",
}


class ResultStatus(StrEnum):
    MATCHES = "MATCHES"
    NO_MATCHES = "NO_MATCHES"
    FEED_DOWN = "FEED_DOWN"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    STALE_DATA = "STALE_DATA"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NOT_SEARCHED = "NOT_SEARCHED"


DEGRADED_RESULT_STATUSES = {
    ResultStatus.FEED_DOWN,
    ResultStatus.AUTH_REQUIRED,
    ResultStatus.AUTH_FAILED,
    ResultStatus.RATE_LIMITED,
    ResultStatus.POLICY_BLOCKED,
    ResultStatus.STALE_DATA,
    ResultStatus.INVALID_REQUEST,
    ResultStatus.INVALID_RESPONSE,
}


class ContractError(ValueError):
    """Stable machine-readable contract error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ImmutableGoal(StrictModel):
    text: str = Field(min_length=40)
    goal_hash: str | None = None


class CapabilityAuthority(StrictModel):
    local_report: str
    local_resume_variant: str
    gmail_mailbox_draft_create: str
    linkedin_human_handoff_ready: str
    ats_form_inspect: str
    ats_form_prefill: str
    ats_form_submit: str


class LaneCoverage(StrictModel):
    lane: str
    searched: bool
    result_status: ResultStatus
    candidates_observed: int = Field(ge=0)
    candidates_admitted: int = Field(ge=0)
    candidates_admitted_opportunities: int = Field(default=0, ge=0)
    candidates_admitted_source_intel: int = Field(default=0, ge=0)
    source_receipt_ids: list[str]
    limitations: list[str]


class SourceReceipt(StrictModel):
    receipt_id: str
    lane: str
    provider: str
    target: str
    source_class: str
    result_status: ResultStatus
    observed_at: str
    request_summary: str
    response_status: int | None
    content_type: str | None
    response_bytes: int = Field(ge=0)
    content_sha256: str | None
    evidence_refs: list[str]
    limitations: list[str]
    automation_policy: str | None = None
    required_source_id: str | None = None
    channel: str | None = None
    fallback_for_receipt_id: str | None = None


class EligibilityRejection(StrictModel):
    rejection_id: str
    lane: str
    title: str
    organization: str
    reason_code: str
    source_receipt_id: str
    action_worthy: bool
    visible_in_report: bool


class Location(StrictModel):
    display: str
    workplace_type: str
    relocation_required: bool


class ScreeningInterfaceProfile(StrictModel):
    observed: list[str]
    inferred: list[str]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]
    unknowns: list[str] = Field(min_length=1)


class Opportunity(StrictModel):
    opportunity_id: str
    lane: str
    opportunity_type: str
    title: str
    organization: str
    posting_url: str | None = None
    apply_url: str | None = None
    primary_evidence_url: str | None = None
    location: Location
    source_receipt_ids: list[str] = Field(min_length=1)
    eligibility_state: str
    fit_score: float = Field(ge=0, le=1)
    claim_keys: list[str] = Field(min_length=1)
    why_candidate: list[str] = Field(min_length=1)
    screening_interface_profile: ScreeningInterfaceProfile
    relationship_signal_ids: list[str] = []
    relationship_signal_count: int = Field(default=0, ge=0)
    status: str
    action_worthy: bool
    visible_in_report: bool


class SourceIntel(StrictModel):
    signal_id: str
    lane: str
    signal_type: str
    title: str
    organization: str
    source_receipt_ids: list[str] = Field(min_length=1)
    primary_evidence_url: str | None = None
    decision: str
    reasons: list[str]
    action_worthy: bool
    visible_in_report: bool


class PresentationDiff(StrictModel):
    allowed_changes: list[str]
    prohibited_changes: list[str]


class ResumeVariant(StrictModel):
    variant_id: str
    opportunity_id: str
    claim_snapshot_sha256: str
    claim_keys: list[str] = Field(min_length=1)
    artifact_refs: list[str] = Field(min_length=1)
    presentation_diff: PresentationDiff
    status: str
    action_worthy: bool
    visible_in_report: bool


class OutreachPacket(StrictModel):
    packet_id: str
    opportunity_id: str
    channel: str
    recipient: str
    contact_provenance: str
    subject: str | None
    body: str
    character_count: int = Field(ge=1)
    claim_keys: list[str] = Field(min_length=1)
    claim_snapshot_sha256: str
    roundtable_status: str
    roundtable_verdict: str | None
    roundtable_receipt_digest: str | None
    reviewed_payload_digest: str | None = None
    revision_note: str | None = None
    payload_digest: str
    readiness_state: str
    effect_status: str
    draft_id: str | None = None
    mailbox_draft_ref: str | None = None
    effect_receipt_digest: str | None = None
    sendable: bool
    candidate_transmits: bool
    human_send_steps: list[str] = Field(min_length=1)
    action_worthy: bool
    visible_in_report: bool


class ApplicationField(StrictModel):
    name: str
    field_type: str
    required: bool
    disposition: str
    automated_answer: str | None


class Application(StrictModel):
    application_id: str
    opportunity_id: str
    ats_provider: str | None
    state: str
    authorized: bool
    form_schema_digest: str | None
    fields: list[ApplicationField]
    action_worthy: bool
    visible_in_report: bool


class ApplicationPacket(StrictModel):
    schema_name: str = Field(alias="schema")
    packet_id: str
    created_at: str
    application_id: str
    opportunity_id: str
    posting_digest: str
    screening_interface_profile_digest: str
    resume_variant_id: str
    resume_artifacts: list[dict[str, Any]]
    resume_digest: str
    claim_snapshot_digest: str
    field_answer_digest: str
    attachment_digest: str
    outreach_digest: str
    policy_observations: list[str]
    policy_observations_digest: str
    approval_payload_digest: str
    approval_status: str
    packet_ref: str
    action_worthy: bool
    visible_in_report: bool
    external_effects: bool


class RelationshipSignal(StrictModel):
    signal_id: str
    source_opportunity_id: str
    signal_type: str
    subject: str
    organization: str
    relationship_path: list[str] = Field(min_length=2)
    evidence_refs: list[str]
    source_receipt_ids: list[str]
    provenance: str
    memory_recall_found: bool | None = None
    memory_recall_degraded: bool | None = None
    recommended_action: str
    contact_channel_risk: str
    preferred_human_channels: list[str] = Field(min_length=1)
    channel_guidance: list[str] = Field(min_length=1)
    external_effects: bool
    action_worthy: bool
    visible_in_report: bool


class RelationshipBindingDiagnostic(StrictModel):
    diagnostic_id: str
    signal_id: str
    opportunity_id: str | None = None
    organization_key: str
    reason_code: str
    detail: str
    external_effects: bool
    visible_in_report: bool


class TauSemanticRelationshipStatus(StrEnum):
    HAS_RELATIONSHIP_EVIDENCE = "HAS_RELATIONSHIP_EVIDENCE"
    NO_RELATIONSHIP_EVIDENCE = "NO_RELATIONSHIP_EVIDENCE"


class TauSemanticOutputType(StrEnum):
    SEMANTIC_ADDENDUM = "semantic_addendum"
    INTERVIEW_ADDENDUM = "interview_addendum"


class TauSemanticRelationshipEvidence(StrictModel):
    signal_id: str
    redacted_contact_ref: str
    relationship_type: str
    strength_confidence: float = Field(ge=0, le=1)
    observed_at: str
    source_receipt_hash: str
    permitted_fact: str


class TauSemanticPolicy(StrictModel):
    external_effects: bool
    allowed_output_types: list[TauSemanticOutputType] = Field(min_length=1)
    timeout_seconds: int = Field(gt=0, le=3600)
    max_concurrency: int = Field(gt=0, le=4)
    max_attempts: int = Field(gt=0, le=3)
    max_cost_usd: float = Field(ge=0, le=25)


class TauSemanticInput(StrictModel):
    schema_name: str = Field(alias="schema")
    run_id: str
    source_run_receipt_ref: str
    source_run_sha256: str
    opportunity_id: str
    rank: int = Field(ge=1)
    selected_at: str
    immutable_goal: ImmutableGoal
    goal_hash: str
    candidate_profile_version: str
    candidate_profile_sha256: str
    allowed_fact_ledger: list[str] = Field(min_length=1)
    primary_opportunity_evidence_present: bool
    primary_opportunity_evidence_ids: list[str] = Field(min_length=1)
    primary_source_classes: list[str] = Field(min_length=1)
    retained_artifact_hashes: list[str] = Field(min_length=1)
    source_receipt_hashes: list[str] = Field(min_length=1)
    fetched_at: str
    source_health_state: str
    relationship_status: TauSemanticRelationshipStatus
    relationship_evidence: list[TauSemanticRelationshipEvidence] = Field(default_factory=list)
    meetup_evidence_present: bool = False
    meetup_policy: str = "SUPPLEMENTAL_ONLY"
    policy: TauSemanticPolicy


class TalkingPoint(StrictModel):
    text: str
    claim_keys: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class InterviewPrep(StrictModel):
    opportunity_id: str
    talking_points: list[TalkingPoint] = Field(min_length=1)


class DecisionAction(StrictModel):
    action: str
    target_type: str
    enabled: bool
    effects_external: bool


class ArtifactAccounting(StrictModel):
    action_worthy_total: int = Field(ge=0)
    visible_total: int = Field(ge=0)
    hidden_total: int = Field(ge=0)
    hidden_ids: list[str]


class ReportManifest(StrictModel):
    schema_name: str = Field(alias="schema")
    run_id: str
    generated_at: str
    contract_version: str
    immutable_goal: ImmutableGoal
    stage: str
    operational_readiness: str
    capability_authority: CapabilityAuthority
    lane_coverage: list[LaneCoverage]
    source_receipts: list[SourceReceipt]
    eligibility_rejections: list[EligibilityRejection]
    opportunities: list[Opportunity]
    source_intel: list[SourceIntel] = []
    resume_variants: list[ResumeVariant]
    outreach_packets: list[OutreachPacket]
    applications: list[Application]
    application_packets: list[ApplicationPacket] = []
    relationship_signals: list[RelationshipSignal] = []
    relationship_binding_diagnostics: list[RelationshipBindingDiagnostic] = []
    interview_prep: list[InterviewPrep]
    decision_actions: list[DecisionAction]
    artifact_accounting: ArtifactAccounting
    non_claims: list[str] = Field(min_length=1)


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise ContractError("SCHEMA_INVALID", f"Missing required top-level field: {key}")
    return raw[key]


def _validate_raw_semantics(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise ContractError("SCHEMA_INVALID", "Report manifest must be a JSON object")

    if _require(raw, "stage") != STAGE:
        raise ContractError("STAGE_NOT_RESEARCH_ONLY", f"Stage must be {STAGE}")

    opportunities = _require(raw, "opportunities")
    if not isinstance(opportunities, list):
        raise ContractError("SCHEMA_INVALID", "opportunities must be an array")
    if len(opportunities) > 8:
        raise ContractError("SHORTLIST_LIMIT_EXCEEDED", "Stage 0 shortlist cannot exceed eight")

    valid_statuses = {status.value for status in ResultStatus}
    for lane in _require(raw, "lane_coverage"):
        status = lane.get("result_status")
        if status not in valid_statuses:
            raise ContractError("UNKNOWN_SOURCE_STATUS", f"Unknown lane result status: {status}")
        if lane.get("searched") is False and status != ResultStatus.NOT_SEARCHED.value:
            raise ContractError(
                "NOT_SEARCHED_MISMATCH", "A lane not searched must be NOT_SEARCHED"
            )
        if status == ResultStatus.NOT_SEARCHED.value and lane.get("searched") is not False:
            raise ContractError(
                "NOT_SEARCHED_MISMATCH", "NOT_SEARCHED requires searched=false"
            )

    for receipt in _require(raw, "source_receipts"):
        status = receipt.get("result_status")
        if status not in valid_statuses:
            raise ContractError("UNKNOWN_SOURCE_STATUS", f"Unknown receipt status: {status}")

    for opportunity in opportunities:
        if opportunity.get("location", {}).get("relocation_required") is True:
            raise ContractError(
                "RELOCATION_SHORTLISTED", "Relocation-required opportunities cannot be shortlisted"
            )
        if opportunity.get("opportunity_type") == "networking_signal":
            raise ContractError(
                "NETWORKING_SIGNAL_ADMITTED",
                "Networking source intelligence cannot be admitted as an opportunity",
            )
        if any("linkedin.com" in str(opportunity.get(field) or "").lower() for field in ("posting_url", "primary_evidence_url")):
            raise ContractError(
                "LINKEDIN_ONLY_ADMITTED",
                "LinkedIn-only evidence is source intelligence until primary-source readback admits it",
            )

    for item in raw.get("source_intel", []):
        signal_type = item.get("signal_type")
        decision = item.get("decision")
        if signal_type == "MEETUP_NETWORKING" and decision not in {"ATTEND_MEETUP", "WATCH_MEETUP", "SKIP_MEETUP"}:
            raise ContractError("SOURCE_INTEL_DECISION_INVALID", f"Unsupported Meetup decision: {decision}")
        if signal_type == "LINKEDIN_LOCATOR" and item.get("action_worthy") is not False:
            raise ContractError("LINKEDIN_LOCATOR_ACTIONABLE", "LinkedIn locator evidence is not action-worthy")

    for signal in raw.get("relationship_signals", []):
        if signal.get("external_effects") is not False:
            raise ContractError("RELATIONSHIP_SIGNAL_EXTERNAL_EFFECT", "Relationship signals are local-only")
        if signal.get("visible_in_report") is not True:
            raise ContractError("RELATIONSHIP_SIGNAL_HIDDEN", "Relationship signals must be report-visible")

    relationship_ids = {signal.get("signal_id") for signal in raw.get("relationship_signals", [])}
    for diagnostic in raw.get("relationship_binding_diagnostics", []):
        if diagnostic.get("external_effects") is not False:
            raise ContractError(
                "RELATIONSHIP_BINDING_DIAGNOSTIC_EXTERNAL_EFFECT",
                "Relationship binding diagnostics are local-only",
            )
        if diagnostic.get("visible_in_report") is not True:
            raise ContractError(
                "RELATIONSHIP_BINDING_DIAGNOSTIC_HIDDEN",
                "Relationship binding diagnostics must be report-visible",
            )
        signal_id = diagnostic.get("signal_id")
        if signal_id not in relationship_ids:
            raise ContractError(
                "RELATIONSHIP_BINDING_DIAGNOSTIC_SIGNAL_MISSING",
                f"Relationship binding diagnostic references missing signal: {signal_id}",
            )
    for opportunity in opportunities:
        attached = opportunity.get("relationship_signal_ids") or []
        if opportunity.get("relationship_signal_count", 0) != len(attached):
            raise ContractError(
                "RELATIONSHIP_SIGNAL_COUNT_MISMATCH",
                "Opportunity relationship_signal_count must equal relationship_signal_ids length",
            )
        missing = [signal_id for signal_id in attached if signal_id not in relationship_ids]
        if missing:
            raise ContractError(
                "RELATIONSHIP_SIGNAL_ATTACHMENT_MISSING",
                f"Opportunity references missing relationship signals: {missing}",
            )

    for packet in _require(raw, "outreach_packets"):
        if packet.get("sendable") is not False:
            raise ContractError("OUTREACH_SENDABLE_STAGE0", "Stage 0 outreach cannot be sendable")
        if packet.get("candidate_transmits") is not True:
            raise ContractError(
                "HUMAN_TRANSMISSION_REQUIRED", "The candidate must transmit every message"
            )
        effect_status = packet.get("effect_status")
        if effect_status not in {"WOULD_PRESENT_STAGE0", "DRAFT_CREATED_NOT_SENT", "INDETERMINATE"}:
            raise ContractError("OUTREACH_EFFECT_STATUS_INVALID", f"Unsupported outreach effect: {effect_status}")
        if effect_status == "DRAFT_CREATED_NOT_SENT":
            if packet.get("channel") != "GMAIL":
                raise ContractError("OUTREACH_DRAFT_CHANNEL_INVALID", "Only Gmail packets can reference Gmail drafts")
            if packet.get("gmail_sent") is True or packet.get("sendable") is not False:
                raise ContractError("OUTREACH_SENDABLE_STAGE0", "Gmail draft packets cannot be sendable")
            if not packet.get("draft_id") or not packet.get("effect_receipt_digest"):
                raise ContractError("OUTREACH_DRAFT_RECEIPT_MISSING", "Gmail draft packets require draft readback")
            if packet.get("roundtable_status") != "PASS" or packet.get("readiness_state") != "REVIEW_PERMITTED":
                raise ContractError("OUTREACH_DRAFT_WITHOUT_REVIEW", "Gmail drafts require permitting review")
        elif any(packet.get(field) for field in ("draft_id", "mailbox_draft_ref", "effect_receipt_digest")):
            raise ContractError("OUTREACH_EFFECT_REF_WITHOUT_EFFECT", "Draft refs require a draft effect")
        if packet.get("channel") == "LINKEDIN" and packet.get("subject") is not None:
            raise ContractError("LINKEDIN_SUBJECT_INVALID", "LinkedIn handoff packets do not use a subject")
        if packet.get("contact_provenance") in {"", None}:
            raise ContractError("CONTACT_PROVENANCE_MISSING", "Outreach packets must record contact provenance")
        if packet.get("roundtable_status") != "PASS" and packet.get("readiness_state") == "REVIEW_PERMITTED":
            raise ContractError("OUTREACH_READY_WITHOUT_ROUNDTABLE", "Outreach readiness requires PASS roundtable")

    for application in _require(raw, "applications"):
        if application.get("authorized") is not False or application.get("state") != "BLOCKED_STAGE_0":
            raise ContractError(
                "ATS_AUTHORIZED_STAGE0", "ATS applications must remain blocked and unauthorized"
            )
        for field in application.get("fields", []):
            field_type = field.get("field_type")
            if field_type in SENSITIVE_FIELD_TYPES:
                if field.get("disposition") != "human_required" or field.get(
                    "automated_answer"
                ) is not None:
                    raise ContractError(
                        "HUMAN_REQUIRED_FIELD_AUTOFILLED",
                        f"Sensitive/free-text field was automated: {field.get('name')}",
                    )
            if field.get("disposition") == "human_required" and field.get(
                "automated_answer"
            ) is not None:
                raise ContractError(
                    "HUMAN_REQUIRED_FIELD_AUTOFILLED",
                    f"human_required field has an automated answer: {field.get('name')}",
                )

    for packet in raw.get("application_packets", []):
        if packet.get("visible_in_report") is not True:
            raise ContractError("APPLICATION_PACKET_HIDDEN", "Application packet must be visible in the report")
        if packet.get("approval_status") != "NOT_AUTHORIZED":
            raise ContractError("APPLICATION_PACKET_AUTHORIZED_STAGE0", "Stage 0 packet starts unauthorized")
        if packet.get("external_effects") is not False:
            raise ContractError("APPLICATION_PACKET_EXTERNAL_EFFECT", "Application packet cannot cause external effects")


def _artifact_rows(manifest: ReportManifest) -> list[tuple[str, bool, bool]]:
    rows: list[tuple[str, bool, bool]] = []
    for item in manifest.opportunities:
        rows.append((item.opportunity_id, item.action_worthy, item.visible_in_report))
    for item in manifest.source_intel:
        rows.append((item.signal_id, item.action_worthy, item.visible_in_report))
    for item in manifest.resume_variants:
        rows.append((item.variant_id, item.action_worthy, item.visible_in_report))
    for item in manifest.outreach_packets:
        rows.append((item.packet_id, item.action_worthy, item.visible_in_report))
    for item in manifest.applications:
        rows.append((item.application_id, item.action_worthy, item.visible_in_report))
    for item in manifest.application_packets:
        rows.append((item.packet_id, item.action_worthy, item.visible_in_report))
    for item in manifest.relationship_signals:
        rows.append((item.signal_id, item.action_worthy, item.visible_in_report))
    return rows


def _validate_model_semantics(manifest: ReportManifest) -> None:
    if manifest.schema_name != "monitor_opportunities.report.v1":
        raise ContractError(
            "SCHEMA_VERSION_UNSUPPORTED", f"Unsupported schema: {manifest.schema_name}"
        )
    if manifest.contract_version != CONTRACT_VERSION:
        raise ContractError(
            "CONTRACT_VERSION_UNSUPPORTED",
            f"Contract must be {CONTRACT_VERSION}, got {manifest.contract_version}",
        )
    if manifest.immutable_goal.text != IMMUTABLE_GOAL:
        raise ContractError("IMMUTABLE_GOAL_MISMATCH", "Report is not bound to the immutable goal")

    lanes = [lane.lane for lane in manifest.lane_coverage]
    if sorted(lanes) != ["A", "B", "C"]:
        raise ContractError("LANE_COVERAGE_INCOMPLETE", "Exactly one record for lanes A, B, and C is required")

    receipts_by_lane: dict[str, list[SourceReceipt]] = {"A": [], "B": [], "C": []}
    receipts_by_id: dict[str, SourceReceipt] = {}
    for receipt in manifest.source_receipts:
        receipts_by_lane.setdefault(receipt.lane, []).append(receipt)
        receipts_by_id[receipt.receipt_id] = receipt

    for lane in manifest.lane_coverage:
        receipt_statuses = {
            receipt.result_status
            for receipt in receipts_by_lane.get(lane.lane, [])
            if receipt.receipt_id in lane.source_receipt_ids
        }
        if lane.result_status == ResultStatus.NO_MATCHES and receipt_statuses & DEGRADED_RESULT_STATUSES:
            raise ContractError(
                "FEED_FAILURE_MISLABELED",
                f"Lane {lane.lane} reports NO_MATCHES despite degraded source evidence",
            )
        if lane.searched and not lane.source_receipt_ids:
            raise ContractError(
                "SOURCE_RECEIPT_MISSING", f"Searched lane {lane.lane} has no source receipt"
            )

    def validate_source_backing(
        *,
        item_kind: str,
        item_id: str,
        source_receipt_ids: list[str],
        allow_degraded: bool,
    ) -> None:
        if not source_receipt_ids:
            raise ContractError(
                "REPORT_VISIBLE_SOURCE_RECEIPT_MISSING",
                f"{item_kind} {item_id} is report-visible without source receipts",
            )
        for receipt_id in source_receipt_ids:
            receipt = receipts_by_id.get(receipt_id)
            if receipt is None:
                raise ContractError(
                    "REPORT_VISIBLE_SOURCE_RECEIPT_UNKNOWN",
                    f"{item_kind} {item_id} cites unknown source receipt: {receipt_id}",
                )
            if receipt.result_status == ResultStatus.MATCHES:
                continue
            if allow_degraded and receipt.result_status in DEGRADED_RESULT_STATUSES:
                if not receipt.limitations:
                    raise ContractError(
                        "DEGRADED_SOURCE_LIMITATION_MISSING",
                        f"{item_kind} {item_id} cites degraded receipt {receipt_id} without limitations",
                    )
                continue
            raise ContractError(
                "REPORT_VISIBLE_SOURCE_NOT_ACCEPTED",
                f"{item_kind} {item_id} cites {receipt_id} with status {receipt.result_status.value}",
            )

    for opportunity in manifest.opportunities:
        if opportunity.visible_in_report:
            validate_source_backing(
                item_kind="opportunity",
                item_id=opportunity.opportunity_id,
                source_receipt_ids=opportunity.source_receipt_ids,
                allow_degraded=False,
            )

    for item in manifest.source_intel:
        if item.visible_in_report:
            validate_source_backing(
                item_kind="source_intel",
                item_id=item.signal_id,
                source_receipt_ids=item.source_receipt_ids,
                allow_degraded=True,
            )

    for signal in manifest.relationship_signals:
        if signal.visible_in_report:
            validate_source_backing(
                item_kind="relationship_signal",
                item_id=signal.signal_id,
                source_receipt_ids=signal.source_receipt_ids,
                allow_degraded=True,
            )

    visible_opportunity_ids = {
        opportunity.opportunity_id
        for opportunity in manifest.opportunities
        if opportunity.visible_in_report
    }

    def require_visible_opportunity(item_kind: str, item_id: str, opportunity_id: str) -> None:
        if opportunity_id not in visible_opportunity_ids:
            raise ContractError(
                "DERIVED_ARTIFACT_OPPORTUNITY_MISSING",
                f"{item_kind} {item_id} references non-visible or missing opportunity {opportunity_id}",
            )

    for variant in manifest.resume_variants:
        if variant.visible_in_report:
            require_visible_opportunity("resume_variant", variant.variant_id, variant.opportunity_id)
    for packet in manifest.outreach_packets:
        if packet.visible_in_report:
            require_visible_opportunity("outreach_packet", packet.packet_id, packet.opportunity_id)
    for application in manifest.applications:
        if application.visible_in_report:
            require_visible_opportunity("application", application.application_id, application.opportunity_id)
    for packet in manifest.application_packets:
        if packet.visible_in_report:
            require_visible_opportunity("application_packet", packet.packet_id, packet.opportunity_id)
    for prep in manifest.interview_prep:
        require_visible_opportunity("interview_prep", prep.opportunity_id, prep.opportunity_id)
        for index, point in enumerate(prep.talking_points):
            validate_source_backing(
                item_kind="interview_talking_point",
                item_id=f"{prep.opportunity_id}:{index}",
                source_receipt_ids=point.source_refs,
                allow_degraded=False,
            )

    rows = _artifact_rows(manifest)
    action_worthy = [row for row in rows if row[1]]
    hidden = [artifact_id for artifact_id, _, visible in action_worthy if not visible]
    visible = [row for row in action_worthy if row[2]]
    accounting = manifest.artifact_accounting
    if hidden:
        raise ContractError("HIDDEN_ACTION_ARTIFACT", f"Hidden action-worthy artifacts: {hidden}")
    if accounting.hidden_total != 0 or accounting.hidden_ids:
        raise ContractError("HIDDEN_ACTION_ARTIFACT", "Manifest declares hidden artifacts")
    if accounting.action_worthy_total != len(action_worthy):
        raise ContractError(
            "ARTIFACT_ACCOUNTING_MISMATCH",
            "action_worthy_total does not match calculated artifacts",
        )
    if accounting.visible_total != len(visible):
        raise ContractError(
            "ARTIFACT_ACCOUNTING_MISMATCH", "visible_total does not match calculated artifacts"
        )

    blocked_values = {"BLOCKED_STAGE_0", "NOT_IMPLEMENTED"}
    authority = manifest.capability_authority
    external = {
        "gmail_mailbox_draft_create": authority.gmail_mailbox_draft_create,
        "linkedin_human_handoff_ready": authority.linkedin_human_handoff_ready,
        "ats_form_inspect": authority.ats_form_inspect,
        "ats_form_prefill": authority.ats_form_prefill,
        "ats_form_submit": authority.ats_form_submit,
    }
    invalid = {name: value for name, value in external.items() if value not in blocked_values}
    if invalid:
        raise ContractError(
            "EXTERNAL_CAPABILITY_ENABLED_STAGE0", f"Stage 0 external capabilities enabled: {invalid}"
        )

    for variant in manifest.resume_variants:
        if variant.presentation_diff.prohibited_changes:
            raise ContractError(
                "PROHIBITED_RESUME_DELTA", f"Variant {variant.variant_id} changes facts"
            )

    for action in manifest.decision_actions:
        if action.effects_external:
            raise ContractError(
                "EXTERNAL_DECISION_STAGE0", f"Decision {action.action} cannot cause an effect"
            )


def _validate_against_committed_schema(raw: dict[str, Any]) -> None:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "report.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(raw)
    except OSError as exc:
        raise ContractError("REPORT_SCHEMA_MISSING", str(schema_path)) from exc
    except JsonSchemaValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise ContractError("REPORT_SCHEMA_INVALID", f"{path}: {exc.message}") from exc


def _immutable_goal_hash() -> str:
    return "sha256:" + hashlib.sha256(IMMUTABLE_GOAL.encode("utf-8")).hexdigest()


def validate_tau_semantic_input(raw: dict[str, Any]) -> TauSemanticInput:
    """Parse and fail-closed validate one provider-live Tau semantic input."""

    try:
        payload = TauSemanticInput.model_validate(raw)
    except ValidationError as exc:
        raise ContractError("TAU_SEMANTIC_INPUT_SCHEMA_INVALID", str(exc)) from exc

    if payload.schema_name != "monitor_opportunities.tau_semantic_input.v1":
        raise ContractError("TAU_SEMANTIC_INPUT_SCHEMA_UNSUPPORTED", payload.schema_name)
    if payload.immutable_goal.text != IMMUTABLE_GOAL:
        raise ContractError(
            "TAU_SEMANTIC_GOAL_MISMATCH",
            "Semantic input is not bound to the immutable goal",
        )
    if payload.goal_hash != _immutable_goal_hash():
        raise ContractError(
            "TAU_SEMANTIC_GOAL_HASH_MISMATCH",
            "Semantic input goal hash does not match the immutable goal",
        )
    if payload.policy.external_effects is not False:
        raise ContractError(
            "TAU_SEMANTIC_EXTERNAL_EFFECT",
            "Semantic evaluation must not cause external effects",
        )
    if payload.primary_opportunity_evidence_present is not True:
        raise ContractError(
            "TAU_SEMANTIC_PRIMARY_EVIDENCE_REQUIRED",
            "Primary opportunity evidence is required",
        )

    primary_classes = {source_class.lower() for source_class in payload.primary_source_classes}
    if any("meetup" in source_class for source_class in primary_classes):
        raise ContractError(
            "TAU_SEMANTIC_MEETUP_PRIMARY_FORBIDDEN",
            "Meetup evidence is supplemental only",
        )
    if payload.meetup_evidence_present and payload.meetup_policy != "SUPPLEMENTAL_ONLY":
        raise ContractError(
            "TAU_SEMANTIC_MEETUP_POLICY_INVALID",
            "Meetup evidence must remain supplemental",
        )

    has_relationships = bool(payload.relationship_evidence)
    if (
        has_relationships
        and payload.relationship_status
        != TauSemanticRelationshipStatus.HAS_RELATIONSHIP_EVIDENCE
    ):
        raise ContractError(
            "TAU_SEMANTIC_RELATIONSHIP_STATUS_MISMATCH",
            "Relationship evidence requires HAS_RELATIONSHIP_EVIDENCE",
        )
    if (
        not has_relationships
        and payload.relationship_status != TauSemanticRelationshipStatus.NO_RELATIONSHIP_EVIDENCE
    ):
        raise ContractError(
            "TAU_SEMANTIC_RELATIONSHIP_STATUS_MISMATCH",
            "Missing relationship evidence must be explicit",
        )
    for evidence in payload.relationship_evidence:
        if "@" in evidence.redacted_contact_ref:
            raise ContractError(
                "TAU_SEMANTIC_CONTACT_NOT_REDACTED",
                "Provider inputs cannot expose raw contact addresses",
            )

    return payload


def validate_manifest(raw: dict[str, Any]) -> ReportManifest:
    """Parse and semantically validate a Stage 0 report manifest."""

    _validate_raw_semantics(raw)
    try:
        manifest = ReportManifest.model_validate(raw)
    except ValidationError as exc:
        raise ContractError("SCHEMA_INVALID", str(exc)) from exc
    _validate_model_semantics(manifest)
    _validate_against_committed_schema(raw)
    return manifest
