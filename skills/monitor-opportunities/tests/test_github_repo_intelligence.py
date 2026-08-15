"""GitHub repository intelligence becomes governed contact source-intel."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from monitor_opportunities import contact_changes as cc
from monitor_opportunities.contracts import validate_manifest
from monitor_opportunities.discovery import _github_evidence_candidates
from monitor_opportunities.pipeline import _source_intel
from monitor_opportunities.verification import built_in_fixture

RELATIONSHIP_CANDIDATE_SCHEMA = Path(
    "skills/monitor-opportunities/schemas/relationship-candidate.schema.json"
)


def _report_source_receipt(receipt: dict) -> dict:
    keys = {
        "receipt_id",
        "lane",
        "provider",
        "target",
        "source_class",
        "result_status",
        "observed_at",
        "request_summary",
        "response_status",
        "content_type",
        "response_bytes",
        "content_sha256",
        "evidence_refs",
        "limitations",
        "automation_policy",
        "required_source_id",
        "channel",
        "fallback_for_receipt_id",
    }
    projected = {key: value for key, value in receipt.items() if key in keys}
    projected.setdefault("response_status", None)
    projected.setdefault("content_type", None)
    projected.setdefault("content_sha256", None)
    return projected


def _github_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "monitor_opportunities.github_repo_intelligence.v1",
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "description": "ARCOS formal-methods support tools.",
                        "topics": ["darpa", "arcos", "formal-methods"],
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "role": "repository_owner",
                                "profile_url": "https://github.com/rtinney1",
                                "evidence_url": "https://github.com/rtinney1/arcos-tools",
                                "corroboration": [
                                    {
                                        "type": "profile_name_match",
                                        "evidence_refs": ["https://github.com/rtinney1"],
                                        "note": "Profile evidence supports the handle-to-person mapping.",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_github_evidence_candidates_preserve_repo_contact_receipts(tmp_path: Path) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))

    assert receipt["result_status"] == "MATCHES"
    assert receipt["provider"] == "github"
    assert "https://github.com/rtinney1/arcos-tools" in receipt["evidence_refs"]
    assert "https://github.com/rtinney1" in receipt["evidence_refs"]
    assert candidates[0]["source_provider"] == "github_repo_intelligence"
    assert candidates[0]["source_receipt_id"] == receipt["receipt_id"]
    assert candidates[0]["adjacent_contacts"] == ["Randi Tinney (@rtinney1)"]
    assert candidates[0]["github_contact_hypotheses"][0]["mapping_status"] == "corroborated"
    assert candidates[0]["github_contact_hypotheses"][0]["corroboration"][0]["resolved"] is True
    assert candidates[0]["external_effects"] is False
    assert "No GitHub, LinkedIn, email, or application action" in candidates[0]["unresolved_assumptions"][2]


def test_github_repo_contacts_emit_relationship_candidate_with_edge_receipts(tmp_path: Path) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))

    signals = cc.relationship_signals_from_candidates(candidates)

    assert len(signals) == 1
    signal = signals[0]
    assert signal["schema"] == "monitor_opportunities.relationship_candidate.v1"
    assert signal["signal_type"] == "adjacent_contact"
    assert signal["subject"] == "Randi Tinney (@rtinney1)"
    assert signal["source_receipt_ids"] == [receipt["receipt_id"]]
    assert signal["relationship_path"] == [
        "Graham Anderson",
        "GitHub repo rtinney1/arcos-tools",
        "Randi Tinney (@rtinney1)",
    ]
    assert signal["relationship_degree"] == 2
    assert all(edge["source_receipt_ids"] == [receipt["receipt_id"]] for edge in signal["contact_path"])
    assert all("https://github.com/rtinney1" in edge["evidence_refs"] for edge in signal["contact_path"])
    assert "handle mapping status: corroborated" in signal["provenance"]
    assert signal["external_effects"] is False
    assert "LINKEDIN_HUMAN_HANDOFF" in signal["preferred_human_channels"]

    Draft202012Validator(json.loads(RELATIONSHIP_CANDIDATE_SCHEMA.read_text())).validate(signal)


def test_github_source_intel_and_relationship_signal_validate_in_report(tmp_path: Path) -> None:
    receipt, candidates = _github_evidence_candidates(_github_fixture(tmp_path / "github.json"))
    signal = cc.relationship_signals_from_candidates(candidates)[0]
    source_intel = _source_intel(candidates[0])
    assert source_intel is not None
    assert source_intel["signal_type"] == "GITHUB_REPO_INTELLIGENCE"
    assert source_intel["decision"] == "CONTACT_INTELLIGENCE_ONLY"

    manifest = copy.deepcopy(built_in_fixture())
    manifest["source_receipts"].append(_report_source_receipt(receipt))
    manifest.setdefault("source_intel", []).append(source_intel)
    manifest.setdefault("relationship_signals", []).append(signal)
    manifest["artifact_accounting"]["action_worthy_total"] += 2
    manifest["artifact_accounting"]["visible_total"] += 2

    loaded = validate_manifest(manifest)

    assert loaded.source_intel[-1].signal_type == "GITHUB_REPO_INTELLIGENCE"
    assert loaded.relationship_signals[-1].subject == "Randi Tinney (@rtinney1)"


def test_github_untyped_corroboration_stays_handle_only_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                                "corroboration": "confirmed",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert hypothesis["corroboration"][0]["type"] == "untyped"
    assert hypothesis["corroboration"][0]["resolved"] is False
    assert candidates[0]["adjacent_contacts"] == ["GitHub @rtinney1"]
    assert signal["subject"] == "GitHub @rtinney1"
    assert "Randi Tinney (@" not in signal["subject"]


def test_github_corroboration_refs_must_resolve_to_contact_evidence(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                                "corroboration": [
                                    {
                                        "type": "profile_name_match",
                                        "evidence_refs": ["https://example.invalid/not-in-receipt"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert hypothesis["corroboration"][0]["resolved"] is False
    assert signal["subject"] == "GitHub @rtinney1"


def test_github_name_and_handle_without_corroboration_stays_hypothesis(tmp_path: Path) -> None:
    path = tmp_path / "github.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "repo": "rtinney1/arcos-tools",
                        "repo_url": "https://github.com/rtinney1/arcos-tools",
                        "organization": "DARPA ARCOS network",
                        "contacts": [
                            {
                                "name": "Randi Tinney",
                                "handle": "rtinney1",
                                "profile_url": "https://github.com/rtinney1",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    _receipt, candidates = _github_evidence_candidates(path)
    hypothesis = candidates[0]["github_contact_hypotheses"][0]
    signal = cc.relationship_signals_from_candidates(candidates)[0]

    assert hypothesis["mapping_status"] == "hypothesis"
    assert signal["subject"] == "GitHub @rtinney1"
