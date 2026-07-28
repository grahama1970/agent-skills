#!/usr/bin/env python3
"""Fail closed when SKILL.md stops being a stable executable contract.

SKILL.md is what an agent reads to invoke this skill safely. It drifts in a
specific way: mutable status leaks in (active revision ids, provider request
ids, canary attempt history), the advertised command list falls behind
``run.sh``, and stable invariants get interleaved with execution chronology.
Once that happens an agent cannot tell a durable rule from an aged fact.

This validates the contract properties, never the prose. Every check is
deterministic and makes no live or paid call.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
RUN_SH = ROOT / "run.sh"

REQUIRED_FRONTMATTER = ("name", "description", "triggers", "provides")

#: Markers that are mutable facts, not contract terms. They age independently of
#: the contract, so an agent reading them as current is reading a stale claim.
MUTABLE_MARKERS = (
    "currently active qualified revision",
    "request_id:",
    "actual_provider_call_attempts:",
    "attempt_ledger_state:",
    "provider_result_http_status:",
)

#: Both lanes must be represented: the generic packet lane and the Embry
#: continuity specialization. Advertising only one misroutes agents.
GENERIC_LANE_TOKENS = ("dream packet", "memory residue")
CONTINUITY_LANE_TOKENS = ("continuity", "session mood")

#: Ownership per #1037: an external evaluator scores audio identity; this skill
#: owns lineage and consumes the receipt.
EXTERNAL_EVAL_TOKENS = ("voice-evaluation", "speaker similarity")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    return {
        m.group(1): m.group(2).strip()
        for m in re.finditer(r"^([a-z_]+):(.*)$", block, re.M)
    }


def run_sh_commands(text: str) -> set[str]:
    """Subcommands the dispatcher actually accepts."""
    return {m.group(1) for m in re.finditer(r"^\s{2}([a-z][a-z0-9-]*)\)", text, re.M)}


def advertised_commands(text: str) -> list[str]:
    """Commands the canonical Runtime section advertises via `./run.sh <cmd>`."""
    section = text
    start = text.find("### Canonical operator surface")
    if start != -1:
        end = text.find("### Examples", start)
        section = text[start : end if end != -1 else len(text)]
    return sorted({m.group(1) for m in re.finditer(r"\./run\.sh ([a-z][a-z0-9-]*)", section)})


def check(skill_text: str, run_text: str) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []

    def fail(rule: str, detail: str, offending: str = "") -> None:
        row = {"rule": rule, "detail": detail}
        if offending:
            row["offending"] = offending
        problems.append(row)

    fm = frontmatter(skill_text)
    for key in REQUIRED_FRONTMATTER:
        if key not in fm:
            fail("frontmatter_key_missing", f"required frontmatter key {key!r} absent", key)

    known = run_sh_commands(run_text)
    for cmd in advertised_commands(skill_text):
        if cmd not in known:
            fail(
                "advertised_command_not_in_run_sh",
                f"canonical Runtime advertises './run.sh {cmd}' but run.sh has no such command",
                cmd,
            )

    if skill_text.count("```") % 2 != 0:
        fail("unbalanced_code_fences", f"odd number of ``` fences ({skill_text.count('```')})")

    for target in re.findall(r"\]\((?!http|#)([^)]+)\)", skill_text):
        if not (ROOT / target.split("#")[0]).exists():
            fail("broken_relative_link", f"link target does not exist: {target}", target)

    if "CURRENT_STATUS.json" not in skill_text:
        fail("no_status_pointer", "contract must point at CURRENT_STATUS.json for current status")

    low = skill_text.lower()
    for marker in MUTABLE_MARKERS:
        if marker.lower() in low:
            fail(
                "mutable_status_in_contract",
                f"mutable execution marker present as a contract claim: {marker!r}",
                marker,
            )

    if not any(tok in low for tok in GENERIC_LANE_TOKENS):
        fail("generic_lane_absent", "the generic dream-packet lane is not represented")
    if not any(tok in low for tok in CONTINUITY_LANE_TOKENS):
        fail("continuity_lane_absent", "the Embry continuity lane is not represented")
    if "continuity lane is under active development" not in low and "not complete" not in low:
        fail(
            "continuity_lane_overclaimed",
            "the continuity lane must not be presented as complete",
        )

    if not any(tok in low for tok in EXTERNAL_EVAL_TOKENS):
        fail("speaker_ownership_unstated", "audio-scoring ownership is not stated")
    elif "consumes" not in low:
        fail(
            "speaker_ownership_wrong",
            "contract must say Persona Dream CONSUMES a recognition receipt from the evaluator",
        )

    return problems


def run(args: argparse.Namespace) -> dict[str, Any]:
    skill_text = args.skill.read_text(encoding="utf-8") if args.skill.is_file() else ""
    run_text = args.run_sh.read_text(encoding="utf-8") if args.run_sh.is_file() else ""
    problems: list[dict[str, Any]] = []
    if not skill_text:
        problems.append({"rule": "skill_missing", "detail": f"{args.skill} not readable"})
    if not run_text:
        problems.append({"rule": "run_sh_missing", "detail": f"{args.run_sh} not readable"})
    if skill_text and run_text:
        problems = check(skill_text, run_text)

    receipt = {
        "schema": "persona_dream.skill_contract_check.v1",
        "created_at": utc_now(),
        "status": "PASS_SKILL_CONTRACT" if not problems else "BLOCKED_SKILL_CONTRACT",
        "mocked": False,
        "live": False,
        "skill": str(args.skill),
        "advertised_commands": advertised_commands(skill_text) if skill_text else [],
        "problems": problems,
        "problem_count": len(problems),
        "claims": {
            "proves": [
                "SKILL.md advertises only real run.sh commands, carries no mutable "
                "execution status, points at CURRENT_STATUS.json, and states both lanes"
            ]
            if not problems
            else [],
            "does_not_prove": [
                "that the prose is accurate",
                "that the commands behave correctly",
                "anything about sections outside the checked properties",
            ],
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=SKILL)
    parser.add_argument("--run-sh", type=Path, default=RUN_SH)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    receipt = run(args)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"skill contract: {receipt['status']}")
        for row in receipt["problems"]:
            print(f"  {row['rule']}: {row['detail']}")
        if not receipt["problems"]:
            print(
                f"  {len(receipt['advertised_commands'])} advertised commands checked, "
                "0 problems"
            )
    return 1 if receipt["problems"] and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
