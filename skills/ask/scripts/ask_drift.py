#!/usr/bin/env python3
"""Report open blockers and work done beside them instead of on them.

Reads the durable blocker ledger Ask writes at its own choke point, so the
report does not depend on the agent being watched choosing to file it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask import avoidance_drift, blocker_ledger  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("blockers", help="list open blockers")

    check = sub.add_parser("check", help="assess a target against its open blockers")
    check.add_argument("target")
    check.add_argument("--work", action="append", default=[],
                       help="a claim about work done (repeatable); '-' reads stdin")

    ack = sub.add_parser("acknowledge", help="record that a blocker was reported to the human")
    ack.add_argument("target")
    ack.add_argument("failure_code")
    ack.add_argument("--note", default="")

    clear = sub.add_parser("clear", help="close a blocker with live proof")
    clear.add_argument("target")
    clear.add_argument("failure_code")
    clear.add_argument("--live-proof", required=True)

    for parser in (ap, check):
        parser.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    if args.command == "blockers":
        open_ones = blocker_ledger.open_blockers()
        if getattr(args, "json", False):
            print(json.dumps(open_ones, indent=2))
        elif not open_ones:
            print("no open blockers")
        else:
            for b in open_ones:
                mark = "acknowledged" if b.get("acknowledged") else "UNACKNOWLEDGED"
                print(f"  {b['target']}  {b['failure_code']}  seen {b['observations']}x  {mark}")
        return 0

    if args.command == "acknowledge":
        blocker_ledger.acknowledge(target=args.target, failure_code=args.failure_code, note=args.note)
        print(f"acknowledged: {args.target} / {args.failure_code}")
        return 0

    if args.command == "clear":
        try:
            blocker_ledger.clear(
                target=args.target, failure_code=args.failure_code, live_proof=args.live_proof
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"cleared: {args.target} / {args.failure_code}")
        return 0

    work = list(args.work)
    if "-" in work:
        work = [w for w in work if w != "-"] + [sys.stdin.read()]
    verdict = avoidance_drift.assess_target(args.target, work)
    if getattr(args, "json", False):
        print(json.dumps(verdict, indent=2))
    else:
        print(f"{verdict['verdict']}: {verdict['reason']}")
        for b in verdict["open_blockers"]:
            print(f"  open: {b['failure_code']} (seen {b['observations']}x, {b['age_hours']}h)")
        if verdict["next_action"]:
            print(f"\n{verdict['next_action']}")
    return 1 if verdict["verdict"] == avoidance_drift.AVOIDANCE_DRIFT else 0


if __name__ == "__main__":
    raise SystemExit(main())
