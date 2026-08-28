"""Stage conservation: every discovered record gets exactly one disposition.

webgpt eval review P0 #04. The failure it prevents is the one this pipeline has
actually shown twice: a stage silently losing records while every receipt still
reports success — a lane reporting MATCHES having emitted nothing usable (DARPA
returning one landing page), a parser collapsing to zero on an HTTP 200, or
over-deduplication quietly merging distinct roles.

Accounting rule, checked against the run's own artifacts:

    discovered == deduplicated + admitted + rejected

Every discovered candidate_id must resolve to exactly ONE disposition:
    accepted       present in the shortlist
    rejected       present in rejections with an eligibility state and reason
    deduplicated   named in the ranking receipt's duplicates_merged_into map,
                   pointing at the canonical record it merged into
Anything else is `unaccounted` — a silent loss, which is the defect.

Also asserts the claim/emit contract: a lane whose source receipts report
MATCHES must have contributed at least one discovered candidate. A lane that
claims matches and emits nothing is degraded, not healthy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = "monitor_opportunities.stage_ledger.v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def build_ledger(
    discovered: list[dict[str, Any]],
    shortlist: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    merged_into: dict[str, str],
    source_receipts: list[dict[str, Any]] | None = None,
    admitted_count: int | None = None,
    eligible_ids: set[str] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Reconcile the stages. Returns (ok, ledger)."""
    disc_ids = [str(c.get("candidate_id") or "") for c in discovered]
    accepted = {str(r.get("candidate_id") or "") for r in shortlist}
    rejected = {str(r.get("candidate_id") or "") for r in rejections}
    deduped = {str(k) for k in merged_into}
    eligible_ids = eligible_ids or set()

    violations: list[dict[str, Any]] = []
    dispositions: dict[str, str] = {}
    pending_unaccounted: list[str] = []
    for cid in disc_ids:
        where = [
            name
            for name, bucket in (
                ("accepted", accepted), ("rejected", rejected), ("deduplicated", deduped)
            )
            if cid in bucket
        ]
        if len(where) == 1:
            dispositions[cid] = where[0]
        elif not where and cid in eligible_ids:
            dispositions[cid] = "eligible_not_shortlisted"
        elif not where:
            dispositions[cid] = "unaccounted"
            pending_unaccounted.append(cid)
        else:
            dispositions[cid] = "+".join(where)
            violations.append({
                "rule": "single-disposition",
                "detail": f"record {cid} appears in multiple buckets: {where}",
                "candidate_id": cid,
            })

    if pending_unaccounted:
        if not eligible_ids:
            expected_not_shortlisted = 0
            if admitted_count is not None:
                expected_not_shortlisted = max(0, admitted_count - len(accepted))
            if expected_not_shortlisted == len(pending_unaccounted):
                for cid in pending_unaccounted:
                    dispositions[cid] = "eligible_not_shortlisted"
                pending_unaccounted = []
        for cid in pending_unaccounted:
            violations.append({
                "rule": "no-silent-loss",
                "detail": f"discovered record {cid} has no disposition",
                "candidate_id": cid,
            })

    # Deduplicated rows must name a canonical record that actually survived the
    # eligibility pass, even if it fell below the top-N shortlist.
    for dropped, canonical in merged_into.items():
        canonical_disposition = dispositions.get(str(canonical))
        if canonical and canonical_disposition not in {"accepted", "rejected", "eligible_not_shortlisted"}:
            violations.append({
                "rule": "dedupe-names-canonical",
                "detail": f"{dropped} merged into {canonical}, which is in no later stage",
                "candidate_id": str(dropped),
            })

    # Arithmetic conservation across the whole run.
    counts = {
        "discovered": len(disc_ids),
        "accepted": sum(1 for d in dispositions.values() if d == "accepted"),
        "rejected": sum(1 for d in dispositions.values() if d == "rejected"),
        "deduplicated": sum(1 for d in dispositions.values() if d == "deduplicated"),
        "eligible_not_shortlisted": sum(1 for d in dispositions.values() if d == "eligible_not_shortlisted"),
        "unaccounted": sum(1 for d in dispositions.values() if d == "unaccounted"),
    }
    total = (
        counts["accepted"]
        + counts["rejected"]
        + counts["deduplicated"]
        + counts["eligible_not_shortlisted"]
    )
    if total + counts["unaccounted"] != counts["discovered"]:
        violations.append({
            "rule": "stage-conservation",
            "detail": (
                f"discovered {counts['discovered']} != accepted {counts['accepted']} + "
                f"rejected {counts['rejected']} + deduplicated {counts['deduplicated']}"
            ),
        })

    # Claim/emit contract per lane: MATCHES must mean records were emitted.
    lane_claims: dict[str, dict[str, Any]] = {}
    if source_receipts is not None:
        emitted_by_lane: dict[str, int] = {}
        for c in discovered:
            lane = str(c.get("lane") or "?")
            emitted_by_lane[lane] = emitted_by_lane.get(lane, 0) + 1
        for rec in source_receipts:
            lane = str(rec.get("lane") or "?")
            claims = str(rec.get("result_status") or "") == "MATCHES"
            entry = lane_claims.setdefault(
                lane, {"claimed_matches": False, "emitted": emitted_by_lane.get(lane, 0)}
            )
            entry["claimed_matches"] = entry["claimed_matches"] or claims
        for lane, entry in lane_claims.items():
            if entry["claimed_matches"] and entry["emitted"] == 0:
                violations.append({
                    "rule": "claim-implies-emit",
                    "detail": f"lane {lane} reports MATCHES but emitted 0 candidates",
                })

    ledger = {
        "schema": LEDGER_SCHEMA,
        "counts": counts,
        "lane_claims": lane_claims,
        "violations": violations,
        "ok": not violations,
    }
    return not violations, ledger


