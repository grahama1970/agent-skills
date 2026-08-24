#!/usr/bin/env python3
"""Replay agent-skills#1499: a passing repair DAG that proved nothing.

The live failure: ``$ask tau-dag`` exited 0, both node receipts said
``status: PASS``, and the watchdog landed and closed grahama1970/agent-skills#1499
as completed. What the seats actually wrote was a creator declaring
NEEDS_ATTENTION with no tools, and a reviewer reporting the live proof had
failed with ``g1_delta_validation_failed`` while a retry was still running.
No proof artifact and no commit existed.

This guard drives the real ``handle_ticket_repair`` twice against a real git
repository: once with those two responses (must refuse to close), and once with
a reviewer ``VERDICT: PASS`` plus a fresh passing proof artifact and a real
commit (must still land, so the gate is a gate and not a wall).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

CREATOR = "gpt-5.5-high"
REVIEWER = "claude-opus-5-medium"
PROOF_ARTIFACT = "project-watchdog-ticket-repair-proof-gate.json"

# Verbatim shape of what the two seats wrote on agent-skills#1499.
REFUSING_CREATOR = """## Position

NEEDS_ATTENTION - I cannot complete this repair or commit from this session
because no repository/tool execution access is available.

## Evidence

- This chat session does not expose shell, filesystem, git, or repository
  tools, so I could not run the required proof or create a commit.

## Blockers

- Missing execution/filesystem access.
"""

UNFINISHED_REVIEWER = """I've set up the wait. The second focused attempt is running; I'll be
re-invoked when it produces its receipt or the process exits.

- Ran the required live proof once. It failed fail-closed: `status: FAIL`,
  `stop_condition: g1_delta_validation_failed`, 7/11 checks true.
- I'm giving it the second attempt the goal doc's retry rule sanctions before
  deciding between a genuine PASS receipt or a verified blocker report.
"""

PASSING_CREATOR = """## Position

PASS

## Evidence

- Implemented the fix and committed it on the repair branch.
"""

PASSING_REVIEWER = """Checked the diff against the acceptance criterion and re-ran the proof
command; its artifact reads readiness READY with the case PASS.

VERDICT: PASS
"""

PASSING_REVIEWER_RELATIVE_PROOF = """Checked the diff against the acceptance
criterion and read back `local/issue147_agentic_eval_report.json`.

VERDICT: PASS
"""


def node_id(handler: str) -> str:
    """The node-artifacts directory $ask writes for a seat.

    Spelled out here rather than imported so this guard fails on the behaviour
    it is about, not on a missing symbol, when run against a build without the
    gate.
    """
    return "handler-" + re.sub(r"[^a-z0-9]+", "-", handler.lower()).strip("-")


def git(cwd: Path, *args: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


def issue_body(proof_path: Path) -> str:
    """A ticket body in the shape /ticket files, naming one proof artifact."""
    return (
        "## Type\n\nbug\n\n"
        "## Target\n\nskills/project-watchdog\n\n"
        "## Required proof\n\n"
        "Run: skills/agentic-evals/run.sh run "
        "skills/project-watchdog/fixtures/agentic_eval.json "
        f"--case ticket-repair-rejects-needs-attention-without-proof --output {proof_path} "
        "--timeout-seconds 600 and read back readiness READY with the case PASS.\n\n"
        "## Non-goals\n\nNo unrelated refactors.\n"
    )


def issue_body_with_agentic_eval_input_only() -> str:
    """The graph-memory #147 shape: the eval fixture is input, not output."""
    return (
        "## Type\n\nmaintenance\n\n"
        "## Target\n\nsrc/graph_memory/lessons/skill_chains.py\n\n"
        "## Required proof\n\n"
        "/agentic-evals run fixtures/skill_chains/agentic_eval.json "
        "--case skill-chain-live-idempotent-upsert; receipt must show readiness "
        "READY with the case PASS.\n\n"
        "## Non-goals\n\nNo unrelated refactors.\n"
    )


