# Prefill executor gate tests (no browser, no network).
"""Behavioral gates for the ATS prefill executor's pure parts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor_opportunities.ats.prefill_executor import (
    PrefillError,
    build_fill_script,
    fillable_fields,
    require_prefill_policy,
)


def _plan() -> dict:
    return {
        "provider": "greenhouse",
        "site": "discord",
        "posting_id": "1",
        "url": "https://example.invalid/jobs/1",
        "plan_digest": "d" * 64,
        "form_schema_digest": "f" * 64,
        "unresolved_required_fields": ["Why?"],
        "fields": [
            {"name": "First Name", "disposition": "exact_approved_answer", "automated_answer": "Graham", "selector": "#first_name"},
            {"name": "Why?", "disposition": "human_required", "automated_answer": None, "selector": "#why"},
            {"name": "Email", "disposition": "exact_approved_answer", "automated_answer": "graham@grahama.co", "selector": "#email"},
        ],
    }


def _policy() -> dict:
    return {
        "capability": "ats_form_prefill:greenhouse:discord",
        "actor": "human",
        "decision": "PROMOTE",
        "does_not_authorize": ["ats_form_submit"],
    }


def test_fillable_fields_exclude_human_required() -> None:
    rows = fillable_fields(_plan(), {})
    assert [row["name"] for row in rows] == ["First Name", "Email"]


def test_missing_selector_fails_closed() -> None:
    plan = _plan()
    plan["fields"][0].pop("selector")
    with pytest.raises(PrefillError, match="SELECTOR_MISSING"):
        fillable_fields(plan, {})


def test_binding_map_fallback_supplies_selector() -> None:
    plan = _plan()
    plan["fields"][0].pop("selector")
    rows = fillable_fields(plan, {"First Name": "#first_name"})
    assert rows[0]["selector"] == "#first_name"


def test_policy_must_be_site_scoped_human_promote_excluding_submit() -> None:
    require_prefill_policy(_policy(), "greenhouse", "discord")
    with pytest.raises(PrefillError):
        require_prefill_policy(None, "greenhouse", "discord")
    with pytest.raises(PrefillError, match="SCOPE"):
        require_prefill_policy(_policy(), "greenhouse", "other")
    bad = {**_policy(), "does_not_authorize": []}
    with pytest.raises(PrefillError, match="EXCLUDE_SUBMIT"):
        require_prefill_policy(bad, "greenhouse", "discord")


def test_fill_script_targets_only_fillable_fields_and_never_submit() -> None:
    rows = fillable_fields(_plan(), {})
    script = build_fill_script(rows)
    assert "#first_name" in script and "#email" in script
    assert "#why" not in script
    assert "submit" not in script.lower()
    assert "click" not in script.lower()


def test_choice_field_resolves_from_standing_answer_on_exact_option_match() -> None:
    from monitor_opportunities.application_plan import _planned_field

    field = {"name": "Are you currently located in the US?", "field_type": "choice",
             "required": True, "options": ["Yes", "No"], "classification": "human_required"}
    planned = _planned_field(field, {"Are you currently located in the US?": "Yes"})
    assert planned["disposition"] == "exact_approved_answer"
    assert planned["automated_answer"] == "Yes"


def test_choice_field_without_matching_option_stays_human_required() -> None:
    from monitor_opportunities.application_plan import _planned_field

    field = {"name": "Office preference", "field_type": "choice",
             "required": True, "options": ["SF", "NY"], "classification": "human_required"}
    planned = _planned_field(field, {"Office preference": "Buffalo"})
    assert planned["disposition"] == "human_required"


def test_sensitive_field_never_resolves_from_answers() -> None:
    from monitor_opportunities.application_plan import _planned_field

    field = {"name": "Gender", "field_type": "self_identification",
             "required": True, "options": ["Male", "Female"], "classification": "human_required"}
    planned = _planned_field(field, {"Gender": "Male"})
    assert planned["disposition"] == "human_required"
    assert planned["automated_answer"] is None
