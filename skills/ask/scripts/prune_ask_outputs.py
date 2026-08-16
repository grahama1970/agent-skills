#!/usr/bin/env python3
"""Reclaim finished Ask DAG output trees. Dry-run by default.

The mechanism existed and nothing ran it -- the same shape of bug as the
browser-window reaper: `run_state.prune_runs` covers runtime runs, but the DAG
output tree grew to 2.2 GB across 332 runs because nothing pruned it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask import prune_outputs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="output root (default: the 12TB ask outputs tree)")
    ap.add_argument("--older-than-days", type=int, default=prune_outputs.DEFAULT_OLDER_THAN_DAYS)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    ap.add_argument("--json", action="store_true", help="emit the JSON receipt only")
    args = ap.parse_args(argv)

    receipt = prune_outputs.prune(
        args.root, older_than_days=args.older_than_days, apply=args.apply
    )

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        mode = "APPLIED" if receipt["applied"] else "DRY-RUN"
        gib = receipt["freed_bytes"] / (1024 ** 3)
        print(
            f"[{mode}] {receipt['removed_count']} finished DAG run(s) "
            f"{'removed' if receipt['applied'] else 'would be removed'}, "
            f"{gib:.2f} GiB; {receipt['kept_count']} kept; {len(receipt['errors'])} error(s)."
        )
        for e in receipt["errors"]:
            print(f"  ERROR  {e['path']}: {e['error']}")
    return 1 if receipt["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
