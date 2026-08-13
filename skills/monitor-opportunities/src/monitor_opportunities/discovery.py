"""Read-only source discovery with typed local receipts and no external effects."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger

from .receipts import base_receipt as _base_receipt, finalize_receipt as _finalize_receipt
from .required_source_receipts import client_research_receipt as _client_research_receipt, federal_website_receipt as _federal_website_receipt, linkedin_required_receipt as _linkedin_required_receipt
from .util import read_json, sha256_bytes, stable_id, utc_now, write_json, write_jsonl

from dotenv import load_dotenv

load_dotenv(override=False)

LANES = ("A", "B", "C")
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=3.0)
MAX_RESPONSE_BYTES = 1_500_000
SOURCE_LOCATOR_TERMS = ("greenhouse", "lever", "ashby", "workday", "workable")
LINKEDIN_AUTOMATION_POLICY = "linkedin_no_automation"
LINKEDIN_AUTHORIZED_READ_ONLY_POLICY = "linkedin_authorized_read_only_no_actions"
MEETUP_AUTOMATION_POLICY = "meetup_authorized_read_only_no_rsvp_no_message"

_MEETUP_RELEVANT_TERMS = (
    "ai",
    "artificial intelligence",
    "machine learning",
    "ml",
    "llm",
    "agent",
    "python",
    "rust",
    "azure",
    "cloud",
    "data",
    "security",
    "infosec",
    "cyber",
    "hackerspace",
    "cmmc",
    "compliance",
    "software",
    "developer",
    "code",
    "robotics",
    "d365",
    "power platform",
)
_MEETUP_GENERIC_OR_LOW_VALUE_TERMS = (
    "real estate",
    "apartment investor",
    "wealth",
    "toastmasters",
    "referral",
    "network after work",
    "business networking",
)




def _local_file_ref(path: Path) -> str:
    return "file://" + quote(str(path.resolve()))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "top_candidate", "top candidate"}
    return False


def _candidate_id(prefix: str, payload: dict[str, Any]) -> str:
    """Return a stable opportunity identity independent of mutable page content."""

    return stable_id(
        prefix,
        {
            "lane": payload.get("lane"),
            "source_provider": payload.get("source_provider"),
            "source_identity": payload.get("source_identity"),
            "organization": payload.get("organization"),
            "title": payload.get("title"),
            "primary_evidence_url": payload.get("primary_evidence_url") or payload.get("posting_url"),
        },
    )


def _text_evidence_record(raw: str) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized:
            record[normalized] = value.strip()
    if "title" not in record:
        first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
        if first_line:
            record["title"] = first_line[:120]
    record.setdefault("raw_text_excerpt", raw[:1200])
    return record


def _load_linkedin_records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = read_json(path)
    except Exception:
        record = _text_evidence_record(raw)
        return [record] if record else []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("opportunities", "evidence", "records", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _linkedin_evidence_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("A", "linkedin", "Human-supplied LinkedIn evidence", "human_supplied_linkedin")
    receipt["automation_policy"] = LINKEDIN_AUTOMATION_POLICY
    receipt["request_summary"] = f"Read local human-supplied LinkedIn artifact {path.name}; no browser or platform access"
    receipt["response_status"] = None
    receipt["content_type"] = "application/json" if path.suffix.lower() == ".json" else "text/plain"
    receipt["response_bytes"] = len(raw)
    receipt["content_sha256"] = sha256_bytes(raw)
    receipt["evidence_refs"] = [_local_file_ref(path)]
    receipt["limitations"].extend(
        [
            "Human-supplied LinkedIn evidence is a relevance signal only.",
            "LinkedIn is not logged into, scraped, clicked, connected, messaged, or otherwise automated.",
        ]
    )
    try:
        records = _load_linkedin_records(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Local LinkedIn artifact could not be parsed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []
    source_values = {str(row.get("source") or "") for row in records}
    authorized_capture = "human_authorized_linkedin_tab" in source_values
    if authorized_capture:
        receipt["target"] = "ops-linkedin authorized read-only opportunity capture"
        receipt["source_class"] = "ops_linkedin_authorized_read_only"
        receipt["automation_policy"] = LINKEDIN_AUTHORIZED_READ_ONLY_POLICY
        receipt["request_summary"] = (
            f"Read ops-linkedin authorized read-only evidence artifact {path.name}; "
            "the capture used a human-supplied tab id and performed no LinkedIn actions"
        )
        receipt["limitations"].append(
            "ops-linkedin read one human-authorized LinkedIn opportunity tab; no apply/connect/message/post action was taken."
        )
    receipt["limitations"].append(f"Automation policy: {receipt['automation_policy']}.")

    receipt["result_status"] = "MATCHES" if records else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for record in records:
        title = str(record.get("title") or record.get("role") or "").strip()
        organization = str(record.get("organization") or record.get("company") or "").strip()
        if not title or not organization:
            receipt["limitations"].append("One LinkedIn evidence record lacked title or organization and was not ranked.")
            continue
        location = str(record.get("location") or record.get("location_display") or "Unknown").strip()
        top_candidate = _coerce_bool(
            record.get("top_candidate")
            or record.get("top_candidate_signal")
            or record.get("top_candidate_evidence")
        )
        evidence_text = str(
            record.get("top_candidate_text")
            or record.get("evidence_text")
            or record.get("raw_text_excerpt")
            or "Human-supplied LinkedIn top-candidate evidence."
        )
        primary_url = str(
            record.get("primary_evidence_url")
            or record.get("posting_url")
            or record.get("job_url")
            or record.get("linkedin_url")
            or ""
        ).strip() or None
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "ops_linkedin_authorized_read_only"
            if str(record.get("source") or "") == "human_authorized_linkedin_tab"
            else "human_supplied_linkedin",
            "source_identity": str(record.get("linkedin_url") or primary_url or path.name),
            "source_class": "ops_linkedin_authorized_read_only"
            if str(record.get("source") or "") == "human_authorized_linkedin_tab"
            else "human_supplied_linkedin",
            "automation_policy": LINKEDIN_AUTHORIZED_READ_ONLY_POLICY
            if str(record.get("source") or "") == "human_authorized_linkedin_tab"
            else LINKEDIN_AUTOMATION_POLICY,
            "top_candidate_evidence": top_candidate,
            "organization": organization,
            "title": title,
            "location_display": location,
            "workplace_type": _workplace_type(location),
            "relocation_required": _relocation_required(location, evidence_text),
            "clearance_required": False,
            "posting_url": primary_url,
            "apply_url": None,
            "primary_evidence_url": primary_url or _local_file_ref(path),
            "published_at": record.get("published_at") or record.get("observed_at"),
            "updated_at": record.get("updated_at") or record.get("observed_at"),
            "content_hash": receipt["content_sha256"],
            "posting_text": evidence_text[:4000],
            "fit_score": float(record.get("fit_score") or (0.93 if top_candidate else 0.72)),
        }
        # Premium capture signals (LinkedIn computes these server-side): an
        # under-10-applicants posting is a low-competition channel; a "connection
        # works here" is a live warm path. Optional passthrough — the response
        # ranker reads row-level competition/warm_path directly.
        if record.get("under_10_applicants"):
            payload["competition"] = 0.1
        if record.get("warm_path"):
            payload["warm_path"] = float(record["warm_path"])
            payload["warm_path_via"] = str(record.get("warm_path_via") or "LinkedIn: connection works here")
        payload["candidate_id"] = _candidate_id("candidate:a:linkedin", payload)
        candidates.append(payload)
    return receipt, candidates


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _load_meetup_records(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("groups", "meetups", "records", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _meetup_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("name"),
        record.get("title"),
        record.get("description"),
        record.get("summary"),
        record.get("page_text"),
    ]
    for event in record.get("upcoming_events") or []:
        if isinstance(event, dict):
            parts.extend([event.get("title"), event.get("description"), event.get("venue")])
    parts.extend(_as_str_list(record.get("organizers")))
    parts.extend(_as_str_list(record.get("company_sponsors") or record.get("sponsors")))
    parts.extend(_as_str_list(record.get("known_monitor_contacts")))
    return "\n".join(str(part) for part in parts if part)


def _meetup_url(record: dict[str, Any]) -> str | None:
    for key in ("url", "group_url", "meetup_url", "primary_evidence_url"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def _meetup_first_event(record: dict[str, Any]) -> dict[str, Any]:
    events = record.get("upcoming_events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                return event
    return {}


def _meetup_decision(record: dict[str, Any]) -> tuple[str, float, list[str], list[str]]:
    text = _meetup_text(record)
    low = f" {text.lower()} "
    hits = []
    for term in _MEETUP_RELEVANT_TERMS:
        if term in {"ai", "ml", "llm", "agent"}:
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", low):
                hits.append(term)
        elif term in low:
            hits.append(term)
    generic_hits = [term for term in _MEETUP_GENERIC_OR_LOW_VALUE_TERMS if term in low]
    sponsors = _as_str_list(record.get("company_sponsors") or record.get("sponsors"))
    contacts = _as_str_list(record.get("known_monitor_contacts") or record.get("monitor_contacts"))
    upcoming = bool(_meetup_first_event(record)) or "upcoming event" in low or "upcoming events" in low
    buffalo = any(term in low for term in ("buffalo", "western new york", "wny"))

    reasons: list[str] = []
    if hits:
        reasons.append("topical match: " + ", ".join(hits[:6]))
    if sponsors:
        reasons.append("company/venue sponsor signal: " + ", ".join(sponsors[:4]))
    if contacts:
        reasons.append("monitor contact signal: " + ", ".join(contacts[:4]))
    if upcoming:
        reasons.append("upcoming event present")
    if buffalo:
        reasons.append("Buffalo/WNY area signal")
    if generic_hits:
        reasons.append("generic/low-value meetup warning: " + ", ".join(generic_hits[:4]))

    if not (hits or sponsors or contacts):
        return "SKIP", 0.0, reasons or ["no topical, company, or contact signal"], generic_hits
    if generic_hits and not hits and not (sponsors or contacts):
        return "SKIP", 0.0, reasons, generic_hits

    score = 0.18
    if hits:
        score += 0.2 + min(0.12, 0.03 * len(hits))
    if sponsors:
        score += 0.16
    if contacts:
        score += 0.18
    if upcoming:
        score += 0.08
    if buffalo:
        score += 0.06
    if generic_hits:
        score -= 0.12
    score = round(max(0.0, min(score, 0.78)), 3)
    if score >= 0.6 and upcoming:
        return "ATTEND", score, reasons, generic_hits
    if score >= 0.45:
        return "WATCH", score, reasons, generic_hits
    return "SKIP", score, reasons, generic_hits


def _meetup_evidence_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("C", "meetup", "Meetup Buffalo source-intel capture", "meetup_surf_capture")
    receipt["automation_policy"] = MEETUP_AUTOMATION_POLICY
    receipt["request_summary"] = (
        f"Read local Meetup evidence artifact {path.name}; source-intel only, no RSVP, message, join, or GraphQL action"
    )
    receipt["content_type"] = "application/json"
    receipt["response_bytes"] = len(raw)
    receipt["content_sha256"] = sha256_bytes(raw)
    receipt["evidence_refs"] = [_local_file_ref(path)]
    receipt["limitations"].extend(
        [
            "Meetup evidence is not a job or application source.",
            "Most Meetup groups are expected to be skipped unless topical, company-sponsored, or contact-linked.",
            f"Automation policy: {MEETUP_AUTOMATION_POLICY}.",
        ]
    )
    try:
        records = _load_meetup_records(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Local Meetup artifact could not be parsed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    candidates: list[dict[str, Any]] = []
    skipped: list[str] = []
    for record in records:
        name = str(record.get("name") or record.get("title") or "").strip()
        if not name:
            skipped.append("unnamed record")
            continue
        decision, fit_score, reasons, warnings = _meetup_decision(record)
        if decision == "SKIP":
            skipped.append(name)
            continue
        group_url = _meetup_url(record)
        event = _meetup_first_event(record)
        event_title = str(event.get("title") or "").strip()
        event_url = str(event.get("url") or event.get("event_url") or "").strip()
        location = str(
            event.get("venue")
            or record.get("location")
            or record.get("location_display")
            or "Buffalo/WNY meetup; delivery model not applicable"
        )
        sponsors = _as_str_list(record.get("company_sponsors") or record.get("sponsors"))
        contacts = _as_str_list(record.get("known_monitor_contacts") or record.get("monitor_contacts"))
        evidence_url = event_url or group_url or _local_file_ref(path)
        posting_text = "\n".join(
            [
                f"Meetup decision: {decision}",
                "Reasons: " + "; ".join(reasons),
                "Warnings: " + "; ".join(warnings) if warnings else "",
                _meetup_text(record)[:3000],
            ]
        ).strip()
        payload = {
            "lane": "C",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "meetup_surf",
            "source_class": "meetup_surf_capture",
            "source_identity": group_url or name,
            "automation_policy": MEETUP_AUTOMATION_POLICY,
            "networking_decision": decision,
            "networking_reasons": reasons,
            "networking_warnings": warnings,
            "company_sponsors": sponsors,
            "known_monitor_contacts": contacts,
            "organization": name,
            "title": event_title or f"{name} meetup source-intel",
            "location_display": location,
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": evidence_url,
            "apply_url": None,
            "primary_evidence_url": evidence_url,
            "published_at": event.get("starts_at") or record.get("observed_at"),
            "updated_at": record.get("observed_at"),
            "content_hash": sha256_bytes(json.dumps(record, sort_keys=True).encode("utf-8")),
            "posting_text": posting_text,
            "fit_score": fit_score,
            "contact_state": "CONTACT_PRESENT" if contacts else "CONTACT_UNKNOWN",
            "unresolved_assumptions": [
                "Actual attendee list, sponsor intent, and decision-maker attendance are unknown until human inspection.",
                "Attend/watch/skip is a human networking decision, not outreach or application authorization.",
            ],
        }
        payload["candidate_id"] = _candidate_id("candidate:c:meetup", payload)
        candidates.append(payload)
        if group_url:
            receipt["evidence_refs"].append(group_url)
    receipt["result_status"] = "MATCHES" if candidates else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt["limitations"].append(
        f"{len(records)} Meetup records inspected; {len(candidates)} attend/watch candidates emitted; {len(skipped)} skipped."
    )
    if skipped:
        receipt["limitations"].append("Skipped Meetup groups: " + ", ".join(skipped[:12]))
    finalized = _finalize_receipt(receipt)
    for candidate in candidates:
        candidate["source_receipt_id"] = finalized["receipt_id"]
    return finalized, candidates


def _registry_limit(target: dict[str, Any], default: int) -> int:
    try:
        return max(0, min(int(target.get("limit", default)), default))
    except (TypeError, ValueError):
        return default


def _add_registry_evidence(receipt: dict[str, Any], target: dict[str, Any], *urls: str | None) -> None:
    entry_id = target.get("registry_entry_id")
    if entry_id:
        receipt["limitations"].append(f"Reviewed registry entry: {entry_id}")
    for url in urls:
        if url and url not in receipt["evidence_refs"]:
            receipt["evidence_refs"].append(url)


def _fixture_sweep(fixture_dir: Path, lanes: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixture = read_json(fixture_dir / "discovery-run.json")
    receipts = [row for row in fixture["source_receipts"] if row["lane"] in lanes]
    candidates = [row for row in fixture["candidates"] if row["lane"] in lanes]
    attempted = {row["lane"] for row in receipts}
    for lane in sorted(lanes - attempted):
        receipt = _base_receipt(lane, "fixture", f"lane-{lane}", "fixture")
        receipt["result_status"] = "NOT_SEARCHED"
        receipt["limitations"] = ["Lane was requested but fixture has no source."]
        receipts.append(_finalize_receipt(receipt))
    return receipts, candidates


def _greenhouse_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "greenhouse", target["name"], "employer_ats")
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Greenhouse board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt), []
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    jobs = jobs if isinstance(jobs, list) else []
    receipt["result_status"] = "MATCHES" if jobs else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in jobs[: _registry_limit(target, 20)]:
        if not isinstance(job, dict):
            logger.warning("greenhouse board {} returned a non-dict job entry; skipping", target.get("name"))
            continue
        location = (job.get("location") or {}).get("name") or "Unknown"
        posting_url = job.get("absolute_url")
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "greenhouse",
            "source_identity": slug,
            "organization": job.get("company_name") or target["name"],
            "title": job.get("title") or "Untitled",
            "location_display": location,
            "workplace_type": _workplace_type(location),
            "relocation_required": "relocation" in location.lower() and "required" in location.lower(),
            "clearance_required": False,
            "posting_url": posting_url,
            "apply_url": posting_url,
            "primary_evidence_url": posting_url or url,
            "published_at": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": (job.get("content") or "")[:4000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _lever_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "lever", target["name"], "employer_ats")
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Lever board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt), []
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    postings = data if isinstance(data, list) else []
    receipt["result_status"] = "MATCHES" if postings else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in postings[: _registry_limit(target, 20)]:
        if not isinstance(job, dict):
            logger.warning("lever board {} returned a non-dict posting; skipping", target.get("name"))
            continue
        categories = job.get("categories") or {}
        location = categories.get("location") or "Unknown"
        hosted_url = job.get("hostedUrl") or job.get("applyUrl")
        posting_text = _lever_posting_text(job)
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "lever",
            "source_identity": slug,
            "organization": target["name"],
            "title": job.get("text") or "Untitled",
            "location_display": location,
            "workplace_type": _workplace_type(location),
            "relocation_required": _relocation_required(location, posting_text),
            "clearance_required": False,
            "posting_url": hosted_url,
            "apply_url": job.get("applyUrl") or hosted_url,
            "primary_evidence_url": hosted_url,
            "published_at": str(job.get("createdAt")) if job.get("createdAt") is not None else None,
            "updated_at": str(job.get("updatedAt")) if job.get("updatedAt") is not None else None,
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": posting_text[:4000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _ashby_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "ashby", target["name"], "employer_ats")
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Ashby board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt), []
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    receipt["result_status"] = "MATCHES" if jobs else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in jobs[: _registry_limit(target, 20)]:
        if not isinstance(job, dict):
            logger.warning("ashby board {} returned a non-dict job; skipping", target.get("name"))
            continue
        location = _ashby_location(job)
        posting_url = job.get("jobUrl")
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "ashby",
            "source_identity": slug,
            "organization": target["name"],
            "title": job.get("title") or "Untitled",
            "location_display": location,
            "workplace_type": _workplace_type(location),
            "relocation_required": _relocation_required(location, str(job)),
            "clearance_required": False,
            "posting_url": posting_url,
            "apply_url": job.get("applyUrl") or posting_url,
            "primary_evidence_url": posting_url,
            "published_at": job.get("publishedDate"),
            "updated_at": job.get("updatedAt"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": (job.get("descriptionHtml") or job.get("descriptionPlain") or "")[:4000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _builtin_candidates(
    client: httpx.Client, target: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Built In job-board search (builtin.com) via its schema.org JSON-LD.

    Server-rendered and keyless: each search page embeds an ItemList of
    ListItem{name, url, description} in an ld+json script (the '+' is
    HTML-encoded as &#x2B; in the type attribute). Organization comes from the
    /company/<slug> link adjacent to each job link in the DOM. Niche-board tier:
    lower applicant volume than LinkedIn, so it scores better on competition.
    """
    receipt = _base_receipt("A", "builtin", target["name"], "job_board")
    url = target["url"]
    _add_registry_evidence(receipt, target, url)
    receipt["request_summary"] = f"GET {url} with no credentials; JSON-LD ItemList parse"
    try:
        response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        response.raise_for_status()
        html = body.decode("utf-8", errors="replace")
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    # ld+json blocks; the type attribute encodes '+' as &#x2B; on builtin.com.
    items: list[dict[str, Any]] = []
    for block in re.findall(
        r'<script type="application/ld(?:\+|&#x2B;)json">\s*(\{.*?\})\s*</script>', html, re.S
    ):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        graphs = data.get("@graph", [data])
        for node in graphs:
            if isinstance(node, dict) and node.get("@type") == "ItemList":
                items = [i for i in node.get("itemListElement", []) if isinstance(i, dict)]
                break
        if items:
            break

    receipt["result_status"] = "MATCHES" if items else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    default_location = str(target.get("location_display") or "Remote")
    # slug -> company map from every DOM job anchor (the JSON-LD lists canonical
    # job ids while the DOM renders variant ids, so URL matching fails; and a
    # first-occurrence slug find can land outside the cards). For each anchor,
    # the nearest preceding /company/ link names the employer.
    slug_company: dict[str, str] = {}
    for m in re.finditer(r'href="/job/([a-z0-9-]+)/[0-9]+"', html):
        slug = m.group(1)
        if slug in slug_company:
            continue
        window = html[max(0, m.start() - 2500):m.start()]
        found = re.findall(r"/company/([a-z0-9-]+)", window)
        if found:
            slug_company[slug] = found[-1].replace("-", " ").title()
    candidates: list[dict[str, Any]] = []
    for item in items[: _registry_limit(target, 25)]:
        title = str(item.get("name") or "").strip()
        job_url = str(item.get("url") or "").strip()
        if not title or "/job/" not in job_url:
            continue
        org = target["name"]
        slug_m = re.search(r"/job/([a-z0-9-]+)/", job_url)
        if slug_m:
            org = slug_company.get(slug_m.group(1), org)
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "builtin",
            "source_class": "job_board",
            "source_identity": url,
            "organization": org,
            "title": title,
            "location_display": default_location,
            "workplace_type": _workplace_type(default_location),
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": job_url,
            "apply_url": job_url,
            "primary_evidence_url": job_url,
            "published_at": None,
            "updated_at": None,
            "content_hash": sha256_bytes(job_url.encode("utf-8")),
            "posting_text": str(item.get("description") or "")[:4000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _lever_posting_text(job: dict[str, Any]) -> str:
    parts = [str(job.get("description") or "")]
    for list_key in ("lists", "additional"):
        for section in job.get(list_key) or []:
            if isinstance(section, dict):
                parts.append(str(section.get("text") or section.get("content") or ""))
            elif isinstance(section, str):
                parts.append(section)
    return "\n".join(part for part in parts if part)


def _ashby_location(job: dict[str, Any]) -> str:
    location = job.get("location")
    if isinstance(location, str) and location:
        return location
    if isinstance(location, dict):
        return str(location.get("name") or location.get("displayName") or "Unknown")
    locations = job.get("locations")
    if isinstance(locations, list) and locations:
        first = locations[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return str(first.get("name") or first.get("displayName") or "Unknown")
    return "Unknown"


def _workplace_type(location: str) -> str:
    text = location.lower()
    if "buffalo" in text and "hybrid" in text:
        return "WNY_HYBRID"
    if "buffalo" in text:
        return "WNY_ONSITE"
    if "remote" in text:
        return "REMOTE"
    return "AMBIGUOUS"


def _relocation_required(location: str, content: str) -> bool:
    text = f"{location}\n{content}".lower()
    return "relocation required" in text or "must relocate" in text


def _source_locator_receipt(client: httpx.Client, target: dict[str, Any]) -> dict[str, Any]:
    provider = str(target.get("provider") or "source-locator")
    lane = str(target.get("lane") or "A")
    receipt = _base_receipt(lane, provider, target["name"], "source_locator")
    url = target["url"]
    _add_registry_evidence(receipt, target, url)
    receipt["request_summary"] = f"GET {url} source-locator hint only; no candidates admitted"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt)
        text = response.text.lower()
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Source-locator read failed: {type(exc).__name__}")
        return _finalize_receipt(receipt)
    hits = [term for term in SOURCE_LOCATOR_TERMS if term in text]
    receipt["result_status"] = "MATCHES" if hits else "NO_MATCHES"
    receipt["parser_result"] = "HINTS_ONLY"
    receipt["limitations"].append(
        "Aggregator/locator evidence is hint-only; candidates require primary-source readback."
    )
    if hits:
        receipt["limitations"].append("Observed primary-source locator terms: " + ", ".join(hits))
    return _finalize_receipt(receipt)


def _sam_receipt(target: dict[str, Any] | None = None) -> dict[str, Any]:
    target = target or {"name": "SAM.gov Opportunities"}
    receipt = _base_receipt("B", "sam.gov", target["name"], "federal_feed")
    api_key = os.getenv("SAM_GOV_API_KEY")
    _add_registry_evidence(receipt, target, "https://api.sam.gov/prod/opportunities/v2/search")
    receipt["request_summary"] = "SAM.gov opportunity probe; credential value redacted"
    if not api_key:
        receipt["result_status"] = "AUTH_REQUIRED"
        receipt["parser_result"] = "BLOCKED"
        receipt["limitations"].append("SAM_GOV_API_KEY is not present; no unauthenticated query was attempted.")
        return _finalize_receipt(receipt)
    url = "https://api.sam.gov/prod/opportunities/v2/search"
    # The v2 search API 404s without a bounded postedFrom/postedTo window.
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    params = {
        "api_key": api_key,
        "limit": "1",
        "postedFrom": (now - timedelta(days=30)).strftime("%m/%d/%Y"),
        "postedTo": now.strftime("%m/%d/%Y"),
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
            response = client.get(url, params=params)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(response.content[:MAX_RESPONSE_BYTES])
        if response.status_code != 200:
            receipt["result_status"] = "FEED_DOWN"
            receipt["parser_result"] = "ERROR"
            if response.status_code == 404 and not response.content:
                # GSA returns an empty 404 for a superseded key. Keys rotate every
                # 90 days (observed: a 10-month-stale key 404'd until replaced
                # 2026-08-12). Name the likely fix so the morning report can say it.
                receipt["limitations"].append(
                    "Empty 404 usually means the API key was superseded by SAM's "
                    "90-day rotation. Copy the current key from SAM.gov Account "
                    "Details into ~/.zshrc AND ~/workspace/experiments/.env."
                )
        elif len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
        else:
            data = response.json()
            total = data.get("totalRecords", data.get("totalrecords", 0))
            try:
                total_records = int(total)
            except (TypeError, ValueError):
                total_records = 0
            receipt["result_status"] = "MATCHES" if total_records > 0 else "NO_MATCHES"
            receipt["parser_result"] = "PARSED"
    except (httpx.HTTPError, ValueError) as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"SAM.gov probe failed: {type(exc).__name__}")
    return _finalize_receipt(receipt)


def _federal_page_candidates(target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    provider = str(target.get("provider") or "federal-primary")
    receipt = _base_receipt("B", provider, target["name"], "federal_feed")
    url = target["url"]
    _add_registry_evidence(receipt, target, url)
    receipt["request_summary"] = f"GET {url} federal primary source; no credentials"
    candidates: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url)
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            receipt["result_status"] = "INVALID_RESPONSE"
            receipt["parser_result"] = "SIZE_LIMIT"
            receipt["limitations"].append("Response exceeded bounded parser limit.")
            return _finalize_receipt(receipt), []
        text = response.text.lower()
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Federal primary-source read failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []
    keywords = [word.lower() for word in target.get("need_keywords", [])]
    hits = [word for word in keywords if word in text]
    receipt["result_status"] = "MATCHES" if hits else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    if hits:
        payload = {
            "lane": "B",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": provider,
            "source_identity": url,
            "organization": target["name"],
            "title": target.get("need_title", "Federal primary-source opportunity signal"),
            "location_display": "Federal notice or R&D signal; delivery model not applicable",
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": url,
            "apply_url": None,
            "primary_evidence_url": url,
            "published_at": None,
            "updated_at": None,
            "content_hash": receipt["content_sha256"],
            "posting_text": f"Observed primary-source keywords: {', '.join(hits)}",
            "fit_score": target.get("default_fit_score", 0.6),
        }
        payload["candidate_id"] = _candidate_id("candidate:b", payload)
        candidates.append(payload)
    return receipt, candidates


def _commercial_receipt(target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt = _base_receipt("C", "primary-company-source", target["name"], "primary_company_source")
    receipt["request_summary"] = f"GET {target['url']} primary source; no credentials"
    _add_registry_evidence(receipt, target, target["url"])
    candidates: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(target["url"])
        body = response.content[:MAX_RESPONSE_BYTES]
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        response.raise_for_status()
        text = response.text.lower()
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Primary-source read failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []
    keywords = [word.lower() for word in target.get("need_keywords", [])]
    hits = [word for word in keywords if word in text]
    receipt["result_status"] = "MATCHES" if hits else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    if hits:
        payload = {
            "lane": "C",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "primary-company-source",
            "source_identity": target["url"],
            "organization": target["name"],
            "title": target.get("need_title", "Primary-source need signal"),
            "location_display": "Commercial signal; delivery model unknown",
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "posting_url": target["url"],
            "apply_url": None,
            "primary_evidence_url": target["url"],
            "published_at": None,
            "updated_at": None,
            "content_hash": receipt["content_sha256"],
            "posting_text": f"Observed primary-source keywords: {', '.join(hits)}",
            "fit_score": target.get("default_fit_score", 0.65),
            "contact_state": "CONTACT_UNKNOWN",
            "unresolved_assumptions": ["Budget, buyer, and timing are unknown."],
        }
        payload["candidate_id"] = _candidate_id("candidate:c", payload)
        candidates.append(payload)
    return receipt, candidates


def _load_targets(skill_dir: Path) -> dict[str, Any]:
    return read_json(skill_dir / "config" / "target_accounts.json")


def _employment_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    provider = target.get("provider")
    if provider == "greenhouse":
        return _greenhouse_candidates(client, target)
    if provider == "lever":
        return _lever_candidates(client, target)
    if provider == "ashby":
        return _ashby_candidates(client, target)
    if provider == "builtin":
        return _builtin_candidates(client, target)
    receipt = _base_receipt("A", str(provider or "unknown"), target.get("name", "Unknown"), "employer_ats")
    _add_registry_evidence(receipt, target, target.get("primary_source_url"))
    receipt["result_status"] = "INVALID_REQUEST"
    receipt["parser_result"] = "UNSUPPORTED_PROVIDER"
    receipt["limitations"].append("Employment target provider is not supported by Stage 0 discovery.")
    return _finalize_receipt(receipt), []


def _federal_candidates(target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    provider = target.get("provider")
    if provider == "sam.gov":
        return _sam_receipt(target), []
    return _federal_page_candidates(target)




def sweep(
    *,
    skill_dir: Path,
    lanes: set[str],
    out_dir: Path,
    fixture_dir: Path | None = None,
    linkedin_evidence: Path | None = None,
    federal_evidence: Path | None = None,
    meetup_evidence: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if fixture_dir is not None:
        receipts, candidates = _fixture_sweep(fixture_dir, lanes)
    else:
        targets = _load_targets(skill_dir)
        receipts = []
        candidates = []
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False) as client:
            for target in targets.get("source_locators", []):
                if target.get("lane", "A") in lanes:
                    receipts.append(_source_locator_receipt(client, target))
            if "A" in lanes:
                if linkedin_evidence is not None:
                    receipt, rows = _linkedin_evidence_candidates(linkedin_evidence)
                    receipts.append(receipt)
                    candidates.extend(rows)
                else:
                    # No human capture supplied: honest AUTH_REQUIRED, never a silent skip.
                    receipts.append(_linkedin_required_receipt(False))
                for target in targets.get("employment", []):
                    receipt, rows = _employment_candidates(client, target)
                    receipts.append(receipt)
                    candidates.extend(rows)
        if "B" in lanes:
            for target in targets.get("federal", [{"name": "SAM.gov Opportunities", "provider": "sam.gov"}]):
                receipt, rows = _federal_candidates(target)
                receipts.append(receipt)
                candidates.extend(rows)
            if federal_evidence is not None:
                receipt, rows = _federal_website_receipt(federal_evidence)
                receipts.append(receipt)
                candidates.extend(rows)
        if "C" in lanes:
            receipts.append(_client_research_receipt(skill_dir))
            for target in targets.get("commercial", []):
                receipt, rows = _commercial_receipt(target)
                receipts.append(receipt)
                candidates.extend(rows)
    if "C" in lanes and meetup_evidence is not None:
        receipt, rows = _meetup_evidence_candidates(meetup_evidence)
        receipts.append(receipt)
        candidates.extend(rows)

    lane_summaries = []
    for lane in LANES:
        lane_receipts = [row for row in receipts if row["lane"] == lane]
        lane_candidates = [row for row in candidates if row["lane"] == lane]
        if lane not in lanes:
            status = "NOT_SEARCHED"
        elif any(row["result_status"] == "MATCHES" for row in lane_receipts):
            status = "MATCHES"
        elif any(row["result_status"] in {"FEED_DOWN", "AUTH_REQUIRED", "AUTH_FAILED"} for row in lane_receipts):
            status = lane_receipts[0]["result_status"]
        else:
            status = "NO_MATCHES"
        lane_summaries.append(
            {
                "lane": lane,
                "searched": lane in lanes,
                "result_status": status,
                "candidates_observed": len(lane_candidates),
                "source_receipt_ids": [row["receipt_id"] for row in lane_receipts],
            }
        )

    manifest = {
        "schema": "monitor_opportunities.discovery_run.v1",
        "run_id": stable_id("discovery", {"lanes": sorted(lanes), "receipts": receipts}),
        "generated_at": utc_now(),
        "mocked": False,
        "live": fixture_dir is None,
        "external_effects": False,
        "lanes_requested": sorted(lanes),
        "artifact_paths": {
            "source_receipts": str(out_dir / "source-receipts.jsonl"),
            "candidates": str(out_dir / "candidates.jsonl"),
            "lane_summaries": str(out_dir / "lane-summaries.json"),
        },
    }
    write_json(out_dir / "run-manifest.json", manifest)
    write_jsonl(out_dir / "source-receipts.jsonl", receipts)
    write_jsonl(out_dir / "candidates.jsonl", sorted(candidates, key=lambda row: row["candidate_id"]))
    write_json(out_dir / "lane-summaries.json", lane_summaries)
    return manifest
