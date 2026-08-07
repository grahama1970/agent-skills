"""Real-world end-to-end evaluation for monitor-opportunities.

Runs the LIVE nightly (real surf browser-capture of SAM.gov, real sweep of the
live Greenhouse/Ashby/DARPA boards, real memory writes) and asserts real-world
outcomes — not fixture stubs. Exits 0 only if every real assertion holds; prints
FAIL with the exact failing check otherwise.

This needs the real environment: Chrome open (surf), network access to the live
boards, and the memory service on :8601. That is the point — it proves the skill
works against the real world, and honestly fails when the environment is not
there.

Usage: python3 e2e_eval.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_DIR / "run.sh"
MEMORY_URL = "http://127.0.0.1:8601"

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

    # 1. Run the LIVE nightly (real SAM browser capture + real sweep + real memory sync).
    proc = subprocess.run(
        [str(RUN_SH), "nightly", "--out", str(out), "--skip-buzz"],
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

    # 3. Real report: real shortlist, and live ATS boards actually returned candidates.
    report = _load(out / "report" / "report.json")
    if len(report.get("opportunities", [])) < MIN_SHORTLIST:
        _fail("shortlist-empty", f"{len(report.get('opportunities', []))} shortlisted (< {MIN_SHORTLIST})")
    receipts = report.get("source_receipts", [])
    sam_website = [r for r in receipts if r.get("source_class") == "sam.gov_website" and r.get("result_status") == "MATCHES"]
    if not sam_website:
        _fail("sam-not-in-run", "no MATCHES sam.gov_website receipt in the run (browser fallback did not feed the run)")
    live_board_candidates = sum(
        int(l.get("candidates_observed", 0)) for l in report.get("lane_coverage", []) if l.get("lane") == "A"
    )
    if live_board_candidates < MIN_LIVE_BOARD_CANDIDATES:
        _fail("live-boards-empty", f"lane A observed only {live_board_candidates} candidates from live boards (< {MIN_LIVE_BOARD_CANDIDATES})")

    # 4. Real memory write: recalling the run's opportunities returns them.
    q = report["opportunities"][0]
    query = f"{q['title']} {q['organization']}"
    body = json.dumps({"q": query, "collections": ["morning_opportunities"], "k": 5}).encode()
    req = urllib.request.Request(f"{MEMORY_URL}/recall", data=body, headers={"Content-Type": "application/json"})
    try:
        recall = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except Exception as exc:  # noqa: BLE001 - memory service down is a real E2E failure
        _fail("memory-recall-error", f"recall failed: {exc}")
    if not recall.get("items"):
        _fail("memory-empty", f"recall for {query!r} returned nothing from morning_opportunities")

    print(
        "E2E PASS: "
        f"sam_website_opps={sam.get('opportunities_captured')} "
        f"shortlist={len(report['opportunities'])} "
        f"live_board_candidates={live_board_candidates} "
        f"memory_recall_hits={len(recall['items'])} "
        f"run={out}"
    )


if __name__ == "__main__":
    main()
