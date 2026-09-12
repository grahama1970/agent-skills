from __future__ import annotations

import json
from pathlib import Path

from battle_skill.contract_variation_plan import PLAN_SCHEMA, build_plan, write_plan


def _bundle(path: Path, *, open_questions: bool = False) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "acceptance_contract.bundle.v1",
                "project_name": "generic-ledger-service",
                "source": {"kind": "file", "path": "brief.md", "sha256": "abc"},
                "requirements": [
                    {
                        "id": "REQ-001",
                        "kind": "must",
                        "statement": "The service must reject unauthorized ledger transfers before any balance changes.",
                        "source_path": "brief.md",
                        "source_line": 1,
                        "evidence_text": "reject unauthorized ledger transfers before any balance changes",
                    },
                    {
                        "id": "REQ-002",
                        "kind": "must",
                        "statement": "The service must preserve cents exactly across API, CSV import, and database storage.",
                        "source_path": "brief.md",
                        "source_line": 2,
                        "evidence_text": "preserve cents exactly across API, CSV import, and database storage",
                    },
                ],
                "acceptance_cases": [
                    {
                        "id": "AC-001",
                        "requirement_id": "REQ-001",
                        "kind": "MUST_VERIFY",
                        "predicate": "Unauthorized ledger transfers are rejected before mutation.",
                        "deterministic_check": "Run Battle auth-boundary cases.",
                    },
                    {
                        "id": "AC-002",
                        "requirement_id": "REQ-002",
                        "kind": "MUST_VERIFY",
                        "predicate": "Cent values remain exact through API, CSV, and database paths.",
                        "deterministic_check": "Run Battle parser/representation cases.",
                    },
                ],
                "open_questions": ["who approves overdrafts?"] if open_questions else [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_contract_variation_plan_is_generic_dogpile_to_battle_bridge(tmp_path: Path) -> None:
    plan = build_plan(_bundle(tmp_path / "acceptance_bundle.json"))

    assert plan["schema"] == PLAN_SCHEMA
    assert plan["status"] == "READY"
    assert plan["acceptance_bundle"]["project_name"] == "generic-ledger-service"
    assert plan["dogpile_role"] == "phase_2_research_input_only"
    assert plan["battle_role"] == "phase_3_freeze_selected_families_into_deterministic_generators_and_prove_with_Docker_Judge_receipts"
    assert plan["phase_order"] == ["acceptance-floor", "research-expansion", "adaptive-lineage"]
    assert [phase["phase"] for phase in plan["phases"]] == [1, 2, 3]
    assert plan["phases"][1]["id"] == "research-expansion"
    assert {step["tool"] for step in plan["phases"][1]["steps"]} == {"project-state", "dogpile", "ask"}
    assert plan["phases"][2]["id"] == "adaptive-lineage"
    assert len(plan["contract_items"]) == 2
    assert len(plan["dogpile_lanes"]) == 6
    assert plan["deterministic_case_floor"] >= 60
    assert 20 <= len(plan["agentic_eval_plan"]) <= 30
    assert plan["release_gate"]["must_pass_phase_1_acceptance_floor_before_phase_2"] is True
    assert plan["release_gate"]["must_run_dogpile_or_attach_source_bearing_research"] is True
    assert plan["release_gate"]["must_run_ask_one_shot_or_attach_reviewer_receipts"] is True
    assert plan["release_gate"]["must_promote_adaptive_lineage_in_phase_3"] is True
    assert plan["release_gate"]["red_win_blocks_release"] is True

    families = {family["id"] for family in plan["contract_items"][0]["variation_families"]}
    assert {
        "representation-equivalence",
        "parser-differentials",
        "surface-boundaries",
        "failure-leak-boundary",
    } <= families
    assert all("oai" not in json.dumps(item).lower() for item in plan["contract_items"])


def test_contract_variation_plan_filters_dogpile_sources_without_bespoke_targets(tmp_path: Path) -> None:
    receipt = tmp_path / "battle-receipt.json"
    receipt.write_text('{"schema":"battle.campaign_contract_receipt.v1"}\n', encoding="utf-8")
    plan = build_plan(
        _bundle(tmp_path / "acceptance_bundle.json"),
        dogpile_sources=["brave-search", "arxiv"],
        project_root=tmp_path,
        battle_receipts=[receipt],
        ask_handlers=["webgpt", "webgemini"],
    )

    assert plan["dogpile_source_filter"] == ["brave-search", "arxiv"]
    assert len(plan["dogpile_lanes"]) == 6
    assert plan["ask_handlers"] == ["webgpt", "webgemini"]
    assert plan["phases"][1]["battle_receipts"] == [str(receipt.resolve())]
    assert plan["phases"][1]["steps"][0]["cwd"] == str(tmp_path.resolve())
    assert "webgpt" in plan["phases"][1]["steps"][2]["command"]
    for lane in plan["dogpile_lanes"]:
        assert lane["dogpile_sources"] == ["brave-search", "arxiv"]
        assert lane["command"].count("--source") == 2
        assert "brave-search" in lane["command"]
        assert "arxiv" in lane["command"]
        assert "oai" not in json.dumps(lane).lower()


def test_contract_variation_plan_blocks_unknown_dogpile_source(tmp_path: Path) -> None:
    try:
        build_plan(_bundle(tmp_path / "acceptance_bundle.json"), dogpile_sources=["made-up"])
    except ValueError as exc:
        assert "unknown Dogpile source filter: made-up" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unknown source filter should fail closed")


def test_contract_variation_plan_blocks_open_questions_without_losing_plan(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    plan = write_plan(_bundle(tmp_path / "acceptance_bundle.json", open_questions=True), out)

    assert out.is_file()
    assert plan["status"] == "BLOCKED"
    assert plan["acceptance_bundle"]["open_questions"] == 1
    assert plan["dogpile_lanes"]
