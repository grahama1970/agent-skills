"""Deterministic eligibility admission and ranking receipts."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json, write_jsonl

GEO_PRIORITY = {"WNY_HYBRID": 300, "WNY_ONSITE": 200, "REMOTE": 100, "NOT_APPLICABLE": 150}


def _max_age_days() -> int:
    """Only recent opportunities count; default window is 2 weeks (Graham 2026-08-07)."""
    try:
        return max(1, int(os.environ.get("MONITOR_MAX_AGE_DAYS", "")))
    except (TypeError, ValueError):
        return 14


def _posting_age_days(candidate: dict[str, Any]) -> float | None:
    """Age in days from published_at/updated_at, or None if no parseable date."""
    for key in ("published_at", "updated_at"):
        raw = candidate.get(key)
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return (datetime.now(UTC) - parsed).total_seconds() / 86400.0
    return None


def _eligibility(candidate: dict[str, Any]) -> tuple[str, list[str]]:
    if candidate.get("source_valid") is False:
        return "REJECT_SOURCE_INVALID", ["source_valid=false"]
    if candidate.get("relocation_required") is True:
        return "REJECT_RELOCATION_REQUIRED", ["relocation_required=true"]
    if candidate.get("already_applied") is True:
        return "REJECT_DUPLICATE_OR_ALREADY_APPLIED", ["already_applied=true"]
    if candidate.get("stale") is True:
        return "REJECT_STALE", ["stale=true"]
    # Recency: we only care about opportunities within the last 2 weeks. A
    # parseable date older than the window is rejected; a missing/unparseable
    # date is NOT rejected (many boards omit dates — do not silently drop them).
    age = _posting_age_days(candidate)
    max_age = _max_age_days()
    if age is not None and age > max_age:
        return "REJECT_STALE_AGE", [f"published {age:.0f}d ago (> {max_age}d window)"]
    if candidate.get("work_authorization_mismatch") is True:
        return "REJECT_WORK_AUTHORIZATION_MISMATCH", ["work_authorization_mismatch=true"]
    if candidate.get("clearance_required") == "UNKNOWN":
        return "HUMAN_REVIEW_ELIGIBILITY_UNKNOWN", ["clearance requirement is unknown"]
    if candidate.get("clearance_required") is True:
        return "REJECT_CLEARANCE_REQUIRED_UNATTESTED", ["clearance requirement is unattested"]
    lane = candidate.get("lane")
    workplace = candidate.get("workplace_type")
    if lane == "B":
        return "ELIGIBLE_FEDERAL_NOTICE", ["federal notice has primary-source receipt"]
    if lane == "C":
        return "ELIGIBLE_COMMERCIAL_SIGNAL", ["commercial signal has primary-source receipt"]
    if workplace == "WNY_HYBRID":
        return "ELIGIBLE_WNY_HYBRID", ["Buffalo/WNY hybrid"]
    if workplace == "WNY_ONSITE":
        return "ELIGIBLE_WNY_ONSITE", ["Buffalo/WNY onsite"]
    if workplace == "REMOTE":
        return "ELIGIBLE_REMOTE", ["credible remote"]
    if workplace == "AMBIGUOUS":
        return "HUMAN_REVIEW_LOCATION_AMBIGUOUS", ["location cannot be disambiguated"]
    return "REJECT_LOCATION", [f"unsupported workplace_type={workplace!r}"]


def _load_candidates(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_file():
        payload = read_json(input_path)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
            return payload["candidates"]
        raise ValueError(f"ranking input file must be a candidate list or object with candidates: {input_path}")
    return read_jsonl(input_path / "candidates.jsonl")


def _score(candidate: dict[str, Any]) -> dict[str, Any]:
    geo = GEO_PRIORITY.get(candidate.get("workplace_type"), 0)
    role = round(float(candidate.get("fit_score", 0.0)) * 100, 3)
    source = 20 if candidate.get("source_receipt_id") else 0
    total = geo + role + source
    return {"geo_priority": geo, "role_fit": role, "source_quality": source, "total": total}


def rank(discovery_run: Path, limit: int, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = _load_candidates(discovery_run)
    eligibility_receipts = []
    ranking_receipts = []
    admitted = []
    rejections = []
    for candidate in candidates:
        state, reasons = _eligibility(candidate)
        receipt = {
            "receipt_id": stable_id("eligibility", {"candidate": candidate["candidate_id"], "state": state}),
            "candidate_id": candidate["candidate_id"],
            "source_candidate_hash": sha256_json(candidate),
            "policy_version": "eligibility.v1",
            "policy_digest": sha256_json({"policy": "eligibility.v1"}),
            "state": state,
            "reasons": reasons,
            "limitations": [],
        }
        eligibility_receipts.append(receipt)
        if state.startswith("ELIGIBLE_"):
            scored = {**candidate, "eligibility_state": state, "eligibility_receipt_id": receipt["receipt_id"]}
            scored["score_components"] = _score(candidate)
            admitted.append(scored)
        else:
            rejections.append({**candidate, "eligibility_state": state, "eligibility_receipt_id": receipt["receipt_id"]})

    admitted.sort(
        key=lambda row: (
            -row["score_components"]["total"],
            row.get("organization", ""),
            row.get("title", ""),
            row["candidate_id"],
        )
    )
    shortlist = admitted[:limit]
    for position, candidate in enumerate(shortlist, start=1):
        ranking_receipts.append(
            {
                "receipt_id": stable_id("ranking", {"candidate": candidate["candidate_id"], "position": position}),
                "candidate_id": candidate["candidate_id"],
                "rank": position,
                "policy_version": "ranking.v1",
                "policy_digest": sha256_json({"policy": "ranking.v1", "limit": limit}),
                "component_scores": candidate["score_components"],
                "limitations": ["Deterministic score is not employer selection probability."],
            }
        )

    receipt = {
        "schema": "monitor_opportunities.rank_receipt.v1",
        "generated_at": utc_now(),
        "mocked": False,
        "live": True,
        "external_effects": False,
        "input": str(discovery_run),
        "limit": limit,
        "inspected": len(candidates),
        "admitted": len(admitted),
        "shortlisted": len(shortlist),
        "rejected_or_review": len(rejections),
    }
    write_jsonl(out_dir / "eligibility-receipts.jsonl", eligibility_receipts)
    write_jsonl(out_dir / "ranking-receipts.jsonl", ranking_receipts)
    write_json(out_dir / "shortlist.json", shortlist)
    write_json(out_dir / "rejections.json", rejections)
    write_json(out_dir / "ranking-receipt.json", receipt)
    return receipt
