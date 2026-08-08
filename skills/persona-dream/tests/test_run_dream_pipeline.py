"""The spine entrypoint must refuse, not improvise.

These pin the three refusals that make `run.sh dream` an actual constraint
rather than a convenience wrapper. A wrapper that runs steps in order is worth
little; what stops an agent hand-assembling a pipeline is that the alternatives
fail loudly and leave evidence.

The failure this guards against is documented and real: a session in which an
agent called scripts by path, wrote three new ones, invoked run.sh zero times,
and had 112 passing tests the whole way. Tests covered what existed, not the
boundary that was crossed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_dream_pipeline as rdp  # noqa: E402

CONTRACT = ROOT / "contracts" / "dream_spine.v1.yaml"


def test_the_spine_is_data_not_welded_to_a_run_record():
    """The 42-step taxonomy was unusable because it lived inside an audit
    script with a hardcoded RUN_ID. A definition fused to one run cannot be
    executed or compiled."""
    spine = rdp.load_spine(CONTRACT)
    assert spine["schema"] == "persona_dream.dream_spine.v1"
    assert [s["id"] for s in spine["steps"]][-1] == spine["terminates_at"]
    src = (ROOT / "scripts" / "run_dream_pipeline.py").read_text(encoding="utf-8")
    assert "REVISION_ID" not in src and "RUN_ID = " not in src


def test_a_dirty_run_dir_is_refused(tmp_path):
    """A stale artifact must never be indistinguishable from fresh output."""
    (tmp_path / "journal.md").write_text("left over", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rdp.assert_clean_run_dir(tmp_path)
    assert "BLOCKED_RUN_DIR_NOT_EMPTY" in str(exc.value)


def test_a_step_that_exits_zero_without_artifacts_fails(tmp_path, monkeypatch):
    """Exit status is what a script claims; artifacts are what it did."""
    class Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(rdp.subprocess, "run", lambda *a, **k: Ok())
    record = rdp.run_step(
        {"id": "journal_entry", "name": "Journal Entry", "command": "write-dream-journal",
         "produces": ["journal_entry.json"]},
        tmp_path, [], dry_run=False,
    )
    assert record["status"] == "FAIL_ARTIFACTS_NOT_PRODUCED"
    assert "journal_entry.json" in record["failed_gates"][0]


def test_nothing_downstream_runs_after_a_failure(tmp_path, monkeypatch):
    """The legacy ledger sat at BLOCKED_FINAL_ACCEPTANCE while work continued
    around it. That is precisely what must become impossible."""
    class Fail:
        returncode = 2
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(rdp.subprocess, "run", lambda *a, **k: Fail())
    receipt = rdp.run_pipeline(run_dir=tmp_path, contract=CONTRACT, extra=[],
                               dry_run=False, allow_dirty=True)
    assert receipt["status"].startswith("BLOCKED_AT_")
    assert receipt["steps"][0]["status"] == "FAIL_STEP_EXIT"
    assert all(s["status"] == "NOT_REACHED" for s in receipt["steps"][1:])
    assert receipt["steps_passed"] == 0


def test_an_undeclared_artifact_is_reported(tmp_path):
    """Gating invocation does not help when the bypass is 'write a new script'.
    An artifact no step owns is the only trace such a path leaves."""
    (tmp_path / "bespoke_side_output.json").write_text("{}", encoding="utf-8")
    (tmp_path / "conversation.jsonl").write_text("", encoding="utf-8")
    spine = rdp.load_spine(CONTRACT)
    undeclared = rdp.find_undeclared(tmp_path, spine)
    assert "bespoke_side_output.json" in undeclared
    # The chat surface is legitimately post-pipeline and must not be flagged.
    assert "conversation.jsonl" not in undeclared


def test_each_step_declares_its_own_run_dir_flag():
    """They genuinely disagree -- --run-root, --run-dir, --cycles-dir, none.
    Assuming one flag is how an orchestrator mis-invokes a step and then
    reports the wrong reason for the failure."""
    spine = rdp.load_spine(CONTRACT)
    for step in spine["steps"]:
        assert "run_dir_arg" in step, f"{step['id']} does not declare its flag"


def test_every_step_says_what_it_does_not_prove():
    """A step that only advertises what it proves invites over-reading."""
    spine = rdp.load_spine(CONTRACT)
    for step in spine["steps"]:
        assert step.get("proves") and step.get("does_not_prove"), step["id"]
