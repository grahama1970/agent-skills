from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_skill.relayforge_v16_live_topology import (
    CampaignJournal,
    LiveTopologyContractError,
    build_memory_judge_delta,
    classify_judge_verdict,
    execute_blue_action,
    memory_strategy_blue_proposal,
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
        },
        "sink_hashes": {},
    }


def _write_receipt(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"name": name}, sort_keys=True), encoding="utf-8")
    return path


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


def test_memory_strategy_derives_extractor_identity_control() -> None:
    proposal = memory_strategy_blue_proposal(
        {
            "context": {
                "team_contexts": {
                    "blue": {
                        "memory_design_input": {
                            "strategy": {
                                "selected_methods": [
                                    "evidence-targeted-boundary-control"
                                ],
                                "parameters": {
                                    "boundary_checks": [
                                        "reject_parent_traversal",
                                        "resolve_and_verify_destination_containment",
                                    ]
                                },
                            }
                        }
                    }
                }
            }
        }
    )

    assert proposal is not None
    assert proposal["operation"] == "extractor-object-identity"
    assert proposal["evidence_refs"] == [
        "setup-import",
        "public-action-catalog",
        "memory-chain",
        "post-memory-strategy",
    ]


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


def test_red_legacy_strategy_genome_can_derive_one_public_action() -> None:
    valid, rejected = validate_action_proposals(
        team="red",
        parsed={
            "strategy_genome": {
                "selected_methods": [
                    "regular-package-import",
                    "bounded traversal-like ZIP member",
                ],
                "parameters": {"zip_entry": "../arena_escape.txt"},
                "expected_observation": "regular import returns one bounded response",
            }
        },
        known_evidence_refs={"setup-import", "public-action-catalog"},
        private_identifiers=["judge-probe"],
    )

    assert rejected == []
    assert valid == [
        {
            "action_id": "red-derived-regular-package-import",
            "rank": 1,
            "operation": "regular-package-import",
            "evidence_refs": ["setup-import", "public-action-catalog"],
            "expected_observation": "regular import returns one bounded response",
            "parameters": {},
        }
    ]


def test_red_zip_exploit_artifact_derives_regular_import_action() -> None:
    valid, rejected = validate_action_proposals(
        team="red",
        parsed={
            "artifact_type": "red_exploit",
            "exploit_py": "make a zip with ../arena_escape.txt and call import_zip",
            "strategy_genome": {
                "selected_methods": ["direct local app.py import"],
                "parameters": {"zip_entry": "../arena_escape.txt"},
                "expected_observation": "RED_EXPLOIT_CONFIRMED on traversal",
            },
        },
        known_evidence_refs={"setup-import", "public-action-catalog"},
        private_identifiers=["judge-probe"],
    )

    assert rejected == []
    assert valid[0]["operation"] == "regular-package-import"
    assert valid[0]["evidence_refs"] == ["setup-import", "public-action-catalog"]


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


def test_memory_judge_delta_passes_for_fresh_state_reduction(tmp_path: Path) -> None:
    receipt, path = build_memory_judge_delta(
        control=_measurement("PROTECTED_OBJECTIVE"),
        memory=_measurement("REPRODUCIBLE_PROBE"),
        regressions={"failure_count": 0},
        red_operation="regular-package-import",
        blue_operation="extractor-object-identity",
        control_measurement_path=_write_receipt(tmp_path, "control.json"),
        memory_measurement_path=_write_receipt(tmp_path, "memory.json"),
        control_red_execution_path=_write_receipt(tmp_path, "control-red.json"),
        memory_blue_execution_path=_write_receipt(tmp_path, "memory-blue.json"),
        memory_red_execution_path=_write_receipt(tmp_path, "memory-red.json"),
        regression_path=_write_receipt(tmp_path, "regressions.json"),
        out=tmp_path,
    )

    assert receipt["status"] == "PASS"
    assert receipt["memory_improvement_proven"] is True
    assert receipt["delta"]["control_minus_memory_stage_score"] == 2
    assert path.is_file()


def test_memory_judge_delta_fails_closed_without_reduction(tmp_path: Path) -> None:
    receipt, _path = build_memory_judge_delta(
        control=_measurement("REPRODUCIBLE_PROBE"),
        memory=_measurement("REPRODUCIBLE_PROBE"),
        regressions={"failure_count": 0},
        red_operation="regular-package-import",
        blue_operation="extractor-object-identity",
        control_measurement_path=_write_receipt(tmp_path, "control.json"),
        memory_measurement_path=_write_receipt(tmp_path, "memory.json"),
        control_red_execution_path=_write_receipt(tmp_path, "control-red.json"),
        memory_blue_execution_path=_write_receipt(tmp_path, "memory-blue.json"),
        memory_red_execution_path=_write_receipt(tmp_path, "memory-red.json"),
        regression_path=_write_receipt(tmp_path, "regressions.json"),
        out=tmp_path,
    )

    assert receipt["status"] == "FAIL"
    assert receipt["memory_improvement_proven"] is False


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


def test_blue_action_execution_records_required_schema_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Response:
        status_code = 200

        def json(self) -> dict:
            return {"status": "DEPLOYED"}

    class _Client:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "_Client":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def request(
            self,
            method: str,
            route: str,
            json: dict | None = None,
            headers: dict | None = None,
        ) -> _Response:
            assert method == "POST"
            assert route == "/api/v1/defenses/cache-principal-partition"
            assert json == {"enabled": True}
            assert headers == {"x-relayforge-team": "blue"}
            return _Response()

    monkeypatch.setattr(
        "battle_skill.relayforge_v16_live_topology.httpx.Client", _Client
    )
    selection_path = tmp_path / "selection.json"
    selection_path.write_text("{}", encoding="utf-8")
    selection = {
        "selected_proposal": {
            "operation": "cache-principal-partition",
            "parameters": {"enabled": True},
        },
        "provider_call_sha256": "a" * 64,
        "provider_artifact_sha256": "b" * 64,
    }

    receipt, path = execute_blue_action(
        selection=selection,
        selection_path=selection_path,
        base_url="http://relayforge",
        out=tmp_path,
    )

    assert receipt["response_contains_protected_value"] is False
    assert receipt["replay"] is False
    assert receipt["equivalence_basis"] is None
    assert path.is_file()
