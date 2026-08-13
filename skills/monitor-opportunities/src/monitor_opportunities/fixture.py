"""Built-in Stage 0 fixture used by deterministic verification."""

from __future__ import annotations

from typing import Any

from .contracts import IMMUTABLE_GOAL


def built_in_fixture() -> dict[str, Any]:
    zero = "0" * 64
    one = "1" * 64
    two = "2" * 64
    three = "3" * 64
    four = "4" * 64
    return {
        "schema": "monitor_opportunities.report.v1",
        "run_id": "mo_verify_builtin",
        "generated_at": "2026-08-03T13:00:00Z",
        "contract_version": "0.2.0",
        "immutable_goal": {"text": IMMUTABLE_GOAL, "goal_hash": zero},
        "stage": "STAGE_0_RESEARCH_ONLY",
        "operational_readiness": "FIXTURE_ONLY",
        "capability_authority": {
            "local_report": "ALLOWED",
            "local_resume_variant": "ALLOWED",
            "gmail_mailbox_draft_create": "BLOCKED_STAGE_0",
            "linkedin_human_handoff_ready": "BLOCKED_STAGE_0",
            "ats_form_inspect": "BLOCKED_STAGE_0",
            "ats_form_prefill": "BLOCKED_STAGE_0",
            "ats_form_submit": "BLOCKED_STAGE_0",
        },
        "lane_coverage": [
            {
                "lane": "A",
                "searched": True,
                "result_status": "MATCHES",
                "candidates_observed": 2,
                "candidates_admitted": 1,
                "source_receipt_ids": ["src:a"],
                "limitations": ["Built-in verification fixture."],
            },
            {
                "lane": "B",
                "searched": True,
                "result_status": "FEED_DOWN",
                "candidates_observed": 0,
                "candidates_admitted": 0,
                "source_receipt_ids": ["src:b"],
                "limitations": ["Run-specific fixture degradation."],
            },
            {
                "lane": "C",
                "searched": True,
                "result_status": "MATCHES",
                "candidates_observed": 1,
                "candidates_admitted": 1,
                "source_receipt_ids": ["src:c"],
                "limitations": ["Contact identity unknown."],
            },
        ],
        "source_receipts": [
            {
                "receipt_id": "src:a",
                "lane": "A",
                "provider": "greenhouse",
                "target": "Fixture Aerospace",
                "source_class": "employer_ats",
                "result_status": "MATCHES",
                "observed_at": "2026-08-03T12:30:00Z",
                "request_summary": "Fixture read",
                "response_status": 200,
                "content_type": "application/json",
                "response_bytes": 100,
                "content_sha256": one,
                "evidence_refs": ["fixture://a"],
                "limitations": ["No live network request."],
            },
            {
                "receipt_id": "src:b",
                "lane": "B",
                "provider": "sam.gov",
                "target": "SAM.gov Opportunities",
                "source_class": "federal_feed",
                "result_status": "FEED_DOWN",
                "observed_at": "2026-08-03T12:31:00Z",
                "request_summary": "Fixture health read",
                "response_status": 503,
                "content_type": "text/plain",
                "response_bytes": 0,
                "content_sha256": None,
                "evidence_refs": ["fixture://b"],
                "limitations": ["Fixture state only."],
            },
            {
                "receipt_id": "src:c",
                "lane": "C",
                "provider": "primary-company-source",
                "target": "Fixture Manufacturing",
                "source_class": "primary_company_source",
                "result_status": "MATCHES",
                "observed_at": "2026-08-03T12:32:00Z",
                "request_summary": "Fixture primary source read",
                "response_status": 200,
                "content_type": "text/html",
                "response_bytes": 200,
                "content_sha256": two,
                "evidence_refs": ["fixture://c"],
                "limitations": ["Budget and buyer unknown."],
            },
        ],
        "eligibility_rejections": [
            {
                "rejection_id": "reject:relocation",
                "lane": "A",
                "title": "Relocation Role",
                "organization": "Fixture Remote Co",
                "reason_code": "REJECT_RELOCATION_REQUIRED",
                "source_receipt_id": "src:a",
                "action_worthy": False,
                "visible_in_report": True,
            }
        ],
        "opportunities": [
            {
                "opportunity_id": "opp:a",
                "lane": "A",
                "opportunity_type": "employment_posting",
                "title": "Principal AI Architect",
                "organization": "Fixture Aerospace",
                "location": {
                    "display": "Buffalo, NY (hybrid)",
                    "workplace_type": "WNY_HYBRID",
                    "relocation_required": False,
                },
                "source_receipt_ids": ["src:a"],
                "eligibility_state": "ELIGIBLE_WNY_HYBRID",
                "fit_score": 0.9,
                "claim_keys": ["claim:tau"],
                "why_candidate": ["Receipt-gated agent architecture aligns."],
                "screening_interface_profile": {
                    "observed": ["Greenhouse host observed."],
                    "inferred": ["Single-column resume is prudent."],
                    "confidence": 0.7,
                    "evidence_refs": ["src:a"],
                    "unknowns": ["Ranking weights are unknown."],
                },
                "status": "SHORTLISTED",
                "action_worthy": True,
                "visible_in_report": True,
            },
            {
                "opportunity_id": "opp:c",
                "lane": "C",
                "opportunity_type": "commercial_signal",
                "title": "Document modernization need",
                "organization": "Fixture Manufacturing",
                "location": {
                    "display": "Delivery model unknown",
                    "workplace_type": "NOT_APPLICABLE",
                    "relocation_required": False,
                },
                "source_receipt_ids": ["src:c"],
                "eligibility_state": "ELIGIBLE_COMMERCIAL_SIGNAL",
                "fit_score": 0.8,
                "claim_keys": ["claim:pdf"],
                "why_candidate": ["Document extraction experience aligns."],
                "screening_interface_profile": {
                    "observed": ["No ATS is present."],
                    "inferred": ["Use a capability profile."],
                    "confidence": 0.6,
                    "evidence_refs": ["src:c"],
                    "unknowns": ["Budget and procurement path are unknown."],
                },
                "status": "SHORTLISTED",
                "action_worthy": True,
                "visible_in_report": True,
            },
        ],
        "resume_variants": [
            {
                "variant_id": "resume:a",
                "opportunity_id": "opp:a",
                "claim_snapshot_sha256": three,
                "claim_keys": ["claim:tau"],
                "artifact_refs": ["fixture://resume-a"],
                "presentation_diff": {
                    "allowed_changes": ["CLAIM_SELECTION"],
                    "prohibited_changes": [],
                },
                "status": "WOULD_PRESENT_STAGE0",
                "action_worthy": True,
                "visible_in_report": True,
            }
        ],
        "outreach_packets": [
            {
                "packet_id": "outreach:gmail",
                "opportunity_id": "opp:a",
                "channel": "GMAIL",
                "recipient": "CONTACT_UNKNOWN",
                "contact_provenance": "CONTACT_UNKNOWN",
                "subject": "Fixture opportunity",
                "body": "Local candidate-transmitted text.",
                "character_count": 33,
                "claim_keys": ["claim:tau"],
                "claim_snapshot_sha256": three,
                "roundtable_status": "NOT_RUN",
                "roundtable_verdict": None,
                "roundtable_receipt_digest": None,
                "payload_digest": zero,
                "readiness_state": "BLOCKED_ROUNDTABLE",
                "effect_status": "WOULD_PRESENT_STAGE0",
                "sendable": False,
                "candidate_transmits": True,
                "human_send_steps": ["Human reviews and transmits manually."],
                "action_worthy": True,
                "visible_in_report": True,
            }
        ],
        "applications": [
            {
                "application_id": "application:a",
                "opportunity_id": "opp:a",
                "ats_provider": "greenhouse",
                "state": "BLOCKED_STAGE_0",
                "authorized": False,
                "form_schema_digest": four,
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
        ],
        "interview_prep": [
            {
                "opportunity_id": "opp:a",
                "talking_points": [
                    {
                        "text": "Explain receipt-gated orchestration.",
                        "claim_keys": ["claim:tau"],
                        "source_refs": ["src:a"],
                    }
                ],
            }
        ],
        "decision_actions": [
            {
                "action": "KEEP",
                "target_type": "opportunity",
                "enabled": True,
                "effects_external": False,
            }
        ],
        "artifact_accounting": {
            "action_worthy_total": 5,
            "visible_total": 5,
            "hidden_total": 0,
            "hidden_ids": [],
        },
        "non_claims": ["Built-in fixture does not prove live-source or effect readiness."],
    }
