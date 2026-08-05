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
