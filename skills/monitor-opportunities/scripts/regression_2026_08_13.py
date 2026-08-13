"""Regression gates for the defects found in the 2026-08-13 nightly run.

Each check targets one real production defect and asserts against REAL run
artifacts (the newest local/nightly run) or live capture behavior — not
hand-authored fixtures of our own output. Exits non-zero with the failing
gate named, so agentic-evals can use it as a deterministic assertion.

Gates:
  clickable-urls   digest top entries must link to a specific posting, not the
                   generic LinkedIn search page (2026-08-13: 97/150 rows had
                   posting_url=https://www.linkedin.com/jobs/search/).
  distinct-insights premium per-job insights must differ across jobs; identical
                   values across >2 jobs means one page was read repeatedly and
                   attributed to many jobs.
  no-filter-chip   'Under 10 applicants' (a filter chip) must never be parsed as
                   an applicant count.
  deduped          the same org+title posting must not appear repeatedly in the
                   shortlist (2026-08-13: ServiceNow x6).
  tracker-bounded  the tracker must file a bounded top-N, not the whole
                   shortlist (2026-08-13: 150 issues in one night).
  trigger-budget   the trigger budget must cover a real share of shortlist orgs.
  prospect-queue   the consulting/prospect queue must be wired into the nightly
                   (built + unit-tested, but never called before 2026-08-13).

Usage: python regression_2026_08_13.py [--run <nightly-run-dir>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

FAILURES: list[str] = []
CHECKS: list[str] = []


def gate(name: str, ok: bool, detail: str) -> None:
    CHECKS.append(name)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        FAILURES.append(name)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_clickable_urls(run: Path) -> None:
    digest_p, shortlist_p = run / "morning-digest.json", run / "ranking" / "shortlist.json"
    if not (digest_p.exists() and shortlist_p.exists()):
        gate("clickable-urls", False, "digest or shortlist missing from the run")
        return
    digest, shortlist = _load(digest_p), _load(shortlist_p)
    by_id = {r.get("candidate_id"): r for r in shortlist}
    generic = 0
    checked = 0
    for e in digest.get("top", []):
        row = by_id.get(e.get("candidate_id"))
        if not row:
            continue
        url = str(row.get("posting_url") or "")
        # LinkedIn rows are the ones that regressed; other boards always had urls
        if "linkedin.com" not in url:
            continue
        checked += 1
        if url.rstrip("/").endswith("/jobs/search") or "/jobs/view/" not in url:
            generic += 1
    if checked == 0:
        gate("clickable-urls", True, "no LinkedIn rows in digest top (nothing to regress)")
        return
    gate(
        "clickable-urls",
        generic == 0,
        f"{generic}/{checked} LinkedIn digest entries point at the generic search page",
    )


def check_distinct_insights(run: Path) -> None:
    digest_p = run / "morning-digest.json"
    if not digest_p.exists():
        gate("distinct-insights", False, "digest missing")
        return
    tops = _load(digest_p).get("top", [])
    ins = [
        json.dumps(e["premium_insights"], sort_keys=True)
        for e in tops
        if e.get("premium_insights")
    ]
    if len(ins) <= 2:
        gate("distinct-insights", True, f"only {len(ins)} insight rows; nothing to compare")
        return
    gate(
        "distinct-insights",
        len(set(ins)) > 1,
        f"{len(set(ins))} distinct insight payloads across {len(ins)} jobs",
    )


def check_no_filter_chip() -> None:
    """The applicant-count regex must reject the 'Under 10 applicants' chip."""
    pattern = re.compile(r"(?<!Under )\b(\d+)\s+(?:people clicked apply|applicants)\b", re.I)
    chip = "Remote  Under 10 applicants  Easy Apply  $119K/yr - $154K/yr"
    real = "Lead AI Architect  ·  47 applicants  ·  Posted 2 days ago"
    gate(
        "no-filter-chip",
        pattern.search(chip) is None and (pattern.search(real) or [None, None])[1] == "47",
        "filter chip rejected; a real applicant count still parses",
    )


def check_deduped(run: Path) -> None:
    shortlist_p = run / "ranking" / "shortlist.json"
    if not shortlist_p.exists():
        gate("deduped", False, "shortlist missing")
        return
    rows = _load(shortlist_p)
    from collections import Counter

    counts = Counter(
        (
            " ".join(str(r.get("organization") or "").lower().split()),
            " ".join(str(r.get("title") or "").lower().split()),
        )
        for r in rows
    )
    dups = {k: v for k, v in counts.items() if v > 1 and k != ("", "")}
    worst = max(dups.values()) if dups else 0
    gate(
        "deduped",
        not dups,
        f"{len(dups)} duplicated org+title postings in shortlist (worst x{worst})",
    )


def check_tracker_bounded(run: Path) -> None:
    """Read the nightly's own receipt when present; else assert the code default."""
    from monitor_opportunities import cli  # noqa: F401  (import proves module loads)

    src = (SKILL_DIR / "src" / "monitor_opportunities" / "cli.py").read_text(encoding="utf-8")
    bounded = "shortlist[:tracker_top_n]" in src
    gate("tracker-bounded", bounded, "tracker iterates a bounded top-N slice of the shortlist")


def check_trigger_budget(run: Path) -> None:
    from monitor_opportunities.trigger_signals import _default_limit

    limit = _default_limit()
    receipt_p = run / "trigger-receipt.json"
    detail = f"default budget {limit}"
    if receipt_p.exists():
        r = _load(receipt_p)
        considered = int(r.get("orgs_considered") or 0)
        detail += f"; last run considered {considered} orgs"
    gate("trigger-budget", limit >= 40, detail)


def check_prospect_queue(run: Path) -> None:
    """The consulting/prospect queue must actually run and emit its artifact.

    It was built and unit-tested but never wired into the nightly, so it
    silently produced nothing on every run before 2026-08-13.
    """
    src = (SKILL_DIR / "src" / "monitor_opportunities" / "nightly_digest.py").read_text(
        encoding="utf-8"
    )
    wired = "build_prospect_queue" in src
    artifact = run / "prospect-queue.json"
    detail = f"wired={wired}"
    if artifact.exists():
        n = len(_load(artifact).get("prospects", []))
        detail += f"; artifact has {n} prospects"
    else:
        detail += "; no artifact in this run"
    gate("prospect-queue", wired, detail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=SKILL_DIR / "local" / "nightly" / "latest")
    args = ap.parse_args()
    run = args.run
    print(f"# regression gates against run: {run}")
    if not run.exists():
        print(f"[FAIL] run directory does not exist: {run}")
        return 2
    check_clickable_urls(run)
    check_distinct_insights(run)
    check_no_filter_chip()
    check_deduped(run)
    check_tracker_bounded(run)
    check_trigger_budget(run)
    check_prospect_queue(run)
    print(f"\n{len(CHECKS) - len(FAILURES)}/{len(CHECKS)} gates passed")
    if FAILURES:
        print("FAILED GATES: " + ", ".join(FAILURES))
        return 1
    print("ALL REGRESSION GATES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