def build_repo(root: Path, *, commit_the_repair: bool) -> tuple[Path, Path]:
    """A registered checkout plus a repair worktree with a real ``origin/main``."""
    registered = root / "checkout"
    (registered / "skills" / "project-watchdog").mkdir(parents=True)
    (registered / "skills" / "project-watchdog" / "SKILL.md").write_text("x\n", encoding="utf-8")
    git(registered.parent, "init", "-q", "-b", "main", str(registered))
    git(registered, "add", "-A")
    git(registered, "commit", "-q", "-m", "init")

    origin = root / "origin.git"
    origin.mkdir()
    git(origin, "init", "-q", "--bare")

    repair = root / "repair-worktrees" / "agent-skills-1499"
    repair.mkdir(parents=True)
    git(repair.parent, "init", "-q", "-b", "main", str(repair))
    (repair / "base.txt").write_text("base\n", encoding="utf-8")
    git(repair, "add", "-A")
    git(repair, "commit", "-q", "-m", "base")
    git(repair, "remote", "add", "origin", str(origin))
    git(repair, "push", "-q", "origin", "main")
    git(repair, "checkout", "-q", "-b", "watchdog/issue-1499")
    if commit_the_repair:
        (repair / "fix.txt").write_text("fix\n", encoding="utf-8")
        git(repair, "add", "-A")
        git(repair, "commit", "-q", "-m", "repair")
    return registered, repair


def run_repair(root: Path, *, creator_says: str, reviewer_says: str,
               write_proof: bool, commit_the_repair: bool,
               body: str | None = None, relative_proof_path: str | None = None) -> dict:
    """Drive the real handler with $ask stubbed to write the seats' responses."""
    os.environ["PROJECT_WATCHDOG_STATE_ROOT"] = str(root)
    from watchdog import config, handlers  # noqa: PLC0415
    from watchdog.core import run_cmd as real_run_cmd  # noqa: PLC0415

    registered, repair = build_repo(root, commit_the_repair=commit_the_repair)
    receipt_dir = root / "receipt"
    receipt_dir.mkdir()
    proof_path = root / PROOF_ARTIFACT

    def fake_run_cmd(command, *, cwd=None, input_text=None, timeout_s=120):
        if str(command[0]).endswith("ask/run.sh"):
            node_root = receipt_dir / "ask" / "ask-tau-repair-x" / "node-artifacts"
            for handler, text in (
                (CREATOR, creator_says), (REVIEWER, reviewer_says),
            ):
                node = node_root / node_id(handler)
                node.mkdir(parents=True, exist_ok=True)
                (node / "response.md").write_text(text, encoding="utf-8")
                (node / "node-receipt.json").write_text(
                    json.dumps({"handler": handler, "ok": True, "status": "PASS"}),
                    encoding="utf-8",
                )
            if write_proof:
                artifact = repair / relative_proof_path if relative_proof_path else proof_path
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(
                    json.dumps({
                        "readiness": "READY",
                        "cases": [{
                            "name": "ticket-repair-rejects-needs-attention-without-proof",
                            "status": "PASS",
                        }],
                    }),
                    encoding="utf-8",
                )
                future = time.time() + 5
                os.utime(artifact, (future, future))
            return {"exit_code": 0, "stdout": "{}", "stderr": ""}
        return real_run_cmd(command, cwd=cwd, input_text=input_text, timeout_s=timeout_s)

    calls: list[tuple[str, tuple, dict]] = []

    def record(name, retval=None):
        def _inner(*a, **k):
            calls.append((name, a, k))
            return retval if retval is not None else {"exit_code": 0, "stdout": "", "stderr": ""}
        return _inner

    project = {
        "project_id": "agent-skills",
        "repo": "grahama1970/agent-skills",
        "worktree": str(registered),
        "runner_kind": "project-local",
        "repair_creator": CREATOR,
        "repair_reviewer": REVIEWER,
        "auto_land_main": True,
    }
    issue = {
        "number": 1499,
        "url": "https://github.com/grahama1970/agent-skills/issues/1499",
        "title": "battle: adaptive lineage proof",
        "labels": [{"name": "agent-work"}],
        "body": body or issue_body(proof_path),
        "watchdog_action": "ticket_repair",
    }
    with (
        mock.patch.object(handlers, "run_cmd", side_effect=fake_run_cmd),
        mock.patch.object(handlers.github, "issue_comment", side_effect=record("comment")),
        mock.patch.object(handlers.github, "issue_edit", side_effect=record("edit")),
        mock.patch.object(handlers.github, "issue_close", side_effect=record("close")),
        mock.patch.object(
            handlers.registry, "prepare_repair_worktree",
            return_value={"ok": True, "branch": "watchdog/issue-1499", "worktree": str(repair)},
        ),
    ):
        result = handlers.handle_issue("eval", receipt_dir, project, issue, apply=True)
    result["_calls"] = calls
    result["_gate_receipt_exists"] = (receipt_dir / "repair-proof-gate.json").is_file()
    return result


