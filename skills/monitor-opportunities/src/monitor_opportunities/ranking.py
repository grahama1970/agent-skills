"""Deterministic eligibility admission and ranking receipts."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import readback as _readback
from .readback import AtsProbe
from .util import read_json, read_jsonl, sha256_json, stable_id, utc_now, write_json, write_jsonl

from dotenv import load_dotenv

load_dotenv(override=False)

GEO_PRIORITY = {"WNY_HYBRID": 300, "WNY_ONSITE": 200, "REMOTE": 100, "NOT_APPLICABLE": 150}
SOURCE_INTEL_PROVIDERS = {
    "github_repo_intelligence",
    "human_supplied_linkedin",
    "ops_linkedin_authorized_read_only",
    "meetup_surf",
}
ORG_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "llc",
    "ltd",
}
ORG_ALIASES = {
    "ge aviation": "ge aerospace",
    "general electric aerospace": "ge aerospace",
}


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


# Off-target role types for a Principal AI Architect. Hard-negative title terms
# disqualify a lane-A posting even with a senior prefix (a "Senior Account
# Executive" is still sales). Bounded, fixture-tested vocabulary — not open-ended
# classification. Terms are matched against the space-padded lowercased title.
_ROLE_TYPE_REJECT_TERMS = (
    "account executive", "account manager", "sales representative", "sales rep",
    " sales ", "business development", "solutions engineer", "solutions consultant",
    "sales engineer", "pre-sales", "presales", "chief growth", "growth officer",
    "administrator", "coordinator", "cmms", "accounting", "bookkeeper",
    "recruiter", "talent acquisition", "web designer", "copywriter", " editor",
    "founder in residence", "entrepreneur in residence", "founder", "co-founder",
    "data management specialist", "data entry",
)
# Below Graham's Principal/Staff/Senior floor.
_BELOW_FLOOR_TERMS = ("intern ", "internship", " junior ", "entry level", "entry-level", "apprentice", " co-op ", "associate engineer", "associate developer")
# Engineering/AI signal that keeps a "... manager" title (e.g. Engineering Manager).
_ENG_SIGNAL_TERMS = ("engineer", "architect", "developer", " ml ", " ai ", "machine learning", "research scien", "applied ai", "applied ml", "platform", "llm", "data scien")


def _role_type_reject(title: str) -> str | None:
    low = f" {title.lower().strip()} "
    for term in _ROLE_TYPE_REJECT_TERMS:
        if term in low:
            return term.strip()
    for term in _BELOW_FLOOR_TERMS:
        if term in low:
            return term.strip()
    # A bare "manager" title with no engineering signal is off-mandate
    # (Manager, Analytics / Accounting Manager) — but keep Engineering Manager.
    if "manager" in low and not any(sig in low for sig in _ENG_SIGNAL_TERMS):
        return "non-engineering manager"
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
    github_source_intel = candidate.get("source_provider") == "github_repo_intelligence"
    if age is not None and age > max_age and not github_source_intel:
        return "REJECT_STALE_AGE", [f"published {age:.0f}d ago (> {max_age}d window)"]
    # Role-type targeting: drop off-mandate roles (sales, admin, founder,
    # creative, below-floor) for real job postings. Federal (B) and commercial
    # signal (C) lanes are not title-filtered.
    if candidate.get("lane") == "A":
        off_target = _role_type_reject(str(candidate.get("title") or ""))
        if off_target:
            return "REJECT_ROLE_TYPE", [f"off-target role type: {off_target}"]
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
    if workplace == "ONSITE_ELSEWHERE":
        return "REJECT_RELOCATION_REQUIRED", ["posting body requires on-site outside Buffalo/WNY"]
    if workplace == "AMBIGUOUS":
        # A LinkedIn top-applicant role is high-value (Graham ranks in the top
        # pool) and must not be buried in human-review just because its location
        # string is ambiguous — surface it as eligible so it reaches the report.
        if candidate.get("top_candidate_evidence"):
            return "ELIGIBLE_TOP_APPLICANT", ["LinkedIn top applicant — surfaced despite ambiguous location"]
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
    mandate = round(float(candidate.get("fit_score", 0.0)) * 1000, 3)
    seniority = round(float(candidate.get("seniority_score", candidate.get("fit_score", 0.0))) * 100, 3)
    role = round(float(candidate.get("fit_score", 0.0)) * 100, 3)
    source = 20 if candidate.get("source_receipt_id") else 0
    # LinkedIn top-applicant status is a strong reply signal: among comparable
    # roles it should win a shortlist slot. Ranks just under mandate fit so it
    # breaks ties decisively without overriding a genuinely better-fit role.
    top_candidate = 500_000 if candidate.get("top_candidate_evidence") else 0
    total = (mandate * 1_000_000) + top_candidate + (seniority * 10_000) + (role * 1_000) + geo + source
    return {
        "mandate_fit": mandate,
        "seniority_ownership": seniority,
        "role_fit": role,
        "geo_priority": geo,
        "source_quality": source,
        "total": round(total, 3),
        "ranking_order": [
            "mandate_fit",
            "seniority_ownership",
            "role_fit",
            "geo_priority",
            "source_quality",
        ],
    }


_WNY_WORKPLACES = frozenset({"WNY_HYBRID", "WNY_ONSITE"})


def _wny_reserved_slots(limit: int) -> int:
    """How many shortlist slots to guarantee for eligible WNY roles. Buffalo is
    the hard-constraint, highest-priority geography, so it must be visible in the
    actionable top-N even when higher-fit remote roles exist -- without ranking a
    weak WNY role above a strong one (the reserve is filled by best-fit WNY)."""
    raw = os.environ.get("MONITOR_WNY_RESERVED_SLOTS")
    if raw:
        try:
            return max(0, min(int(raw), limit))
        except ValueError:
            pass
    return min(2, limit)


def _select_with_wny_reserve(admitted_opportunities: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Fit-ranked shortlist with up to N slots reserved for the best-fit eligible
    WNY roles. The reserved WNY roles are the top of the (already fit-sorted) WNY
    subset; remaining slots fill from the overall fit order. When no WNY role is
    eligible the result is identical to plain fit-ranked truncation."""
    reserve = _wny_reserved_slots(limit)
    if reserve <= 0:
        return admitted_opportunities[:limit]
    wny = [r for r in admitted_opportunities if r.get("workplace_type") in _WNY_WORKPLACES]
    reserved = wny[:reserve]
    reserved_ids = {r["candidate_id"] for r in reserved}
    filler = [r for r in admitted_opportunities if r["candidate_id"] not in reserved_ids]
    # Fill the non-reserved slots by overall fit, then place the reserved WNY
    # roles, and re-sort the whole shortlist by fit so the list still reads in
    # rank order (the reserve guarantees inclusion, not a fixed position).
    combined = filler[: max(0, limit - len(reserved))] + reserved
    combined.sort(
        key=lambda row: (
            -row["score_components"]["total"],
            row.get("organization", ""),
            row.get("title", ""),
            row["candidate_id"],
        )
    )
    return combined[:limit]


