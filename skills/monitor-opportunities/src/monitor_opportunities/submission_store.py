"""Persist each application submission to /memory — returnable and editable.

Every prefilled/submitted application is stored in the /memory
`application_submissions` collection, keyed per opportunity, so Graham can return
to it, see exactly what was filled and answered, edit it, and track its state.
Complements the GitHub board (lifecycle labels) with the actual application
content. No submit here — this only records.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from typing import Any

from .util import utc_now

MEMORY_URL = "http://127.0.0.1:8601"
SUBMISSIONS_COLLECTION = "application_submissions"


def _store(doc: dict[str, Any], memory_url: str = MEMORY_URL) -> bool:
    body = json.dumps({"document": doc, "collection": SUBMISSIONS_COLLECTION}).encode()
    req = urllib.request.Request(f"{memory_url}/store", data=body, headers={"Content-Type": "application/json"})
    try:
        return bool(json.loads(urllib.request.urlopen(req, timeout=20).read()).get("stored"))
    except OSError:
        return False


def _key(candidate_id: str, apply_url: str) -> str:
    return "sub-" + hashlib.sha256(f"{candidate_id}|{apply_url}".encode()).hexdigest()[:16]


def store_submission(
    candidate_id: str,
    opportunity: dict[str, Any],
    prefill_result: dict[str, Any],
    screening_answers: dict[str, Any] | None = None,
    state: str = "prefilled_awaiting_human",
    resume: str | None = None,
    memory_url: str = MEMORY_URL,
) -> dict[str, Any]:
    """Upsert one application submission record (idempotent per opportunity).

    Deduped by candidate_id+apply_url so re-prefilling or editing overwrites the
    same record. state: prefilled_awaiting_human | submitted | responded | closed.
    """
    apply_url = str(opportunity.get("apply_url") or prefill_result.get("apply_url") or "")
    doc = {
        "_key": _key(str(candidate_id), apply_url),
        "schema": "monitor_opportunities.application_submission.v1",
        "candidate_id": candidate_id,
        "organization": opportunity.get("organization"),
        "role": opportunity.get("title"),
        "apply_url": apply_url,
        "provider": prefill_result.get("provider") or opportunity.get("ats_provider"),
        "state": state,
        "filled_values": prefill_result.get("filled_ok", []),
        "fill_failed": prefill_result.get("fill_failed", []),
        "remaining_for_human": prefill_result.get("remaining_for_human", []),
        "screening_answers": screening_answers or {},
        "resume": resume,
        "tab_id": prefill_result.get("tab_id"),
        "submitted_by_agent": False,
        "note": "Prefilled by agent; human reviews, attaches resume, answers screening, and clicks Apply. Editable.",
        "updated_at": utc_now(),
    }
    ok = _store(doc, memory_url)
    return {"stored": ok, "key": doc["_key"], "state": state}


def update_submission_state(candidate_id: str, apply_url: str, state: str, memory_url: str = MEMORY_URL) -> bool:
    """Advance a submission's state (e.g. human marks it submitted/responded)."""
    doc = {"_key": _key(str(candidate_id), apply_url), "state": state, "updated_at": utc_now()}
    return _store(doc, memory_url)
