"""Read-only source discovery with typed local receipts and no external effects."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger

from .receipts import base_receipt as _base_receipt, finalize_receipt as _finalize_receipt
from .required_source_receipts import (
    client_research_receipt as _client_research_receipt,
    federal_website_receipt as _federal_website_receipt,
    human_browser_required_receipt as _human_browser_required_receipt,
    linkedin_required_receipt as _linkedin_required_receipt,
    unavailable_required_source_receipt as _unavailable_required_source_receipt,
)
from .util import read_json, sha256_bytes, stable_id, utc_now, write_json, write_jsonl

from dotenv import load_dotenv

load_dotenv(override=False)

LANES = ("A", "B", "C")
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=3.0)
MAX_RESPONSE_BYTES = 1_500_000
MAX_EMPLOYER_ATS_RESPONSE_BYTES = 8_000_000
SOURCE_LOCATOR_TERMS = ("greenhouse", "lever", "ashby", "workday", "workable")
LINKEDIN_AUTOMATION_POLICY = "linkedin_no_automation"
LINKEDIN_AUTHORIZED_READ_ONLY_POLICY = "linkedin_authorized_read_only_no_actions"
MEETUP_AUTOMATION_POLICY = "meetup_authorized_read_only_no_rsvp_no_message"
GITHUB_INTELLIGENCE_POLICY = "github_read_only_no_mutation_no_outreach"
GITHUB_CORROBORATION_TYPES = {
    "profile_name_match",
    "linked_site_match",
    "organization_affiliation",
    "project_history_match",
    "human_confirmation",
}

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


def _linkedin_record_url(record: dict[str, Any]) -> str | None:
    url = str(
        record.get("primary_evidence_url")
        or record.get("posting_url")
        or record.get("job_url")
        or record.get("linkedin_url")
        or ""
    ).strip()
    return url or None


def _linkedin_record_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("primary_evidence_url", "posting_url", "job_url", "linkedin_url"):
        url = str(record.get(key) or "").strip()
        if url:
            urls.append(url)
    return list(dict.fromkeys(urls))


# LinkedIn's top-applicant collection renders each row as
# "<title>\n<title> with verification\n<employer>\n<location>", so a capture that
# reads positionally lands the accessibility echo of the title in `organization`
# and shifts the real employer down into `location` (#1483). Detect that shift
# structurally and put each value back in its own field.
LINKEDIN_VERIFICATION_SUFFIX = " with verification"


def _strip_verification_artifact(value: str) -> str:
    text = value.strip()
    lowered = text.lower()
    if lowered.endswith(LINKEDIN_VERIFICATION_SUFFIX):
        return text[: -len(LINKEDIN_VERIFICATION_SUFFIX)].strip()
    return text


def _is_title_echo(value: str, title: str) -> bool:
    """True when `value` is the row's title rather than an employer name.

    Only the accessibility echo is an echo: the value is the title itself, or
    the title plus the trailing verification artifact. A shorter value that
    merely happens to open the title (employer "Capgemini" under the title
    "Capgemini Invent - ...") is a real employer, not an echo.
    """
    candidate = _strip_verification_artifact(value).lower()
    normalized_title = title.strip().lower()
    if not candidate or not normalized_title:
        return False
    return candidate == normalized_title


def _employer_indistinguishable_from_title(employer: str, title: str) -> bool:
    """True when a recovered employer cannot be told apart from a title fragment.

    An employer name that opens the role title carries no evidence that the
    field shift was undone correctly, so the row is dropped rather than emitted
    with an organization that may still be the title.
    """
    candidate = employer.strip().lower()
    normalized_title = title.strip().lower()
    return bool(candidate) and normalized_title.startswith(candidate)


# Aggregator vocabulary for LinkedIn organization fields. A board or aggregator
# name ("Find Data Science Jobs") is a listing surface, not the hiring employer,
# so it must never be surfaced as the organization. Token-level matching, not
# substring or regex classification: "Jobcase" and "Careerbuilder" tokenize to a
# single token and are therefore not treated as boards.
_JOB_BOARD_TOKENS = frozenset(
    {
        "job",
        "jobs",
        "career",
        "careers",
        "hiring",
        "listing",
        "listings",
        "opening",
        "openings",
        "vacancy",
        "vacancies",
        "recruiting",
        "recruitment",
        "staffing",
    }
)

# Named boards whose brand carries no aggregator token of its own.
_KNOWN_JOB_BOARDS = frozenset(
    {
        "linkedin",
        "indeed",
        "ziprecruiter",
        "glassdoor",
        "monster",
        "dice",
        "simplyhired",
        "hiddenjobs",
        "wellfound",
        "lever",
        "greenhouse",
        "workday",
    }
)


def _name_tokens(value: str) -> list[str]:
    """Lowercase alphanumeric word tokens of a name, punctuation dropped."""
    return ["".join(ch for ch in part if ch.isalnum()).lower() for part in value.split()]


def _is_job_board_name(value: str) -> bool:
    """True when `value` names a job board or aggregator rather than an employer."""
    tokens = [token for token in _name_tokens(value) if token]
    if not tokens:
        return False
    if any(token in _KNOWN_JOB_BOARDS for token in tokens):
        return True
    return any(token in _JOB_BOARD_TOKENS for token in tokens)


def _realign_linkedin_row(record: dict[str, Any], title: str, organization: str, location: str) -> tuple[str, str]:
    """Return (organization, location) with the #1483 field shift undone.

    The employer is taken from an explicit employer field when the capture
    supplied one; otherwise, when `organization` is only an echo of the title,
    the value that was shifted into `location` is the real employer and the row
    carries no usable location.
    """
    organization = _strip_verification_artifact(organization)
    if _is_job_board_name(organization):
        # A board name is never the employer. Recover an explicit employer field
        # when the capture supplied one; otherwise the row has no employer and is
        # dropped by the caller rather than ranked under the board's name.
        for key in ("employer", "company_name", "company", "hiring_organization", "organization_name"):
            explicit = _strip_verification_artifact(str(record.get(key) or ""))
            if explicit and not _is_title_echo(explicit, title) and not _is_job_board_name(explicit):
                return explicit, location
        return "", location
    if not _is_title_echo(organization, title):
        return organization, location
    for key in ("employer", "company_name", "company", "hiring_organization", "organization_name"):
        explicit = _strip_verification_artifact(str(record.get(key) or ""))
        if explicit and not _is_title_echo(explicit, title) and not _is_job_board_name(explicit):
            return explicit, location
    shifted = _strip_verification_artifact(location)
    if (
        shifted
        and not _is_title_echo(shifted, title)
        and not _employer_indistinguishable_from_title(shifted, title)
        and not _is_job_board_name(shifted)
    ):
        return shifted, "Unknown"
    return "", location


def _linkedin_evidence_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("A", "linkedin", "Human-supplied LinkedIn evidence", "human_supplied_linkedin")
    receipt["required_source_id"] = "linkedin_top_applicant"
    receipt["channel"] = "browser_human_supplied"
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
    receipt["evidence_refs"] = list(
        dict.fromkeys(
            [
                *receipt["evidence_refs"],
                *[
                    url
                    for record in records
                    for url in _linkedin_record_urls(record)
                ],
            ]
        )
    )
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for record in records:
        title = str(record.get("title") or record.get("role") or "").strip()
        organization = str(record.get("organization") or record.get("company") or "").strip()
        location = str(record.get("location") or record.get("location_display") or "Unknown").strip()
        organization, location = _realign_linkedin_row(record, title, organization, location)
        if not title:
            receipt["limitations"].append(
                "One LinkedIn evidence record lacked a title and could not be ranked."
            )
            continue
        if not organization:
            # A top-applicant role must still reach ranking when its employer cannot be
            # parsed; surface it with an unknown organization instead of discarding it.
            organization = "Unknown"
            receipt["limitations"].append(
                f"One LinkedIn evidence record lacked a recoverable employer organization and was "
                f"ranked with organization marked unknown: {title[:80]!r}."
            )
        location = location or "Unknown"
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
        primary_url = _linkedin_record_url(record)
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
            "workplace_type": _workplace_type(location, evidence_text),
            "relocation_required": _relocation_required(location, evidence_text),
            "clearance_required": False,
            "posting_url": primary_url,
            "apply_url": None,
            "primary_evidence_url": primary_url or _local_file_ref(path),
            "published_at": record.get("published_at") or record.get("observed_at"),
            "updated_at": record.get("updated_at") or record.get("observed_at"),
            "content_hash": receipt["content_sha256"],
            "posting_text": evidence_text[:14000],
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
        # Easy Apply = LinkedIn's one-click lane. A row-level signal the response
        # ranker rewards and the morning report surfaces as a fast-apply option.
        if _coerce_bool(record.get("easy_apply") or record.get("easy_apply_signal")):
            payload["easy_apply"] = True
        payload["candidate_id"] = _candidate_id("candidate:a:linkedin", payload)
        candidates.append(payload)
    return receipt, candidates


def _required_browser_evidence_receipt(
    path: Path,
    *,
    provider: str,
    required_source_id: str,
    target: str,
    source_class: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("A", provider, target, source_class)
    receipt["required_source_id"] = required_source_id
    receipt["channel"] = "browser_human_supplied"
    receipt["automation_policy"] = "read_only_browser_capture_no_apply_no_message"
    receipt["request_summary"] = (
        f"Read local browser evidence artifact {path.name}; source-health coverage only, "
        "no apply, save, login, message, or submit action"
    )
    receipt["response_status"] = None
    receipt["content_type"] = "application/json" if path.suffix.lower() == ".json" else "text/plain"
    receipt["response_bytes"] = len(raw)
    receipt["content_sha256"] = sha256_bytes(raw)
    receipt["evidence_refs"] = [_local_file_ref(path)]
    receipt["limitations"].extend(
        [
            "Browser evidence satisfies required-source coverage only.",
            "Aggregator/locator rows are hint-only and are not independently admitted as ranked opportunities.",
            f"Automation policy: {receipt['automation_policy']}.",
        ]
    )
    try:
        payload = read_json(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Browser source artifact could not be parsed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []
    records = payload.get("records") if isinstance(payload, dict) else []
    records = [row for row in records if isinstance(row, dict)] if isinstance(records, list) else []
    text = str(payload.get("text") or "") if isinstance(payload, dict) else ""
    receipt["parser_result"] = "PARSED"
    receipt["result_status"] = "MATCHES" if records or text.strip() else "NO_MATCHES"
    if isinstance(payload, dict) and payload.get("url"):
        receipt["evidence_refs"].append(str(payload["url"]))
    receipt["limitations"].append(
        f"{len(records)} browser records observed; 0 candidates admitted from {provider} without primary-source readback."
    )
    return _finalize_receipt(receipt), []


SOCIAL_SKILL_TERMS = (
    "agentic",
    "ai engineer",
    "artificial intelligence",
    "machine learning",
    "llm",
    "automation",
    "document extraction",
    "data extraction",
    "contract",
    "consulting",
    "part-time",
    "fractional",
    "buffalo",
    "remote",
    "python",
    "react",
    "node",
)
SOCIAL_OPPORTUNITY_INTENT_TERMS = (
    "apply",
    "contract",
    "consulting",
    "fractional",
    "freelance",
    "hiring",
    "job alert",
    "job opening",
    "job opportunity",
    "job post",
    "job posting",
    "jobs",
    "opening",
    "opportunity",
    "part-time",
    "position",
    "proposal",
    "recruiter",
    "rfp",
    "role",
    "seeking",
)
SOCIAL_OPPORTUNITY_INTENT_PATTERNS = (
    re.compile(
        r"(?<![a-z0-9])(?:team|company|client|customer|organization|agency|firm|office|group|shop)"
        r"\s+need(?:s|ed|ing)?(?![a-z0-9])"
    ),
    re.compile(
        r"(?<![a-z0-9])need(?:s|ed|ing)?\s+"
        r"(?:ai|automation|document extraction|data extraction|workflow|python|react|node|engineer|consultant|developer)"
    ),
    re.compile(r"(?<![a-z0-9])look(?:ing)? for(?![a-z0-9])"),
)
SOCIAL_POLICY = "read_only_message_evidence_no_send_no_reply_no_apply"


def _load_message_records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except ValueError:
        record = _text_evidence_record(raw)
        return [record] if record else []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("messages", "emails", "threads", "records", "items", "opportunities"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _message_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("title"),
        record.get("subject"),
        record.get("role"),
        record.get("company"),
        record.get("organization"),
        record.get("channel"),
        record.get("sender"),
        record.get("author"),
        record.get("body"),
        record.get("content"),
        record.get("text"),
        record.get("snippet"),
        record.get("raw_text_excerpt"),
    ]
    return "\n".join(str(part) for part in parts if part)


def _message_url(record: dict[str, Any]) -> str | None:
    for key in ("url", "permalink", "message_url", "thread_url", "job_url", "posting_url", "apply_url"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return None


def _message_hits(record: dict[str, Any]) -> list[str]:
    low = f" {_message_text(record).lower()} "
    hits = []
    for term in SOCIAL_SKILL_TERMS:
        if term in {"llm"}:
            matched = re.search(r"(?<![a-z0-9])llms?(?![a-z0-9])", low) is not None
        elif term == "python":
            matched = re.search(r"(?<![a-z0-9])python(?![a-z0-9])", low) is not None
        elif term == "react":
            matched = re.search(r"(?<![a-z0-9])react(?![a-z0-9])", low) is not None
        elif term == "node":
            matched = re.search(r"(?<![a-z0-9])node(?:\\.js)?(?![a-z0-9])", low) is not None
        else:
            matched = term in low
        if matched:
            hits.append(term)
    return hits


def _message_opportunity_intent_hits(record: dict[str, Any]) -> list[str]:
    low = f" {_message_text(record).lower()} "
    hits = [term for term in SOCIAL_OPPORTUNITY_INTENT_TERMS if term in low]
    hits.extend(pattern.pattern for pattern in SOCIAL_OPPORTUNITY_INTENT_PATTERNS if pattern.search(low))
    return hits


def _message_evidence_candidates(
    path: Path,
    *,
    provider: str,
    required_source_id: str,
    target: str,
    source_class: str,
    channel: str,
    automation_policy: str = SOCIAL_POLICY,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("C", provider, target, source_class)
    receipt["required_source_id"] = required_source_id
    receipt["channel"] = channel
    receipt["automation_policy"] = automation_policy
    receipt["external_effects"] = False
    receipt["request_summary"] = (
        f"Read local {provider} opportunity evidence artifact {path.name}; "
        "no send, reply, DM, apply, archive, label, or platform mutation"
    )
    receipt["response_status"] = None
    receipt["content_type"] = "application/json" if path.suffix.lower() == ".json" else "text/plain"
    receipt["response_bytes"] = len(raw)
    receipt["content_sha256"] = sha256_bytes(raw)
    receipt["evidence_refs"] = [_local_file_ref(path)]
    receipt["limitations"].extend(
        [
            f"{provider} evidence is a read-only opportunity signal.",
            "Rows are admitted only when the captured message text contains explicit opportunity terms.",
            f"Automation policy: {automation_policy}.",
        ]
    )
    try:
        records = _load_message_records(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Local {provider} artifact could not be parsed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    candidates: list[dict[str, Any]] = []
    skipped = 0
    for index, record in enumerate(records, start=1):
        hits = _message_hits(record)
        intent_hits = _message_opportunity_intent_hits(record)
        if not hits or not intent_hits:
            skipped += 1
            continue
        text = _message_text(record)
        title = str(record.get("title") or record.get("subject") or record.get("role") or "").strip()
        if not title:
            title = f"{provider.title()} opportunity signal #{index}"
        organization = str(
            record.get("organization")
            or record.get("company")
            or record.get("client")
            or record.get("sender")
            or record.get("author")
            or record.get("channel")
            or target
        ).strip()
        evidence_url = _message_url(record) or _local_file_ref(path)
        location = str(record.get("location") or record.get("location_display") or "Opportunity channel; delivery model unknown").strip()
        payload = {
            "lane": "C",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": provider,
            "source_class": source_class,
            "source_identity": str(record.get("id") or record.get("message_id") or evidence_url),
            "automation_policy": automation_policy,
            "organization": organization,
            "title": title,
            "location_display": location,
            "workplace_type": _workplace_type(location, text),
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": evidence_url,
            "apply_url": str(record.get("apply_url") or record.get("job_url") or "") or None,
            "primary_evidence_url": evidence_url,
            "published_at": record.get("published_at") or record.get("sent_at") or record.get("timestamp") or record.get("observed_at"),
            "updated_at": record.get("updated_at") or record.get("observed_at"),
            "content_hash": sha256_bytes(json.dumps(record, sort_keys=True).encode("utf-8")),
            "posting_text": text[:14000],
            "fit_score": float(record.get("fit_score") or min(0.72, 0.36 + 0.04 * len(hits))),
            "contact_state": "CONTACT_PRESENT"
            if (record.get("sender") or record.get("author") or record.get("contact"))
            else "CONTACT_UNKNOWN",
            "unresolved_assumptions": [
                "Message evidence is a lead; primary-source opportunity details must be checked before any application or outreach.",
                "No Slack, Discord, Gmail, LinkedIn, ATS, or Meetup external action is authorized by this evidence.",
            ],
            "matched_skill_terms": hits,
            "matched_opportunity_terms": intent_hits,
        }
        payload["candidate_id"] = _candidate_id(f"candidate:c:{provider}", payload)
        candidates.append(payload)
        receipt["evidence_refs"].append(evidence_url)
    receipt["result_status"] = "MATCHES" if candidates else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt["evidence_refs"] = list(dict.fromkeys(receipt["evidence_refs"]))
    receipt["limitations"].append(
        f"{len(records)} {provider} records inspected; {len(candidates)} opportunity candidates emitted; {skipped} skipped."
    )
    finalized = _finalize_receipt(receipt)
    for candidate in candidates:
        candidate["source_receipt_id"] = finalized["receipt_id"]
    return finalized, candidates


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


def _load_github_repo_records(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("repositories", "repos", "records", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        return [payload]
    return []


def _github_repo_url(record: dict[str, Any]) -> str | None:
    value = str(
        record.get("repo_url")
        or record.get("html_url")
        or record.get("url")
        or ""
    ).strip()
    if value:
        return value
    repo = str(record.get("repo") or record.get("full_name") or "").strip()
    if "/" in repo:
        return f"https://github.com/{repo}"
    return None


def _github_contacts(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, default_role in (
        ("contacts", "repository_participant"),
        ("owners", "repository_owner"),
        ("maintainers", "repository_maintainer"),
        ("contributors", "repository_contributor"),
        ("commit_authors", "commit_author"),
        ("issue_participants", "issue_participant"),
        ("pr_participants", "pull_request_participant"),
        ("mentioned_contacts", "mentioned_contact"),
    ):
        value = record.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    rows.append({"role": default_role, **item})
                elif isinstance(item, str) and item.strip():
                    rows.append({"role": default_role, "handle": item.strip()})
        elif isinstance(value, str) and value.strip():
            rows.append({"role": default_role, "handle": value.strip()})
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("name") or "").strip()
        handle = str(row.get("handle") or row.get("login") or row.get("username") or "").strip().lstrip("@")
        key = f"handle:{handle.lower()}" if handle else f"name:{name.lower()}"
        if key in seen or not (name or handle):
            continue
        seen.add(key)
        row["handle"] = handle
        deduped.append(row)
    return deduped


def _github_contact_subject(contact: dict[str, Any], *, mapping_status: str = "hypothesis") -> str:
    name = str(contact.get("name") or "").strip()
    handle = str(contact.get("handle") or "").strip().lstrip("@")
    if name and handle and mapping_status == "corroborated":
        return f"{name} (@{handle})"
    if handle:
        return f"GitHub @{handle}"
    if name:
        return name
    return "GitHub @unknown"


def _github_contact_evidence_refs(
    contact: dict[str, Any], repo_url: str | None
) -> list[str]:
    refs: list[str] = []
    for key in ("evidence_url", "profile_url", "commit_url", "issue_url", "pull_request_url", "discussion_url"):
        value = str(contact.get(key) or "").strip()
        if value:
            refs.append(value)
    refs.extend(_as_str_list(contact.get("evidence_refs")))
    if repo_url:
        refs.append(repo_url)
    return list(dict.fromkeys(refs))


def _github_contact_corroboration(
    contact: dict[str, Any], *, contact_evidence_refs: list[str]
) -> list[dict[str, Any]]:
    raw = contact.get("corroboration")
    if raw is None:
        raw = contact.get("corroboration_refs")
    if raw is None:
        return []
    rows = raw if isinstance(raw, list) else [raw]
    allowed_refs = set(contact_evidence_refs)
    out: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            kind = str(item.get("type") or item.get("kind") or "").strip()
            refs = _as_str_list(item.get("evidence_refs"))
            for key in ("evidence_url", "profile_url", "source_url"):
                value = str(item.get(key) or "").strip()
                if value:
                    refs.append(value)
            refs = list(dict.fromkeys(refs))
            note = str(item.get("note") or item.get("description") or "").strip()
        else:
            kind = "untyped"
            refs = []
            note = str(item).strip()
        out.append(
            {
                "type": kind,
                "evidence_refs": refs,
                "note": note,
                "resolved": bool(kind in GITHUB_CORROBORATION_TYPES and refs and set(refs) <= allowed_refs),
            }
        )
    return out


def _github_evidence_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = path.read_bytes()
    receipt = _base_receipt("C", "github", "GitHub repository contact intelligence", "github_repo_intelligence")
    receipt["automation_policy"] = GITHUB_INTELLIGENCE_POLICY
    receipt["channel"] = "read_only_local_artifact"
    receipt["request_summary"] = (
        f"Read local GitHub repository intelligence artifact {path.name}; no clone execution, issue mutation, "
        "star, fork, follow, connection, message, or application action"
    )
    receipt["content_type"] = "application/json"
    receipt["response_bytes"] = len(raw)
    receipt["content_sha256"] = sha256_bytes(raw)
    receipt["evidence_refs"] = [_local_file_ref(path)]
    receipt["limitations"].extend(
        [
            "GitHub repository intelligence is contact/source intelligence, not outreach authority.",
            "Handle-to-person mappings remain hypotheses unless the artifact supplies corroborating evidence.",
            f"Automation policy: {GITHUB_INTELLIGENCE_POLICY}.",
        ]
    )
    try:
        records = _load_github_repo_records(path)
        payload = read_json(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Local GitHub artifact could not be parsed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    degradations: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("degradations"), list):
        degradations = [row for row in payload["degradations"] if isinstance(row, dict)]
    if degradations:
        messages = []
        for item in degradations[:6]:
            stage = str(item.get("stage") or "unknown_stage")
            error = str(item.get("error") or item.get("message") or "unspecified degradation")
            messages.append(f"{stage}: {error[:220]}")
        receipt["limitations"].append("GitHub producer degraded: " + "; ".join(messages))
        lowered = " ".join(messages).lower()
        if "rate limit" in lowered or "rate_limit" in lowered or "http 429" in lowered:
            receipt["parser_result"] = "DEGRADED"
            receipt["result_status"] = "RATE_LIMITED"
            return _finalize_receipt(receipt), []
        if not records:
            receipt["parser_result"] = "DEGRADED"
            receipt["result_status"] = "INVALID_RESPONSE"
            return _finalize_receipt(receipt), []

    candidates: list[dict[str, Any]] = []
    for record in records:
        repo = str(record.get("repo") or record.get("full_name") or record.get("name") or "").strip()
        repo_url = _github_repo_url(record)
        if not repo and repo_url:
            repo = repo_url.rstrip("/").removeprefix("https://github.com/")
        contacts = _github_contacts(record)
        if not repo or not repo_url or not contacts:
            continue
        org = str(
            record.get("organization")
            or record.get("company")
            or record.get("owner")
            or repo.split("/", 1)[0]
        ).strip()
        repository_analysis = record.get("repository_analysis")
        analysis_refs = (
            _as_str_list(repository_analysis.get("evidence_refs"))
            if isinstance(repository_analysis, dict)
            else []
        )
        matched_terms = (
            _as_str_list(repository_analysis.get("matched_terms"))
            if isinstance(repository_analysis, dict)
            else []
        )
        relevance_quality_status = (
            str(repository_analysis.get("relevance_quality_status") or "MISSING_RELEVANCE_QUALITY").strip()
            if isinstance(repository_analysis, dict)
            else "MISSING_RELEVANCE_QUALITY"
        )
        relevance_quality_reasons = (
            _as_str_list(repository_analysis.get("relevance_quality_reasons"))
            if isinstance(repository_analysis, dict)
            else []
        )
        relevance_quality_warnings = (
            _as_str_list(repository_analysis.get("relevance_quality_warnings"))
            if isinstance(repository_analysis, dict)
            else []
        )
        observed_via = _as_str_list(record.get("observed_via"))
        explicit_repo_seed = any(item.startswith("repo:") for item in observed_via)
        confirmed_owner_contact = any(
            any(
                isinstance(row, dict) and row.get("type") == "human_confirmation"
                for row in (contact.get("corroboration") or [])
            )
            for contact in contacts
            if isinstance(contact, dict)
        )
        github_fit_score = 0.58
        if explicit_repo_seed:
            github_fit_score += 0.16
        if confirmed_owner_contact:
            github_fit_score += 0.03
        github_fit_score += min(len(matched_terms), 8) * 0.015
        if relevance_quality_status == "REVIEW_RELEVANCE":
            github_fit_score = min(github_fit_score, 0.52)
        elif relevance_quality_status != "STRONG_RELEVANCE":
            github_fit_score = min(github_fit_score, 0.42)
        github_fit_score = min(0.9, round(github_fit_score, 3))
        snippets = []
        if isinstance(repository_analysis, dict) and isinstance(repository_analysis.get("readme_snippets"), list):
            snippets = [
                str(row.get("snippet") or "").strip()
                for row in repository_analysis["readme_snippets"]
                if isinstance(row, dict) and str(row.get("snippet") or "").strip()
            ]
        activity_snippets = []
        if isinstance(repository_analysis, dict) and isinstance(repository_analysis.get("activity_snippets"), list):
            for item in repository_analysis["activity_snippets"]:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind") or "activity")
                for snippet in item.get("snippets") or []:
                    if isinstance(snippet, dict) and str(snippet.get("snippet") or "").strip():
                        activity_snippets.append(f"{kind}: {str(snippet['snippet']).strip()}")
        repo_refs = [repo_url, *_as_str_list(record.get("evidence_refs")), *analysis_refs]
        receipt["evidence_refs"].extend(repo_refs)
        github_contact_hypotheses = []
        for contact in contacts:
            evidence_refs = _github_contact_evidence_refs(contact, repo_url)
            receipt["evidence_refs"].extend(evidence_refs)
            role = str(contact.get("role") or "repository_participant").strip()
            handle = str(contact.get("handle") or "").strip().lstrip("@")
            name = str(contact.get("name") or "").strip()
            corroboration = _github_contact_corroboration(
                contact,
                contact_evidence_refs=evidence_refs,
            )
            mapping_status = "corroborated" if name and handle and any(row["resolved"] for row in corroboration) else "hypothesis"
            subject = _github_contact_subject(contact, mapping_status=mapping_status)
            github_contact_hypotheses.append(
                {
                    "subject": subject,
                    "name": name,
                    "handle": handle,
                    "role": role,
                    "relationship": str(contact.get("relationship") or "adjacent_contact"),
                    "evidence_refs": evidence_refs,
                    "corroboration": corroboration,
                    "mapping_status": mapping_status,
                }
            )
        posting_text = "\n".join(
            [
                f"GitHub repo intelligence: {repo}",
                f"Repository URL: {repo_url}",
                f"Organization/context: {org}",
                "Description: " + str(record.get("description") or "")[:1000],
                "Topics: " + ", ".join(_as_str_list(record.get("topics"))[:12]),
                "Matched repository terms: " + ", ".join(matched_terms[:12]),
                "Repository relevance quality: " + relevance_quality_status,
                "Repository relevance reasons: " + " | ".join(relevance_quality_reasons[:4])[:1000],
                "Repository relevance warnings: " + ", ".join(relevance_quality_warnings[:8]),
                "README evidence snippets: " + " | ".join(snippets[:4])[:1200],
                "Recent activity snippets: " + " | ".join(activity_snippets[:4])[:1200],
                "Contacts: " + "; ".join(row["subject"] for row in github_contact_hypotheses[:12]),
                "No external effects are authorized.",
            ]
        ).strip()
        payload = {
            "lane": "C",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "github_repo_intelligence",
            "source_class": "github_repo_intelligence",
            "source_identity": repo_url,
            "automation_policy": GITHUB_INTELLIGENCE_POLICY,
            "organization": org or repo,
            "title": f"{repo} GitHub repository intelligence",
            "location_display": "GitHub source-intel; delivery model not applicable",
            "workplace_type": "NOT_APPLICABLE",
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": repo_url,
            "apply_url": None,
            "primary_evidence_url": repo_url,
            "published_at": record.get("created_at"),
            "updated_at": record.get("pushed_at") or record.get("updated_at"),
            "content_hash": sha256_bytes(json.dumps(record, sort_keys=True).encode("utf-8")),
            "posting_text": posting_text[:14000],
            "fit_score": float(record.get("fit_score") or github_fit_score),
            "contact_state": "CONTACT_PRESENT",
            "github_repo": repo,
            "github_repo_url": repo_url,
            "github_contact_hypotheses": github_contact_hypotheses,
            "adjacent_contacts": [row["subject"] for row in github_contact_hypotheses],
            "github_evidence_refs": list(dict.fromkeys(repo_refs)),
            "github_observed_via": observed_via,
            "github_explicit_repo_seed": explicit_repo_seed,
            "github_repository_analysis": repository_analysis if isinstance(repository_analysis, dict) else {},
            "github_relevance_quality_status": relevance_quality_status,
            "github_relevance_quality_reasons": relevance_quality_reasons,
            "github_relevance_quality_warnings": relevance_quality_warnings,
            "external_effects": False,
            "unresolved_assumptions": [
                "GitHub participation does not prove current employment, availability, or willingness to reconnect.",
                "Handle-to-person mappings require corroboration before human outreach.",
                "No GitHub, LinkedIn, email, or application action is authorized by this source-intel candidate.",
            ],
        }
        payload["candidate_id"] = _candidate_id("candidate:c:github", payload)
        candidates.append(payload)
    receipt["evidence_refs"] = list(dict.fromkeys(receipt["evidence_refs"]))
    receipt["result_status"] = "MATCHES" if candidates else "NO_MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt["limitations"].append(
        f"{len(records)} GitHub repository records inspected; {len(candidates)} source-intel candidates emitted."
    )
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


def _parse_employer_ats_json_response(
    response: httpx.Response,
    receipt: dict[str, Any],
) -> tuple[Any | None, str | None]:
    """Parse ATS JSON even when the retained evidence preview is capped.

    The response body is already materialized by httpx. The byte cap controls
    retained evidence/hash size; it must not by itself convert a valid HTTP 200
    employer board into INVALID_RESPONSE.
    """

    oversized = len(response.content) > MAX_EMPLOYER_ATS_RESPONSE_BYTES
    try:
        data = response.json()
    except ValueError as exc:
        receipt["result_status"] = "INVALID_RESPONSE"
        receipt["parser_result"] = "JSON_PARSE_ERROR_OVERSIZE" if oversized else "ERROR"
        if oversized:
            receipt["limitations"].append(
                "Employer ATS response exceeded bounded evidence preview and JSON parsing failed; "
                f"response_bytes={len(response.content)}, "
                f"retained_bytes={MAX_EMPLOYER_ATS_RESPONSE_BYTES}, error={type(exc).__name__}."
            )
        else:
            receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return None, None
    if oversized:
        receipt["limitations"].append(
            "Employer ATS response exceeded bounded evidence preview but parsed as full JSON; "
            f"response_bytes={len(response.content)}, "
            f"retained_bytes={MAX_EMPLOYER_ATS_RESPONSE_BYTES}."
        )
        return data, "PARSED_OVERSIZE"
    return data, "PARSED"


FIXTURE_DATE_FIELDS = ("published_at", "updated_at", "observed_at")


def _parse_fixture_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def shift_fixture_dates(rows: list[dict[str, Any]], now: datetime | None = None) -> timedelta:
    """Re-date fixture rows relative to now, preserving the gaps between them.

    A fixture is dated when it is authored, so the recency gate silently ages it
    out: on 2026-08-17 every candidate in the committed discovery fixture was
    exactly 14 days old, the shortlist came back empty, and 17 tests that need
    one report-visible opportunity failed for a reason that had nothing to do
    with the code under test. Shifting by (now - newest) keeps every relative
    age intact, so a row authored as deliberately stale stays stale.
    """

    now = now or datetime.now(timezone.utc)
    stamps = [
        parsed
        for row in rows
        for field in FIXTURE_DATE_FIELDS
        if (parsed := _parse_fixture_date(row.get(field))) is not None
    ]
    if not stamps:
        return timedelta(0)
    offset = now - max(stamps)
    for row in rows:
        for field in FIXTURE_DATE_FIELDS:
            parsed = _parse_fixture_date(row.get(field))
            if parsed is not None:
                row[field] = (parsed + offset).isoformat().replace("+00:00", "Z")
    return offset


def _fixture_sweep(fixture_dir: Path, lanes: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixture = read_json(fixture_dir / "discovery-run.json")
    receipts = [row for row in fixture["source_receipts"] if row["lane"] in lanes]
    candidates = [row for row in fixture["candidates"] if row["lane"] in lanes]
    shift_fixture_dates(candidates + receipts)
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
    receipt["required_source_id"] = "greenhouse"
    receipt["channel"] = "api"
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_EMPLOYER_ATS_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Greenhouse board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        data, parser_result = _parse_employer_ats_json_response(response, receipt)
        if data is None:
            return _finalize_receipt(receipt), []
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    jobs = jobs if isinstance(jobs, list) else []
    receipt["result_status"] = "MATCHES" if jobs else "NO_MATCHES"
    receipt["parser_result"] = parser_result or "PARSED"
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
            "workplace_type": _workplace_type(location, str(job.get("content") or "")),
            "relocation_required": "relocation" in location.lower() and "required" in location.lower(),
            "clearance_required": False,
            "posting_url": posting_url,
            "apply_url": posting_url,
            "primary_evidence_url": posting_url or url,
            "published_at": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": (job.get("content") or "")[:14000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _lever_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "lever", target["name"], "employer_ats")
    receipt["channel"] = "api"
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_EMPLOYER_ATS_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Lever board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        if len(response.content) > MAX_EMPLOYER_ATS_RESPONSE_BYTES:
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
    for job in _prioritized_jobs_for_target(target, postings, default_limit=20):
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
            "workplace_type": _workplace_type(location, posting_text),
            "relocation_required": _relocation_required(location, posting_text),
            "clearance_required": False,
            "posting_url": hosted_url,
            "apply_url": job.get("applyUrl") or hosted_url,
            "primary_evidence_url": hosted_url,
            "published_at": str(job.get("createdAt")) if job.get("createdAt") is not None else None,
            "updated_at": str(job.get("updatedAt")) if job.get("updatedAt") is not None else None,
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": posting_text[:14000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


def _ashby_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = target["slug"]
    receipt = _base_receipt("A", "ashby", target["name"], "employer_ats")
    receipt["required_source_id"] = "ashby"
    receipt["channel"] = "api"
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    _add_registry_evidence(receipt, target, target.get("primary_source_url"), url)
    receipt["request_summary"] = f"GET {url} with no credentials; response capped"
    try:
        response = client.get(url)
        receipt["response_status"] = response.status_code
        receipt["content_type"] = response.headers.get("content-type")
        body = response.content[:MAX_EMPLOYER_ATS_RESPONSE_BYTES]
        receipt["response_bytes"] = len(response.content)
        receipt["content_sha256"] = sha256_bytes(body)
        if response.status_code == 404:
            receipt["result_status"] = "INVALID_REQUEST"
            receipt["parser_result"] = "NO_PARSE"
            receipt["limitations"].append("Ashby board slug did not route.")
            return _finalize_receipt(receipt), []
        response.raise_for_status()
        data, parser_result = _parse_employer_ats_json_response(response, receipt)
        if data is None:
            return _finalize_receipt(receipt), []
    except httpx.HTTPError as exc:
        receipt["result_status"] = "FEED_DOWN"
        receipt["parser_result"] = "ERROR"
        receipt["limitations"].append(f"Read-only request failed: {type(exc).__name__}")
        return _finalize_receipt(receipt), []

    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    receipt["result_status"] = "MATCHES" if jobs else "NO_MATCHES"
    receipt["parser_result"] = parser_result or "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in _prioritized_jobs_for_target(target, jobs, default_limit=20):
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
            "workplace_type": _workplace_type(
                location,
                str(job.get("descriptionHtml") or job.get("descriptionPlain") or ""),
                str(job.get("workplaceType") or ""),
            ),
            "relocation_required": _relocation_required(location, str(job)),
            "clearance_required": False,
            "posting_url": posting_url,
            "apply_url": job.get("applyUrl") or posting_url,
            "primary_evidence_url": posting_url,
            "published_at": job.get("publishedDate"),
            "updated_at": job.get("updatedAt"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": (job.get("descriptionHtml") or job.get("descriptionPlain") or "")[:14000],
            "fit_score": target.get("default_fit_score", 0.5),
        }
        payload["candidate_id"] = _candidate_id("candidate:a", payload)
        candidates.append(payload)
    return receipt, candidates


# Workday tenants split across data centers; these cover the vast majority of
# US employer tenants. Sites are the board name inside a tenant.
# Bounded to the highest-probability coordinates: wd1/wd5 host the large
# majority of US tenants, and "ExternalCareers" is Workday's default external
# site. Ordered most-likely first; the adapter early-exits on the first hit.
_WORKDAY_DATACENTERS = ("wd1", "wd5")
_WORKDAY_SITE_HINTS = ("ExternalCareers", "External", "Careers", "External_Careers")


def _workday_job_url(host: str, site: str, external_path: str) -> str:
    path = external_path if external_path.startswith("/") else f"/{external_path}"
    return f"https://{host}/{site}{path}"


def _keyword_in_text(keyword: str, text: str) -> bool:
    needle = keyword.strip().lower()
    if not needle:
        return False
    haystack = text.lower()
    if len(needle) <= 3 and needle.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack


def _target_keywords(target: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("title_keywords", "need_keywords"):
        raw = target.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
    return [item for item in values if item.strip()]


def _keyword_match_count(target: dict[str, Any], *parts: object) -> int:
    text = "\n".join(str(part or "") for part in parts)
    return sum(1 for keyword in _target_keywords(target) if _keyword_in_text(keyword, text))


def _keyword_match_score(target: dict[str, Any], *, title: object = "", body: object = "") -> int:
    title_score = _keyword_match_count(target, title)
    body_score = _keyword_match_count(target, body)
    return title_score * 10 + body_score


def _prioritized_jobs_for_target(
    target: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    default_limit: int = 20,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            continue
        score = _keyword_match_score(
            target,
            title=job.get("title"),
            body="\n".join(
                str(part or "")
                for part in (
                    job.get("descriptionHtml"),
                    job.get("descriptionPlain"),
                    job.get("content"),
                    job.get("text"),
                )
            ),
        )
        scored.append((score, index, job))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [job for _score, _index, job in scored[: _registry_limit(target, default_limit)]]


def _workday_title_allowed(job: dict[str, Any], target: dict[str, Any]) -> bool:
    keywords = target.get("title_keywords")
    if not isinstance(keywords, list) or not keywords:
        return True
    title = str(job.get("title") or "")
    bullets = " ".join(str(item) for item in (job.get("bulletFields") or []))
    text = f"{title}\n{bullets}"
    return any(_keyword_in_text(str(keyword), text) for keyword in keywords)


def _workday_candidates(client: httpx.Client, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read-only Workday CXS board reader.

    Workday hosts are ``{tenant}.{dc}.myworkdayjobs.com`` and the public job feed
    is ``POST /wday/cxs/{tenant}/{site}/jobs``. Tenant, data center, and site are
    per-employer and not derivable with certainty, so this tries a small bounded
    matrix (``tenant`` from the slug x a few data centers x a few site names) and
    stops at the first host+site that returns postings. No credentials, capped
    body, per-request failures swallowed. Most WNY employers (Roswell Park, Moog,
    PwC, Voya) publish on Workday, which the greenhouse/lever/ashby readers miss.
    """
    tenant = re.sub(r"[^a-z0-9]", "", str(target.get("workday_tenant") or target["slug"]).lower())
    receipt = _base_receipt("A", "workday", target["name"], "employer_ats")
    receipt["required_source_id"] = "workday"
    receipt["channel"] = "api"
    # Explicit coordinates (from a resolved myworkdayjobs URL) mean exactly one
    # request; otherwise fall back to the bounded enumeration matrix.
    explicit = target.get("workday_dc") and target.get("workday_site")
    datacenters = (str(target["workday_dc"]),) if explicit else _WORKDAY_DATACENTERS
    sites = [str(target["workday_site"])] if explicit else list(dict.fromkeys([tenant, *(_WORKDAY_SITE_HINTS)]))
    search_texts = target.get("search_texts")
    if isinstance(search_texts, list):
        search_terms = [str(term).strip() for term in search_texts if str(term).strip()]
    else:
        search_terms = [str(target.get("search_text") or "").strip()]
    search_terms = list(dict.fromkeys(search_terms or [""]))
    attempts: list[str] = []
    postings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    resolved_host = ""
    resolved_site = ""
    for dc in datacenters:
        host = f"{tenant}.{dc}.myworkdayjobs.com"
        for site in sites:
            url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
            host_site_postings: list[dict[str, Any]] = []
            for search_text in search_terms:
                attempts.append(f"{url}?searchText={search_text}")
                body = {
                    "appliedFacets": {},
                    "limit": _registry_limit(target, 20),
                    "offset": 0,
                    "searchText": search_text,
                }
                try:
                    response = client.post(url, json=body, headers={"Accept": "application/json"})
                    if response.status_code != 200:
                        continue
                    if len(response.content) > MAX_EMPLOYER_ATS_RESPONSE_BYTES:
                        continue
                    data = response.json()
                except (httpx.HTTPError, ValueError):
                    continue
                jobs = data.get("jobPostings", []) if isinstance(data, dict) else []
                if not isinstance(jobs, list):
                    continue
                for job in jobs:
                    if not isinstance(job, dict):
                        continue
                    if not _workday_title_allowed(job, target):
                        continue
                    external_path = str(job.get("externalPath") or "")
                    dedupe_key = external_path or str(job)
                    if dedupe_key in seen_paths:
                        continue
                    seen_paths.add(dedupe_key)
                    host_site_postings.append(job)
            if host_site_postings:
                postings = host_site_postings
                resolved_host, resolved_site = host, site
                break
        if postings:
            break

    _add_registry_evidence(receipt, target, target.get("primary_source_url"),
                           f"https://{resolved_host}" if resolved_host else None)
    receipt["request_summary"] = (
        f"POST wday/cxs/{tenant}/<site>/jobs across {len(attempts)} host/site combos; "
        f"resolved={resolved_host or 'none'}"
    )
    receipt["response_bytes"] = len(str(postings))
    receipt["content_sha256"] = sha256_bytes(str(postings).encode("utf-8"))
    if not postings:
        receipt["result_status"] = "NO_MATCHES"
        receipt["parser_result"] = "NO_PARSE"
        receipt["limitations"].append("No Workday host/site combo resolved for this tenant guess.")
        return _finalize_receipt(receipt), []

    receipt["result_status"] = "MATCHES"
    receipt["parser_result"] = "PARSED"
    receipt = _finalize_receipt(receipt)
    candidates: list[dict[str, Any]] = []
    for job in postings[: _registry_limit(target, 20)]:
        if not isinstance(job, dict):
            continue
        location = str(job.get("locationsText") or "Unknown")
        content = " ".join(str(x) for x in (job.get("bulletFields") or []))
        posting_url = _workday_job_url(resolved_host, resolved_site, str(job.get("externalPath") or ""))
        payload = {
            "lane": "A",
            "source_receipt_id": receipt["receipt_id"],
            "source_provider": "workday",
            "source_identity": f"{tenant}/{resolved_site}",
            "organization": target["name"],
            "title": job.get("title") or "Untitled",
            "location_display": location,
            "workplace_type": _workplace_type(location, content),
            "relocation_required": _relocation_required(location, content),
            "clearance_required": False,
            "posting_url": posting_url,
            "apply_url": posting_url,
            "primary_evidence_url": posting_url,
            "published_at": job.get("postedOn"),
            "updated_at": job.get("postedOn"),
            "content_hash": sha256_bytes(str(job).encode("utf-8")),
            "posting_text": content[:14000],
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
            "workplace_type": _workplace_type(default_location, str(item.get("description") or "")),
            "relocation_required": False,
            "clearance_required": False,
            "posting_url": job_url,
            "apply_url": job_url,
            "primary_evidence_url": job_url,
            "published_at": None,
            "updated_at": None,
            "content_hash": sha256_bytes(job_url.encode("utf-8")),
            "posting_text": str(item.get("description") or "")[:14000],
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


_REMOTE_BODY_MARKERS = (
    "fully remote", "100% remote", "remote-first", "remote first", "work from anywhere",
    "us-remote", "remote (us", "remote, us", "remote within the us", "this role is remote",
    "this is a remote", "remote position", "remote role", "remote work environment",
)
_ONSITE_BODY_MARKERS = (
    "in-person", "in person at", "on-site", "onsite", "in office", "in our office",
    "in the office", "days per week in", "days a week in", "days/week in",
)


def _workplace_type(location: str, content: str = "", provider_workplace_type: str = "") -> str:
    """Infer workplace from location AND posting body.

    Reading only the location string sent 172 candidates per night - including
    all 63 LinkedIn top-applicant rows - into HUMAN_REVIEW_LOCATION_AMBIGUOUS,
    a bucket no surface ever showed the human. 'United States' with 'fully
    remote' in the body is not ambiguous, and 'New York Office' with 'In-Person'
    in the body is not a question either.
    """

    text = location.lower()
    provider = (
        provider_workplace_type.lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )
    if "buffalo" in text and "hybrid" in text:
        return "WNY_HYBRID"
    if "buffalo" in text and provider == "hybrid":
        return "WNY_HYBRID"
    if "buffalo" in text:
        return "WNY_ONSITE"
    if provider == "remote":
        return "REMOTE"
    if "remote" in text:
        return "REMOTE"
    if provider in {"onsite", "inperson", "hybrid"} and text and text != "unknown":
        return "ONSITE_ELSEWHERE"
    body = str(content or "").lower()
    if body:
        if any(marker in body for marker in _REMOTE_BODY_MARKERS):
            return "REMOTE"
        if any(marker in body for marker in _ONSITE_BODY_MARKERS) and "remote" not in body:
            return "ONSITE_ELSEWHERE"
    return "AMBIGUOUS"


def _relocation_required(location: str, content: str) -> bool:
    text = f"{location}\n{content}".lower()
    return "relocation required" in text or "must relocate" in text


def _source_locator_receipt(client: httpx.Client, target: dict[str, Any]) -> dict[str, Any]:
    provider = str(target.get("provider") or "source-locator")
    lane = str(target.get("lane") or "A")
    receipt = _base_receipt(lane, provider, target["name"], "source_locator")
    required_ids = {"hiddenjobs.dev": "hiddenjobs", "indeed": "indeed"}
    if provider in required_ids:
        receipt["required_source_id"] = required_ids[provider]
        receipt["channel"] = "source_locator"
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
    receipt["required_source_id"] = "sam.gov"
    receipt["channel"] = "api"
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
    if provider == "darpa":
        receipt["required_source_id"] = "darpa"
        receipt["channel"] = "api"
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
    receipt["channel"] = "primary_source"
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
    if provider == "workday":
        return _workday_candidates(client, target)
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
    indeed_evidence: Path | None = None,
    hiddenjobs_evidence: Path | None = None,
    federal_evidence: Path | None = None,
    meetup_evidence: Path | None = None,
    github_evidence: Path | None = None,
    slack_evidence: Path | None = None,
    discord_evidence: Path | None = None,
    gmail_evidence: Path | None = None,
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
                if indeed_evidence is not None:
                    receipt, rows = _required_browser_evidence_receipt(
                        indeed_evidence,
                        provider="indeed",
                        required_source_id="indeed",
                        target="Indeed jobs",
                        source_class="human_supplied_indeed",
                    )
                    receipts.append(receipt)
                    candidates.extend(rows)
                else:
                    receipts.append(
                        _human_browser_required_receipt(
                            provider="indeed",
                            required_source_id="indeed",
                            target="Indeed jobs",
                            source_class="human_supplied_indeed",
                            website_fallback="https://www.indeed.com/jobs",
                        )
                    )
                if hiddenjobs_evidence is not None:
                    receipt, rows = _required_browser_evidence_receipt(
                        hiddenjobs_evidence,
                        provider="hiddenjobs.dev",
                        required_source_id="hiddenjobs",
                        target="Hidden Jobs",
                        source_class="human_supplied_hiddenjobs",
                    )
                    receipts.append(receipt)
                    candidates.extend(rows)
                else:
                    receipts.append(
                        _human_browser_required_receipt(
                            provider="hiddenjobs.dev",
                            required_source_id="hiddenjobs",
                            target="Hidden Jobs",
                            source_class="human_supplied_hiddenjobs",
                            website_fallback="https://hiddenjobs.dev/",
                        )
                    )
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
                sam_api = next(
                    (
                        row
                        for row in receipts
                        if row.get("required_source_id") == "sam.gov"
                        and row.get("source_class") == "federal_feed"
                    ),
                    None,
                )
                if sam_api is not None:
                    receipt["fallback_for_receipt_id"] = sam_api["receipt_id"]
                receipts.append(receipt)
                candidates.extend(rows)
        if "C" in lanes:
            receipts.append(_client_research_receipt(skill_dir))
            if slack_evidence is not None:
                receipt, rows = _message_evidence_candidates(
                    slack_evidence,
                    provider="slack",
                    required_source_id="slack_channels",
                    target="Slack opportunity channels",
                    source_class="slack_channel_capture",
                    channel="slack",
                )
                receipts.append(receipt)
                candidates.extend(rows)
            else:
                receipts.append(
                    _unavailable_required_source_receipt(
                        provider="slack",
                        required_source_id="slack_channels",
                        target="Slack opportunity channels",
                        source_class="slack_channel_capture",
                        channel="slack",
                        limitation=(
                            "Slack channel evidence was not supplied; provide --slack-evidence "
                            "from the Slack connector or a read-only channel export for G2i/job-alert mining."
                        ),
                        evidence_refs=["slack://C01H317TX7X"],
                    )
                )
            if discord_evidence is not None:
                receipt, rows = _message_evidence_candidates(
                    discord_evidence,
                    provider="discord",
                    required_source_id="discord_channels",
                    target="Discord opportunity channels",
                    source_class="discord_channel_capture",
                    channel="discord",
                    automation_policy="read_only_discord_channel_capture_no_send_no_reply_no_react_no_apply",
                )
                receipts.append(receipt)
                candidates.extend(rows)
            else:
                receipts.append(
                    _unavailable_required_source_receipt(
                        provider="discord",
                        required_source_id="discord_channels",
                        target="Discord opportunity channels",
                        source_class="discord_channel_capture",
                        channel="discord",
                        limitation=(
                            "Discord channel evidence was not supplied; provide --discord-evidence "
                            "from ops-discord, a read-only channel export, or a surf capture."
                        ),
                        evidence_refs=["https://discord.com/channels/1344341191893979290/1344341192518799442"],
                    )
                )
            if gmail_evidence is not None:
                receipt, rows = _message_evidence_candidates(
                    gmail_evidence,
                    provider="gmail",
                    required_source_id="gmail_mailbox",
                    target="graham@grahama.co mailbox mining",
                    source_class="mailbox_mined_gmail",
                    channel="mailbox_mining",
                )
                receipts.append(receipt)
                candidates.extend(rows)
            else:
                receipts.append(
                    _unavailable_required_source_receipt(
                        provider="gmail",
                        required_source_id="gmail_mailbox",
                        target="graham@grahama.co mailbox mining",
                        source_class="mailbox_mined_gmail",
                        channel="mailbox_mining",
                        limitation=(
                            "Gmail mailbox evidence was not supplied; provide --gmail-evidence "
                            "from a read-only mailbox-mining export. Gmail send remains forbidden."
                        ),
                        evidence_refs=["mailto:graham@grahama.co"],
                    )
                )
            for target in targets.get("commercial", []):
                receipt, rows = _commercial_receipt(target)
                receipts.append(receipt)
                candidates.extend(rows)
    if "C" in lanes and meetup_evidence is not None:
        receipt, rows = _meetup_evidence_candidates(meetup_evidence)
        receipts.append(receipt)
        candidates.extend(rows)
    if "C" in lanes and github_evidence is not None:
        receipt, rows = _github_evidence_candidates(github_evidence)
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

def _merge_linkedin_priority_fields(existing: dict[str, Any], row: dict[str, Any]) -> bool:
    changed = False
    for field in ("top_candidate", "easy_apply", "easy_apply_signal", "under_10_applicants"):
        if row.get(field) and not existing.get(field):
            existing[field] = row[field]
            changed = True
    for field in (
        "top_candidate_text",
        "evidence_text",
        "matched_query",
        "warm_path_via",
        "linkedin_url",
    ):
        if row.get(field) not in (None, "", [], {}) and existing.get(field) in (None, "", [], {}):
            existing[field] = row[field]
            changed = True

    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if row.get("competition") is not None:
        incoming = _as_float(row.get("competition"))
        current = _as_float(existing.get("competition"))
        if existing.get("competition") is None or (
            incoming is not None and (current is None or incoming < current)
        ):
            existing["competition"] = row["competition"]
            changed = True
    if row.get("warm_path") is not None:
        incoming = _as_float(row.get("warm_path"))
        current = _as_float(existing.get("warm_path"))
        if existing.get("warm_path") is None or (
            incoming is not None and (current is None or incoming > current)
        ):
            existing["warm_path"] = row["warm_path"]
            changed = True
            if row.get("warm_path_via") not in (None, "", [], {}):
                existing["warm_path_via"] = row["warm_path_via"]
    return changed


def _merge_linkedin_top_candidate(base_path: Path, other_path: Path) -> int:
    """Merge one LinkedIn evidence stream into another, preserving priority fields.

    Picking only the higher-row-count file dropped the top-applicant stream and
    its ``top_candidate`` flags. This merges the other stream's opportunities in:
    a matching (title, organization) row inherits Top Applicant, Easy Apply,
    low-competition, and warm-path fields if either stream carries them;
    unmatched rows are appended with their signals intact.
    """
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
        other = json.loads(other_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    base_rows = base.get("opportunities")
    if not isinstance(base_rows, list):
        return 0
    index = {(r.get("title"), r.get("organization")): r for r in base_rows if isinstance(r, dict)}
    merged = 0
    for row in other.get("opportunities", []) or []:
        if not isinstance(row, dict):
            continue
        key = (row.get("title"), row.get("organization"))
        existing = index.get(key)
        if existing is not None:
            if _merge_linkedin_priority_fields(existing, row):
                merged += 1
        else:
            base_rows.append(row)
            index[key] = row
            merged += 1
    # A file-level top_candidate:true (whole page is the top-applicant collection)
    # applies to every row it contributed.
    if other.get("top_candidate"):
        base["top_candidate"] = base.get("top_candidate") or True
    base_path.write_text(json.dumps(base, indent=1), encoding="utf-8")
    return merged
