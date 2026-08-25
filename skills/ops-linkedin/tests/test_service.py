"""Behavioral tests for draft-only preparation, blocking, and attestation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ops_linkedin.cli import app
from ops_linkedin.models import (
    Claim,
    ClaimStatus,
    ContactGraphTarget,
    ExecutionClaim,
    HandoffRequest,
    PacketStatus,
    Readiness,
)
from ops_linkedin.profile_sync import (
    LinkedInProfileEntry,
    build_profile_entry,
    build_profile_sync_packet_from_entry,
)
from ops_linkedin.service import (
    attest_human_completion,
    build_contact_graph_capture_plan,
    policy_report,
    prepare_handoff,
)

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=UTC)


ROUNDTABLE_REVIEW = {'ran': True, 'run_dir': '/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/example-linkedin-r1', 'topology': 'concurrent', 'immutable_goal': 'Approve or reject this outbound LinkedIn action without overclaiming beyond the bound claim ledger.', 'shared_packet_identical_for_every_seat': True, 'seats': [{'handler': 'webgpt', 'status': 'PASS', 'response_bytes': 3820}, {'handler': 'webclaude', 'status': 'PASS', 'response_bytes': 3410}, {'handler': 'webkimi', 'status': 'NEEDS_ATTENTION', 'failure_code': 'missing_sentinel'}], 'synthesis': {'seat_status': '2 PASS; webkimi NEEDS_ATTENTION (missing_sentinel), named separately and not folded into consensus', 'common_ground': 'Specific non-generic reason present; single low-friction ask; no claim exceeds the ledger', 'attributed_dissent': '', 'claims_still_unverified': 'none beyond the bound ledger', 'surviving_dissent_reported_to_human': False}, 'rounds_run': 1, 'verdict': 'SEND_AS_IS', 'follows_best_practices_roundtable': True, 'closure_note': 'Deliberation closed; the packet must still pass local validation and a human executes it.'}
"""A PASSing panel receipt reused by outbound-action tests."""


def publish_request() -> HandoffRequest:
    """Return a minimal evidence-backed post request."""

    return HandoffRequest.model_validate(
        {
            "schema_version": "ops-linkedin.request.v1",
            "lane": "publish",
            "action": "post",
            "content": {"text": "A reviewed local draft."},
            "claims": [
                {
                    "claim_id": "draft-source",
                    "text": "The draft was reviewed locally.",
                    "status": "verified",
                    "claim_key": "test.bound.claim",
                    "source_refs": ["local-review-receipt.json"],
                }
            ],
            "roundtable_review": ROUNDTABLE_REVIEW,
        }
    )



def test_prepare_packet_never_claims_execution() -> None:
    """Prepared output must prove only local preparation."""

    packet = prepare_handoff(publish_request(), now=NOW)

    assert packet.status is PacketStatus.PREPARED
    assert packet.readiness is Readiness.READY_FOR_HUMAN_REVIEW
    assert packet.requires_human is True
    assert packet.guardrails.automated_linkedin_access is False
    assert packet.guardrails.automated_submission is False
    assert packet.proof.execution_claim is ExecutionClaim.NOT_EXECUTED
    assert packet.proof.platform_verified is False
    assert packet.proof.human_attestation is None


def test_profile_update_without_verified_claims_is_blocked() -> None:
    """Evidence-sensitive profile copy must fail closed."""

    request = HandoffRequest.model_validate(
        {
            "schema_version": "ops-linkedin.request.v1",
            "lane": "profile",
            "action": "profile-update",
            "content": {"text": "Built systems at exceptional scale."},
            "claims": [
                {
                    "claim_id": "scale",
                    "text": "Built systems at exceptional scale.",
                    "status": "needs-source",
                }
            ],
        }
    )

    packet = prepare_handoff(request, now=NOW)

    assert packet.readiness is Readiness.BLOCKED_UNVERIFIED_CLAIMS
    assert any("blocked" in warning.lower() for warning in packet.warnings)


def test_verified_claim_requires_source_reference() -> None:
    """A verified label without evidence is invalid at the boundary."""

    with pytest.raises(ValidationError):
        Claim(
            claim_key="test.bound.claim",
            claim_id="unsupported",
            text="Unsupported claim.",
            status=ClaimStatus.VERIFIED,
            source_refs=[],
        )


def test_blank_source_reference_is_rejected() -> None:
    """Whitespace cannot satisfy the evidence ledger."""

    with pytest.raises(ValidationError, match="nonblank"):
        Claim(
            claim_key="test.bound.claim",
            claim_id="blank-source",
            text="Claim with a hollow reference.",
            status=ClaimStatus.VERIFIED,
            source_refs=["   "],
        )


def test_duplicate_claim_ids_are_rejected() -> None:
    """A request ledger must have stable, unambiguous claim identities."""

    with pytest.raises(ValidationError, match="unique"):
        HandoffRequest.model_validate(
            {
                "schema_version": "ops-linkedin.request.v1",
                "lane": "publish",
                "action": "post",
                "content": {"text": "Duplicate claims."},
                "claims": [
                    {
                        "claim_id": "same",
                        "text": "First.",
                        "status": "verified",
                    "claim_key": "test.bound.claim",
                        "source_refs": ["source-1"],
                    },
                    {
                        "claim_id": "same",
                        "text": "Second.",
                        "status": "verified",
                    "claim_key": "test.bound.claim",
                        "source_refs": ["source-2"],
                    },
                ],
            }
        )


def test_packet_created_at_must_be_utc_aware() -> None:
    """Serialized packets cannot admit naive timestamps."""

    packet = prepare_handoff(publish_request(), now=NOW)
    payload = packet.model_dump(mode="python")
    payload["created_at"] = datetime(2026, 8, 2, 15, 0)

    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        type(packet).model_validate(payload)


def test_schema_version_is_required() -> None:
    """External manifests must opt into the exact supported schema."""

    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(
            {
                "lane": "publish",
                "action": "post",
                "content": {"text": "Missing schema."},
            }
        )


def test_lane_action_mismatch_is_rejected() -> None:
    """The router contract must reject cross-lane actions."""

    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(
            {
                "schema_version": "ops-linkedin.request.v1",
                "lane": "publish",
                "action": "message",
                "content": {"text": "Wrong lane."},
            }
        )


def test_attachment_paths_must_be_absolute() -> None:
    """Relative paths are ambiguous across agent working directories."""

    with pytest.raises(ValidationError, match="absolute"):
        HandoffRequest.model_validate(
            {
                "schema_version": "ops-linkedin.request.v1",
                "lane": "publish",
                "action": "image-post",
                "content": {
                    "text": "Image caption.",
                    "attachment_paths": ["relative/banner.png"],
                },
            }
        )


def test_attestation_requires_explicit_confirmation() -> None:
    """The CLI/service cannot infer that a human completed an action."""

    packet = prepare_handoff(publish_request(), now=NOW)

    with pytest.raises(ValueError, match="explicit"):
        attest_human_completion(packet, actor="Graham", confirmed=False, now=NOW)


def test_attestation_remains_distinct_from_platform_verification() -> None:
    """A human statement must not become an independent LinkedIn receipt."""

    packet = prepare_handoff(publish_request(), now=NOW)
    completed = attest_human_completion(packet, actor="Graham", confirmed=True, now=NOW)

    assert completed.status is PacketStatus.HUMAN_ATTESTED_COMPLETE
    assert completed.proof.execution_claim is ExecutionClaim.USER_ATTESTED_MANUAL_ACTION
    assert completed.proof.platform_verified is False
    assert completed.proof.human_attestation is not None
    assert completed.proof.human_attestation.actor == "Graham"


def test_blocked_packet_cannot_be_attested() -> None:
    """A missing evidence gate cannot be bypassed by manual-attestation flags."""

    request = HandoffRequest.model_validate(
        {
            "schema_version": "ops-linkedin.request.v1",
            "lane": "lead-gen",
            "action": "lead-research-plan",
            "content": {"text": "Target people with unverified roles."},
        }
    )
    packet = prepare_handoff(request, now=NOW)

    with pytest.raises(ValueError, match="blocked"):
        attest_human_completion(packet, actor="Graham", confirmed=True, now=NOW)


def test_policy_allows_bounded_contact_graph_plans_without_outbound_actions() -> None:
    """The policy report must name the narrow contact-graph allowance and bans."""

    policy = policy_report()
    allowed = " ".join(policy.allowed).lower()
    prohibited = " ".join(policy.prohibited).lower()

    assert "contact-graph capture plans" in allowed
    assert "unscoped automated access" in prohibited
    assert "scraping" in prohibited
    assert "cookies" in prohibited
    assert "automated posting" in prohibited
    assert "beyond visible relationship degree" in prohibited


def test_policy_cli_outputs_machine_readable_json() -> None:
    """Exercise the real Typer entrypoint without mocks or network access."""

    result = CliRunner().invoke(app, ["policy"])

    assert result.exit_code == 0, result.output
    assert '"schema_version": "ops-linkedin.policy.v1"' in result.output
    assert '"design_posture": "draft-human-handoff-plus-opt-in-own-profile-sync"' in result.output


def test_example_manifest_is_valid() -> None:
    """Keep the shipped publish example synchronized with the request schema."""

    path = Path(__file__).parent.parent / "assets" / "examples" / "publish-post.json"
    request = HandoffRequest.model_validate_json(path.read_text(encoding="utf-8"))

    assert request.action.value == "post"


def _outbound(action: str, lane: str, **overrides: object) -> dict:
    """Build a minimal outbound request payload for gate tests."""

    payload = {
        "schema_version": "ops-linkedin.request.v1",
        "lane": lane,
        "action": action,
        "content": {"text": "A specific, reviewed reason for writing."},
        "target": {"name": "Example Recipient"},
        "roundtable_review": ROUNDTABLE_REVIEW,
    }
    payload.update(overrides)
    return payload


def test_outbound_action_without_roundtable_is_blocked() -> None:
    """Every outbound action requires a panel; absence must fail closed."""

    payload = _outbound("connection-note", "interact")
    del payload["roundtable_review"]
    packet = prepare_handoff(HandoffRequest.model_validate(payload), now=NOW)

    assert packet.readiness is Readiness.BLOCKED_MISSING_ROUNDTABLE
    assert packet.status is PacketStatus.PREPARED
    assert any("roundtable" in warning.lower() for warning in packet.warnings)


def test_outbound_action_with_passing_roundtable_is_ready() -> None:
    """A concurrent panel with two PASSing seats and a send verdict unblocks review."""

    packet = prepare_handoff(
        HandoffRequest.model_validate(_outbound("message", "interact")), now=NOW
    )

    assert packet.readiness is Readiness.READY_FOR_HUMAN_REVIEW
    assert packet.proof.execution_claim is ExecutionClaim.NOT_EXECUTED


def test_do_not_send_verdict_blocks_execution() -> None:
    """A panel that says do not send cannot yield a human-executable packet."""

    review = dict(ROUNDTABLE_REVIEW)
    review["verdict"] = "DO_NOT_SEND"
    packet = prepare_handoff(
        HandoffRequest.model_validate(
            _outbound("comment", "interact", roundtable_review=review)
        ),
        now=NOW,
    )

    assert packet.readiness is Readiness.BLOCKED_MISSING_ROUNDTABLE
    assert any("DO_NOT_SEND" in warning for warning in packet.warnings)


def test_needs_human_decision_verdict_blocks_execution() -> None:
    """An undecided panel is not an approval."""

    review = dict(ROUNDTABLE_REVIEW)
    review["verdict"] = "NEEDS_HUMAN_DECISION"
    packet = prepare_handoff(
        HandoffRequest.model_validate(
            _outbound("post", "publish", target=None, roundtable_review=review)
        ),
        now=NOW,
    )

    assert packet.readiness is Readiness.BLOCKED_MISSING_ROUNDTABLE


def test_single_passing_seat_is_not_a_panel() -> None:
    """One voice is not a roundtable; the model must reject it outright."""

    review = dict(ROUNDTABLE_REVIEW)
    review["seats"] = [
        {"handler": "webgpt", "status": "PASS"},
        {"handler": "webclaude", "status": "NEEDS_ATTENTION"},
        {"handler": "webkimi", "status": "RATE_LIMITED"},
    ]
    with pytest.raises(ValidationError, match=">=2 PASS seats"):
        HandoffRequest.model_validate(
            _outbound("message", "interact", roundtable_review=review)
        )


def test_sequential_topology_is_rejected() -> None:
    """A sequential chain is a pipeline, not a roundtable."""

    review = dict(ROUNDTABLE_REVIEW)
    review["topology"] = "sequential"
    with pytest.raises(ValidationError):
        HandoffRequest.model_validate(
            _outbound("message", "interact", roundtable_review=review)
        )


def test_verified_claim_requires_canonical_claim_key() -> None:
    """A verified claim with no claim_key would be a second source of truth."""

    with pytest.raises(ValidationError, match="claim_key"):
        HandoffRequest.model_validate(
            _outbound(
                "post",
                "publish",
                target=None,
                claims=[
                    {
                        "claim_id": "unbound",
                        "text": "An unbound verified assertion.",
                        "status": "verified",
                        "source_refs": ["https://example.org/proof"],
                    }
                ],
            )
        )


def test_profile_update_does_not_require_a_roundtable() -> None:
    """profile-update edits the user's own surface and is not outbound contact."""

    packet = prepare_handoff(
        HandoffRequest.model_validate(
            {
                "schema_version": "ops-linkedin.request.v1",
                "lane": "profile",
                "action": "profile-update",
                "content": {"text": "Updated headline copy."},
                "claims": [
                    {
                        "claim_id": "role",
                        "text": "Prime and lead researcher for CS Group on DARPA ARCOS.",
                        "status": "verified",
                        "claim_key": "arcos.acert.prime_lead_researcher",
                        "source_refs": ["career_profile:resume:general"],
                    }
                ],
            }
        ),
        now=NOW,
    )

    assert packet.readiness is Readiness.READY_FOR_HUMAN_REVIEW


