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
    ExecutionClaim,
    HandoffRequest,
    PacketStatus,
    Readiness,
)
from ops_linkedin.service import attest_human_completion, policy_report, prepare_handoff

NOW = datetime(2026, 8, 2, 15, 0, tzinfo=UTC)


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
                    "source_refs": ["local-review-receipt.json"],
                }
            ],
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
            claim_id="unsupported",
            text="Unsupported claim.",
            status=ClaimStatus.VERIFIED,
            source_refs=[],
        )


def test_blank_source_reference_is_rejected() -> None:
    """Whitespace cannot satisfy the evidence ledger."""

    with pytest.raises(ValidationError, match="nonblank"):
        Claim(
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
                        "source_refs": ["source-1"],
                    },
                    {
                        "claim_id": "same",
                        "text": "Second.",
                        "status": "verified",
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


def test_policy_has_no_automation_escape_hatch() -> None:
    """The policy report must name the prohibited technical surfaces."""

    policy = policy_report()
    prohibited = " ".join(policy.prohibited).lower()

    assert "automated access" in prohibited
    assert "scraping" in prohibited
    assert "cookies" in prohibited
    assert "automated posting" in prohibited


def test_policy_cli_outputs_machine_readable_json() -> None:
    """Exercise the real Typer entrypoint without mocks or network access."""

    result = CliRunner().invoke(app, ["policy"])

    assert result.exit_code == 0, result.output
    assert '"schema_version": "ops-linkedin.policy.v1"' in result.output
    assert '"design_posture": "draft-and-human-handoff"' in result.output


def test_example_manifest_is_valid() -> None:
    """Keep the shipped publish example synchronized with the request schema."""

    path = Path(__file__).parent.parent / "assets" / "examples" / "publish-post.json"
    request = HandoffRequest.model_validate_json(path.read_text(encoding="utf-8"))

    assert request.action.value == "post"
