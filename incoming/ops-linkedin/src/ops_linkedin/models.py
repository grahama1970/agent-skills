"""Typed contracts for the draft-only LinkedIn operations skill.

Inputs are JSON request manifests written by an agent or human. Outputs are local
handoff packets that explicitly prove preparation only; they never prove that a
LinkedIn action was executed. Validation errors are fail-closed and surfaced to
the CLI as non-zero exits.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

REQUEST_SCHEMA = "ops-linkedin.request.v1"
HANDOFF_SCHEMA = "ops-linkedin.handoff.v1"
STATUS_SCHEMA = "ops-linkedin.status.v1"
POLICY_SCHEMA = "ops-linkedin.policy.v1"


def _require_utc(value: datetime, field_name: str) -> datetime:
    """Return an aware UTC timestamp or fail the external boundary."""

    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


class Lane(StrEnum):
    """High-level capability lanes exposed by the skill router."""

    PROFILE = "profile"
    EXPLORE = "explore"
    PUBLISH = "publish"
    INTERACT = "interact"
    LEAD_GEN = "lead-gen"
    CONTENT_OPS = "content-ops"


class Action(StrEnum):
    """Supported local preparation actions; no action performs network IO."""

    PROFILE_UPDATE = "profile-update"
    SEARCH_PLAN = "search-plan"
    POST = "post"
    IMAGE_POST = "image-post"
    COMMENT = "comment"
    CONNECTION_NOTE = "connection-note"
    MESSAGE = "message"
    LEAD_RESEARCH_PLAN = "lead-research-plan"
    CONTENT_REVIEW = "content-review"


class ClaimStatus(StrEnum):
    """Evidence state for a factual claim carried in a draft."""

    VERIFIED = "verified"
    NEEDS_SOURCE = "needs-source"
    EXCLUDED = "excluded"


class Readiness(StrEnum):
    """Whether a packet may be handed to a human for manual execution."""

    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    BLOCKED_UNVERIFIED_CLAIMS = "BLOCKED_UNVERIFIED_CLAIMS"
    BLOCKED_INVALID_REQUEST = "BLOCKED_INVALID_REQUEST"


class PacketStatus(StrEnum):
    """Lifecycle state for a local handoff packet."""

    PREPARED = "PREPARED"
    HUMAN_ATTESTED_COMPLETE = "HUMAN_ATTESTED_COMPLETE"


class ExecutionClaim(StrEnum):
    """Proof vocabulary that prevents prepared drafts from becoming fake receipts."""

    NOT_EXECUTED = "NOT_EXECUTED"
    USER_ATTESTED_MANUAL_ACTION = "USER_ATTESTED_MANUAL_ACTION"


class FeatureState(StrEnum):
    """State vocabulary used by the status report."""

    READY = "READY"
    PROHIBITED = "PROHIBITED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class ContentBlock(BaseModel):
    """User-facing copy and optional local attachments for a handoff."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, max_length=300)
    attachment_paths: list[Path] = Field(default_factory=list)

    @field_validator("attachment_paths")
    @classmethod
    def attachment_paths_are_absolute(cls, paths: list[Path]) -> list[Path]:
        """Require explicit local paths so handoff packets are unambiguous."""

        non_absolute = [str(path) for path in paths if not path.is_absolute()]
        if non_absolute:
            joined = ", ".join(non_absolute)
            raise ValueError(f"attachment paths must be absolute: {joined}")
        return paths


class Target(BaseModel):
    """Optional human-selected destination or recipient metadata."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    url: AnyHttpUrl | None = None


class Claim(BaseModel):
    """Evidence-bounded factual statement used by a profile or content draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=2_000)
    status: ClaimStatus
    source_refs: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("source_refs")
    @classmethod
    def source_refs_are_nonblank(cls, refs: list[str]) -> list[str]:
        """Reject blank evidence references that would create a hollow verified label."""

        cleaned = [ref.strip() for ref in refs]
        if any(not ref for ref in cleaned):
            raise ValueError("source_refs entries must be nonblank")
        return cleaned

    @model_validator(mode="after")
    def verified_claims_require_sources(self) -> Claim:
        """Reject a claim labeled verified when no evidence reference is supplied."""

        if self.status is ClaimStatus.VERIFIED and not self.source_refs:
            raise ValueError("verified claims require at least one source_refs entry")
        return self


