"""Persist learned ATS application forms to /memory, keyed per opportunity.

The nightly captures each top job's application-form schema read-only. This
stores the real captures (not the 1-field LinkedIn-view stubs) into the /memory
`ats_selector_bindings` collection, keyed by provider-site-posting and linked to
the opportunity's candidate_id, digest-bound so an unchanged employer form is
never re-learned. This is the "learn the client apply site once" store — the
element/selector handlers for sites that seldom change.

No browser here — reads the form file the capture already wrote and upserts it.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from .util import sha256_json, utc_now

MEMORY_URL = "http://127.0.0.1:8601"
BINDINGS_COLLECTION = "ats_selector_bindings"
# Below this many fields the capture is a stub (e.g. a LinkedIn view page, not
# the real application form) and must NOT be stored as a learned form.
MIN_REAL_FIELDS = 3


def _store(doc: dict[str, Any], memory_url: str = MEMORY_URL) -> bool:
    body = json.dumps({"document": doc, "collection": BINDINGS_COLLECTION}).encode()
    req = urllib.request.Request(f"{memory_url}/store", data=body, headers={"Content-Type": "application/json"})
    try:
        return bool(json.loads(urllib.request.urlopen(req, timeout=20).read()).get("stored"))
    except OSError:
        return False


def store_learned_form(candidate_id: str, form_receipt: dict[str, Any], memory_url: str = MEMORY_URL) -> dict[str, Any]:
    """Persist one captured ATS form to /memory if it is a real form.

    Skips stubs (field_count < MIN_REAL_FIELDS) and failed/deferred captures.
    Digest-bound: the _key is stable per provider-site-posting, so re-capturing an
    unchanged form overwrites the same doc (idempotent), and the form_schema_digest
    lets callers detect drift.
    """
    if form_receipt.get("status") != "OK":
        return {"stored": False, "reason": f"status={form_receipt.get('status')}"}
    field_count = int(form_receipt.get("field_count") or 0)
    if field_count < MIN_REAL_FIELDS:
        return {"stored": False, "reason": f"stub_form_{field_count}_fields", "hint": "apply_url is likely a LinkedIn view, not the employer ATS"}
    form_path = form_receipt.get("form_path")
    if not form_path or not Path(form_path).exists():
        return {"stored": False, "reason": "no_form_file"}
    form = json.loads(Path(form_path).read_text(encoding="utf-8"))
    provider = str(form.get("provider") or "unknown")
    site = str(form.get("site") or "site")
    posting_id = str(form.get("posting_id") or "id")
    doc = {
        "_key": f"{provider}-{site}-{posting_id}",
        "schema": "monitor_opportunities.ats_selector_binding.v1",
        "candidate_id": candidate_id,
        "provider": provider,
        "site": site,
        "posting_id": posting_id,
        "url": form.get("url"),
        "field_count": field_count,
        "fields": form.get("fields", []),
        "accepted_attachments": form.get("accepted_attachments", []),
        "form_schema_digest": sha256_json(form.get("fields", [])),
        "captured_at": utc_now(),
        "automation_policy": "read_only_learned_form_submit_requires_human",
    }
    ok = _store(doc, memory_url)
    return {"stored": ok, "key": doc["_key"], "field_count": field_count}
