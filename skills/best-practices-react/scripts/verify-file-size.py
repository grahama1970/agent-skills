#!/usr/bin/env python3
"""Fail when a source file grows past the ceiling for what it contains.

This skill already calls a large page monolith wrong, but gave no number, so
nothing failed until a real component reached 14,767 lines. A ceiling only
enforces modularity if it is low enough to fire: measured over a 99-file React
surface, the median module was 56-192 lines, and a limit of 800 flagged 2 files
out of 99.

Two ceilings, because the kinds fail differently. Logic files -- components,
hooks, helpers -- are capped at 400, because size there means branching and
state. Pure data files -- style maps, token tables, fixtures -- are capped at
800, because a long lookup table is reviewable by scanning and splitting it adds
imports without reducing risk.

Data files are detected, not declared, so nobody can dodge the lower ceiling by
renaming a component. A file counts as data only when it has no control flow, no
JSX, and no function bodies.

Exit 1 on violation. Intended for CI and for the definition of done on any UX
task, alongside verify-data-qid.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LOGIC_CEILING = 400
DATA_CEILING = 800

#: Anything that branches, loops, or renders. A file containing none of these is
#: a lookup table however it is named.
CONTROL_FLOW = re.compile(
    r"""^\s*(if|for|while|switch|try)\b        # statements
      | \breturn\s*\(                          # returns of expressions
      | =>\s*\{                                # function bodies
      | \bfunction\b                           # declarations
      | \bclass\b
      | <[A-Z][A-Za-z0-9]*[\s/>]               # JSX elements
      | \buse[A-Z]\w*\(                        # hook calls
    """,
    re.M | re.X,
)

ALLOWLIST_NAME = ".file-size-allowlist"


def is_data_file(text: str) -> bool:
    """True when the file is a lookup table rather than logic."""
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
    return not CONTROL_FLOW.search(stripped)


def load_allowlist(root: Path) -> dict[str, int]:
    """Known violations: path -> the size recorded when it was allowlisted.

    An entry is a debt marker, not an exemption. The file may stay at its
    recorded size; growing past it fails, so debt cannot quietly increase.
    """
    path = root / ALLOWLIST_NAME
    if not path.is_file():
        return {}
    out: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, size = line.partition(":")
        out[name.strip()] = int(size) if size.strip().isdigit() else 0
    return out


def scan(root: Path, logic: int, data: int) -> dict:
    allow = load_allowlist(root)
    rows: list[dict] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"} or not path.is_file():
            continue
        if any(part in {"node_modules", "dist", "build", ".next"} for part in path.parts):
            continue
        if path.name.endswith((".d.ts", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        count = len(text.splitlines())
        kind = "data" if is_data_file(text) else "logic"
        ceiling = data if kind == "data" else logic
        rel = str(path.relative_to(root))
        allowed = allow.get(rel)
        over = count > ceiling
        # Allowlisted files may hold their recorded size, never exceed it.
        status = "ok"
        if over:
            status = "over" if allowed is None else ("grew" if count > allowed else "allowlisted")
        rows.append({"file": rel, "lines": count, "kind": kind,
                     "ceiling": ceiling, "status": status,
                     "allowlisted_at": allowed})
    failures = [r for r in rows if r["status"] in {"over", "grew"}]
    return {
        "schema": "best_practices_react.file_size_report.v1",
        "root": str(root),
        "ceilings": {"logic": logic, "data": data},
        "files": len(rows),
        "violations": failures,
        "allowlisted": [r for r in rows if r["status"] == "allowlisted"],
        "status": "PASS_FILE_SIZE" if not failures else "FAIL_FILE_SIZE",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path, nargs="?", default=Path("src"))
    ap.add_argument("--logic-ceiling", type=int, default=LOGIC_CEILING)
    ap.add_argument("--data-ceiling", type=int, default=DATA_CEILING)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2

    report = scan(args.root, args.logic_ceiling, args.data_ceiling)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['status']}  {report['files']} files  "
              f"(logic<={report['ceilings']['logic']}, data<={report['ceilings']['data']})")
        for r in report["allowlisted"]:
            print(f"  allowlisted  {r['lines']:>5}  {r['file']}")
        for r in report["violations"]:
            why = "grew past its allowlisted size" if r["status"] == "grew" else f"over the {r['kind']} ceiling"
            print(f"  FAIL         {r['lines']:>5}  {r['file']}  ({why} {r['ceiling']})")
        if report["violations"]:
            print("\nSplit the file, or record it in .file-size-allowlist as debt.")
            print("An allowlist entry pins the current size: the file may not grow further.")
    return 0 if not report["violations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