class HandoffRequest(BaseModel):
    """Validated boundary object accepted by the prepare command."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[REQUEST_SCHEMA]
    lane: Lane
    action: Action
    content: ContentBlock | None = None
    target: Target | None = None
    claims: list[Claim] = Field(default_factory=list)
    research_inputs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def action_matches_lane_and_shape(self) -> HandoffRequest:
        """Fail closed on cross-lane actions or requests missing required copy."""

        allowed: dict[Lane, set[Action]] = {
            Lane.PROFILE: {Action.PROFILE_UPDATE},
            Lane.EXPLORE: {Action.SEARCH_PLAN},
            Lane.PUBLISH: {Action.POST, Action.IMAGE_POST},
            Lane.INTERACT: {
                Action.COMMENT,
                Action.CONNECTION_NOTE,
                Action.MESSAGE,
            },
            Lane.LEAD_GEN: {Action.LEAD_RESEARCH_PLAN},
            Lane.CONTENT_OPS: {Action.CONTENT_REVIEW},
        }
        if self.action not in allowed[self.lane]:
            raise ValueError(
                f"action '{self.action.value}' is not valid for lane '{self.lane.value}'"
            )

        actions_requiring_content = {
            Action.PROFILE_UPDATE,
            Action.SEARCH_PLAN,
            Action.POST,
            Action.IMAGE_POST,
            Action.COMMENT,
            Action.CONNECTION_NOTE,
            Action.MESSAGE,
            Action.LEAD_RESEARCH_PLAN,
            Action.CONTENT_REVIEW,
        }
        if self.action in actions_requiring_content and self.content is None:
            raise ValueError(f"action '{self.action.value}' requires content")

        if self.action is Action.IMAGE_POST and not self.content.attachment_paths:
            raise ValueError("image-post requires at least one local attachment path")

        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique within one request")

        return self


class Guardrails(BaseModel):
    """Machine-readable negative capabilities embedded in every handoff."""

    model_config = ConfigDict(extra="forbid")

    automated_linkedin_access: Literal[False] = False
    automated_submission: Literal[False] = False
    browser_cookie_access: Literal[False] = False
    scraping: Literal[False] = False
    bulk_action: Literal[False] = False
    human_execution_required: Literal[True] = True


class HumanAttestation(BaseModel):
    """A user's statement that they manually performed the prepared action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    actor: str = Field(min_length=1, max_length=200)
    attested_at: datetime
    statement: Literal["I performed this LinkedIn action manually."]

    @field_validator("attested_at")
    @classmethod
    def timestamp_is_utc_aware(cls, value: datetime) -> datetime:
        """Require an aware UTC timestamp so receipts compare deterministically."""

        return _require_utc(value, "attested_at")


class Proof(BaseModel):
    """Bounded proof attached to a handoff packet."""

    model_config = ConfigDict(extra="forbid")

    execution_claim: ExecutionClaim = ExecutionClaim.NOT_EXECUTED
    platform_verified: Literal[False] = False
    human_attestation: HumanAttestation | None = None


class HandoffPacket(BaseModel):
    """Local output passed to a human for review and manual execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[HANDOFF_SCHEMA] = HANDOFF_SCHEMA
    packet_id: UUID
    created_at: datetime
    request_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lane: Lane
    action: Action
    status: PacketStatus
    readiness: Readiness
    requires_human: Literal[True] = True
    target: Target | None = None
    content: ContentBlock | None = None
    claims: list[Claim] = Field(default_factory=list)
    guardrails: Guardrails = Field(default_factory=Guardrails)
    manual_steps: list[str] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)
    proof: Proof = Field(default_factory=Proof)

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc_aware(cls, value: datetime) -> datetime:
        """Reject naive or non-UTC packet timestamps at the file boundary."""

        return _require_utc(value, "created_at")

    @model_validator(mode="after")
    def lifecycle_is_consistent(self) -> HandoffPacket:
        """Keep status, readiness, and proof from contradicting one another."""

        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique within one packet")

        if self.status is PacketStatus.PREPARED:
            if self.proof.execution_claim is not ExecutionClaim.NOT_EXECUTED:
                raise ValueError("prepared packets must use NOT_EXECUTED proof")
            if self.proof.human_attestation is not None:
                raise ValueError("prepared packets cannot contain a human attestation")

        if self.status is PacketStatus.HUMAN_ATTESTED_COMPLETE:
            if self.readiness is not Readiness.READY_FOR_HUMAN_REVIEW:
                raise ValueError("blocked packets cannot be attested complete")
            if self.proof.execution_claim is not ExecutionClaim.USER_ATTESTED_MANUAL_ACTION:
                raise ValueError("completed packets require user-attested proof")
            if self.proof.human_attestation is None:
                raise ValueError("completed packets require a human attestation")
            if self.proof.human_attestation.attested_at < self.created_at:
                raise ValueError("human attestation cannot predate packet creation")

        return self


class FeatureStatus(BaseModel):
    """One inspectable feature row in the readiness report."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    state: FeatureState
    evidence: str


class StatusReport(BaseModel):
    """Current implementation state for the intentionally bounded skill."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[STATUS_SCHEMA] = STATUS_SCHEMA
    generated_at: datetime
    profile: Literal["local-draft-only"] = "local-draft-only"
    overall_readiness: Literal["READY_FOR_DRAFT_ONLY_USE"] = "READY_FOR_DRAFT_ONLY_USE"
    features: list[FeatureStatus]
    claims_proves: list[str]
    claims_does_not_prove: list[str]

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_utc_aware(cls, value: datetime) -> datetime:
        """Require the readiness snapshot to use an aware UTC timestamp."""

        return _require_utc(value, "generated_at")


class PolicyReport(BaseModel):
    """Dated platform-policy snapshot used to constrain implementation scope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[POLICY_SCHEMA] = POLICY_SCHEMA
    checked_at: str
    design_posture: Literal["draft-and-human-handoff"] = "draft-and-human-handoff"
    allowed: list[str]
    prohibited: list[str]
    official_sources: list[AnyHttpUrl]
    caveat: str
