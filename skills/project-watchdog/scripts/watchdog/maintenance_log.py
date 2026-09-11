"""Shared maintenance-log bridge (best-effort, exact-match, stdlib-only).

Contract: skills/best-practices-skills/references/maintenance_log_contract.md.
The memory daemon (default http://127.0.0.1:8601) owns the ``maintenance_events``
collection; this module is the watchdog's sanctioned client surface:

- ``covering_events(repo, paths)`` — READ side of the target-ownership gate:
  exact-match lookup (``/list`` filtered by ``entity_id``, NEVER semantic
  recall) for an event whose ``repo`` matches, whose ``changed_paths`` contains
  the conflicting path verbatim, whose ``proof_receipt`` is non-empty, and
  whose ``observed_at`` is inside the 30-day window (the contract's default
  maintenance cadence). Such an event is durable provenance: the gate adopts
  the path as ``verified_maintenance_provenance`` instead of refusing
  ``unowned_target_edit``. Any daemon error degrades to "no coverage" so the
  byte-level fail-closed behavior is unchanged when the log is unreachable.

- ``emit_tick_event(...)`` — WRITE side at the ``core.finish()`` persist
  boundary: one ``decision.recorded`` event per eventful tick receipt
  (``entity_id`` ``<repo-short>:project``, ``proof_receipt`` = the persisted
  receipt path) with a run-id-keyed deterministic ``_key`` so a retried tick
  does not double-write. Verified by immediate read-back; NEVER raises — a
  maintenance-log outage cannot fail a tick (same posture as ops-discord
  alerting).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

MAINTENANCE_BASE = os.environ.get("MAINTENANCE_LOG_BASE", "http://127.0.0.1:8601")
COLLECTION = "maintenance_events"
EVENT_SCHEMA = "agent-skills.skill_maintenance_event.v1"
#: An event older than this is stale provenance (contract default cadence P30D).
DEFAULT_MAX_AGE_DAYS = 30
_TIMEOUT_S = 8.0


def _post_json(path: str, payload: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        MAINTENANCE_BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("documents") or payload.get("items") or []
    return [r for r in rows if isinstance(r, dict)]


def entity_candidates(repo: str, paths: list[str]) -> list[str]:
    """Exact-match entity ids to query for these paths.

    Project-level events use ``<repo-short>:project`` (e.g. ``tau:project``);
    inside agent-skills a path under ``skills/<name>/`` may instead be covered
    by that skill's own entity (``agent-skills:<name>``).
    """
    short = repo.rstrip("/").split("/")[-1]
    candidates = [f"{short}:project"]
    for p in paths:
        parts = p.split("/")
        if len(parts) > 2 and parts[0] == "skills":
            candidates.append(f"{short}:{parts[1]}")
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _age_days(observed_at: Any) -> float | None:
    try:
        ts = datetime.fromisoformat(str(observed_at))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0


def covering_events(repo: str, paths: list[str], *,
                    max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict[str, dict[str, Any]]:
    """Map each path to a covering provenance event, exact-match only.

    Best-effort: any transport/parse error returns {} (the ownership gate then
    refuses exactly as it does today). Never raises.
    """
    if not paths:
        return {}
    try:
        rows: list[dict[str, Any]] = []
        for entity in entity_candidates(repo, paths):
            payload = _post_json("/list", {"collection": COLLECTION,
                                           "filters": {"entity_id": entity}, "limit": 100})
            rows.extend(_rows(payload))
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    rows = [r for r in rows
            if r.get("repo") == repo
            and r.get("proof_receipt")
            and isinstance(r.get("changed_paths"), list)]
    rows.sort(key=lambda r: str(r.get("observed_at") or ""), reverse=True)
    covered: dict[str, dict[str, Any]] = {}
    for path in paths:
        for row in rows:
            age = _age_days(row.get("observed_at"))
            if age is None or age > max_age_days:
                continue
            if path in [str(p) for p in row.get("changed_paths") or []]:
                covered[path] = row
                break
    return covered


def emit_tick_event(*, repo: str, run_id: str, summary: str, proof_receipt: str,
                    changed_paths: list[str] | None = None,
                    tags: list[str] | None = None) -> dict[str, Any]:
    """Append one decision.recorded event for a persisted tick receipt.

    Deterministic ``_key`` from (run_id, entity, summary) makes a retried tick
    idempotent. Verified by read-back. NEVER raises: failures return a status
    dict so core.finish() cannot be blocked by the maintenance log.
    """
    short = repo.rstrip("/").split("/")[-1]
    entity_id = f"{short}:project"
    observed_at = datetime.now(timezone.utc).isoformat()
    doc: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "entity_id": entity_id,
        "repo": repo,
        "event_type": "decision.recorded",
        "summary": summary[:300],
        "changed_paths": changed_paths or [],
        "proof_receipt": proof_receipt,
        "actor": "project-watchdog",
        "tags": tags or ["project-watchdog"],
        "observed_at": observed_at,
        "_key": "me_" + hashlib.sha256(
            f"{run_id}|{entity_id}|{summary}".encode("utf-8")).hexdigest()[:32],
    }
    try:
        _post_json("/store", {"document": doc, "collection": COLLECTION})
        back = _post_json("/list", {"collection": COLLECTION,
                                    "filters": {"_key": doc["_key"]}, "limit": 1})
        ok = any(r.get("_key") == doc["_key"] for r in _rows(back))
        return {"status": "EMITTED" if ok else "EMIT_FAILED", "key": doc["_key"],
                "readback": len(_rows(back))}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"status": "SKIPPED", "reason": str(exc)[:160], "key": doc["_key"]}
