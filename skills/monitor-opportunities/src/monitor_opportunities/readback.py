"""Primary-source readback: promote LinkedIn-located roles to real opportunities.

The research-first architecture is "locate via aggregator, then read the primary
source." The locate half runs (LinkedIn Jobs rows become source-intelligence),
but the readback half was never built, so every LinkedIn-located role was
quarantined as ``LOCATOR_ONLY`` / ``action_worthy: False`` and could never enter
the ranked opportunity shortlist. Because Buffalo/WNY roles surface almost
entirely via LinkedIn, the highest-priority geography was structurally absent
from the actionable list every run (diagnosed 2026-08-23 against
run-20260823T060000Z: 6 eligible WNY_ONSITE roles, all stuck in source_intel).

This module performs the missing readback. For a LinkedIn locator it asks a
primary-source probe (the employer's own Greenhouse/Lever/Ashby board, reusing
the existing discovery adapters) whether the same posting exists on a primary
source. On a confirmed match the locator is PROMOTED into a full primary-source
candidate bound to the employer URL, so it flows through the normal
eligibility -> fit -> ranking path and competes for the shortlist. On no match
a WNY-priority locator is NOT silently buried: it is surfaced as
``PENDING_PRIMARY_VERIFICATION`` / ``action_worthy: True`` so the human can
verify and apply.

The probe is dependency-injected so this is deterministic to test without
network; production wires it to the live ATS adapters.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Callable, Protocol

from .util import stable_id

# Geographies that get an active primary-source readback. Buffalo is the hard
# constraint, so WNY roles are resolved first; a locator elsewhere stays intel.
READBACK_PRIORITY_GEO = frozenset({"WNY_HYBRID", "WNY_ONSITE"})

_TITLE_MATCH_THRESHOLD = 0.60

# A primary-source probe takes the locator candidate (employer + title) and
# returns whatever primary-ATS candidates it can find for that employer (each
# shaped like a discovery candidate: source_provider greenhouse/lever/ashby/
# workday, title, primary_evidence_url, workplace_type, ...). It must never
# return a LinkedIn/locator row. The title lets search-capable boards (Workday)
# target the specific posting instead of paging the whole board.
AtsProbe = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _is_linkedin_locator(candidate: dict[str, Any]) -> bool:
    return candidate.get("source_provider") in {
        "human_supplied_linkedin",
        "ops_linkedin_authorized_read_only",
    }


def _normalize_title(title: str) -> str:
    t = (title or "").lower()
    # Drop seniority/level noise and punctuation so "Senior Computational
    # Scientist" matches "Computational Scientist".
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    noise = {"senior", "sr", "staff", "principal", "lead", "junior", "jr", "i", "ii", "iii",
             "the", "a", "of", "and", "-"}
    tokens = [w for w in t.split() if w and w not in noise]
    return " ".join(tokens)


def _title_similarity(a: str, b: str) -> float:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def same_employer(a: str, b: str) -> bool:
    """Loose employer-name equality, resistant to legal suffixes and descriptors.
    Guards against ATS slug collisions promoting a different company's posting."""
    def norm(s: str) -> str:
        s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
        drop = _ORG_SUFFIX_NOISE | {"comprehensive", "center", "centre", "solutions",
                                    "technologies", "technology", "labs", "systems", "cancer"}
        return " ".join(w for w in s.split() if w and w not in drop)
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def _best_primary_match(
    locator: dict[str, Any], primaries: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float]:
    """The primary-ATS posting that best matches the locator, if any clears the
    title threshold AND is the same employer. The employer check is essential:
    a fetched board may belong to a slug-collision company, and a title-only
    match would then promote the wrong employer's role. Locator rows are never
    accepted as their own primary."""
    title = locator.get("title", "")
    org = locator.get("organization", "")
    best: dict[str, Any] | None = None
    best_score = 0.0
    for cand in primaries:
        if _is_linkedin_locator(cand):
            continue
        if not same_employer(org, str(cand.get("organization") or "")):
            continue
        score = _title_similarity(title, str(cand.get("title", "")))
        if score > best_score:
            best, best_score = cand, score
    if best is not None and best_score >= _TITLE_MATCH_THRESHOLD:
        return best, best_score
    return None, best_score


