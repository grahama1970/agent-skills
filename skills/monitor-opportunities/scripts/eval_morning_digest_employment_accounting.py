"""Evaluate morning-digest employment selection accounting against a live run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from monitor_opportunities.morning_digest import build_digest

CANONICAL_LIVE_RUN = Path(
    "/home/graham/workspace/experiments/agent-skills/"
    "skills/monitor-opportunities/local/nightly/latest"
)


def _default_run() -> Path:
    env = os.environ.get("MONITOR_OPPORTUNITIES_LIVE_RUN")
    if env:
        return Path(env)
    local_latest = Path(__file__).resolve().parents[1] / "local" / "nightly" / "latest"
    if (local_latest / "report-manifest.json").exists():
        return local_latest
    return CANONICAL_LIVE_RUN


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=_default_run())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest_path = args.run / "report-manifest.json"
    digest_path = args.run / "morning-digest.json"
    manifest = _read_json(manifest_path)
    existing_digest = _read_json(digest_path)

    lane_a = next(
        lane for lane in manifest.get("lane_coverage", [])
        if lane.get("lane") == "A"
    )
    opportunities = list(manifest.get("opportunities") or [])
    source_intel = list(manifest.get("source_intel") or [])
    rebuilt = build_digest(
        opportunities + source_intel,
        top_n=len(existing_digest.get("top") or []) or 8,
    )
    accounting = rebuilt["selection_accounting"]
    employment = accounting["by_type"].get(
        "employment",
        {"input": 0, "included": 0, "excluded": 0},
    )
    employment_rows = [
        row for row in accounting["candidates"]
        if row["opportunity_type"] == "employment"
    ]
    missing_reasons = [
        row for row in employment_rows
        if not row.get("reason_code")
    ]
    invariant_pass = (
        accounting["included"] + accounting["excluded"] == accounting["input"]
        and accounting["unaccounted"] == 0
        and employment["input"] >= int(lane_a.get("candidates_admitted_opportunities") or 0)
        and len(missing_reasons) == 0
    )

    receipt = {
        "schema": "monitor_opportunities.eval.morning_digest_employment_accounting.v1",
        "live": True,
        "mocked": False,
        "source_run": str(args.run),
        "manifest": {
            "lane_a_candidates_admitted": lane_a.get("candidates_admitted"),
            "lane_a_candidates_admitted_opportunities": lane_a.get(
                "candidates_admitted_opportunities"
            ),
            "opportunities": len(opportunities),
            "source_intel": len(source_intel),
        },
        "existing_digest": {
            "has_selection_accounting": "selection_accounting" in existing_digest,
            "top": len(existing_digest.get("top") or []),
            "employment_top": sum(
                1 for row in existing_digest.get("top") or []
                if row.get("opportunity_type") == "employment"
            ),
            "counts": existing_digest.get("counts"),
        },
        "rebuilt_digest": {
            "counts": rebuilt.get("counts"),
            "selection_accounting": accounting,
        },
        "missing_employment_reason_count": len(missing_reasons),
        "invariant_pass": invariant_pass,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")

    if not invariant_pass:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 1

    print(
        "MORNING_DIGEST_EMPLOYMENT_ACCOUNTING_OK "
        f"input={accounting['input']} "
        f"employment_input={employment['input']} "
        f"employment_included={employment['included']} "
        f"employment_excluded={employment['excluded']} "
        f"unaccounted={accounting['unaccounted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
