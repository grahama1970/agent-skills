"""Read-only prior-application history for ranking exclusion.

The write-side store keys application submissions by candidate_id+apply_url.
This module performs the matching read before ranking, using only bounded
`/recall/by-keys` requests. It never lists Memory collections and never writes.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from .util import read_jsonl, utc_now, write_jsonl

SUBMISSIONS_COLLECTION = "application_submissions"
ACTIONED_STATES = {
    "prefilled_awaiting_human",
    "submitted",
    "responded",
    "closed",
}


def submission_key(candidate_id: str, apply_url: str) -> str:
    return "sub-" + hashlib.sha256(f"{candidate_id}|{apply_url}".encode()).hexdigest()[:16]


def _candidate_apply_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("apply_url") or candidate.get("posting_url") or "").strip()


def _memory_post(memory_url: str, path: str, payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{memory_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def annotate_candidates_with_prior_applications(
    discovery_dir: Path,
    memory_url: str,
) -> dict[str, Any]:
    """Mark candidates already present in Memory application history.

    Returns an honest receipt. Memory read failures do not fabricate history;
    they set status=UNKNOWN so the run can report degraded prior-action proof.
    """

    candidates_path = discovery_dir / "candidates.jsonl"
    candidates = read_jsonl(candidates_path)
    candidate_by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        apply_url = _candidate_apply_url(candidate)
        if not candidate_id or not apply_url:
            continue
        candidate_by_key[submission_key(candidate_id, apply_url)] = candidate

    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.application_history_receipt.v1",
        "observed_at": utc_now(),
        "collection": SUBMISSIONS_COLLECTION,
        "lookup": "recall/by-keys",
        "candidates_inspected": len(candidates),
        "keys_requested": len(candidate_by_key),
        "history_matches": 0,
        "marked_already_applied": 0,
        "external_effects": False,
        "status": "OK",
        "limitations": [],
    }
    if not candidate_by_key:
        receipt["limitations"].append("No candidate had both candidate_id and apply/posting URL.")
        return receipt

    try:
        payload = _memory_post(
            memory_url,
            "/recall/by-keys",
            {"collection": SUBMISSIONS_COLLECTION, "keys": sorted(candidate_by_key)},
        )
    except Exception as exc:  # noqa: BLE001 - history read degrades, it does not invent facts
        receipt["status"] = "UNKNOWN"
        receipt["limitations"].append(f"Application history read unavailable: {exc}")
        return receipt

    marked = 0
    matches = 0
    for row in payload.get("documents", []) or []:
        doc = row.get("document") if isinstance(row, dict) else None
        if not isinstance(doc, dict):
            doc = row if isinstance(row, dict) else {}
        key = str(doc.get("_key") or "")
        candidate = candidate_by_key.get(key)
        if candidate is None:
            continue
        matches += 1
        state = str(doc.get("state") or "").strip().lower()
        if state in ACTIONED_STATES:
            candidate["already_applied"] = True
            candidate["application_history_key"] = key
            candidate["application_history_state"] = state
            marked += 1
    if marked:
        write_jsonl(candidates_path, candidates)
    receipt["history_matches"] = matches
    receipt["marked_already_applied"] = marked
    return receipt
