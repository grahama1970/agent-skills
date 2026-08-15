"""Locator evidence cannot independently admit opportunities."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from monitor_opportunities.contracts import ContractError, validate_manifest
from monitor_opportunities.discovery import _linkedin_evidence_candidates
from monitor_opportunities.pipeline import _is_report_opportunity, _source_intel
from monitor_opportunities.verification import built_in_fixture


def test_linkedin_only_candidate_is_source_intel_not_opportunity() -> None:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "ops-linkedin-jobs-capture.json"
    receipt, candidates = _linkedin_evidence_candidates(fixture)
    assert receipt["required_source_id"] == "linkedin_top_applicant"
    assert candidates
    assert all(not _is_report_opportunity(candidate) for candidate in candidates)
    intel = [_source_intel(candidate) for candidate in candidates]
    assert all(item and item["signal_type"] == "LINKEDIN_LOCATOR" for item in intel)
    assert all(item and item["decision"] == "LOCATOR_ONLY" for item in intel)


def test_report_visible_opportunity_must_cite_known_accepted_source_receipt() -> None:
    data = copy.deepcopy(built_in_fixture())
    data["opportunities"][0]["source_receipt_ids"] = ["src:missing"]

    with pytest.raises(ContractError) as exc:
        validate_manifest(data)

    assert exc.value.code == "REPORT_VISIBLE_SOURCE_RECEIPT_UNKNOWN"


def test_report_visible_opportunity_cannot_be_admitted_from_degraded_source() -> None:
    data = copy.deepcopy(built_in_fixture())
    data["source_receipts"][0]["result_status"] = "FEED_DOWN"
    data["source_receipts"][0]["limitations"] = ["source unavailable"]

    with pytest.raises(ContractError) as exc:
        validate_manifest(data)

    assert exc.value.code == "REPORT_VISIBLE_SOURCE_NOT_ACCEPTED"


def test_report_visible_source_intel_can_cite_visible_degraded_receipt() -> None:
    data = copy.deepcopy(built_in_fixture())
    data["source_receipts"].append(
        {
            **data["source_receipts"][0],
            "receipt_id": "src:degraded",
            "result_status": "AUTH_REQUIRED",
            "response_status": None,
            "content_sha256": None,
            "limitations": ["Human read-only capture required."],
        }
    )
    data["source_intel"] = [
        {
            "signal_id": "intel:auth-required",
            "lane": "A",
            "signal_type": "LINKEDIN_LOCATOR",
            "title": "LinkedIn top-applicant capture required",
            "organization": "LinkedIn",
            "source_receipt_ids": ["src:degraded"],
            "primary_evidence_url": None,
            "decision": "LOCATOR_ONLY",
            "reasons": ["Visible degraded-source receipt, not a no-match."],
            "action_worthy": False,
            "visible_in_report": True,
        }
    ]

    manifest = validate_manifest(data)

    assert manifest.source_intel[0].source_receipt_ids == ["src:degraded"]


def test_report_visible_source_intel_cannot_cite_no_matches_receipt() -> None:
    data = copy.deepcopy(built_in_fixture())
    data["source_receipts"].append(
        {
            **data["source_receipts"][0],
            "receipt_id": "src:no-matches",
            "result_status": "NO_MATCHES",
            "limitations": [],
        }
    )
    data["source_intel"] = [
        {
            "signal_id": "intel:no-matches",
            "lane": "A",
            "signal_type": "LINKEDIN_LOCATOR",
            "title": "No matches is not evidence for a visible proposition",
            "organization": "LinkedIn",
            "source_receipt_ids": ["src:no-matches"],
            "primary_evidence_url": None,
            "decision": "LOCATOR_ONLY",
            "reasons": ["This should fail."],
            "action_worthy": False,
            "visible_in_report": True,
        }
    ]

    with pytest.raises(ContractError) as exc:
        validate_manifest(data)

    assert exc.value.code == "REPORT_VISIBLE_SOURCE_NOT_ACCEPTED"


def test_report_visible_relationship_signal_must_cite_source_receipt() -> None:
    data = copy.deepcopy(built_in_fixture())
    data["relationship_signals"] = [
        {
            "signal_id": "rel:missing-source",
            "source_opportunity_id": data["opportunities"][0]["opportunity_id"],
            "signal_type": "direct_contact",
            "subject": "Known contact",
            "organization": data["opportunities"][0]["organization"],
            "relationship_path": ["Graham Anderson", "Known contact"],
            "evidence_refs": ["memory://relationship"],
            "source_receipt_ids": [],
            "provenance": "Relationship claim without source receipt should fail.",
            "recommended_action": "human_decide_reconnect_or_defer",
            "contact_channel_risk": "corporate_email_may_be_blocked_after_long_gap",
            "preferred_human_channels": ["LINKEDIN_HUMAN_HANDOFF"],
            "channel_guidance": ["Use a human-authorized channel."],
            "external_effects": False,
            "action_worthy": True,
            "visible_in_report": True,
        }
    ]
    data["artifact_accounting"]["action_worthy_total"] += 1
    data["artifact_accounting"]["visible_total"] += 1

    with pytest.raises(ContractError) as exc:
        validate_manifest(data)

    assert exc.value.code == "REPORT_VISIBLE_SOURCE_RECEIPT_MISSING"