def _is_source_intel_candidate(candidate: dict[str, Any]) -> bool:
    """Rows that inform human sourcing must not consume application shortlist slots."""

    return str(candidate.get("source_provider") or "") in SOURCE_INTEL_PROVIDERS


def _source_intel_provider(candidate: dict[str, Any]) -> str:
    return str(candidate.get("source_provider") or candidate.get("source_class") or "unknown")


def _source_intel_limit(opportunity_limit: int) -> int:
    """Return the bounded report cap for source-intel rows."""

    raw = os.environ.get("MONITOR_SOURCE_INTEL_LIMIT")
    if raw:
        try:
            return max(0, min(int(raw), 25))
        except ValueError:
            pass
    return max(opportunity_limit, 12)


def _diverse_source_intel_shortlist(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Round-robin source-intel providers so one locator cannot hide another."""

    if limit <= 0:
        return []
    groups: dict[str, list[dict[str, Any]]] = {}
    provider_order: list[str] = []
    for candidate in candidates:
        provider = _source_intel_provider(candidate)
        if provider not in groups:
            groups[provider] = []
            provider_order.append(provider)
        groups[provider].append(candidate)

    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(groups.values()):
        for provider in provider_order:
            rows = groups.get(provider) or []
            if not rows:
                continue
            selected.append(rows.pop(0))
            if len(selected) >= limit:
                break
    return selected


def _posting_identity(candidate: dict[str, Any]) -> str:
    """Stable identity for one real-world posting, across sources.

    A board can list the same posting under several ids (Built In's JSON-LD
    emits variant job ids: ServiceNow 'Solution Architect - AI & Data' appeared
    6x on 2026-08-13), and the same role arrives from both LinkedIn lanes. Key
    on the durable pair instead: normalized organization + title.
    """
    org = _organization_identity(candidate)
    title = " ".join(str(candidate.get("title") or "").lower().split())
    return f"{org}|{title}"


def _organization_identity(candidate: dict[str, Any]) -> str:
    """Canonical organization key used only for same-posting dedupe."""

    raw = str(candidate.get("organization_canonical") or candidate.get("organization") or "")
    words = re.findall(r"[a-z0-9]+", raw.lower())
    key = " ".join(word for word in words if word not in ORG_SUFFIXES)
    return ORG_ALIASES.get(key, key)


def dedupe_postings(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, dict[str, str]]:
    """Collapse duplicate postings, keeping the richest row.

    Returns (rows, dropped, merged_into). `merged_into` maps every dropped
    candidate_id to the canonical candidate_id that survived, because a
    disposition of "deduplicated" is only auditable if it names the record the
    row was merged INTO (webgpt eval review P0 #04).
    """
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    duplicates_by_key: dict[str, list[str]] = {}

    def _cid(row: dict[str, Any]) -> str:
        return str(row.get("candidate_id") or "")

    for c in candidates:
        key = _posting_identity(c)
        if key == "|":  # no identity to dedupe on; keep as-is
            order.append(f"__keep__{len(order)}")
            best[order[-1]] = c
            continue
        prior = best.get(key)
        if prior is None:
            best[key] = c
            order.append(key)
            continue
        # Keep the row carrying more usable signal (real apply/posting url wins,
        # then more populated fields) so dedup never loses the clickable one.
        def _richness(row: dict[str, Any]) -> tuple[int, int]:
            urls = " ".join(str(row.get(key) or "") for key in ("posting_url", "apply_url"))
            detail_url = 2 if "/jobs/view/" in urls else 0
            clickable = 1 if urls.strip() else 0
            return (detail_url + clickable, sum(1 for v in row.values() if v not in (None, "", [], {})))

        if _richness(c) > _richness(prior):
            # the incoming row wins; the prior one is now the duplicate
            best[key] = c
            duplicates_by_key.setdefault(key, []).append(_cid(prior))
        else:
            duplicates_by_key.setdefault(key, []).append(_cid(c))
    deduped = [best[k] for k in order]
    merged_into: dict[str, str] = {}
    for key, dropped_ids in duplicates_by_key.items():
        canonical_id = _cid(best[key])
        for dropped_id in dropped_ids:
            if dropped_id and dropped_id != canonical_id:
                merged_into[dropped_id] = canonical_id
    _propagate_duplicate_history(best, candidates)
    return deduped, len(candidates) - len(deduped), merged_into


def _propagate_duplicate_history(best: dict[str, dict[str, Any]], candidates: list[dict[str, Any]]) -> None:
    """Carry prior-action evidence from dropped aliases to the survivor."""

    originals_by_key: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        key = _posting_identity(candidate)
        if key and key != "|":
            originals_by_key.setdefault(key, []).append(candidate)

    for key, survivor in best.items():
        rows = originals_by_key.get(key, [])
        actioned = [row for row in rows if row.get("already_applied") is True]
        if not actioned:
            continue
        survivor["already_applied"] = True
        keys = [
            str(row.get("application_history_key") or "")
            for row in actioned
            if row.get("application_history_key")
        ]
        states = [
            str(row.get("application_history_state") or "")
            for row in actioned
            if row.get("application_history_state")
        ]
        if keys:
            survivor["application_history_key"] = keys[0]
            survivor["application_history_keys"] = list(dict.fromkeys(keys))
        if states:
            survivor["application_history_state"] = states[0]


def _run_local_ats_probe(candidates: list[dict[str, Any]]) -> "AtsProbe":
    """A primary-source probe that corroborates a LinkedIn locator against the
    primary-ATS postings already discovered in THIS run. Zero new network and
    deterministic: if the employer's Greenhouse/Lever/Ashby posting was found
    independently, the locator is confirmed and promoted; otherwise it stays a
    locator (and WNY ones are surfaced as pending verification, never buried)."""
    primaries = [c for c in candidates if not _readback._is_linkedin_locator(c)
                 and not _is_source_intel_candidate(c)]

    def probe(locator: dict[str, Any]) -> list[dict[str, Any]]:
        org = str(locator.get("organization") or "")
        return [c for c in primaries if _readback.same_employer(org, str(c.get("organization") or ""))]

    return probe


def rank(discovery_run: Path, limit: int, out_dir: Path,
         ats_probe: "AtsProbe | None" = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = _load_candidates(discovery_run)
    # Primary-source readback: promote LinkedIn-located WNY roles that a primary
    # ATS source corroborates into the rankable pool; surface the rest as
    # pending-verification instead of burying them in non-actionable source-intel.
    # Always cross-reference the run's own primary candidates (free); when a live
    # probe is supplied, union it in so an employer's ATS board is fetched too.
    probe = _readback.compose_probes(_run_local_ats_probe(candidates), ats_probe)
    candidates, readback_receipts = _readback.promote_linkedin_locators(candidates, probe)
    write_jsonl(out_dir / "readback-receipts.jsonl", readback_receipts)
    readback_promoted_into = {
        str(row.get("locator_candidate_id")): str(row.get("promoted_candidate_id"))
        for row in readback_receipts
        if row.get("status") == "PRIMARY_CONFIRMED"
        and row.get("locator_candidate_id")
        and row.get("promoted_candidate_id")
    }
    candidates, duplicates_dropped, merged_into = dedupe_postings(candidates)
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
    admitted_opportunities = [row for row in admitted if not _is_source_intel_candidate(row)]
    admitted_source_intel = [row for row in admitted if _is_source_intel_candidate(row)]
    shortlist = _select_with_wny_reserve(admitted_opportunities, limit)
    source_intel_limit = _source_intel_limit(limit)
    source_intel_shortlist = _diverse_source_intel_shortlist(
        admitted_source_intel,
        source_intel_limit,
    )
    for position, candidate in enumerate(shortlist, start=1):
        ranking_receipts.append(
            {
                "receipt_id": stable_id("ranking", {"candidate": candidate["candidate_id"], "position": position}),
                "candidate_id": candidate["candidate_id"],
                "rank": position,
                "ranking_context": "opportunity_shortlist",
                "policy_version": "ranking.v1",
                "policy_digest": sha256_json({"policy": "ranking.v1", "limit": limit}),
                "component_scores": candidate["score_components"],
                "limitations": ["Deterministic score is not employer selection probability."],
            }
        )
    for position, candidate in enumerate(source_intel_shortlist, start=1):
        ranking_receipts.append(
            {
                "receipt_id": stable_id("ranking-source-intel", {"candidate": candidate["candidate_id"], "position": position}),
                "candidate_id": candidate["candidate_id"],
                "rank": position,
                "ranking_context": "source_intel",
                "policy_version": "ranking.v1",
                "policy_digest": sha256_json({"policy": "ranking.v1", "limit": source_intel_limit, "context": "source_intel"}),
                "component_scores": candidate["score_components"],
                "limitations": ["Source-intel rows are visible sourcing signals, not application opportunities."],
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
        "source_intel_limit": source_intel_limit,
        "inspected": len(candidates),
        "duplicates_dropped": duplicates_dropped,
        "duplicates_merged_into": merged_into,
        "readback_promoted_into": readback_promoted_into,
        "admitted": len(admitted),
        "admitted_opportunities": len(admitted_opportunities),
        "admitted_source_intel": len(admitted_source_intel),
        "shortlisted": len(shortlist),
        "source_intel_shortlisted": len(source_intel_shortlist),
        "rejected_or_review": len(rejections),
        "linkedin_readback_attempts": len(readback_receipts),
        "linkedin_readback_promoted": sum(1 for r in readback_receipts if r.get("status") == "PRIMARY_CONFIRMED"),
        "linkedin_readback_pending": sum(1 for r in readback_receipts if r.get("status") != "PRIMARY_CONFIRMED"),
    }
    write_jsonl(out_dir / "eligibility-receipts.jsonl", eligibility_receipts)
    write_jsonl(out_dir / "ranking-receipts.jsonl", ranking_receipts)
    write_json(out_dir / "shortlist.json", shortlist)
    write_json(out_dir / "source-intel-shortlist.json", source_intel_shortlist)
    write_json(out_dir / "rejections.json", rejections)
    write_json(out_dir / "ranking-receipt.json", receipt)
    return receipt
