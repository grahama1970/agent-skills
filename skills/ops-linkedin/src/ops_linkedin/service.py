"""Pure service functions for creating and attesting LinkedIn handoff packets.

The module performs no network calls and has no browser integration. Its outputs
are deterministic apart from UUIDs and UTC timestamps, and every output carries
machine-readable proof limits.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from ops_linkedin.models import (
    OUTBOUND_ACTIONS,
    Action,
    ClaimStatus,
    ExecutionClaim,
    FeatureState,
    FeatureStatus,
    Guardrails,
    HandoffPacket,
    HandoffRequest,
    HumanAttestation,
    PacketStatus,
    PolicyReport,
    Proof,
    Readiness,
    StatusReport,
)

POLICY_CHECKED_AT = "2026-08-02"
HUMAN_ATTESTATION_STATEMENT = "I performed this LinkedIn action manually."


def utc_now() -> datetime:
    """Return one timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def request_digest(request: HandoffRequest) -> str:
    """Hash a canonical JSON rendering of a validated request."""

    payload = request.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def determine_readiness(request: HandoffRequest) -> Readiness:
    """Block evidence-sensitive operations when their claim ledger is incomplete."""

    unresolved = [claim for claim in request.claims if claim.status is ClaimStatus.NEEDS_SOURCE]
    if unresolved:
        return Readiness.BLOCKED_UNVERIFIED_CLAIMS

    claim_required_actions = {
        Action.PROFILE_UPDATE,
        Action.LEAD_RESEARCH_PLAN,
    }
    verified = [claim for claim in request.claims if claim.status is ClaimStatus.VERIFIED]
    if request.action in claim_required_actions and not verified:
        return Readiness.BLOCKED_UNVERIFIED_CLAIMS

    # Operator decision 2026-08-02: every outbound action is gated by an /ask
    # roundtable following best-practices-roundtable. Checked here rather than in
    # the model alone so a request without a panel is BLOCKED and inspectable
    # instead of raising a validation error the caller might mistake for a bug.
    if request.action in OUTBOUND_ACTIONS:
        review = request.roundtable_review
        if review is None or not review.permits_execution:
            return Readiness.BLOCKED_MISSING_ROUNDTABLE

    return Readiness.READY_FOR_HUMAN_REVIEW


def warnings_for(request: HandoffRequest, readiness: Readiness) -> list[str]:
    """Return explicit limitations without inferring claims from free-form text."""

    warnings: list[str] = []
    if readiness is Readiness.BLOCKED_MISSING_ROUNDTABLE:
        review = request.roundtable_review
        if review is None:
            warnings.append(
                "This outbound action has no roundtable_review. Every outbound LinkedIn "
                "action requires an /ask roundtable per best-practices-roundtable: concurrent "
                "topology, an immutable goal, at least two PASSing seats, and an attributed "
                "synthesis. Run the panel and attach its receipt."
            )
        else:
            warnings.append(
                f"The roundtable returned verdict '{review.verdict.value}', which does not "
                "permit execution. Revise the draft and convene a new panel, or record the "
                "human decision explicitly."
            )
    if readiness is Readiness.BLOCKED_UNVERIFIED_CLAIMS:
        warnings.append(
            "The request is blocked because evidence-sensitive content has no complete "
            "verified claim ledger. Add source references or exclude the unsupported claims."
        )
    if not request.claims:
        warnings.append(
            "No claim ledger was supplied. The human reviewer must verify every factual "
            "statement before copying this draft into LinkedIn."
        )
    if request.action in {Action.CONNECTION_NOTE, Action.MESSAGE}:
        warnings.append(
            "Confirm the recipient, relationship context, consent expectations, and tone "
            "before sending a single manual message."
        )
    if request.action is Action.LEAD_RESEARCH_PLAN:
        warnings.append(
            "Do not turn this plan into scraping, bulk profile collection, or automated outreach."
        )
    return warnings


