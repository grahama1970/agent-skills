#!/usr/bin/env python3
"""Executable native lifecycle recovery; never launches a replacement worker."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog import primary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reattach-journal", type=Path)
    args = parser.parse_args()
    if args.reattach_journal:
        result = primary.reattach_and_resume(args.root, args.reattach_journal, apply=args.apply)
    else:
        result = primary.reconcile(args.root) if args.apply else primary.pending(args.root)
    print(json.dumps(result or {"ok": True, "pending": False}, indent=2))
    if args.reattach_journal:
        return 0 if result.get("ok") is True else 1
    if not result:
        return 0
    if result.get("invalid_operations"):
        return 1
    # A live writer means recovery has nothing to do yet. Returning nonzero made
    # the machine-actionable next command look like another failure every tick.
    return 0 if result.get("writer_active") else 1 if result.get("operations") else 0


if __name__ == "__main__":
    raise SystemExit(main())
