# Read-only ATS inspect gate tests over a captured Greenhouse payload.
"""Behavioral gates for the Greenhouse form capture and inspect policy path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor_opportunities.application_plan import ApplicationGateError, inspect_ats_form
from monitor_opportunities.ats.greenhouse import (
    GreenhouseFormError,
    form_from_greenhouse_job,
)

FIXTURE = Path("skills/monitor-opportunities/tests/fixtures/ats/greenhouse_discord_8433948002.json")


def _job() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _policy() -> dict:
    return {
        "capability": "ats_form_inspect:greenhouse:discord",
        "actor": "human",
        "decision": "PROMOTE",
    }


def test_form_mapping_covers_every_question() -> None:
    form = form_from_greenhouse_job("discord", _job())
    assert form["provider"] == "greenhouse"
    assert form["site"] == "discord"
    assert form["posting_id"] == "8433948002"
    assert len(form["fields"]) == len(_job()["questions"])


def test_sensitive_and_free_text_fields_classify_human_required() -> None:
    form = form_from_greenhouse_job("discord", _job())
    inspection = inspect_ats_form(form, _policy())
    by_name = {field["name"]: field for field in inspection["fields"]}
    assert by_name["Why do you want to work at Discord?"]["field_type"] == "free_text"
    assert by_name["Why do you want to work at Discord?"]["classification"] == "human_required"
    auth = by_name["Are you legally authorized to work in the United States for our Company?"]
    assert auth["field_type"] == "work_authorization"
    assert auth["classification"] == "human_required"
    assert inspection["mutation_performed"] is False
    assert inspection["external_effects"] is False


def test_inspection_digest_is_stable() -> None:
    form = form_from_greenhouse_job("discord", _job())
    first = inspect_ats_form(form, _policy())
    second = inspect_ats_form(form, _policy())
    assert first["form_schema_digest"] == second["form_schema_digest"]


def test_inspect_fails_closed_without_policy() -> None:
    form = form_from_greenhouse_job("discord", _job())
    with pytest.raises(ApplicationGateError):
        inspect_ats_form(form, None)


def test_inspect_fails_closed_on_wrong_site_scope() -> None:
    form = form_from_greenhouse_job("discord", _job())
    with pytest.raises(ApplicationGateError):
        inspect_ats_form(form, {**_policy(), "capability": "ats_form_inspect:greenhouse:other"})


def test_incomplete_payload_fails_closed() -> None:
    with pytest.raises(GreenhouseFormError):
        form_from_greenhouse_job("discord", {"id": 1})