def manual_steps_for(request: HandoffRequest) -> list[str]:
    """Build action-specific instructions that always require a human at LinkedIn."""

    common = [
        "Review the target, copy, attachments, and evidence ledger outside LinkedIn.",
        "Open LinkedIn yourself in a supported browser; this skill must not inspect the session.",
    ]
    action_steps: dict[Action, list[str]] = {
        Action.PROFILE_UPDATE: [
            "Navigate manually to the relevant profile section and compare each proposed field.",
            "Apply only evidence-backed edits, review public visibility, and save manually.",
        ],
        Action.SEARCH_PLAN: [
            "Paste the prepared query into LinkedIn manually and inspect results yourself.",
            "Record only the small set of profiles or posts you deliberately select; do not scrape.",
        ],
        Action.POST: [
            "Create a new post manually, paste the reviewed copy, and inspect the audience setting.",
            "Publish only after the preview and factual claims are correct.",
        ],
        Action.IMAGE_POST: [
            "Create a new post manually, add only the listed local images, and inspect alt text.",
            "Paste the reviewed copy, confirm the audience, and publish manually.",
        ],
        Action.COMMENT: [
            "Open the exact post manually and confirm the draft still fits the live context.",
            "Paste and submit one comment manually.",
        ],
        Action.CONNECTION_NOTE: [
            "Open the exact profile manually and confirm that a connection request is appropriate.",
            "Paste the reviewed note and send one request manually.",
        ],
        Action.MESSAGE: [
            "Open the exact conversation manually and confirm the intended recipient.",
            "Paste the reviewed message and send it manually.",
        ],
        Action.LEAD_RESEARCH_PLAN: [
            "Use public-web research and user-provided data to narrow the candidate set first.",
            "Inspect any LinkedIn profile manually and decide individually whether outreach is appropriate.",
        ],
        Action.CONTENT_REVIEW: [
            "Review the analysis against the user-provided or exported source material.",
            "Make any LinkedIn edits or follow-up actions manually.",
        ],
    }
    return common + action_steps[request.action] + [
        "Run the attest command only after you personally completed the action; attestation is not platform verification."
    ]


def prepare_handoff(request: HandoffRequest, *, now: datetime | None = None) -> HandoffPacket:
    """Create a local, non-executing handoff packet from a validated request."""

    created_at = now or utc_now()
    readiness = determine_readiness(request)
    return HandoffPacket(
        packet_id=uuid4(),
        created_at=created_at,
        request_digest_sha256=request_digest(request),
        lane=request.lane,
        action=request.action,
        status=PacketStatus.PREPARED,
        readiness=readiness,
        target=request.target,
        content=request.content,
        claims=request.claims,
        guardrails=Guardrails(),
        manual_steps=manual_steps_for(request),
        warnings=warnings_for(request, readiness),
        proof=Proof(),
    )


def attest_human_completion(
    packet: HandoffPacket,
    *,
    actor: str,
    confirmed: bool,
    now: datetime | None = None,
) -> HandoffPacket:
    """Add a bounded user attestation without claiming independent platform proof."""

    if not confirmed:
        raise ValueError("explicit --confirm-human-completed is required")
    if packet.status is not PacketStatus.PREPARED:
        raise ValueError("only PREPARED packets can be attested")
    if packet.readiness is not Readiness.READY_FOR_HUMAN_REVIEW:
        raise ValueError("blocked packets cannot be attested complete")

    attestation = HumanAttestation(
        actor=actor,
        attested_at=now or utc_now(),
        statement=HUMAN_ATTESTATION_STATEMENT,
    )
    payload = packet.model_dump(mode="python")
    payload.update(
        {
            "status": PacketStatus.HUMAN_ATTESTED_COMPLETE,
            "proof": Proof(
                execution_claim=ExecutionClaim.USER_ATTESTED_MANUAL_ACTION,
                platform_verified=False,
                human_attestation=attestation,
            ),
        }
    )
    return HandoffPacket.model_validate(payload)


