#!/usr/bin/env python3
"""Validate a debugger escalation-ladder receipt.

Purpose
    Turn the ladder from prose into a gate. Documentation asking an agent to
    read the receipt before setting a breakpoint is ignorable; this validator
    refuses the artifact, so the rung cannot be claimed without the evidence
    that rung is defined by.

    The rules that matter, and why each exists:

    - Rungs run in canonical order with no skipping. Jumping to a breakpoint
      is the exact failure this ladder was written to stop.
    - Only the LAST rung may be resolved. You escalate because the previous
      rung failed; a resolved rung with another after it is a rewritten
      history.
    - Every cited artifact must EXIST on disk. This is the load-bearing check:
      an agent can assert it read a receipt, but it cannot conjure the file.
    - Dispatch must name the field it read. "I checked the receipt" without a
      field is a guess wearing a receipt.
    - At two or more prior attempts the research rung is mandatory, matching
      the bar tau enforces on its own subagents: a third attempt from
      unchanged context supplies no new input.

Inputs
    A JSON file containing a ``debugger.ladder.v1`` object.

Outputs
    Exit 0 and ``LADDER OK`` when the receipt satisfies the contract;
    exit 1 with the first violation named, or the expected-invalid reason
    under ``--expect-invalid``.

Failure modes
    Missing file, non-JSON, wrong schema id, out-of-order or skipped rungs,
    a non-final resolved rung, a cited artifact that does not exist, a
    dispatch without a citation, a breakpoint without a proof artifact, a
    research rung without a query and at least one result URL, a mandatory
    research rung omitted, or an outcome that contradicts the rungs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

LADDER_ORDER = ["dispatch", "breakpoint", "research"]
# Dispatch layers that are answered by an artifact somebody else wrote. Only
# "none_exists" legitimately skips straight to a breakpoint, and it must say so.
ARTIFACT_LAYERS = {
    "tau_dag_error",
    "tau_receipt_alerts",
    "ask_lane_diagnostics",
    "surf_live_dom",
    "seam_violation",
}


class LadderError(ValueError):
    """The ladder receipt violated its contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LadderError(message)


def _validate_dispatch(rung: dict[str, Any], index: int) -> None:
    layer = str(rung.get("layer") or "")
    require(
        layer in ARTIFACT_LAYERS | {"none_exists"},
        f"rung {index} (dispatch) must name a layer; got {layer!r}",
    )
    if layer == "none_exists":
        # A legitimate escape hatch, but an explicit one: the agent is
        # asserting no artifact owns this symptom, and that assertion is
        # visible in the receipt rather than implied by silence.
        return
    artifact = str(rung.get("artifact") or "")
    require(bool(artifact), f"rung {index} (dispatch) on layer {layer!r} cites no artifact")
    require(
        Path(artifact).is_file(),
        f"rung {index} (dispatch) cites {artifact!r}, which does not exist",
    )
    cited = rung.get("cited")
    require(
        isinstance(cited, dict) and str(cited.get("field") or "").strip() != "",
        f"rung {index} (dispatch) read {artifact!r} without citing a field; "
        "naming the field is what distinguishes reading from guessing",
    )


