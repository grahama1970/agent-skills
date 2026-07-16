from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_skill.relayforge_v16_live_topology import (
    CampaignJournal,
    LiveTopologyContractError,
    classify_judge_verdict,
    validate_action_proposals,
)


def _proposal(operation: str, *, rank: int = 1, parameters: dict | None = None) -> dict:
    return {
        "action_id": f"action-{rank}",
        "rank": rank,
        "operation": operation,
        "evidence_refs": ["OBS-21"],
        "expected_observation": "one bounded public response",
        "parameters": parameters or {},
    }


def _parsed(*proposals: dict) -> dict:
    return {
        "strategy_genome": {
            "selected_methods": ["bounded-public-action"],
            "rejected_methods": [],
            "parameters": {"action_proposals": list(proposals)},
            "mutation_origin": "public observations",
            "expected_observation": "bounded response",
        }
    }


def _measurement(stage: str) -> dict:
    return {
        "path_outcomes": {
            "RF-A": {"highest_stage": stage},
            "RF-B": {"highest_stage": "UNSEEN"},
            "RF-C": {"highest_stage": "UNSEEN"},
        }
    }


def test_red_proposal_is_typed_and_evidence_bound() -> None:
    valid, rejected = validate_action_proposals(
        team="red",
        parsed=_parsed(_proposal("retrieve-observed-report")),
        known_evidence_refs={"OBS-21"},
        private_identifiers=["RF-A", "judge-probe"],
    )
    assert [item["operation"] for item in valid] == ["retrieve-observed-report"]
    assert rejected == []


def test_blue_broad_action_is_rejected_for_memory_strategy() -> None:
    valid, rejected = validate_action_proposals(
        team="blue",
        parsed=_parsed(
            _proposal("broad-quarantine"),
            _proposal("cache-principal-partition", rank=2, parameters={"enabled": True}),
        ),
        known_evidence_refs={"OBS-21"},
        private_identifiers=["RF-A", "judge-probe"],
    )
    assert [item["operation"] for item in valid] == ["cache-principal-partition"]
    assert rejected[0]["reasons"] == ["inconsistent_with_memory_targeted_control"]


def test_provider_controlled_transport_is_rejected() -> None:
    proposal = _proposal("retrieve-observed-report")
    proposal["parameters"] = {"url": "http://internal"}
    valid, rejected = validate_action_proposals(
        team="red",
        parsed=_parsed(proposal),
        known_evidence_refs={"OBS-21"},
        private_identifiers=["RF-A", "judge-probe"],
    )
    assert valid == []
    assert "provider_controlled_command_or_transport" in rejected[0]["reasons"]


def test_private_identifier_in_proposal_is_rejected() -> None:
    proposal = _proposal("retrieve-observed-report")
    proposal["expected_observation"] = "contact judge-probe"
    valid, rejected = validate_action_proposals(
        team="red",
        parsed=_parsed(proposal),
        known_evidence_refs={"OBS-21"},
        private_identifiers=["judge-probe"],
    )
    assert valid == []
    assert "private_identifier_leak" in rejected[0]["reasons"]


def test_unknown_evidence_reference_is_rejected() -> None:
    proposal = _proposal("retrieve-observed-report")
    proposal["evidence_refs"] = ["private-judge"]
    valid, rejected = validate_action_proposals(
        team="red",
        parsed=_parsed(proposal),
        known_evidence_refs={"OBS-21"},
        private_identifiers=[],
    )
    assert valid == []
    assert "unknown_evidence_ref" in rejected[0]["reasons"]


def test_missing_structured_proposals_fails_closed() -> None:
    with pytest.raises(LiveTopologyContractError, match="action_proposals"):
        validate_action_proposals(
            team="red",
            parsed={"strategy_genome": {"parameters": {}}},
            known_evidence_refs={"OBS-21"},
            private_identifiers=[],
        )


def test_judge_accepts_red_success() -> None:
    verdict = classify_judge_verdict(
        before_red=_measurement("UNSEEN"),
        after_red=_measurement("PROTECTED_OBJECTIVE"),
        final=_measurement("PROTECTED_OBJECTIVE"),
        regressions={"failure_count": 0},
    )
    assert verdict == "RED_SUCCESS"


def test_judge_accepts_blue_success_without_memory_claim() -> None:
    verdict = classify_judge_verdict(
        before_red=_measurement("UNSEEN"),
        after_red=_measurement("PROTECTED_OBJECTIVE"),
        final=_measurement("REPRODUCIBLE_PROBE"),
        regressions={"failure_count": 0},
    )
    assert verdict == "BLUE_SUCCESS"


def test_judge_accepts_contested_and_insufficient_evidence() -> None:
    assert (
        classify_judge_verdict(
            before_red=_measurement("UNSEEN"),
            after_red=_measurement("REPRODUCIBLE_PROBE"),
            final=_measurement("REPRODUCIBLE_PROBE"),
            regressions={"failure_count": 0},
        )
        == "CONTESTED"
    )
    assert (
        classify_judge_verdict(
            before_red=_measurement("UNSEEN"),
            after_red=_measurement("EVIDENCE_GATHERED"),
            final=_measurement("EVIDENCE_GATHERED"),
            regressions={"failure_count": 0},
        )
        == "INSUFFICIENT_EVIDENCE"
    )


def test_campaign_journal_is_monotonic_and_hash_chained(tmp_path: Path) -> None:
    journal = CampaignJournal(tmp_path / "campaign-events.jsonl")
    first = journal.append(
        event_type="first",
        phase="bind",
        actor="battle",
        source_receipt_sha256="a" * 64,
    )
    second = journal.append(
        event_type="second",
        phase="execute",
        actor="red",
        source_receipt_sha256="b" * 64,
    )
    lines = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert [item["seq"] for item in lines] == [1, 2]
    assert second["prior_event_sha256"] == first["event_sha256"]
    assert (
        second["source_time"]["elapsed_seconds"]
        > first["source_time"]["elapsed_seconds"]
    )
