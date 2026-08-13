"""Pre-publish truth contract: nothing untrustworthy becomes human-visible.

Recommended as P0 by the webgpt eval-coverage review (2026-08-13): the existing
suite "catches several defects AFTER a run artifact exists; the next layer must
prevent an untrustworthy artifact from becoming human-visible."

Every check below is a property of THIS run's own artifacts, verified against an
independent source (the shortlist, the ranking receipt, the trigger receipt) —
never by asking the digest to agree with itself.

Invariants (webgpt's mandatory list, restricted to what this run can prove):
  unique-canonical   at most `max_rows` rows, no duplicate posting identity
                     (never REQUIRE a full 8 — padding is a defect)
  current-run        every digest row exists in this run's shortlist
  frozen-selection   digest membership is a subset of the ranked shortlist and
                     ordering is monotonically non-increasing by score
  eligible           every row carries an ELIGIBLE_ eligibility state
  fresh              a parseable published_at is inside the recency window
  resolvable-url     every row links to a specific posting, not a search page
  evidence-backed    displayed facts have provenance: premium_insights only on
                     rows with a real posting URL; a nonzero trigger driver
                     requires trigger evidence
  typed-missingness  an unavailable signal is never presented as an observed
                     zero (webgpt P0 #05): if the trigger pass could not run,
                     the digest must not imply triggers were observed-absent

Returns (ok, report). The caller fails the run closed on ok=False.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

VIOLATION_SCHEMA = "monitor_opportunities.prepublish_contract.v1"


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _posting_identity(row: dict[str, Any]) -> str:
    org = " ".join(str(row.get("organization") or "").lower().split())
    title = " ".join(str(row.get("title") or "").lower().split())
    return f"{org}|{title}"


def validate(
    digest: dict[str, Any],
    shortlist: list[dict[str, Any]],
    trigger_receipt: dict[str, Any] | None = None,
    max_rows: int = 8,
    max_age_days: int = 14,
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Check the digest against this run's own evidence. Pure; no I/O."""
    now = now or datetime.now(UTC)
    top = list(digest.get("top") or [])
    by_id = {r.get("candidate_id"): r for r in shortlist}
    violations: list[dict[str, Any]] = []

    def bad(rule: str, detail: str, row: dict[str, Any] | None = None) -> None:
        violations.append({
            "rule": rule,
            "detail": detail,
            "candidate_id": (row or {}).get("candidate_id"),
            "organization": (row or {}).get("organization"),
        })

    # unique-canonical — over-length or duplicated rows mean padding/dedup failure
    if len(top) > max_rows:
        bad("unique-canonical", f"{len(top)} rows exceeds max {max_rows}")
    seen: dict[str, int] = {}
    for e in top:
        key = _posting_identity(e)
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            bad("unique-canonical", f"posting appears {count}x: {key}")

    prior_score = None
    for e in top:
        row = by_id.get(e.get("candidate_id"))
        # current-run — a row not in this run's shortlist is stale or invented
        if row is None:
            bad("current-run", "digest row is not in this run's shortlist", e)
            continue
        # eligible
        state = str(row.get("eligibility_state") or "")
        if not state.startswith("ELIGIBLE_"):
            bad("eligible", f"eligibility_state={state or 'MISSING'}", e)
        # fresh (only when a date is parseable; missing dates are not failures)
        published = _parse_dt(row.get("published_at"))
        if published is not None and published < now - timedelta(days=max_age_days):
            age = (now - published).days
            bad("fresh", f"published {age}d ago (> {max_age_days}d window)", e)
        # resolvable-url — a generic board search page is not an opportunity link
        url = str(row.get("posting_url") or "")
        if not url:
            bad("resolvable-url", "no posting_url", e)
        elif url.rstrip("/").endswith("/jobs/search") or url.rstrip("/").endswith("/search"):
            bad("resolvable-url", f"links to a search page, not a posting: {url}", e)
        # evidence-backed — per-job facts require a per-job source
        if e.get("premium_insights") and "/jobs/view/" not in url and "linkedin.com" in url:
            bad("evidence-backed", "premium_insights present without a per-job URL", e)
        drivers = e.get("drivers") or {}
        if float(drivers.get("trigger") or 0) > 0 and not e.get("trigger_evidence"):
            bad("evidence-backed", "nonzero trigger driver with no trigger_evidence", e)
        # frozen-selection ordering
        score = float(e.get("response_score") or 0)
        if prior_score is not None and score > prior_score + 1e-9:
            bad("frozen-selection", f"score {score} follows lower score {prior_score}", e)
        prior_score = score

    # typed-missingness — an unavailable signal must not read as observed-absent
    wired = digest.get("signals_wired") or {}
    if trigger_receipt is not None:
        searched = int(trigger_receipt.get("orgs_searched") or 0)
        unavailable = trigger_receipt.get("error") or (
            searched == 0 and not trigger_receipt.get("brave_search_available", True)
        )
        if unavailable and wired.get("trigger") is True:
            bad(
                "typed-missingness",
                "signals_wired.trigger=true but the trigger pass was unavailable; "
                "an unavailable signal must not be presented as observed",
            )

    report = {
        "schema": VIOLATION_SCHEMA,
        "rows_checked": len(top),
        "shortlist_rows": len(shortlist),
        "max_rows": max_rows,
        "max_age_days": max_age_days,
        "violations": violations,
        "ok": not violations,
    }
    return not violations, report


def validate_run(run_dir: Path, **kwargs: Any) -> tuple[bool, dict[str, Any]]:
    """Validate a nightly run directory's digest against its own artifacts."""
    digest_p = run_dir / "morning-digest.json"
    shortlist_p = run_dir / "ranking" / "shortlist.json"
    if not digest_p.exists() or not shortlist_p.exists():
        return False, {
            "schema": VIOLATION_SCHEMA,
            "ok": False,
            "violations": [{"rule": "artifacts", "detail": "digest or shortlist missing"}],
        }
    trigger_p = run_dir / "trigger-receipt.json"
    trigger = None
    if trigger_p.exists():
        try:
            trigger = json.loads(trigger_p.read_text(encoding="utf-8"))
        except ValueError:
            trigger = None
    return validate(
        json.loads(digest_p.read_text(encoding="utf-8")),
        json.loads(shortlist_p.read_text(encoding="utf-8")),
        trigger_receipt=trigger,
        **kwargs,
    )