def resolve_primary_source(
    locator: dict[str, Any], ats_probe: AtsProbe
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Attempt primary-source readback for one LinkedIn locator.

    Returns ``(promoted_candidate | None, receipt)``. ``promoted_candidate`` is a
    full primary-source candidate (so downstream ranking treats it as a real
    opportunity) carrying provenance back to the LinkedIn row. The receipt records
    the outcome for the report's source-integrity accounting.
    """
    org = str(locator.get("organization") or "")
    locator_url = locator.get("primary_evidence_url") or locator.get("posting_url")
    receipt: dict[str, Any] = {
        "receipt_id": stable_id("readback", locator.get("candidate_id", org)),
        "kind": "primary_source_readback",
        "organization": org,
        "title": locator.get("title"),
        "workplace_type": locator.get("workplace_type"),
        "locator_url": locator_url,
        "locator_source": locator.get("source_provider"),
    }
    try:
        primaries = ats_probe(locator) or []
    except Exception as exc:  # noqa: BLE001 - a probe failure is INDETERMINATE, never a match
        receipt["status"] = "READBACK_ERROR"
        receipt["detail"] = f"{type(exc).__name__}: {exc}"[:200]
        return None, receipt

    match, score = _best_primary_match(locator, primaries)
    receipt["primaries_seen"] = len(primaries)
    receipt["best_title_score"] = round(score, 3)
    if match is None:
        receipt["status"] = "NO_PRIMARY_FOUND"
        return None, receipt

    promoted = dict(match)
    promoted["located_via"] = "linkedin"
    promoted["locator_url"] = locator_url
    promoted["locator_candidate_id"] = locator.get("candidate_id")
    promoted["readback_receipt_id"] = receipt["receipt_id"]
    receipt["status"] = "PRIMARY_CONFIRMED"
    receipt["primary_url"] = match.get("primary_evidence_url") or match.get("posting_url")
    receipt["primary_provider"] = match.get("source_provider")
    receipt["primary_workplace_type"] = promoted.get("workplace_type")
    receipt["locator_workplace_type"] = locator.get("workplace_type")
    receipt["location_authority"] = "primary_source"
    if (
        locator.get("workplace_type") in READBACK_PRIORITY_GEO
        and promoted.get("workplace_type") not in READBACK_PRIORITY_GEO
    ):
        receipt["location_conflict"] = True
        receipt["location_conflict_resolution"] = (
            "primary_source_workplace_type_retained; linkedin_locator_not_used_for_wny_eligibility"
        )
    return promoted, receipt


_ORG_SUFFIX_NOISE = {"inc", "llc", "ltd", "corp", "corporation", "company", "co", "the",
                     "group", "holdings", "plc", "gmbh"}


def slug_variants(org: str) -> list[str]:
    """Candidate ATS board slugs derived from an employer name, most-specific
    first. Employers pick non-obvious slugs, so we try a small ordered set
    (full-join, first-two-words, first word, hyphenated, acronym) rather than
    guess one. Deduped, order-preserving, bounded by the caller."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (org or "").lower())
    words = [w for w in s.split() if w and w not in _ORG_SUFFIX_NOISE]
    if not words:
        return []
    variants = [
        "".join(words),
        "".join(words[:2]) if len(words) >= 2 else "",
        words[0],
        "-".join(words),
        "-".join(words[:2]) if len(words) >= 2 else "",
        "".join(w[0] for w in words) if len(words) >= 2 else "",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        if v and len(v) >= 2 and v not in seen:
            seen.add(v)
            out.append(v)
    return out


# An ATS adapter matches the discovery signature: (client, target) -> (receipt, candidates).
AtsAdapter = Callable[[Any, dict[str, Any]], tuple[dict[str, Any], list[dict[str, Any]]]]


_WORKDAY_URL = re.compile(
    r"https?://(?P<tenant>[a-z0-9][a-z0-9-]*)\.(?P<dc>wd\d+)\.myworkdayjobs\.com/"
    r"(?:(?P<locale>[a-z]{2}-[A-Z]{2})/)?(?P<site>[^/?#]+)",
    re.IGNORECASE,
)

# A search function returns candidate result URLs (or free text containing them)
# for a query. Injected so the resolver is testable without a live search.
SearchFn = Callable[[str], list[str]]


def parse_workday_url(url: str) -> "dict[str, str] | None":
    """Parse a myworkdayjobs.com URL into exact CXS coordinates."""
    m = _WORKDAY_URL.search(url or "")
    if not m:
        return None
    site = m.group("site")
    # A job-detail URL segment is not a site; those live under /job/... which the
    # regex already excludes by matching the first path segment. Guard the common
    # non-site first segments.
    if site.lower() in {"job", "jobs", "wday"}:
        return None
    return {"workday_tenant": m.group("tenant").lower(), "workday_dc": m.group("dc").lower(),
            "workday_site": site}


def resolve_workday_coordinates(org: str, search_fn: SearchFn) -> "dict[str, str] | None":
    """Find an employer's exact Workday coordinates via search, replacing blind
    enumeration with one targeted CXS call. Returns None when no myworkdayjobs URL
    is found (the caller falls back to enumeration or leaves the role pending)."""
    for query in (f"{org} careers site:myworkdayjobs.com", f'"{org}" myworkdayjobs'):
        try:
            urls = search_fn(query) or []
        except Exception:  # noqa: BLE001 - search failure is not a readback failure
            continue
        for url in urls:
            coords = parse_workday_url(url)
            if coords:
                return coords
    return None


def live_ats_probe(
    client: Any,
    *,
    max_slugs: int = 5,
    adapters: "list[AtsAdapter] | None" = None,
    search_fn: "SearchFn | None" = None,
) -> AtsProbe:
    """A primary-source probe that actively fetches the employer's own ATS board.

    For each derived slug it queries the real Greenhouse/Lever/Ashby adapters
    (read-only, no credentials) and returns every posting from a board that
    resolved (``MATCHES``). Read-only and bounded: at most ``max_slugs`` slugs x
    len(adapters) requests per employer. Any per-request failure is swallowed so
    one dead slug never aborts the readback. ``adapters`` is injectable so the
    live path is testable without network.
    """
    if adapters is None:  # pragma: no cover - exercised live; unit path injects adapters
        from .discovery import (
            _ashby_candidates,
            _greenhouse_candidates,
            _lever_candidates,
            _workday_candidates,
        )
        adapters = [_greenhouse_candidates, _lever_candidates, _ashby_candidates, _workday_candidates]

    workday_adapter = None
    if search_fn is not None:
        for a in adapters:
            if getattr(a, "__name__", "") == "_workday_candidates":
                workday_adapter = a
                break

    def probe(locator: dict[str, Any]) -> list[dict[str, Any]]:
        org = str(locator.get("organization") or "")
        results: list[dict[str, Any]] = []
        # Targeted Workday: resolve exact coordinates via search and make one CXS
        # call instead of enumerating tenant x dc x site. High yield, one request.
        if workday_adapter is not None:
            coords = resolve_workday_coordinates(org, search_fn)
            if coords:
                target = {"slug": coords["workday_tenant"], "name": org,
                          "search_text": locator.get("title") or "", **coords}
                try:
                    receipt, cands = workday_adapter(client, target)
                    if receipt.get("result_status") == "MATCHES":
                        results.extend(cands)
                except Exception:  # noqa: BLE001
                    pass
            if results:
                return results
        for slug in slug_variants(org)[:max_slugs]:
            target = {"slug": slug, "name": org, "search_text": locator.get("title") or ""}
            for adapter in adapters:
                try:
                    receipt, cands = adapter(client, target)
                except Exception:  # noqa: BLE001 - a dead slug/board is not a readback failure
                    continue
                if receipt.get("result_status") == "MATCHES":
                    results.extend(cands)
            # Employer-level early exit: once any board resolves for this employer,
            # stop trying more slug variants (bounds requests on a shared checkout).
            if results:
                break
        return results

    return probe


def compose_probes(*probes: "AtsProbe | None") -> AtsProbe:
    """Union of several probes (cross-reference + live fetch), deduping primaries
    by primary URL then org+title so the same posting is not offered twice."""
    active = [p for p in probes if p is not None]

    def probe(locator: dict[str, Any]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for p in active:
            for cand in p(locator):
                key = str(cand.get("primary_evidence_url") or cand.get("posting_url")
                          or f"{cand.get('organization')}|{cand.get('title')}")
                if key in seen:
                    continue
                seen.add(key)
                out.append(cand)
        return out

    return probe


def promote_linkedin_locators(
    candidates: list[dict[str, Any]], ats_probe: AtsProbe
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run primary-source readback across a candidate set.

    Returns ``(candidates_out, readback_receipts)``. Each WNY-priority LinkedIn
    locator is either replaced by a confirmed primary-source candidate (promoted
    into the rankable pool) or annotated ``pending_primary_verification`` so it is
    surfaced as human-actionable instead of buried. Non-priority locators and
    non-locators pass through unchanged.
    """
    out: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for cand in candidates:
        if not _is_linkedin_locator(cand) or cand.get("workplace_type") not in READBACK_PRIORITY_GEO:
            out.append(cand)
            continue
        promoted, receipt = resolve_primary_source(cand, ats_probe)
        receipts.append(receipt)
        if promoted is not None:
            out.append(promoted)
        else:
            annotated = dict(cand)
            annotated["pending_primary_verification"] = True
            annotated["readback_receipt_id"] = receipt["receipt_id"]
            out.append(annotated)
    return out, receipts
