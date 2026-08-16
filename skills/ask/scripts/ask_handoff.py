#!/usr/bin/env python3
"""Show the handoff chain for an Ask run: who handed what to whom.

Every node emits a tau.agent_handoff.v1 payload naming its result, its evidence
and the next agent. Until now those were printed to stdout and lost, so there
was no way to answer "where did this run hand off to, and what did it carry"
after the fact. They are written as handoff.json beside each node receipt; this
reads them back in order.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path("/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs")


def latest_run(root: Path) -> Path | None:
    try:
        runs = [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime, default=None)


def chain(run_dir: Path) -> list[dict]:
    out = []
    for path in sorted(run_dir.glob("node-artifacts/*/handoff.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        result = payload.get("result") or {}
        out.append({
            "node": path.parent.name,
            "schema": payload.get("schema"),
            "status": result.get("status"),
            "summary": str(result.get("summary") or "")[:160],
            "next_agent": (payload.get("next_agent") or {}).get("name"),
            "evidence": len(result.get("evidence") or []),
            "artifacts": len((payload.get("context") or {}).get("artifacts") or []),
            "path": str(path),
        })
    # join last: it is the node that hands back to the human
    out.sort(key=lambda r: (r["node"] == "join", r["node"]))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", nargs="?", help="run directory (default: most recent)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    run = Path(args.run_dir) if args.run_dir else latest_run(Path(args.root))
    if not run or not run.is_dir():
        print("no run found", file=sys.stderr)
        return 2

    rows = chain(run)
    if args.json:
        print(json.dumps({"run_dir": str(run), "handoffs": rows}, indent=2))
        return 0 if rows else 1

    print(f"run: {run}")
    if not rows:
        # A run with no handoff.json predates the fix, or every node died before
        # emitting one. Say which, rather than printing nothing.
        print("  no handoff artifacts (run predates handoff persistence, or no node completed)")
        return 1
    for r in rows:
        print(f"  {r['node']:32} {str(r['status']):6} -> {r['next_agent']:12} "
              f"evidence={r['evidence']} artifacts={r['artifacts']}")
        if r["summary"]:
            print(f"      {r['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