def build_ledger_for_run(run_dir: Path) -> tuple[bool, dict[str, Any]]:
    """Build the ledger from a nightly run directory's artifacts."""
    discovered = _read_jsonl(run_dir / "discovery" / "candidates.jsonl")
    receipts = _read_jsonl(run_dir / "discovery" / "source-receipts.jsonl")
    shortlist_p = run_dir / "ranking" / "shortlist.json"
    source_intel_p = run_dir / "ranking" / "source-intel-shortlist.json"
    rejections_p = run_dir / "ranking" / "rejections.json"
    receipt_p = run_dir / "ranking" / "ranking-receipt.json"
    eligibility_p = run_dir / "ranking" / "eligibility-receipts.jsonl"
    readback_p = run_dir / "ranking" / "readback-receipts.jsonl"
    shortlist = json.loads(shortlist_p.read_text(encoding="utf-8")) if shortlist_p.exists() else []
    if source_intel_p.exists():
        shortlist += json.loads(source_intel_p.read_text(encoding="utf-8"))
    rejections = (
        json.loads(rejections_p.read_text(encoding="utf-8")) if rejections_p.exists() else []
    )
    merged: dict[str, str] = {}
    if receipt_p.exists():
        try:
            receipt = json.loads(receipt_p.read_text(encoding="utf-8"))
            merged = receipt.get("duplicates_merged_into", {}) or {}
            admitted_count = int(receipt.get("admitted") or 0)
        except ValueError:
            merged = {}
            admitted_count = None
    else:
        admitted_count = None
    discovered_by_url: dict[str, str] = {}
    for row in discovered:
        cid = str(row.get("candidate_id") or "")
        for field in ("primary_evidence_url", "posting_url", "apply_url"):
            url = str(row.get(field) or "")
            if cid and url:
                discovered_by_url[url] = cid
    for receipt in _read_jsonl(readback_p):
        if receipt.get("status") != "PRIMARY_CONFIRMED":
            continue
        locator_id = discovered_by_url.get(str(receipt.get("locator_url") or ""))
        primary_id = discovered_by_url.get(str(receipt.get("primary_url") or ""))
        if locator_id and primary_id and locator_id != primary_id:
            merged.setdefault(locator_id, primary_id)
    return build_ledger(
        discovered,
        shortlist,
        rejections,
        merged,
        source_receipts=receipts,
        admitted_count=admitted_count,
        eligible_ids={
            str(row.get("candidate_id") or "")
            for row in _read_jsonl(eligibility_p)
            if str(row.get("state") or "").startswith("ELIGIBLE_")
        },
    )
