#!/usr/bin/env python3
"""Turn an open blocker into one singular, provable MVP fix.

Grounds the blocker with /brave-search, competes it across isolated browser
models (which run their own web search), and judges the proposals on
singularity plus a proof command that must fail right now.

Dry-run by default: it compiles and prints the packet. `--execute` dispatches
the isolated candidates through Ask's competition path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask import blocker_ledger, mvp_unblock  # noqa: E402

DEFAULT_HANDLERS = ("webgpt", "webclaude")


def _resolve_blocker(target: str | None, failure_code: str | None) -> dict:
    open_ones = blocker_ledger.open_blockers()
    if not open_ones:
        raise SystemExit("no open blockers; nothing to unblock")
    matches = [
        b for b in open_ones
        if (not target or str(b.get("target")) == target)
        and (not failure_code or str(b.get("failure_code")) == failure_code)
    ]
    if not matches:
        raise SystemExit(f"no open blocker matches target={target!r} failure_code={failure_code!r}")
    if len(matches) > 1 and not (target and failure_code):
        listed = "\n".join(f"  {b['target']}  {b['failure_code']}" for b in matches)
        raise SystemExit(f"several open blockers match; name one:\n{listed}")
    # Most-observed first: the wall hit most often is the one in the way.
    return sorted(matches, key=lambda b: int(b.get("observations") or 0), reverse=True)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", default=None)
    ap.add_argument("--failure-code", default=None)
    ap.add_argument("--handler", action="append", default=[],
                    help=f"isolated candidate (default: {', '.join(DEFAULT_HANDLERS)})")
    ap.add_argument("--no-research", action="store_true", help="skip /brave-search grounding")
    ap.add_argument("--execute", action="store_true", help="dispatch the isolated candidates")
    ap.add_argument("--judge", metavar="FILE", action="append", default=[],
                    help="judge an already-collected candidate response file")
    ap.add_argument("--run-proof", action="store_true",
                    help="run each proposal's proof command and require it to fail now")
    ap.add_argument("--cwd", default=str(SKILLS_DIR.parent), help="where to run proof commands")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.judge:
        verdicts = [
            mvp_unblock.judge_candidate(
                Path(path).read_text(encoding="utf-8"),
                handler=Path(path).stem,
                cwd=Path(args.cwd),
                run_proof=args.run_proof,
            )
            for path in args.judge
        ]
        selection = mvp_unblock.select(verdicts)
        print(json.dumps(selection, indent=2) if args.json else _render_selection(selection))
        return 0 if selection["status"] == "SELECTED" else 1

    blocker = _resolve_blocker(args.target, args.failure_code)
    research = (
        {"sources": [], "grounded": False, "queries": [], "searches": []}
        if args.no_research
        else mvp_unblock.research_brief(blocker, skills_dir=SKILLS_DIR)
    )
    packet = mvp_unblock.compile_packet(blocker, research=research)
    handlers = args.handler or list(DEFAULT_HANDLERS)

    if not args.execute:
        if args.json:
            print(json.dumps({"packet": packet, "research": research, "handlers": handlers}, indent=2))
        else:
            print(f"blocker: {packet['target']} / {packet['failure_code']}")
            print(f"grounding: {len(research.get('sources') or [])} source(s) "
                  f"from {len(research.get('queries') or [])} quer(ies)")
            print(f"candidates (isolated): {', '.join(handlers)}\n")
            print(packet["request"])
            print("\nRe-run with --execute to dispatch, or --judge FILE to score responses.")
        return 0

    request_path = SKILL_ROOT / ".ask_artifacts" / "unblock-request.md"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(packet["request"], encoding="utf-8")

    # Two isolated candidates is the floor, not a preference: one "competition"
    # is a single opinion, and best-practices-competition fails closed on it.
    # Caught live -- a one-handler dispatch returned NEEDS_INTERVIEW.
    if len(handlers) < 2:
        raise SystemExit(
            f"compete needs at least 2 isolated candidates; got {handlers}. "
            "One candidate is an opinion, not an outside view."
        )

    # The acceptance bar every candidate is judged against, shared identically.
    immutable_goal = (
        f"Clear the blocker {packet['failure_code']} on {packet['target']} with ONE change "
        "whose proof command fails now and passes after."
    )
    command = [
        str(SKILL_ROOT / "run.sh"), "compete", packet["request"],
        "--repo", "local/agent-skills",
        "--target", f"unblock-{packet['failure_code']}",
        "--immutable-goal", immutable_goal,
        "--criterion", "singular-change-surface",
        "--criterion", "proof-fails-now",
        "--json",
    ]
    for handler in handlers:
        command.extend(["--handler", handler])
    command.append("--execute")

    print(f"dispatching isolated candidates: {', '.join(handlers)}", file=sys.stderr)
    proc = subprocess.run(command, cwd=str(SKILL_ROOT))
    return proc.returncode


def _render_selection(selection: dict) -> str:
    if selection["status"] != "SELECTED":
        lines = [f"NEEDS_ATTENTION: {selection['reason']}", ""]
        for c in selection["candidates"]:
            lines.append(f"  {c['handler'] or 'candidate'}:")
            lines.extend(f"    - {p}" for p in c["problems"])
        return "\n".join(lines)
    winner = selection["winner"]
    fields = winner["fields"]
    return "\n".join([
        f"SELECTED ({winner['handler'] or 'candidate'}) — {selection['reason']}",
        "",
        f"PROBLEM: {fields.get('PROBLEM', '')}",
        f"CHANGE:  {fields.get('CHANGE', '')}",
        f"PROOF:   {fields.get('PROOF_COMMAND', '')}",
        f"WHY:     {fields.get('WHY_THIS_UNBLOCKS', '')}",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
