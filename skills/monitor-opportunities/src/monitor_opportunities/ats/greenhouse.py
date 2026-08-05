"""Read-only Greenhouse job-board form capture.

Fetches one posting's application questions from the public Greenhouse
job-board API and maps them into the neutral form shape consumed by
``application_plan.inspect_ats_form``. No form field is written and no
application is created; the only network effect is a credentialless GET.
"""

from __future__ import annotations

from typing import Any

import httpx

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"
HTTP_TIMEOUT = httpx.Timeout(connect=3.0, read=10.0, write=3.0, pool=3.0)
MAX_RESPONSE_BYTES = 1_500_000

_SENSITIVE_LABEL_TYPES = (
    ("work_authorization", ("legally authorized", "work authorization", "sponsorship", "visa")),
    ("self_identification", ("gender", "race", "veteran", "disability", "ethnicity", "self-identif")),
    ("salary", ("salary", "compensation")),
    ("clearance", ("clearance",)),
)


class GreenhouseFormError(ValueError):
    """Stable Greenhouse form capture error."""


def greenhouse_questions_url(board: str, job_id: str) -> str:
    return f"{GREENHOUSE_API_BASE}/{board}/jobs/{job_id}?questions=true"


def _field_type(label: str, input_types: list[str]) -> str:
    lowered = label.lower()
    for field_type, needles in _SENSITIVE_LABEL_TYPES:
        if any(needle in lowered for needle in needles):
            return field_type
    if "input_file" in input_types:
        return "file"
    if "textarea" in input_types:
        return "free_text"
    if any(t.startswith("multi_value") for t in input_types):
        return "choice"
    if "email" in lowered:
        return "email"
    if "phone" in lowered:
        return "phone"
    return "text"


def form_from_greenhouse_job(board: str, job: dict[str, Any]) -> dict[str, Any]:
    """Map one Greenhouse job payload (with questions) to the neutral form shape."""

    job_id = job.get("id")
    questions = job.get("questions")
    if job_id is None or questions is None:
        raise GreenhouseFormError("GREENHOUSE_JOB_PAYLOAD_INCOMPLETE")
    fields = []
    accepted_attachments = []
    for question in questions:
        label = str(question.get("label") or "")
        input_types = [str(item.get("type") or "") for item in question.get("fields", [])]
        field_type = _field_type(label, input_types)
        options = [
            str(value.get("label"))
            for item in question.get("fields", [])
            for value in item.get("values", []) or []
        ]
        fields.append(
            {
                "name": label,
                "field_type": field_type,
                "required": bool(question.get("required")),
                "options": options,
            }
        )
        if field_type == "file":
            accepted_attachments.append(label)
    return {
        "provider": "greenhouse",
        "site": board,
        "posting_id": str(job_id),
        "url": str(job.get("absolute_url") or greenhouse_questions_url(board, str(job_id))),
        "title": str(job.get("title") or ""),
        "fields": fields,
        "accepted_attachments": accepted_attachments,
        "policy_observations": [
            "Captured read-only via the public Greenhouse job-board API; no browser session and no form write.",
        ],
    }


def form_from_dom_capture(
    board: str,
    job_id: str,
    url: str,
    dom_rows: list[dict[str, Any]],
    api_questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Map a read-only browser DOM capture to the neutral form shape.

    The rendered application form is the authoritative surface: it carries
    required fields (country, location, demographic selects) that the
    job-board API omits. Rows come from a surf read-only element query:
    {tag, type, id, aria, label, required}.
    """

    api_types: dict[str, list[str]] = {}
    api_options: dict[str, list[str]] = {}
    for question in api_questions or []:
        api_label = str(question.get("label") or "").strip()
        if api_label:
            api_types[api_label] = [str(item.get("type") or "") for item in question.get("fields", [])]
            api_options[api_label] = [
                str(value.get("label"))
                for item in question.get("fields", [])
                for value in item.get("values", []) or []
            ]
    fields = []
    accepted_attachments = []
    seen: set[str] = set()
    for row in dom_rows:
        label = str(row.get("aria") or row.get("label") or "").rstrip("*").strip()
        element_id = row.get("id") or ""
        if not label or label in seen or element_id.endswith("__search-input"):
            continue
        seen.add(label)
        input_type = str(row.get("type") or "")
        tag = str(row.get("tag") or "")
        # Greenhouse renders selects/autocompletes as text inputs backed by
        # listboxes; only these ids are true free-text inputs.
        free_input = element_id in {"first_name", "last_name", "email", "phone", "candidate-location"} or element_id.startswith("question_")
        if label in api_types:
            # The API knows the true input kind (e.g. a choice rendered as a
            # text input); the DOM stays authoritative for the field set.
            input_types = api_types[label]
        elif input_type == "file":
            input_types = ["input_file"]
        elif tag == "textarea":
            input_types = ["textarea"]
        elif tag == "select" or not free_input:
            input_types = ["multi_value_single_select"]
        else:
            input_types = ["input_text"]
        field_type = _field_type(label, input_types)
        fields.append(
            {
                "name": label,
                "field_type": field_type,
                "required": bool(row.get("required")),
                "options": api_options.get(label, []),
                "selector": f"#{element_id}" if element_id else None,
            }
        )
        if field_type == "file":
            accepted_attachments.append(label)
    if not fields:
        raise GreenhouseFormError("GREENHOUSE_DOM_CAPTURE_EMPTY")
    return {
        "provider": "greenhouse",
        "site": board,
        "posting_id": str(job_id),
        "url": url,
        "fields": fields,
        "accepted_attachments": accepted_attachments,
        "policy_observations": [
            "Captured read-only from the rendered application form DOM (authoritative surface); no form write.",
            "Job-board API questions payload is advisory only: the DOM carries required fields the API omits.",
        ],
    }


def fetch_greenhouse_form(board: str, job_id: str, client: httpx.Client | None = None) -> dict[str, Any]:
    """Fetch one posting's questions and return the neutral form shape."""

    url = greenhouse_questions_url(board, job_id)
    owned = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True)
    try:
        response = client.get(url)
        if response.status_code != 200:
            raise GreenhouseFormError(f"GREENHOUSE_HTTP_{response.status_code}")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise GreenhouseFormError("GREENHOUSE_RESPONSE_TOO_LARGE")
        return form_from_greenhouse_job(board, response.json())
    finally:
        if owned:
            client.close()
