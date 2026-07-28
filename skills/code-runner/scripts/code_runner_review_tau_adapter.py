#!/usr/bin/env python3
"""Tau reviewer adapter: independently verify a coder patch before it is accepted.

Purpose
    A real coder feeding a stub reviewer is a false-green machine. The shipped
    `agent-command-specs/reviewer/tau-dispatch-command.json` returns
    ``--result-status COMPLETED`` unconditionally, so every patch would pass.

    This reviewer re-derives the verdict from artifacts instead of believing the
    coder's handoff. The coder says what it did; this checks.

Inputs
    stdin  : the coder's `tau.agent_handoff.v1`, carrying `changed_files`,
             `focused_tests`, and the patch path in `evidence`.
    env    : ``TAU_HANDOFF_COMMAND_ARTIFACT_DIR``, ``TAU_HANDOFF_ACTIVE_GOAL_HASH``.

Outputs
    A `tau.agent_handoff.v1` carrying `review_verdict` — the `required_evidence`
    the repair DAG's reviewer node gates on — plus the checks that produced it.

Checks, all of which must pass
    1. The patch file exists and is non-empty. An empty diff is not a repair.
    2. Every file the patch touches is inside the allowlist the coder was given.
       A patch that writes outside its declared scope is rejected even if the
       tests pass; scope violation is the failure the sandbox exists to catch.
    3. The focused test command is re-run *here*, against the patch applied to a
       throwaway copy. The coder's own "definition of done passed" claim is not
       evidence — the whole point of a reviewer is that it does not inherit the
       creator's conclusion.

Failure modes
    Fails closed. Any missing artifact, unreadable patch, scope violation, or
    non-zero re-run produces ``review_verdict: FAIL`` and routes to human. A
    reviewer that cannot verify must never report PASS.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


def _patch_targets(patch_text: str) -> list[str]:
    """Return every path the patch writes to."""
    return [
        line.split(" b/", 1)[1].strip()
        for line in patch_text.splitlines()
        if line.startswith("diff --git ") and " b/" in line
    ]


def _within_allowlist(path: str, allowlist: list[str]) -> bool:
    return any(path == entry or fnmatch(path, entry) for entry in allowlist)


def _verdict(
    status: str,
    goal_hash: str,
    checks: list[dict[str, Any]],
    summary: str,
    handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the reviewer response, preserving the identity fields Tau checks."""
    passed = status == "PASS"
    packet: dict[str, Any] = {
        "schema": "tau.agent_handoff.v1",
        "goal": {"goal_hash": goal_hash},
        "previous_subagent": "reviewer",
        "result": {
            "status": "COMPLETED" if passed else "BLOCKED",
            "summary": summary,
            "review_verdict": status,
            "checks": checks,
            # Tau matches required_evidence inside result.evidence.
            "evidence": [{"review_verdict": status}, *[c["name"] for c in checks]],
        },
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": (
                "Patch verified independently; a human decides whether to apply it."
                if passed
                else "Review failed; a human must decide how to proceed."
            ),
        },
        "required_evidence": ["human decision on the reviewed patch"],
        "stop_condition": "Human applies, rejects, or redirects the patch.",
    }
    source = handoff or {}
    if source.get("github"):
        packet["github"] = source["github"]
    if source.get("goal"):
        packet["goal"] = source["goal"]
    packet["context"] = {"summary": summary, "artifacts": [c["name"] for c in checks]}
    packet["rationale"] = summary
    return packet


def main() -> int:
    goal_hash = os.environ.get("TAU_HANDOFF_ACTIVE_GOAL_HASH", "")
    checks: list[dict[str, Any]] = []
    handoff: dict[str, Any] = {}

    def fail(summary: str) -> int:
        print(
            json.dumps(
                _verdict("FAIL", goal_hash, checks, summary, handoff), indent=2, sort_keys=True
            )
        )
        return 1

    try:
        handoff = json.loads(sys.stdin.read() or "{}")
    except ValueError as exc:
        return fail(f"unparseable coder handoff: {exc}")

    result = handoff.get("result") or {}
    evidence = [str(e) for e in (result.get("evidence") or [])]
    patch_path = next((Path(e) for e in evidence if e.endswith(".patch")), None)
    spec_path = next(
        (Path(e) for e in evidence if e.endswith("code-runner-spec.json")), None
    )

    # 1. patch exists and is non-empty
    if patch_path is None or not patch_path.is_file():
        return fail("coder handoff cites no readable patch artifact")
    patch_text = patch_path.read_text(encoding="utf-8")
    if not patch_text.strip():
        return fail("patch artifact is empty; an empty diff is not a repair")
    checks.append({"name": "patch_present", "ok": True, "detail": str(patch_path)})

    # 2. every touched path is inside the allowlist the coder was given
    if spec_path is None or not spec_path.is_file():
        return fail(
            "coder handoff cites no readable code-runner spec; scope cannot be checked"
        )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    allowlist = [str(p) for p in spec.get("allowlist", [])]
    targets = _patch_targets(patch_text)
    outside = [t for t in targets if not _within_allowlist(t, allowlist)]
    if outside:
        checks.append({"name": "scope_respected", "ok": False, "detail": outside})
        return fail(
            f"patch writes outside its allowlist: {outside}; allowlist was {allowlist}"
        )
    checks.append({"name": "scope_respected", "ok": True, "detail": targets})

    # 3. re-run the definition of done against the patch, independently
    command = str((spec.get("definition_of_done") or {}).get("command") or "")
    source = Path(str(spec.get("cwd") or ""))
    if not command or not source.is_dir():
        return fail("spec carries no runnable definition of done to re-verify")

    workdir = Path(tempfile.mkdtemp(prefix="tau-review-"))
    try:
        copy = workdir / "src"
        shutil.copytree(source, copy, symlinks=True)
        applied = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=copy,
            capture_output=True,
            text=True,
            check=False,
        )
        if applied.returncode != 0:
            checks.append(
                {"name": "patch_applies", "ok": False, "detail": applied.stderr[:300]}
            )
            return fail(f"patch does not apply cleanly: {applied.stderr.strip()[:200]}")
        checks.append({"name": "patch_applies", "ok": True, "detail": "clean"})

        rerun = subprocess.run(
            command,
            shell=True,
            cwd=copy,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("TAU_REVIEW_TIMEOUT_S", "600")),
            check=False,
        )
        ok = rerun.returncode == 0
        checks.append(
            {
                "name": "independent_rerun",
                "ok": ok,
                "detail": {"command": command, "exit_code": rerun.returncode},
            }
        )
        if not ok:
            return fail(
                f"independent re-run of {command!r} failed with exit {rerun.returncode}: "
                f"{(rerun.stdout or rerun.stderr).strip()[-300:]}"
            )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(
        json.dumps(
            _verdict(
                "PASS",
                goal_hash,
                checks,
                f"Patch applies cleanly, stays inside {allowlist}, and {command!r} passes on "
                "independent re-run.",
                handoff,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
