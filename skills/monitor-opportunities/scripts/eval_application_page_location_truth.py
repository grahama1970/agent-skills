#!/usr/bin/env python3
"""Regression guard for employer application-page location authority.

Incident (2026-08-26): a LinkedIn top-applicant/Buffalo locator promoted a real
Ashby primary posting whose employer apply page said San Francisco OnSite. The
report displayed San Francisco but ranked it as ELIGIBLE_WNY_ONSITE.

This guard fails if:
  - the live Ashby application page metadata cannot be read;
  - Ashby OnSite + San Francisco is not classified ONSITE_ELSEWHERE;
  - a LinkedIn WNY locator overwrites the primary/apply-page workplace type; or
  - ranking admits that promoted onsite-elsewhere opportunity.
"""

from __future__ import annotations

# The skill source path is injected below so this script can run from agentic-evals.
# ruff: noqa: E402,I001

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "src"))

from monitor_opportunities.browser_capture import _fetch_ashby_application_metadata  # noqa: E402
from monitor_opportunities.discovery import _workplace_type  # noqa: E402
from monitor_opportunities.ranking import _eligibility  # noqa: E402
from monitor_opportunities.readback import resolve_primary_source  # noqa: E402
from monitor_opportunities.util import utc_now  # noqa: E402


COGNITION_APPLY_URL = (
    "https://jobs.ashbyhq.com/cognition/d72d584c-bb11-4b6a-b043-d81425ea884a/application"
)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/monitor-opportunities-application-page-location-proof.json"),
    )
    parser.add_argument("--url", default=COGNITION_APPLY_URL)
    args = parser.parse_args()

    failures: list[str] = []
    metadata = _fetch_ashby_application_metadata(args.url)
    if not metadata:
        failures.append("ASHBY_APPLICATION_METADATA_MISSING")
        metadata = {}

    location_display = str(metadata.get("location_display") or "")
    provider_workplace = str(metadata.get("provider_workplace_type") or "")
    app_workplace = str(metadata.get("workplace_type") or "")
    board_workplace = _workplace_type("San Francisco", "", "OnSite")

    if "San Francisco" not in location_display:
        failures.append(f"APPLICATION_LOCATION_NOT_SAN_FRANCISCO: {location_display!r}")
    if "Buffalo" in location_display:
        failures.append(f"APPLICATION_LOCATION_FALSE_BUFFALO: {location_display!r}")
    if provider_workplace != "OnSite":
        failures.append(f"APPLICATION_PROVIDER_WORKPLACE_NOT_ONSITE: {provider_workplace!r}")
    if app_workplace != "ONSITE_ELSEWHERE":
        failures.append(f"APPLICATION_WORKPLACE_WRONG: {app_workplace!r}")
    if board_workplace != "ONSITE_ELSEWHERE":
        failures.append(f"ASHBY_BOARD_WORKPLACE_WRONG: {board_workplace!r}")

    locator = {
        "candidate_id": "candidate:a:linkedin:cognition-location-regression",
        "lane": "A",
        "organization": "Cognition",
        "title": "Deployed Engineer",
        "workplace_type": "WNY_ONSITE",
        "source_provider": "ops_linkedin_authorized_read_only",
        "primary_evidence_url": "https://www.linkedin.com/jobs/view/4347927062/",
        "top_candidate_evidence": True,
        "source_receipt_id": "src:a:linkedin:test",
    }
    primary = {
        "candidate_id": "candidate:a:ashby:cognition-location-regression",
        "lane": "A",
        "organization": "Cognition",
        "title": "Deployed Engineer",
        "location_display": location_display or "San Francisco",
        "workplace_type": app_workplace or "ONSITE_ELSEWHERE",
        "source_provider": "ashby",
        "primary_evidence_url": args.url.removesuffix("/application"),
        "posting_url": args.url.removesuffix("/application"),
        "apply_url": args.url,
        "top_candidate_evidence": False,
        "source_receipt_id": "src:a:ashby:test",
    }

    promoted, receipt = resolve_primary_source(locator, lambda _locator: [primary])
    eligibility_state = None
    if promoted is None:
        failures.append(f"READBACK_DID_NOT_PROMOTE: {receipt.get('status')}")
    else:
        if promoted.get("workplace_type") != "ONSITE_ELSEWHERE":
            failures.append(
                f"READBACK_OVERWROTE_PRIMARY_LOCATION: {promoted.get('workplace_type')!r}"
            )
        if receipt.get("location_authority") != "primary_source":
            failures.append(
                f"READBACK_LOCATION_AUTHORITY_WRONG: {receipt.get('location_authority')!r}"
            )
        if receipt.get("location_conflict") is not True:
            failures.append("READBACK_LOCATION_CONFLICT_NOT_RECORDED")
        eligibility_state, _ = _eligibility(promoted)
        if eligibility_state != "REJECT_RELOCATION_REQUIRED":
            failures.append(f"ONSITE_ELSEWHERE_ADMITTED: {eligibility_state}")

    proof = {
        "schema": "monitor_opportunities.application_page_location_truth_proof.v1",
        "generated_at": utc_now(),
        "status": "PASS" if not failures else "FAIL",
        "mocked": False,
        "live": True,
        "external_effects": False,
        "apply_url": args.url,
        "application_page": metadata,
        "ashby_board_workplace_type": board_workplace,
        "readback_receipt": receipt,
        "promoted_workplace_type": promoted.get("workplace_type") if promoted else None,
        "eligibility_state": eligibility_state,
        "failures": failures,
    }
    _write(args.out, proof)

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"APPLICATION_PAGE_LOCATION_TRUTH_FAIL proof={args.out}")
        return 1
    print(
        "APPLICATION_PAGE_LOCATION_TRUTH_OK "
        f"proof={args.out} "
        f"application_page_workplace_type={app_workplace} "
        f"eligibility_state={eligibility_state}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
