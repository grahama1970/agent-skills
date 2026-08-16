"""One singular, isolated, provable MVP -- or nothing.

A spiralling agent does not need more options. The gates here encode what
separates a fix from the next side-quest wearing a plan's clothes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ask import mvp_unblock as mu

GOOD = """
PROBLEM: the transport lock is held for the whole submit-and-capture cycle, so a
second lane blocks on the first rather than on its own tab.
CHANGE: skills/ask/scripts/tau_roundtable_worker.py::_run_browser_transport_cmd
PROOF_COMMAND: uv run pytest tests/test_tau_dag.py -k transport_lock -q
WHY_THIS_UNBLOCKS: The lock is per-process, not per-tab, so lanes serialize on
each other. Scoping it to the tab removes the contention that produced the timeout.
"""


def _fields(text: str = GOOD) -> dict[str, str]:
    return mu.parse_candidate(text)


# --- the contract ---------------------------------------------------------

def test_a_well_formed_candidate_parses_all_four_fields() -> None:
    fields = _fields()
    assert set(fields) == set(mu.REQUIRED_FIELDS)
    assert fields["PROOF_COMMAND"].startswith("uv run pytest")


def test_a_multi_line_field_is_joined() -> None:
    assert "removes the contention" in _fields()["WHY_THIS_UNBLOCKS"]


def test_a_complete_candidate_passes_the_singularity_gate() -> None:
    assert mu.validate_singular(_fields()) == []


@pytest.mark.parametrize("field", mu.REQUIRED_FIELDS)
def test_every_missing_field_is_named(field: str) -> None:
    fields = _fields()
    fields.pop(field)
    assert any(field in problem for problem in mu.validate_singular(fields))


# --- singularity ----------------------------------------------------------

@pytest.mark.parametrize(
    "phrase",
    ["and also update the docs", "as well as a follow-up refactor", "then we migrate the callers"],
)
def test_a_second_deliverable_is_refused(phrase: str) -> None:
    """A proposal that does five things is the next side-quest, not an MVP."""
    fields = _fields()
    fields["WHY_THIS_UNBLOCKS"] += " " + phrase
    assert any("compound" in p for p in mu.validate_singular(fields))


def test_two_change_surfaces_are_refused() -> None:
    fields = _fields()
    fields["CHANGE"] = "skills/ask/src/ask/a.py and skills/ask/src/ask/b.py"
    assert any("more than one change surface" in p for p in mu.validate_singular(fields))


def test_the_same_file_named_twice_is_still_one_surface() -> None:
    fields = _fields()
    fields["CHANGE"] = "worker.py::submit, later in worker.py::capture"
    assert mu.validate_singular(fields) == []


# --- the proof gate -------------------------------------------------------

@pytest.mark.parametrize("proof", ["pytest", "uv run pytest -q", "npm test", "make check", "./sanity.sh"])
def test_a_whole_suite_proof_is_refused(proof: str) -> None:
    """It was already green while the wall stood, so it proves nothing about it."""
    fields = _fields()
    fields["PROOF_COMMAND"] = proof
    assert any("cannot isolate" in p for p in mu.validate_singular(fields))


def test_a_chained_proof_command_is_refused() -> None:
    fields = _fields()
    fields["PROOF_COMMAND"] = "make build && pytest tests/test_x.py"
    assert any("chains several commands" in p for p in mu.validate_singular(fields))


def test_a_proof_that_already_passes_is_rejected(tmp_path) -> None:
    """The gate that kills the whole failure class: green now proves nothing broken."""
    text = GOOD.replace(
        "uv run pytest tests/test_tau_dag.py -k transport_lock -q", "test 1 -eq 1"
    )
    verdict = mu.judge_candidate(text, cwd=tmp_path, run_proof=True)
    assert verdict["accepted"] is False
    assert any("already passes" in p for p in verdict["problems"])
    assert verdict["proof_check"]["fails_now"] is False


def test_a_proof_that_fails_now_is_accepted(tmp_path) -> None:
    text = GOOD.replace(
        "uv run pytest tests/test_tau_dag.py -k transport_lock -q", "test 1 -eq 2"
    )
    verdict = mu.judge_candidate(text, cwd=tmp_path, run_proof=True)
    assert verdict["accepted"] is True
    assert verdict["proof_check"]["fails_now"] is True


def test_a_proof_that_cannot_run_is_not_treated_as_failing(tmp_path) -> None:
    """A command that errors for unrelated reasons is not evidence of the wall."""
    result = mu.check_proof_fails_now("sleep 5", cwd=tmp_path, timeout=1)
    assert result["ran"] is False and result["fails_now"] is False


def test_the_proof_is_not_run_when_the_proposal_already_failed_singularity(tmp_path) -> None:
    """Never execute a command from a proposal that is already rejected."""
    text = GOOD.replace("PROOF_COMMAND:", "PROOF_COMMAND: touch /tmp/should-not-exist #")
    verdict = mu.judge_candidate(text, cwd=tmp_path, run_proof=True)
    assert verdict["proof_check"] is None or verdict["accepted"] is False


# --- selection ------------------------------------------------------------

def test_no_acceptable_candidate_yields_needs_attention() -> None:
    """An unblocking step that does not unblock is the spiral, not the exit."""
    bad = mu.judge_candidate("PROBLEM: dunno")
    selection = mu.select([bad])
    assert selection["status"] == "NEEDS_ATTENTION"
    assert selection["winner"] is None


def test_a_demonstrated_proof_beats_an_undemonstrated_one() -> None:
    plain = mu.judge_candidate(GOOD, handler="a")
    demonstrated = mu.judge_candidate(GOOD, handler="b")
    demonstrated["proof_check"] = {"ran": True, "fails_now": True}
    selection = mu.select([plain, demonstrated])
    assert selection["winner"]["handler"] == "b"
    assert selection["proof_demonstrated"] is True


def test_selection_never_promotes_a_least_bad_option() -> None:
    verdicts = [mu.judge_candidate("PROBLEM: x"), mu.judge_candidate("CHANGE: y")]
    assert mu.select(verdicts)["status"] == "NEEDS_ATTENTION"


# --- packet + grounding ---------------------------------------------------

def test_a_packet_needs_a_target_and_a_failure_code() -> None:
    with pytest.raises(mu.PacketError):
        mu.compile_packet({"target": "skills/ask"})


def test_the_packet_states_the_fail_now_requirement() -> None:
    packet = mu.compile_packet({"target": "skills/ask", "failure_code": "x_timeout"})
    assert "FAILS RIGHT NOW" in packet["request"]
    assert "x_timeout" in packet["request"]


def test_the_packet_allows_blocked_as_a_valid_answer() -> None:
    """'This needs a human' must be sayable, or candidates invent a fix."""
    packet = mu.compile_packet({"target": "t", "failure_code": "f"})
    assert "human" in packet["request"]


def test_queries_come_from_the_blocker_not_the_agents_theory() -> None:
    queries = mu.research_queries(
        {"target": "skills/ask", "failure_code": "surf_browser_lock_timeout",
         "message": "timed out waiting for the browser transport lock"}
    )
    assert "surf browser lock timeout" in queries
    assert any("transport lock" in q for q in queries)


def test_a_useless_failure_code_does_not_become_a_query() -> None:
    queries = mu.research_queries({"target": "t", "failure_code": "BLOCKED", "message": ""})
    assert "blocked" not in [q.casefold() for q in queries]


def test_a_missing_brave_search_is_reported_not_swallowed(tmp_path) -> None:
    result = mu.run_brave("anything", skills_dir=tmp_path)
    assert result["ok"] is False and "not found" in result["error"]
