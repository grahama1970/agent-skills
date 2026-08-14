"""Cross-mode projection proof for #1401 (required proofs 1, 4, 5, 6, 8, 9, 10).

Committed fixtures under ``fixtures/run_projection/`` cover the ten execution
modes the ticket names. Each fixture encodes a hard case rather than a happy
path, because the projection exists to make absence and non-settlement visible.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask.run_projection import (  # noqa: E402
    SCHEMA,
    project_run,
    render_text,
    to_timeline,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "run_projection"

MODES = (
    "one_handler",
    "roundtable_partial",
    "compete",
    "creator_reviewer",
    "argue",
    "deep_review",
    "team_plan",
    "natural_ask_dag",
    "mixed_targets",
    "local_non_agentic_blocked",
)


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_projects_without_mode_specific_inspection(mode: str) -> None:
    """Required proof 1: one shape answers every mode."""
    projection = project_run(FIXTURES / mode)
    assert projection["schema"] == SCHEMA
    assert projection["nodes"], f"{mode} projected no nodes"
    assert projection["lifecycle"] != "UNKNOWN", f"{mode} could not be classified"


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_is_byte_stable_on_reprojection(mode: str) -> None:
    """Required proof 7: canonical JSON is stable; no observation timestamp."""
    run = FIXTURES / mode
    first = json.dumps(project_run(run), sort_keys=True)
    second = json.dumps(project_run(run), sort_keys=True)
    assert first == second


@pytest.mark.parametrize("mode", MODES)
def test_every_compiled_node_appears_in_every_mode(mode: str) -> None:
    """Required proof 2, applied across modes: the DAG is the roster."""
    run = FIXTURES / mode
    dag = json.loads((run / "dag.json").read_text(encoding="utf-8"))
    expected = [node["id"] for node in dag["nodes"]]
    assert [n["node_id"] for n in project_run(run)["nodes"]] == expected


def test_a_partial_roundtable_names_every_seat_and_its_cause() -> None:
    """Required proof 5: the read-model gap behind #1256."""
    projection = project_run(FIXTURES / "roundtable_partial")
    by_id = {n["node_id"]: n for n in projection["nodes"]}

    assert by_id["handler-webgpt"]["stage"] == "SETTLED"
    assert by_id["handler-webclaude"]["failure_code"] == "browser_provider_rate_limited"
    # The seat that produced nothing is still enumerated, with the absence named.
    assert by_id["handler-webkimi"]["stage"] == "COMPILED"
    assert "never created a worker directory" in by_id["handler-webkimi"]["limitation"]
    assert by_id["join"]["failure_code"] == "degraded_join"
    assert projection["lifecycle"] == "DEGRADED"


def test_a_favorable_provider_answer_cannot_manufacture_pass() -> None:
    """Required proofs 4 and 9.

    The fixture holds confident provider output and a run that exited without
    admitting it. Neither the text nor a zero exit may read as success.
    """
    projection = project_run(FIXTURES / "natural_ask_dag")
    handler = next(n for n in projection["nodes"] if n["node_id"] == "handler-webgpt")

    assert handler["stage"] == "CANDIDATE"
    assert handler["evidence_admitted"] is False
    assert projection["lifecycle"] != "PASS"
    assert projection["admitted_node_count"] == 0


def test_a_blocked_preflight_keeps_request_goal_and_failure() -> None:
    """Required proof 6: nothing is lost because execution never began."""
    projection = project_run(FIXTURES / "local_non_agentic_blocked")

    assert projection["request"], "request text must survive a blocked preflight"
    assert projection["goal_hash"] == "sha256:fixture"
    assert projection["failure_code"] == "browser_provider_probe_timeout"
    assert projection["removed_seats"] == ["webgpt"]
    # The plan survives too: both compiled nodes are still enumerated.
    assert [n["node_id"] for n in projection["nodes"]] == ["handler-webgpt", "join"]
    assert all(n["stage"] == "COMPILED" for n in projection["nodes"])


def test_mixed_targets_are_classified_per_seat() -> None:
    projection = project_run(FIXTURES / "mixed_targets")
    kinds = {n["node_id"]: n["target_kind"] for n in projection["nodes"]}
    assert kinds["handler-webgpt"] == "browser_seat"
    assert kinds["handler-gpt-5.5-high"] == "model"
    assert kinds["join"] == "join"


@pytest.mark.parametrize("mode", MODES)
def test_all_three_consumers_agree(mode: str) -> None:
    """Required proof 8: human text, JSON, and timeline share one projection.

    Each consumer is a pure function of the projection, so none can re-infer
    state from the run directory and disagree with the others.
    """
    projection = project_run(FIXTURES / mode)
    timeline = to_timeline(projection)
    text = "\n".join(render_text(projection))

    assert timeline["lifecycle"] == projection["lifecycle"]
    assert [e["node_id"] for e in timeline["entries"]] == [n["node_id"] for n in projection["nodes"]]
    for node in projection["nodes"]:
        entry = next(e for e in timeline["entries"] if e["node_id"] == node["node_id"])
        assert entry["settled"] == (node["stage"] == "SETTLED")
        assert entry["evidence_admitted"] == node["evidence_admitted"]
        assert node["node_id"] in text


def test_the_timeline_never_reports_settlement_the_projection_denies() -> None:
    """The disagreement that would matter: a timeline claiming success."""
    projection = project_run(FIXTURES / "natural_ask_dag")
    timeline = to_timeline(projection)
    assert not any(entry["settled"] for entry in timeline["entries"])
    assert not any(entry["evidence_admitted"] for entry in timeline["entries"])


def test_render_text_is_a_pure_function_of_the_projection() -> None:
    """Required proof 10 in spirit: no hidden re-reading of the run directory."""
    projection = project_run(FIXTURES / "one_handler")
    detached = json.loads(json.dumps(projection))
    detached["run_dir"] = "/nonexistent"
    # Rendering a projection whose run directory is gone must still work.
    assert render_text(detached)