def test_profile_entry_export_is_editable_source_derived_json() -> None:
    """Project agents edit a profile-entry JSON document, not LinkedIn directly."""

    resume = Path(__file__).resolve().parents[3] / "RESUME.md"
    entry = build_profile_entry(
        resume_path=resume,
        profile_url="https://www.linkedin.com/in/grahamanderson/",
        now=NOW,
    )
    payload = entry.model_dump(mode="json")
    round_trip = LinkedInProfileEntry.model_validate(payload)

    assert round_trip.schema_version == "ops-linkedin.profile_entry.v1"
    assert round_trip.location == "Buffalo, NY (EST)"
    assert round_trip.name == "Graham Anderson"
    assert "Principal AI Engineer" in round_trip.headline
    assert any(link.label == "Resume" for link in round_trip.featured_links)
    assert round_trip.source.sha256
    assert round_trip.editor_notes


def test_profile_sync_plan_consumes_editable_entry_without_execution_claim() -> None:
    """A reviewed profile-entry JSON can become a Surf plan without claiming an edit."""

    resume = Path(__file__).resolve().parents[3] / "RESUME.md"
    entry = build_profile_entry(
        resume_path=resume,
        profile_url="https://www.linkedin.com/in/grahamanderson/",
        now=NOW,
    )
    entry = LinkedInProfileEntry.model_validate(
        {
            **entry.model_dump(mode="json"),
            "headline": "Plain edited headline from the project agent",
        }
    )
    packet = build_profile_sync_packet_from_entry(profile_entry=entry)

    assert packet.schema_version == "ops-linkedin.profile_sync.v1"
    assert packet.profile_entry.headline == "Plain edited headline from the project agent"
    assert packet.guardrails.external_effects is False
    assert packet.guardrails.no_outbound_social_actions is True
    assert packet.execution_claim == "NOT_EXECUTED"
    assert any(field.field == "headline" for field in packet.fields)


