"""Tests for the role-based team-plan CLI (agent-skills#1220)."""

from __future__ import annotations

from ask.project_plan import validate_project_plan
from ask.team_plan_cli import render_team_plan


def test_fullstack_request_infers_all_roles() -> None:
    plan = render_team_plan(
        "build a settings dashboard with a Python API, React UI, docs, and tests",
        repo="grahama1970/agent-skills",
        team="fullstack-premium",
    )
    ids = [ws["id"] for ws in plan["workstreams"]]
    assert ids == ["coordinator", "api", "ui", "docs", "tests", "review"]
    ok, errors = validate_project_plan(plan)
    assert ok, errors
    review = plan["workstreams"][-1]
    assert set(review["depends_on"]) == {"api", "ui", "docs", "tests"}
    assert plan["unresolved"] == []


def test_partial_request_infers_subset() -> None:
    plan = render_team_plan("fix the API and add tests", repo="r", team="economical")
    ids = [ws["id"] for ws in plan["workstreams"]]
    assert ids == ["coordinator", "api", "tests", "review"]


def test_vague_request_fails_closed_to_interview() -> None:
    plan = render_team_plan("do something vague", repo="r", team="fullstack-premium")
    assert plan["unresolved"] == ["workstreams"]


def test_workers_delegated_under_coordinator() -> None:
    plan = render_team_plan("python api with tests", repo="r", team="fullstack-premium")
    for ws in plan["workstreams"]:
        if ws["role"] not in ("coordinator", "independent_reviewer"):
            assert ws["depends_on"] == ["coordinator"]
