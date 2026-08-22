#!/usr/bin/env python3
"""Regression guard: the self-heal remediation path must reach a fileable plan.

Incident (2026-08-22): the self-heal cron detected a red guard but filed NO
ticket. Three wiring defects, all silent, each aborting `iterate_fn` before
`apply_plan`:
  1. the category_map category_id was 'agentic-evals:monitor-opportunities:...'
     but validate_category_map requires the repo slug
     'agentic-evals:agent-skills:...' (v1 same-repo-only) -> CategoryMapError;
  2. phart-dag-chart's pyproject had an impossible requires-python
     ('>=3.14,<3.13') so render_and_validate_dag returned ok=False -> Exit(1);
  3. --max-iterations 1 stops before the first iterate_fn (files need >=2).

This guard reproduces the exact plan-build path the cron runs, against a
SYNTHETIC red report (so it exercises even when every live guard is green), and
fails (exit 1) if the category map does not validate, the DAG does not validate,
or the plan does not reach a fileable step. It does NOT touch GitHub.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
AGENTIC = SKILL_DIR.parent / "agentic-evals" / "src"
sys.path.insert(0, str(AGENTIC))

import remediation as rem  # noqa: E402

CATEGORY_MAP = SKILL_DIR / "fixtures" / "category_map.json"


def main() -> int:
    cmap = rem.load_category_map(CATEGORY_MAP)
    # The single category the self-heal fixture owns.
    cid = next(iter(cmap["categories"].values()))["category_id"]

    # Synthetic COMPLETE red report: one failing case owned by this category.
    categorized = {
        "active_category_ids": [cid],
        "cases_by_category": {cid: ["synthetic-red-guard"]},
    }

    failures: list[str] = []
    try:
        induced = rem.validate_category_map(cmap, active_category_ids={cid})
    except rem.CategoryMapError as exc:
        print(f"SELF_HEAL_CATEGORY_MAP_INVALID: {exc}", file=sys.stderr)
        return 1

    chart = rem.render_and_validate_dag(rem.active_category_dag(induced, cmap))
    if not chart["ok"]:
        failures.append(
            "SELF_HEAL_DAG_INVALID: phart validate failed (env or DAG). "
            f"rc={chart.get('validate_returncode')} err={chart.get('stderr','')[:160]}"
        )

    plan = rem.plan_remediation(categorized, induced, cmap, open_labels=set())
    if not plan["to_file"]:
        failures.append(
            "SELF_HEAL_NO_FILEABLE_STEP: a red category produced no ticket to file "
            f"(skipped={[s['category_id'] for s in plan['skipped_open']]})"
        )

    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    print(f"SELF_HEAL_FILES_TICKET_OK: red category {cid!r} validates and reaches a fileable plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