def test_contact_graph_capture_plan_requires_authorization_flags() -> None:
    """Read-only third-party inspection planning needs both explicit acknowledgements."""

    target = ContactGraphTarget(
        name="George Small",
        company="Moog",
        profile_url="https://www.linkedin.com/in/george-small-moog/",
    )

    with pytest.raises(ValueError, match="user-authorized-read-only"):
        build_contact_graph_capture_plan(
            opportunity="Moog Senior AI Engineer",
            targets=[target],
            user_authorized_read_only=False,
            accept_account_risk=True,
            now=NOW,
        )

    with pytest.raises(ValueError, match="accept-account-risk"):
        build_contact_graph_capture_plan(
            opportunity="Moog Senior AI Engineer",
            targets=[target],
            user_authorized_read_only=True,
            accept_account_risk=False,
            now=NOW,
        )


def test_contact_graph_capture_plan_is_read_only_and_not_executed() -> None:
    """The plan permits degree/mutual capture but never social actions."""

    plan = build_contact_graph_capture_plan(
        opportunity="Moog Senior AI Engineer",
        targets=[
            ContactGraphTarget(
                name="George Small",
                company="Moog",
                profile_url="https://www.linkedin.com/in/george-small-moog/",
            )
        ],
        user_authorized_read_only=True,
        accept_account_risk=True,
        tab_id="837413494",
        now=NOW,
    )

    assert plan.schema_version == "ops-linkedin.contact_graph_capture_plan.v1"
    assert plan.authorization == "USER_AUTHORIZED_READ_ONLY_ACCOUNT_RISK_ACCEPTED"
    assert plan.execution_claim == "NOT_EXECUTED"
    assert plan.platform_verified is False
    assert any("visible LinkedIn relationship degree" in item for item in plan.allowed_observations)
    prohibited = " ".join(plan.prohibited_actions)
    assert "connect" in prohibited
    assert "send any message/InMail" in prohibited
    assert plan.suggested_surf_commands


def test_contact_graph_target_must_be_linkedin_profile_url() -> None:
    """Search result pages and company pages are outside this bounded lane."""

    with pytest.raises(ValidationError, match="linkedin.com/in"):
        ContactGraphTarget(
            name="Moog",
            company="Moog",
            profile_url="https://www.linkedin.com/company/moog-inc/",
        )


def test_contact_graph_capture_plan_cli() -> None:
    """Exercise the real Typer command without opening LinkedIn."""

    result = CliRunner().invoke(
        app,
        [
            "contact-graph-capture-plan",
            "--opportunity",
            "Moog Senior AI Engineer",
            "--target",
            "George Small|Moog|https://www.linkedin.com/in/george-small-moog/",
            "--user-authorized-read-only",
            "--accept-account-risk",
            "--tab-id",
            "837413494",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "ops-linkedin.contact_graph_capture_plan.v1" in result.output
    assert "USER_AUTHORIZED_READ_ONLY_ACCOUNT_RISK_ACCEPTED" in result.output
    assert "NOT_EXECUTED" in result.output
