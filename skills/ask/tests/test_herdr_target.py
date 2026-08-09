"""Targeting another agent's Herdr session must never guess.

The live workstation has 122 panes; `memory` matches 6 and `agent-skills` 44.
Picking one implicitly would deliver another agent's work to a stranger, so
ambiguity is a refusal, not a heuristic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask.herdr_target import HerdrPane, parse_panes, resolve  # noqa: E402

# Shaped exactly like real `herdr pane list` output, including the dead pane.
LIVE_SAMPLE = json.dumps(
    {
        "id": "cli:pane:list",
        "result": {
            "panes": [
                {"pane_id": "w11:p13", "agent": "codex", "agent_status": "idle",
                 "cwd": "/home/graham/workspace/experiments/memory", "workspace_id": "w11"},
                {"pane_id": "w7E:pK", "agent": "claude", "agent_status": "idle",
                 "cwd": "/home/graham/workspace/experiments/memory", "workspace_id": "w7E"},
                {"pane_id": "w88:p7", "agent": "", "agent_status": "unknown",
                 "cwd": "/home/graham/workspace/experiments/memory", "workspace_id": "w88"},
                {"pane_id": "w11:p16", "agent": "codex", "agent_status": "idle",
                 "cwd": "/home/graham/workspace/experiments/fetcher", "workspace_id": "w11"},
                {"pane_id": "w8A:p2", "agent": "claude", "agent_status": "working",
                 "cwd": "/home/graham/workspace/experiments/agent-skills", "workspace_id": "w8A"},
            ]
        },
    }
)

ALIASES = {"graph-memory-operator": "memory"}


@pytest.fixture
def panes() -> list[HerdrPane]:
    return parse_panes(LIVE_SAMPLE)


def test_parses_real_herdr_output(panes: list[HerdrPane]) -> None:
    assert len(panes) == 5
    assert panes[0].pane_id == "w11:p13"
    assert panes[0].project == "memory"


def test_a_unique_name_resolves_without_interview(panes: list[HerdrPane]) -> None:
    result = resolve("fetcher", panes, repo_map=ALIASES)
    assert not result.needs_interview
    assert result.resolved.pane_id == "w11:p16"


def test_an_ambiguous_name_refuses_and_offers_candidates(panes: list[HerdrPane]) -> None:
    result = resolve("memory", panes, repo_map=ALIASES)
    assert result.needs_interview
    assert result.resolved is None, "must not pick one silently"
    assert [c["pane_id"] for c in result.interview_options()] == ["w11:p13", "w7E:pK"]


def test_a_dead_pane_is_never_a_candidate(panes: list[HerdrPane]) -> None:
    """w88:p7 has no agent and status unknown: typing into it is never safe."""
    result = resolve("memory", panes, repo_map=ALIASES)
    assert "w88:p7" not in [c.pane_id for c in result.candidates]


def test_the_repo_slug_reaches_the_checkout_directory(panes: list[HerdrPane]) -> None:
    """Nothing on disk is named graph-memory-operator; the checkout is `memory`."""
    by_repo = resolve("graph-memory-operator", panes, repo_map=ALIASES)
    by_dir = resolve("memory", panes, repo_map=ALIASES)
    assert [c.pane_id for c in by_repo.candidates] == [c.pane_id for c in by_dir.candidates]


def test_an_exact_pane_id_short_circuits_ambiguity(panes: list[HerdrPane]) -> None:
    result = resolve("w7E:pK", panes, repo_map=ALIASES)
    assert result.resolved.pane_id == "w7E:pK"
    assert not result.needs_interview


def test_a_busy_pane_is_excluded_unless_asked_for(panes: list[HerdrPane]) -> None:
    """Interrupting running work needs an explicit decision."""
    assert resolve("agent-skills", panes, repo_map=ALIASES).candidates == ()
    allowed = resolve("agent-skills", panes, repo_map=ALIASES, include_busy=True)
    assert allowed.resolved.pane_id == "w8A:p2"


def test_an_unknown_name_reports_why(panes: list[HerdrPane]) -> None:
    result = resolve("nonexistent", panes, repo_map=ALIASES)
    assert result.candidates == ()
    assert "nonexistent" in result.reason


def test_herdr_being_down_is_not_an_exception() -> None:
    result = resolve("memory", [], repo_map=ALIASES)
    assert result.candidates == ()
    assert "no panes" in result.reason


def test_unparseable_output_yields_no_panes() -> None:
    assert parse_panes("not json") == []
    assert parse_panes(json.dumps({"result": {"panes": "wrong"}})) == []


def test_interview_shows_session_model_and_directory(panes: list[HerdrPane]) -> None:
    """The three facts that let a human tell identical names apart."""
    payload = resolve("memory", panes, repo_map=ALIASES).interview_payload()
    assert payload["version"] == 2
    question = payload["questions"][0]
    assert question["multi_select"] is False
    labels = [o["label"] for o in question["options"]]
    assert labels == ["w11:p13", "w7E:pK"], "label is the session"
    for option in question["options"]:
        assert "model:" in option["description"]
        assert "dir:" in option["description"]


def test_interview_options_carry_machine_readable_fields(panes: list[HerdrPane]) -> None:
    options = resolve("memory", panes, repo_map=ALIASES).interview_options()
    assert options[0]["model"] == "codex"
    assert options[0]["directory"].endswith("/memory")
    assert options[0]["pane_id"] == "w11:p13"
