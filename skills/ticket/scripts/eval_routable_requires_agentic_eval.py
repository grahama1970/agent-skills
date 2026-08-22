#!/usr/bin/env python3
"""Regression guard: agent-routable tickets must prove via /agentic-evals.

project-watchdog's repair loop never authors a regression guard (creator fixes,
reviewer verifies against the ticket's Required proof). So a routable ticket
whose proof is not an /agentic-evals run leaves nothing to stop the fix
regressing. This guard exercises the real validator and fails (exit 1) if:
  - a routable ticket without an agentic-evals proof is accepted, or
  - a routable ticket WITH an agentic-evals proof is rejected, or
  - a human-first (question/triage) ticket is subjected to the rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import typer  # noqa: E402

import ticket_cli as t  # noqa: E402


def _rejected(proof: str, ticket_type: str, route: str) -> bool:
    try:
        t._require_agentic_eval_proof(proof, ticket_type, route)
        return False
    except (typer.Exit, SystemExit):
        return True


def main() -> int:
    failures: list[str] = []
    routable_route = "backend_python_or_skill_runtime"
    eval_proof = ("cd skills/agentic-evals && ./run.sh run ../x/fixtures/agentic_eval.json "
                  "--only-category id --map m.json shows READY")

    if not _rejected("run the entrypoint and read the artifact", "bug", routable_route):
        failures.append("ROUTABLE_NO_EVAL_ACCEPTED: a routable ticket without an /agentic-evals proof was accepted.")
    if _rejected(eval_proof, "bug", routable_route):
        failures.append("ROUTABLE_WITH_EVAL_REJECTED: a routable ticket WITH an /agentic-evals proof was rejected.")
    for human_type in ("question", "triage"):
        if _rejected("anything", human_type, "unknown"):
            failures.append(f"HUMAN_FIRST_SUBJECTED: {human_type} ticket wrongly subjected to the eval rule.")

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print("ROUTABLE_REQUIRES_AGENTIC_EVAL_OK: routable tickets need an /agentic-evals proof; human-first exempt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
