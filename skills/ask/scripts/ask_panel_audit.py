#!/usr/bin/env python3
"""Audit a finished roundtable/competition run against the best-practices contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask import panel_compliance  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--mode", choices=["roundtable", "compete"], default="roundtable")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = panel_compliance.audit(args.run_dir, mode=args.mode)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        verdict = "COMPLIANT" if report["compliant"] else "VIOLATIONS"
        print(f"{verdict}: {args.mode} at {report['run_dir']}")
        for check in report["checks"]:
            mark = "ok  " if check["compliant"] else "FAIL"
            print(f"  [{mark}] {check['rule']}: {check.get('detail') or ''}")
            if not check["compliant"]:
                print(f"         {check['source']}")
    return 0 if report["compliant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