def _validate_breakpoint(rung: dict[str, Any], index: int) -> None:
    proof = str(rung.get("proof") or "")
    require(bool(proof), f"rung {index} (breakpoint) cites no debugger proof artifact")
    require(
        Path(proof).is_file(),
        f"rung {index} (breakpoint) cites proof {proof!r}, which does not exist",
    )
    try:
        payload = json.loads(Path(proof).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LadderError(f"rung {index} (breakpoint) proof {proof!r} is not readable JSON: {exc}") from exc
    require(
        isinstance(payload, dict) and str(payload.get("schema") or "") == "debugger.proof.v1",
        f"rung {index} (breakpoint) proof {proof!r} is not a debugger.proof.v1 artifact",
    )


def _validate_research(rung: dict[str, Any], index: int) -> None:
    require(
        str(rung.get("tool") or "") in {"brave-search", "dogpile", "github-search"},
        f"rung {index} (research) must name the search tool used",
    )
    require(
        len(str(rung.get("query") or "").strip()) >= 3,
        f"rung {index} (research) records no query; a search without its query is unverifiable",
    )
    results = rung.get("results")
    require(
        isinstance(results, list) and len(results) >= 1,
        f"rung {index} (research) returned no results; record what the search actually found",
    )
    for offset, result in enumerate(results):
        require(
            isinstance(result, dict) and len(str(result.get("url") or "")) >= 8,
            f"rung {index} (research) result {offset} has no usable url",
        )


VALIDATORS = {
    "dispatch": _validate_dispatch,
    "breakpoint": _validate_breakpoint,
    "research": _validate_research,
}


def validate_ladder(payload: Any) -> dict[str, Any]:
    """Raise ``LadderError`` unless the receipt satisfies the ladder contract."""
    require(isinstance(payload, dict), "ladder receipt must be a JSON object")
    require(
        str(payload.get("schema") or "") == "debugger.ladder.v1",
        f"schema must be 'debugger.ladder.v1'; got {payload.get('schema')!r}",
    )
    require(
        len(str(payload.get("symptom") or "").strip()) >= 12,
        "symptom must state the stuck state concretely; a vague symptom cannot select a layer",
    )
    attempts = payload.get("attempts")
    require(
        isinstance(attempts, int) and not isinstance(attempts, bool) and attempts >= 0,
        "attempts must be a non-negative integer",
    )
    rungs = payload.get("rungs")
    require(isinstance(rungs, list) and rungs, "ladder must record at least one rung")

    seen: list[str] = []
    for index, rung in enumerate(rungs):
        require(isinstance(rung, dict), f"rung {index} must be an object")
        name = str(rung.get("rung") or "")
        require(name in LADDER_ORDER, f"rung {index} has unknown rung {name!r}")
        require(name not in seen, f"rung {index} repeats rung {name!r}")
        # Order and skipping are one rule: each rung's position in the
        # canonical sequence must be exactly one past the previous one.
        expected = LADDER_ORDER[len(seen)]
        require(
            name == expected,
            f"rung {index} is {name!r} but the ladder requires {expected!r} next; "
            "rungs may not be reordered or skipped",
        )
        seen.append(name)

        resolved = rung.get("resolved")
        require(isinstance(resolved, bool), f"rung {index} must record resolved as a boolean")
        if index < len(rungs) - 1:
            require(
                resolved is False,
                f"rung {index} ({name}) is marked resolved but is followed by another rung; "
                "you escalate only because the previous rung did not resolve it",
            )
        VALIDATORS[name](rung, index)

    outcome = str(payload.get("outcome") or "")
    require(outcome in {"resolved", "needs_attention"}, f"unknown outcome {outcome!r}")
    final_resolved = bool(rungs[-1].get("resolved"))
    require(
        (outcome == "resolved") == final_resolved,
        f"outcome {outcome!r} contradicts the final rung (resolved={final_resolved})",
    )
    if outcome == "needs_attention":
        require(
            "research" in seen,
            "a ladder may not end in needs_attention before the research rung has run",
        )
    if attempts >= 2:
        require(
            "research" in seen,
            f"attempts={attempts} requires the research rung: a third attempt from unchanged "
            "context supplies no new input",
        )
    return {"schema": "debugger.ladder.v1", "rungs_run": seen, "outcome": outcome}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Path to a debugger.ladder.v1 JSON file")
    parser.add_argument("--expect-valid", action="store_true", help="Fail unless the ladder validates")
    parser.add_argument("--expect-invalid", action="store_true", help="Fail unless the ladder is rejected")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        message = f"LADDER UNREADABLE: {exc}"
        if args.expect_invalid:
            print(message)
            return 0
        print(message, file=sys.stderr)
        return 1

    try:
        summary = validate_ladder(payload)
    except LadderError as exc:
        if args.expect_invalid:
            print(f"LADDER REJECTED (expected): {exc}")
            return 0
        print(f"LADDER REJECTED: {exc}", file=sys.stderr)
        return 1

    if args.expect_invalid:
        print("LADDER VALIDATED but --expect-invalid was requested", file=sys.stderr)
        return 1
    print(f"LADDER OK: rungs={'->'.join(summary['rungs_run'])} outcome={summary['outcome']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
