"""Deterministic-core tests for the remediation loop (REMEDIATION_LOOP.md).

These cover pure logic (map validation, categorization, fingerprints) plus a
live composition check against the real phart-dag-chart skill.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import remediation as rem  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CMAP = json.loads((FIXTURES / "category_map.example.json").read_text())


def _report(*failing_seams: str) -> dict:
    return {
        "readiness": "NOT_READY",
        "cases": [
            {
                "name": f"case-{i}",
                "case_id": f"case-{i}",
                "required": True,
                "outcome": "FAIL",
                "seams": [seam],
                "supports_claims": [],
            }
            for i, seam in enumerate(failing_seams)
        ],
    }


# --- map validation (amendment 4) ---


def test_valid_map_induces_active_graph():
    active = {
        "agentic-evals:graph-memory-operator:entity-resolution",
        "agentic-evals:graph-memory-operator:answer-contract",
    }
    induced = rem.validate_category_map(CMAP, active_category_ids=active)
    assert set(induced) == active
    # answer-contract keeps its edge to the active entity-resolution
    assert induced["agentic-evals:graph-memory-operator:answer-contract"] == [
        "agentic-evals:graph-memory-operator:entity-resolution"
    ]


def test_edge_to_inactive_category_is_dropped_not_starved():
    # answer-contract active but entity-resolution NOT active -> edge dropped.
    active = {"agentic-evals:graph-memory-operator:answer-contract"}
    induced = rem.validate_category_map(CMAP, active_category_ids=active)
    assert induced == {"agentic-evals:graph-memory-operator:answer-contract": []}


def test_cycle_is_rejected():
    bad = json.loads(json.dumps(CMAP))
    # make entity-resolution depend on answer-contract -> A<->B cycle
    bad["categories"]["entity-resolution"]["depends_on"] = [
        {
            "category_id": "agentic-evals:graph-memory-operator:answer-contract",
            "rationale": "injected cycle",
        }
    ]
    with pytest.raises(rem.CategoryMapError, match="cycle"):
        rem.validate_category_map(bad)


def test_edge_without_rationale_rejected():
    bad = json.loads(json.dumps(CMAP))
    bad["categories"]["answer-contract"]["depends_on"] = [
        {"category_id": "agentic-evals:graph-memory-operator:entity-resolution"}
    ]
    with pytest.raises(rem.CategoryMapError, match="rationale"):
        rem.validate_category_map(bad)


def test_cross_repo_namespace_rejected():
    bad = json.loads(json.dumps(CMAP))
    bad["categories"]["entity-resolution"]["category_id"] = "agentic-evals:other-repo:x"
    with pytest.raises(rem.CategoryMapError, match="same-repo-only"):
        rem.validate_category_map(bad)


# --- categorization (amendment 3) ---


def test_categorize_assigns_by_seam():
    report = _report("intent.entity_extraction", "intent.skill_registry")
    out = rem.categorize(report, CMAP)
    assert set(out["active_category_ids"]) == {
        "agentic-evals:graph-memory-operator:entity-resolution",
        "agentic-evals:graph-memory-operator:skill-routing",
    }


def test_unclassified_failure_is_hard_error():
    report = _report("intent.unknown_seam")
    with pytest.raises(rem.CategorizationError, match="no category"):
        rem.categorize(report, CMAP)


def test_blocked_and_passing_cases_are_not_failures():
    report = {
        "readiness": "USABLE_WITH_GAPS",
        "cases": [
            {"name": "p", "case_id": "p", "required": True, "outcome": "PASS", "seams": ["intent.entity_extraction"]},
            {"name": "b", "case_id": "b", "required": True, "outcome": "BLOCKED", "seams": ["intent.entity_extraction"]},
        ],
    }
    out = rem.categorize(report, CMAP)
    assert out["active_category_ids"] == []


# --- fingerprints (amendment 5) ---


def test_semantic_fingerprint_is_sha_free():
    report = _report("intent.entity_extraction")
    cat = rem.categorize(report, CMAP)
    fp = rem.semantic_fingerprint(cat, map_version="1")
    p1 = rem.provenance_fingerprint(fp, evaluated_sha="SHA1", frozen_inputs={"fixture": "h"})
    p2 = rem.provenance_fingerprint(fp, evaluated_sha="SHA2", frozen_inputs={"fixture": "h"})
    # same failure state across two commits -> identical SEMANTIC fp (oscillation
    # detectable) but distinct provenance fps (audit traceable).
    assert p1 != p2
    fp_again = rem.semantic_fingerprint(rem.categorize(report, CMAP), map_version="1")
    assert fp == fp_again


# --- live composition: phart-dag-chart (real skill) ---


def test_category_dag_renders_through_phart():
    active = {
        "agentic-evals:graph-memory-operator:entity-resolution",
        "agentic-evals:graph-memory-operator:answer-contract",
    }
    induced = rem.validate_category_map(CMAP, active_category_ids=active)
    dag = rem.active_category_dag(induced, CMAP)
    out = rem.render_and_validate_dag(dag)
    if not out["ok"] and "not found" in out.get("error", ""):
        pytest.skip("phart-dag-chart skill not present")
    assert out["ok"], out
    assert out["chart"].strip(), "phart returned an empty chart"


# --- plan builder (amendment 4) ---


def test_plan_topo_orders_upstreams_first_and_is_idempotent():
    report = _report("intent.entity_extraction", "answer.claim_requirements")
    cat = rem.categorize(report, CMAP)
    induced = rem.validate_category_map(CMAP, active_category_ids=set(cat["active_category_ids"]))
    plan = rem.plan_remediation(cat, induced, CMAP, open_labels=set())
    # entity-resolution (upstream) must come before answer-contract (downstream)
    er = "agentic-evals:graph-memory-operator:entity-resolution"
    ac = "agentic-evals:graph-memory-operator:answer-contract"
    assert plan["topo_order"].index(er) < plan["topo_order"].index(ac)
    assert {s["category_id"] for s in plan["to_file"]} == {er, ac}
    # idempotent: entity-resolution's label already open -> skipped
    plan2 = rem.plan_remediation(cat, induced, CMAP, open_labels={"eval-cat-entity-resolution"})
    assert {s["category_id"] for s in plan2["to_file"]} == {ac}
    assert {s["category_id"] for s in plan2["skipped_open"]} == {er}


def test_apply_dry_run_builds_depends_on_argv_without_mutating():
    report = _report("intent.entity_extraction", "answer.claim_requirements")
    cat = rem.categorize(report, CMAP)
    induced = rem.validate_category_map(CMAP, active_category_ids=set(cat["active_category_ids"]))
    plan = rem.plan_remediation(cat, induced, CMAP, open_labels=set())
    applied = rem.apply_plan(plan, fixture="fixtures/agentic_eval.json", route="backend_python_or_skill_runtime", execute=False)
    assert applied["executed"] is False
    assert len(applied["previewed"]) == 2
    # every step is a ticket bug argv with its label
    for step in applied["steps"]:
        assert step["argv"][1] == "bug"
        assert "--label" in step["argv"]
    ac = [s for s in applied["steps"] if s["category_id"].endswith("answer-contract")][0]
    assert "--depends-on" in ac["argv"]
    assert any("entity-resolution" in a for a in ac["argv"])


# --- outer loop control (amendment 5): pure, injected effects ---


def _cat(active_and_counts: dict[str, list[str]]) -> dict:
    return {"active_category_ids": sorted(active_and_counts), "cases_by_category": active_and_counts}


def test_loop_stops_green_when_no_active_categories():
    reports = iter([{"cases": []}])
    calls = {"iterate": 0, "wait": 0}
    out = rem.remediate_loop(
        run_fn=lambda: next(reports),
        categorize_fn=lambda r: _cat({}),
        iterate_fn=lambda r, c: calls.__setitem__("iterate", calls["iterate"] + 1),
        wait_fn=lambda a: calls.__setitem__("wait", calls["wait"] + 1),
        map_version="1", max_iterations=5,
    )
    assert out["status"] == "GREEN"
    assert calls == {"iterate": 0, "wait": 0}  # nothing to fix, no side effects


def test_loop_converges_then_green():
    # iter1: two cats fail; iter2: one; iter3: none -> GREEN
    seq = [_cat({"A": ["c1"], "B": ["c2"]}), _cat({"A": ["c1"]}), _cat({})]
    it = iter(seq)
    out = rem.remediate_loop(
        run_fn=lambda: {"cases": []},
        categorize_fn=lambda r: next(it),
        iterate_fn=lambda r, c: None,
        wait_fn=lambda a: None,
        map_version="1", max_iterations=10, no_progress_k=3,
    )
    assert out["status"] == "GREEN"
    assert out["iterations"] == 2  # two remediating iterations, third run was green


def test_loop_detects_oscillation_on_semantic_repeat():
    # A,B -> A,B (identical failure state) => oscillation, regardless of SHA
    seq = [_cat({"A": ["c1"], "B": ["c2"]}), _cat({"A": ["c1"], "B": ["c2"]})]
    it = iter(seq)
    out = rem.remediate_loop(
        run_fn=lambda: {"cases": []},
        categorize_fn=lambda r: next(it),
        iterate_fn=lambda r, c: None,
        wait_fn=lambda a: None,
        map_version="1", max_iterations=10, no_progress_k=5,
    )
    assert out["status"] == "OSCILLATION_SEMANTIC_REPEAT"


def test_loop_detects_no_progress():
    # failure count never drops (different case ids so semantic fp differs, but
    # count stays flat) over K iterations -> NO_PROGRESS
    seq = [_cat({"A": ["c1", "c2"]}), _cat({"A": ["c3", "c4"]}), _cat({"A": ["c5", "c6"]})]
    it = iter(seq)
    out = rem.remediate_loop(
        run_fn=lambda: {"cases": []},
        categorize_fn=lambda r: next(it),
        iterate_fn=lambda r, c: None,
        wait_fn=lambda a: None,
        map_version="1", max_iterations=10, no_progress_k=2,
    )
    assert out["status"] == "NO_PROGRESS"
