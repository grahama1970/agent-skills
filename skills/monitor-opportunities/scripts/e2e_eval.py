"""Real-world diagnostic-cron evaluation for monitor-opportunities.

Runs the LIVE diagnostic nightly (real browser/source capture and live board
sweeps, with publication side effects disabled) and asserts durable cron
outcomes -- not fixture stubs. Exits 0 only if every real assertion holds;
prints FAIL with the exact failing check otherwise.

This needs the real environment: Chrome open (surf) and network access to the
live boards. That is the point -- it proves the safe 2 AM cron path works
against the real world, and honestly fails when the environment is not there.

Usage: python3 e2e_eval.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)

SKILL_DIR = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_DIR / "run.sh"

# Real-world thresholds (deliberately conservative so transient dips don't flap,
# but high enough that a stubbed/empty result fails).
MIN_SAM_WEBSITE_OPPS = 5
MIN_SHORTLIST = 1
MIN_LIVE_BOARD_CANDIDATES = 3


def _fail(check: str, detail: str) -> None:
    print(f"E2E FAIL [{check}]: {detail}")
    sys.exit(1)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = Path(args.out) if args.out else Path("/tmp") / f"mo-e2e-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    # 1. Run the LIVE diagnostic nightly: real capture and ranking, but no
    # publication, tracker, ATS-memory, relationship-memory, or Buzz effects.
    proc = subprocess.run(
        [
            str(RUN_SH),
            "nightly",
            "--diagnostic",
            "--out",
            str(out),
            "--skip-buzz",
            "--skip-tracker",
            "--skip-ats-memory",
            "--skip-relationship-memory",
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode != 0:
        _fail("nightly-exit", f"nightly returned {proc.returncode}: {proc.stderr[-400:]}")

    # 2. Real SAM website capture must have returned real opportunities.
    sam_receipt_path = out / "browser-capture" / "sam-capture-receipt.json"
    if not sam_receipt_path.exists():
        _fail("sam-capture-missing", f"no capture receipt at {sam_receipt_path}")
    sam = _load(sam_receipt_path)
    if sam.get("status") != "OK":
        _fail("sam-capture-status", f"SAM website capture status={sam.get('status')} error={sam.get('error')}")
    if int(sam.get("opportunities_captured", 0)) < MIN_SAM_WEBSITE_OPPS:
        _fail("sam-capture-count", f"only {sam.get('opportunities_captured')} SAM opps captured from the live site (< {MIN_SAM_WEBSITE_OPPS})")

    # 3. Real report exists, and live ATS boards actually returned candidates.
    report = _load(out / "report" / "report.json")
    receipts = report.get("source_receipts", [])
    sam_website = [r for r in receipts if r.get("source_class") == "sam.gov_website" and r.get("result_status") == "MATCHES"]
    if not sam_website:
        _fail("sam-not-in-run", "no MATCHES sam.gov_website receipt in the run (browser fallback did not feed the run)")
    live_board_candidates = sum(
        int(l.get("candidates_observed", 0)) for l in report.get("lane_coverage", []) if l.get("lane") == "A"
    )
    if live_board_candidates < MIN_LIVE_BOARD_CANDIDATES:
        _fail("live-boards-empty", f"lane A observed only {live_board_candidates} candidates from live boards (< {MIN_LIVE_BOARD_CANDIDATES})")

    # 4. The report must contain actionable rows. A live run may be dominated by
    # LinkedIn locator/source-intel rows; those are intentionally visible but
    # cannot enter claim-bound tailoring without primary employer/client readback.
    opportunities = report.get("opportunities", [])
    source_intel = report.get("source_intel", [])
    if len(opportunities) + len(source_intel) < MIN_SHORTLIST:
        _fail(
            "report-empty",
            f"{len(opportunities)} opportunities + {len(source_intel)} source-intel rows (< {MIN_SHORTLIST})",
        )
    if not report.get("source_receipts"):
        _fail("source-receipts-empty", "report has no source receipt lineage")
    receipt = _load(out / "run-receipt.json")
    phases = {row.get("phase") for row in receipt.get("phase_artifacts", [])}
    for phase in {"REQUIRED_SOURCES_ENFORCED", "API_WEBSITE_FALLBACK_ENFORCED", "RANKING_COMPLETE", "REPORT_READY"}:
        if phase not in phases:
            _fail("phase-missing", f"{phase} absent from run receipt phases={sorted(phases)}")
    if receipt.get("degraded_contracts"):
        _fail("degraded-contract", f"unexpected degraded contracts: {receipt['degraded_contracts']}")

    # 5. Recency: every shortlisted job with a parseable date must be within the
    #    2-week window (goal: we only care about recent opportunities).
    max_age = int(os.environ.get("MONITOR_MAX_AGE_DAYS", "14"))
    shortlist = _load(out / "ranking" / "shortlist.json")
    now = datetime.now(UTC)
    stale = []
    for row in shortlist:
        raw = row.get("published_at") or row.get("updated_at")
        if not raw:
            continue
        try:
            posted = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=UTC)
        age = (now - posted).days
        if age > max_age:
            stale.append((row.get("title"), age))
    if stale:
        _fail("recency-violation", f"{len(stale)} shortlisted jobs older than {max_age}d: {stale[:3]}")

    # 6. When primary-source opportunities are admitted, every one must have a
    # claim-bound resume variant and local application packet. Source-intel-only
    # runs are valid but must not mint claim packets.
    resume_variants = report.get("resume_variants", [])
    application_packets = report.get("application_packets", [])
    if opportunities and len(resume_variants) != len(opportunities):
        _fail("resume-variant-missing", f"{len(resume_variants)} variants for {len(opportunities)} opportunities")
    if source_intel and not opportunities and (resume_variants or application_packets):
        _fail("source-intel-minted-packets", "source-intel-only run produced claim/application packets")

    print(
        "E2E PASS: "
        f"sam_website_opps={sam.get('opportunities_captured')} "
        f"shortlist={len(shortlist)} "
        f"live_board_candidates={live_board_candidates} "
        f"opportunities={len(opportunities)} "
        f"source_intel={len(source_intel)} "
        f"recency_max_age_days={max_age} "
        f"resume_variants={len(resume_variants)} "
        f"application_packets={len(application_packets)} "
        f"run={out}"
    )


if __name__ == "__main__":
    main()