def policy_report() -> PolicyReport:
    """Return the dated implementation-policy snapshot."""

    return PolicyReport(
        checked_at=POLICY_CHECKED_AT,
        allowed=[
            "Draft profile copy, posts, comments, connection notes, and messages locally.",
            "Prepare source-derived own-profile sync packets and Surf command plans after explicit account-risk acceptance.",
            "Analyze user-provided or exported content and metrics.",
            "Create manual search and lead-research plans using public-web sources.",
            "Create local handoff packets and record explicit human completion attestations.",
        ],
        prohibited=[
            "Automated access to third-party LinkedIn pages, feeds, posts, messages, search results, or DOM content.",
            "Scraping profiles, posts, contacts, or search results.",
            "Reading or copying browser cookies, passwords, or session tokens.",
            "Automated posting, liking, commenting, connecting, following, or messaging.",
            "Bulk or inauthentic engagement and attempts to evade platform controls.",
        ],
        official_sources=[
            "https://www.linkedin.com/legal/user-agreement",
            "https://www.linkedin.com/help/linkedin/answer/a1339701",
        ],
        caveat=(
            "This is a dated engineering-policy snapshot, not legal advice. Re-check the "
            "official terms before expanding the skill or adding an authorized API adapter."
        ),
    )


def status_report(*, now: datetime | None = None) -> StatusReport:
    """Return an honest readiness report for implemented and excluded surfaces."""

    return StatusReport(
        generated_at=now or utc_now(),
        features=[
            FeatureStatus(
                feature="typed request validation",
                state=FeatureState.READY,
                evidence="Pydantic v2 request, claim, and packet models",
            ),
            FeatureStatus(
                feature="local draft and handoff generation",
                state=FeatureState.READY,
                evidence="prepare command emits ops-linkedin.handoff.v1",
            ),
            FeatureStatus(
                feature="bounded human completion attestation",
                state=FeatureState.READY,
                evidence="attest command preserves platform_verified=false",
            ),
            FeatureStatus(
                feature="source-derived editable profile entry",
                state=FeatureState.READY,
                evidence="profile-entry-export emits ops-linkedin.profile_entry.v1 from RESUME.md",
            ),
            FeatureStatus(
                feature="source-derived own-profile sync planning",
                state=FeatureState.READY,
                evidence="profile-sync-plan emits ops-linkedin.profile_sync.v1 from RESUME.md or an editable profile-entry JSON",
            ),
            FeatureStatus(
                feature="LinkedIn browser automation outside own-profile sync",
                state=FeatureState.PROHIBITED,
                evidence="policy and packet guardrails exclude third-party profiles, scraping, and social actions",
            ),
            FeatureStatus(
                feature="official LinkedIn API adapter",
                state=FeatureState.NOT_IMPLEMENTED,
                evidence="requires documented authorization and separate review",
            ),
            FeatureStatus(
                feature="live Surf own-profile execution proof",
                state=FeatureState.NOT_ESTABLISHED,
                evidence="profile-sync-plan prepares a bounded Surf plan but does not execute LinkedIn edits",
            ),
        ],
        claims_proves=[
            "The CLI can validate manifests and create local handoff packets.",
            "The CLI can derive an editable LinkedIn profile entry from a canonical resume source digest.",
            "The CLI can derive an own-profile sync plan from the editable profile-entry JSON.",
            "Prepared packets state that no LinkedIn action was executed.",
            "A human attestation remains distinct from platform verification.",
        ],
        claims_does_not_prove=[
            "That LinkedIn accepted, displayed, or delivered any action.",
            "That Surf executed the emitted own-profile plan or saved a profile edit.",
            "That platform terms will remain unchanged after the policy snapshot date.",
            "That an official API integration is authorized or available.",
        ],
    )
