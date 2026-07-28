#!/usr/bin/env python3
"""Tau coder adapter: turn a `tau.agent_handoff.v1` packet into a code-runner run.

Purpose
    Tau ships `handoff-goal-guardian-adapter` and `handoff-research-auditor-adapter`
    but no coder adapter, so `agent-command-specs/coder/tau-dispatch-command.json`
    is a transport stub that returns ``--result-status COMPLETED`` unconditionally.
    A repair DAG wired to that stub reports fixes it never made.

    This adapter is the missing mapping. It is deliberately not intelligence:
    a `/ticket`-filed issue body already carries every field code-runner needs.

        ## Target / Target paths   ->  allowlist
        ## Current state           ->  prompt (the defect)
        ## Requested outcome       ->  prompt (the goal)
        ## Required proof          ->  definition_of_done.command

Inputs
    stdin  : `tau.agent_handoff.v1` JSON, written by Tau's dispatcher.
    env    : ``TAU_HANDOFF_COMMAND_ARTIFACT_DIR`` for artifacts,
             ``TAU_HANDOFF_ACTIVE_GOAL_HASH`` echoed into the receipt so Tau can
             bind this turn to the immutable goal.

Outputs
    A `tau.agent_handoff.v1` packet on stdout carrying `changed_files` and
    `focused_tests` — the exact `required_evidence` the repair DAG's coder node
    gates on — plus the patch path. Artifacts land in the artifact dir.

Failure modes
    Fails closed in every case, because a coder that reports success it cannot
    evidence is worse than one that refuses:

    - No parseable target paths -> BLOCKED. Never guess an allowlist; an
      unbounded write scope is the one thing the sandbox exists to prevent.
    - No parseable proof command -> BLOCKED. Without a deterministic
      definition of done there is nothing to verify a fix against.
    - code-runner non-zero, or DoD not met -> BLOCKED with its stderr.
    - Patch produced but empty -> BLOCKED. An empty diff is not a repair.

    ``apply_to_source`` is hard-coded false. This adapter returns a patch for
    review and never writes to the target repository. Turning that on is a
    separate, explicit decision that does not belong inside a cron-driven loop.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_DIR / "run.sh"

#: Ticket body headings, as emitted by `/ticket`.
TARGET_PATHS_RE = re.compile(r"##\s*Target paths\s*\n(.*?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)
TARGET_RE = re.compile(r"##\s*Target\s*\n(.*?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)
CURRENT_STATE_RE = re.compile(r"##\s*Current state\s*\n(.*?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)
OUTCOME_RE = re.compile(r"##\s*Requested outcome\s*\n(.*?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)
PROOF_RE = re.compile(r"##\s*Required proof\s*\n(.*?)(?:\n##|\Z)", re.DOTALL | re.IGNORECASE)

#: A proof section is prose; the runnable command is the fenced block or a line
#: that starts with a known runner.
COMMAND_LINE_RE = re.compile(
    r"^\s*(?:uv run |python |pytest |npm |make |cargo |go )\S.*$", re.MULTILINE
)


def _section(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return match.group(1).strip() if match else ""


def parse_allowlist(body: str) -> list[str]:
    """Extract writable paths from the ticket body. Empty means refuse."""
    raw = _section(TARGET_PATHS_RE, body) or _section(TARGET_RE, body)
    paths: list[str] = []
    for line in raw.splitlines():
        candidate = line.strip().lstrip("-*").strip().strip("`")
        # A path, not prose: no spaces, and it looks like a path or glob.
        if (
            candidate
            and " " not in candidate
            and ("/" in candidate or "." in candidate)
        ):
            paths.append(candidate)
    return paths


def parse_proof_command(body: str) -> str:
    """Extract the deterministic verification command. Empty means refuse."""
    proof = _section(PROOF_RE, body)
    fenced = re.search(r"```(?:bash|sh|text)?\s*\n(.*?)```", proof, re.DOTALL)
    haystack = fenced.group(1) if fenced else proof
    match = COMMAND_LINE_RE.search(haystack)
    return match.group(0).strip() if match else ""


def build_spec(
    handoff: dict[str, Any], *, artifact_dir: Path
) -> tuple[dict[str, Any], str]:
    """Return (spec, refusal_reason). A non-empty reason means do not run."""
    context = handoff.get("context") or {}
    # Tau nests the DAG node's declared context under context.tau_dag_node.context;
    # its start handoff carries no issue_body or repo_path at the top level.
    node_context = ((context.get("tau_dag_node") or {}).get("context")) or {}
    body = str(node_context.get("issue_body") or context.get("issue_body") or "")
    repo_path = str(node_context.get("repo_path") or context.get("repo_path") or "")
    target = str((handoff.get("github") or {}).get("target") or "task")

    allowlist = parse_allowlist(body)
    if not allowlist:
        return {}, (
            "ticket body declares no parseable '## Target paths'; refusing to guess "
            "a write allowlist"
        )
    command = parse_proof_command(body)
    if not command:
        return {}, (
            "ticket body declares no runnable command under '## Required proof'; "
            "refusing to run without a deterministic definition of done"
        )
    if not repo_path or not Path(repo_path).is_dir():
        return {}, f"handoff carries no usable repository path: {repo_path!r}"

    task_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", f"watchdog-{target}").strip("-")
    return {
        "task_id": task_id,
        "title": str(context.get("title") or target),
        "prompt": (
            f"{_section(CURRENT_STATE_RE, body)}\n\n"
            f"Required outcome: {_section(OUTCOME_RE, body)}\n\n"
            "Change only the allowlisted paths. Make the definition-of-done command pass."
        ).strip(),
        "backend": os.environ.get("TAU_CODER_BACKEND", "codex"),
        "cwd": repo_path,
        "output_dir": str(artifact_dir / "code-runner"),
        "allowlist": allowlist,
        "definition_of_done": {"command": command, "assertion": "exit_code == 0"},
        "dirty_worktree_policy": "isolated_worktree",
        "max_rounds": int(os.environ.get("TAU_CODER_MAX_ROUNDS", "3")),
        # Never true here. A cron-driven loop must not write to a source repo.
        "apply_to_source": False,
    }, ""


def _echo(handoff: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    """Preserve the identity fields Tau requires a node response to carry.

    Tau rejects a response whose github target or goal differs from the start
    handoff ("response.github target must match start handoff target"), and
    requires context and rationale on every packet. Echoing them is how a node
    proves it acted on the work it was given rather than drifting.
    """
    if handoff.get("github"):
        packet["github"] = handoff["github"]
    if handoff.get("goal"):
        packet["goal"] = handoff["goal"]
    packet.setdefault(
        "context",
        {
            "summary": packet["result"]["summary"],
            "artifacts": [e for e in packet["result"].get("evidence", []) if isinstance(e, str)],
        },
    )
    packet.setdefault("rationale", packet["result"]["summary"])
    return packet


def emit(packet: dict[str, Any]) -> int:
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["result"]["status"] == "COMPLETED" else 1


def blocked(
    reason: str, goal_hash: str, evidence: list[str] | None = None
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "goal": {"goal_hash": goal_hash},
        "previous_subagent": "coder",
        "result": {"status": "BLOCKED", "summary": reason, "evidence": evidence or []},
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Coder could not produce evidenced changes; a human must decide.",
        },
        "required_evidence": ["human review of the blocker"],
        "stop_condition": "Human accepts, redirects, or narrows the ticket.",
    }


def main() -> int:
    goal_hash = os.environ.get("TAU_HANDOFF_ACTIVE_GOAL_HASH", "")
    artifact_dir = Path(
        os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", "/tmp/tau-coder-adapter")
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)

    try:
        handoff = json.loads(sys.stdin.read() or "{}")
    except ValueError as exc:
        return emit(blocked(f"unparseable handoff on stdin: {exc}", goal_hash))

    spec, refusal = build_spec(handoff, artifact_dir=artifact_dir)
    if refusal:
        return emit(_echo(handoff, blocked(refusal, goal_hash)))

    spec_path = artifact_dir / "code-runner-spec.json"
    spec_path.write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    result = subprocess.run(
        [str(RUN_SH), "run", str(spec_path)],
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("TAU_CODER_TIMEOUT_S", "1800")),
        check=False,
    )
    if result.returncode != 0:
        return emit(
            _echo(handoff, blocked(
                f"code-runner exited {result.returncode}: {result.stderr.strip()[:400]}",
                goal_hash,
                [str(spec_path)],
            ))
        )

    patch = Path(spec["output_dir"]) / f"{spec['task_id']}.patch"
    if not patch.is_file() or not patch.read_text(encoding="utf-8").strip():
        return emit(
            _echo(handoff, blocked(
                "code-runner produced no non-empty patch; an empty diff is not a repair",
                goal_hash,
                [str(spec_path)],
            ))
        )

    changed = [
        line.split(" b/", 1)[1].strip()
        for line in patch.read_text(encoding="utf-8").splitlines()
        if line.startswith("diff --git ") and " b/" in line
    ]
    return emit(
        _echo(handoff, {
            "schema": "tau.agent_handoff.v1",
            "goal": {"goal_hash": goal_hash},
            "previous_subagent": "coder",
            "result": {
                "status": "COMPLETED",
                "summary": (
                    f"code-runner produced a reviewed-scope patch touching {len(changed)} "
                    f"file(s); definition of done passed. Source repository not modified."
                ),
                # Tau matches required_evidence by searching the JSON of
                # result.evidence (project_dag._missing_required_evidence), so the
                # named items must live INSIDE this list, not beside it.
                "evidence": [
                    str(patch),
                    str(spec_path),
                    {"changed_files": changed},
                    {"focused_tests": [spec["definition_of_done"]["command"]]},
                ],
                "changed_files": changed,
                "focused_tests": [spec["definition_of_done"]["command"]],
            },
            "next_agent": {
                "name": "reviewer",
                "executor": "local",
                "reason": "A patch exists and must be reviewed before it reaches the repo.",
            },
            "required_evidence": ["review_verdict"],
            "stop_condition": "Reviewer accepts the patch or routes back with findings.",
        })
    )


if __name__ == "__main__":
    raise SystemExit(main())