def labels_added(result: dict) -> set[str]:
    added: set[str] = set()
    for name, _args, kwargs in result["_calls"]:
        if name == "edit":
            added.update(kwargs.get("add") or [])
    return added


def main() -> int:
    from watchdog import config  # noqa: PLC0415

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        refused = run_repair(
            Path(tmp), creator_says=REFUSING_CREATOR, reviewer_says=UNFINISHED_REVIEWER,
            write_proof=False, commit_the_repair=False,
        )
    if any(name == "close" for name, _a, _k in refused["_calls"]):
        failures.append("CLOSED_WITHOUT_PROOF: the issue was closed on an unproven repair")
    if refused.get("status") == "LANDED":
        failures.append("LANDED_WITHOUT_PROOF: an unproven repair was landed on main")
    if config.DONE_LABEL in labels_added(refused):
        failures.append(f"MARKED_DONE_WITHOUT_PROOF: {config.DONE_LABEL} was applied")
    if refused.get("status") != "NEEDS_ATTENTION":
        failures.append(f"NOT_NEEDS_ATTENTION: status={refused.get('status')!r}")
    if refused.get("ok") is not False:
        failures.append("REPORTED_OK: an unproven repair was reported as ok")
    gate = refused.get("proof_gate") or {}
    reasons = " | ".join(gate.get("reasons") or [])
    for needle, code in (
        ("declared NEEDS_ATTENTION", "NO_SEAT_REFUSAL_REASON"),
        ("declared no VERDICT", "NO_MISSING_VERDICT_REASON"),
        ("no required proof artifact", "NO_MISSING_ARTIFACT_REASON"),
        ("no commit ahead of origin/main", "NO_MISSING_COMMIT_REASON"),
    ):
        if needle not in reasons:
            failures.append(f"{code}: gate reasons did not name it ({reasons})")
    if not refused["_gate_receipt_exists"]:
        failures.append("NO_GATE_RECEIPT: repair-proof-gate.json was not written")

    with tempfile.TemporaryDirectory() as tmp:
        allowed = run_repair(
            Path(tmp), creator_says=PASSING_CREATOR, reviewer_says=PASSING_REVIEWER,
            write_proof=True, commit_the_repair=True,
        )
    if allowed.get("status") != "LANDED":
        failures.append(
            f"GATE_IS_A_WALL: a reviewer-passed, proof-backed, committed repair did not "
            f"land (status={allowed.get('status')!r}, "
            f"reasons={(allowed.get('proof_gate') or {}).get('reasons')})"
        )
    if not any(name == "close" for name, _a, _k in allowed["_calls"]):
        failures.append("GATE_IS_A_WALL: a proven repair did not close its issue")

    with tempfile.TemporaryDirectory() as tmp:
        relative_allowed = run_repair(
            Path(tmp),
            creator_says=PASSING_CREATOR,
            reviewer_says=PASSING_REVIEWER_RELATIVE_PROOF,
            write_proof=True,
            commit_the_repair=True,
            body=issue_body_with_agentic_eval_input_only(),
            relative_proof_path="local/issue147_agentic_eval_report.json",
        )
    if relative_allowed.get("status") != "LANDED":
        failures.append(
            "RELATIVE_REVIEWER_PROOF_REJECTED: an agentic-evals input-only ticket "
            "with a reviewer-named relative proof artifact did not land "
            f"(status={relative_allowed.get('status')!r}, "
            f"reasons={(relative_allowed.get('proof_gate') or {}).get('reasons')})"
        )
    gate = relative_allowed.get("proof_gate") or {}
    if gate.get("required_proof_artifacts") != ["local/issue147_agentic_eval_report.json"]:
        failures.append(
            "AGENTIC_EVAL_INPUT_MISREAD: gate did not use the reviewer-named proof "
            f"artifact ({gate.get('required_proof_artifacts')!r})"
        )

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    print(
        "REPAIR_PROOF_GATE_OK: a NEEDS_ATTENTION seat, an unfinished proof, a missing "
        "artifact, and a commitless branch each refuse closure; a reviewer VERDICT: PASS "
        "with a fresh passing artifact and a real commit still lands; an agentic-evals "
        "input fixture without --output is not mistaken for the proof artifact"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
