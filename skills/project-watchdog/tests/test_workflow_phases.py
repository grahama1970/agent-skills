from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from watchdog import handlers, primary, receipt_schema  # noqa: E402


def _project() -> dict:
    return {"project_id": "agent-skills", "repo": "grahama1970/agent-skills", "worktree": "/tmp/agent-skills"}


def _issue() -> dict:
    return {
        "number": 1627,
        "title": "repair",
        "body": "",
        "url": "https://github.com/grahama1970/agent-skills/issues/1627",
        "labels": [{"name": "agent-work"}, {"name": "route:backend_python_or_skill_runtime"}],
        "watchdog_action": "ticket_repair",
    }


def test_new_result_records_route_phase() -> None:
    result = handlers._new_result(_project(), _issue(), "ticket_repair")

    phases = {phase["id"]: phase for phase in result["workflow_phases"]}
    assert phases["issue_observed"]["status"] == "OBSERVED"
    assert phases["route_classified"]["executor"] == "registry.classify_issue_with_reason"
    assert "eligible_next_tick=agent-work and no hold labels" in phases["route_classified"]["details"]


def test_failure_records_triage_and_alert_policy(monkeypatch) -> None:
    monkeypatch.setattr(primary, "recovery_command", lambda root: "recover --apply")
    monkeypatch.setattr(receipt_schema, "_classify_with_triage_error", lambda message: {"code": "triage_classifier_unreachable", "cause": "c", "next_command": None})

    result = primary.failure(_project(), _issue(), "boom")

    phases = {phase["id"]: phase for phase in result["workflow_phases"]}
    assert phases["failure_triaged"]["skill"] == "triage-error"
    assert phases["ops_discord_alert"]["status"] == "PENDING"
    assert "COMPLETED does not alert" in phases["ops_discord_alert"]["details"][0]
