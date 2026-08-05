"""Schema tests for ask.project_plan.v1 (agent-skills#1220)."""

from __future__ import annotations

import copy

from ask.project_plan import DEFAULT_HARNESS_MODE, SCHEMA_ID, validate_project_plan

VALID_PLAN = {
    "schema": SCHEMA_ID,
    "goal": "Add evidence-case collaboration with API, UI, docs, and tests",
    "target": {"repo": "grahama1970/agent-skills"},
    "deliverables": [
        {"name": "Python API", "acceptance_criteria": ["endpoints pass focused tests"]},
        {"name": "React UI", "acceptance_criteria": ["screens render against fixture data"]},
    ],
    "workstreams": [
        {"id": "api", "role": "backend"},
        {"id": "ui", "role": "frontend", "depends_on": ["api"]},
        {"id": "docs", "role": "documentation", "depends_on": ["api", "ui"]},
        {"id": "review", "role": "independent_reviewer", "depends_on": ["api", "ui"]},
    ],
    "team": {"preset": "fullstack-premium"},
    "execution": {"topology": "concurrent", "max_concurrency": 3, "max_retries": 2},
    "unresolved": [],
}


def _invalid(mutate) -> list[str]:
    plan = copy.deepcopy(VALID_PLAN)
    mutate(plan)
    ok, errors = validate_project_plan(plan)
    assert not ok
    return errors


def test_valid_plan_passes() -> None:
    ok, errors = validate_project_plan(VALID_PLAN)
    assert ok, errors


def test_default_harness_mode_is_tau_native() -> None:
    assert DEFAULT_HARNESS_MODE == "tau_native_agent_loop"


def test_non_mapping_rejected() -> None:
    ok, errors = validate_project_plan("not a plan")
    assert not ok and errors == ["plan must be a mapping"]


def test_missing_goal_rejected() -> None:
    errors = _invalid(lambda p: p.update(goal="  "))
    assert any("goal" in e for e in errors)


def test_wrong_schema_rejected() -> None:
    errors = _invalid(lambda p: p.update(schema="ask.project_plan.v0"))
    assert any("schema" in e for e in errors)


def test_missing_target_repo_rejected() -> None:
    errors = _invalid(lambda p: p.update(target={}))
    assert any("target.repo" in e for e in errors)


def test_empty_deliverables_rejected() -> None:
    errors = _invalid(lambda p: p.update(deliverables=[]))
    assert any("deliverables" in e for e in errors)


def test_deliverable_without_acceptance_rejected() -> None:
    errors = _invalid(lambda p: p["deliverables"][0].update(acceptance_criteria=[]))
    assert any("acceptance_criteria" in e for e in errors)


def test_unknown_role_rejected() -> None:
    errors = _invalid(lambda p: p["workstreams"][0].update(role="wizard"))
    assert any("role" in e for e in errors)


def test_duplicate_workstream_id_rejected() -> None:
    errors = _invalid(lambda p: p["workstreams"][1].update(id="api"))
    assert any("duplicated" in e for e in errors)


def test_dangling_dependency_rejected() -> None:
    errors = _invalid(lambda p: p["workstreams"][1].update(depends_on=["ghost"]))
    assert any("unknown workstream" in e for e in errors)


def test_self_dependency_rejected() -> None:
    errors = _invalid(lambda p: p["workstreams"][0].update(depends_on=["api"]))
    assert any("depends on itself" in e for e in errors)


def test_bad_harness_mode_rejected() -> None:
    errors = _invalid(lambda p: p["workstreams"][0].update(harness_mode="freestyle"))
    assert any("harness_mode" in e for e in errors)


def test_compat_mode_requires_justification() -> None:
    errors = _invalid(lambda p: p["workstreams"][0].update(harness_mode="opaque_agent_compat"))
    assert any("compat_justification" in e for e in errors)


def test_compat_mode_with_justification_ok() -> None:
    plan = copy.deepcopy(VALID_PLAN)
    plan["workstreams"][0].update(
        harness_mode="opaque_agent_compat", compat_justification="WebGPT browser handler until tau#310 ships"
    )
    ok, errors = validate_project_plan(plan)
    assert ok, errors


def test_team_without_preset_or_profiles_rejected() -> None:
    errors = _invalid(lambda p: p.update(team={}))
    assert any("preset or profile_ids" in e for e in errors)


def test_bad_topology_rejected() -> None:
    errors = _invalid(lambda p: p["execution"].update(topology="ring"))
    assert any("topology" in e for e in errors)


def test_bad_concurrency_rejected() -> None:
    errors = _invalid(lambda p: p["execution"].update(max_concurrency=0))
    assert any("max_concurrency" in e for e in errors)


def test_unresolved_must_be_strings() -> None:
    errors = _invalid(lambda p: p.update(unresolved=[42]))
    assert any("unresolved" in e for e in errors)
