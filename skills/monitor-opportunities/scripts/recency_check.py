"""Real-logic recency check: the production rank() drops >2-week-old postings.

Not a stub — builds mixed-age candidates and runs the real
monitor_opportunities.ranking.rank pipeline, asserting the stale one is
rejected as REJECT_STALE_AGE and the recent one is admitted. Fast (no network),
but exercises the actual eligibility code the nightly uses.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from monitor_opportunities.ranking import rank


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()


def _candidate(cid: str, days_ago: float) -> dict:
    return {
        "candidate_id": cid,
        "lane": "A",
        "workplace_type": "REMOTE",
        "title": f"Staff AI Engineer {cid}",
        "organization": "Acme",
        "published_at": _iso(days_ago),
        "fit_score": 0.9,
        "source_receipt_id": f"receipt-{cid}",
    }


def main() -> None:
    fresh = _candidate("fresh", 2)
    stale = _candidate("stale", 30)
    with tempfile.TemporaryDirectory(prefix="recency-check-") as tmp:
        disc = Path(tmp) / "discovery"
        disc.mkdir(parents=True)
        (disc / "candidates.jsonl").write_text(
            json.dumps(fresh) + "\n" + json.dumps(stale) + "\n", encoding="utf-8"
        )
        out = Path(tmp) / "ranking"
        rank(disc, 10, out)
        shortlist = json.loads((out / "shortlist.json").read_text(encoding="utf-8"))
        rejections = json.loads((out / "rejections.json").read_text(encoding="utf-8"))

    ids = {c["candidate_id"] for c in shortlist}
    stale_rej = [r for r in rejections if r["candidate_id"] == "stale" and r.get("eligibility_state") == "REJECT_STALE_AGE"]
    if "fresh" not in ids:
        print("RECENCY FAIL: a 2-day-old posting was not admitted")
        sys.exit(1)
    if "stale" in ids:
        print("RECENCY FAIL: a 30-day-old posting leaked into the shortlist")
        sys.exit(1)
    if not stale_rej:
        print(f"RECENCY FAIL: stale posting not rejected as REJECT_STALE_AGE; rejections={rejections}")
        sys.exit(1)
    print("RECENCY OK: fresh (2d) admitted, stale (30d) rejected as REJECT_STALE_AGE")


if __name__ == "__main__":
    main()
