"""Durable provider-transport outage records for automatic seat fallback.

2026-09-10: the codex CLI quota died and the fleet had to be hand-parked.
project-watchdog must instead notice a rate-limited transport once, record it
durably, dispatch cheaply around it (no lease, no DAG burn), substitute
non-authoring seats onto a live transport, and resume automatically when the
outage window passes.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import config

OUTAGES_FILE = "transport-outages.json"

#: Non-authoring seats on a dead transport are substituted with this live
#: API seat (verified live 2026-09-10: zai-glm-high node PASS). Creators
#: cannot be substituted: only the codex transport can author (workspace).
CODEX_SEAT_FALLBACK = os.environ.get("PROJECT_WATCHDOG_CODEX_SEAT_FALLBACK", "zai-glm-high")

DEFAULT_OUTAGE_SECONDS = 6 * 3600


class TransportOutage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: str = Field(default="agent_skills.project_watchdog.transport_outage.v1", alias="schema")
    transport: str
    detected_at: float
    resume_at: float
    evidence: str = ""


def _path() -> Path:
    return config.state_root() / OUTAGES_FILE


def _load() -> dict[str, TransportOutage]:
    try:
        raw = json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, TransportOutage] = {}
    for name, item in (raw or {}).items():
        try:
            out[name] = TransportOutage.model_validate(item)
        except Exception:  # noqa: BLE001 - a corrupt record must not wedge dispatch
            continue
    return out


def record_outage(transport: str, *, resume_at: float | None = None, evidence: str = "") -> TransportOutage:
    now = time.time()
    outage = TransportOutage(
        transport=transport, detected_at=now,
        resume_at=float(resume_at) if resume_at else now + DEFAULT_OUTAGE_SECONDS,
        evidence=evidence[:500],
    )
    outages = _load()
    outages[transport] = outage
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(
        {k: v.model_dump(by_alias=True) for k, v in outages.items()},
        indent=2, sort_keys=True) + "\n")
    return outage


def active_outage(transport: str) -> TransportOutage | None:
    outage = _load().get(transport)
    if outage and outage.resume_at > time.time():
        return outage
    return None


def parse_reset_time(text: str) -> float | None:
    """Parse 'try again at Sep 14th, 2026 9:36 PM' style provider reset hints."""
    m = re.search(r"try again at (\w+) (\d+)\w*, (\d{4}) (\d+):(\d+) (AM|PM)", text)
    if not m:
        return None
    month, day, year, hour, minute, ampm = m.groups()
    try:
        hour24 = int(hour) % 12 + (12 if ampm == "PM" else 0)
        dt = datetime.strptime(f"{month} {day} {year} {hour24}:{minute}", "%b %d %Y %H:%M")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def quota_signal(text: str) -> bool:
    lowered = (text or "").lower()
    return "usage limit" in lowered or "rate limit" in lowered or "purchase more credits" in lowered


QUOTA_CODE = "codex_handler_quota_exhausted"


def classify_transport_failure(text: str) -> str | None:
    """Canonical failure code for a creator-transport failure, or None.

    A quota/limit signal maps to the single catalog code so the log stops
    minting *_unclassified for the same recurring condition.
    """
    return QUOTA_CODE if quota_signal(text) else None


def park_on_quota(transport: str, failure_text: str) -> dict[str, Any]:
    """Park the repair lane on a quota/limit signal.

    Records a durable outage (auto-resume at the parsed reset time), returns the
    canonical code so the caller emits ONE deduped named alert and burns no new
    lease. Recovery and native close are unaffected -- they never consult this.
    A non-quota failure is not parked.
    """
    if not quota_signal(failure_text):
        return {"parked": False, "code": None}
    resume_at = parse_reset_time(failure_text)
    outage = record_outage(transport, resume_at=resume_at, evidence=failure_text[:200])
    return {"parked": True, "code": QUOTA_CODE, "transport": transport,
            "resume_at": outage.resume_at,
            "alert_dedup_key": f"{transport}:{QUOTA_CODE}"}


def _config_review_fallback() -> str:
    """Non-codex-first review route model from seat-routing config; env override wins.

    Single source of truth: the substitution target is the first eligible
    (non-codex) route of the repair_reviewer profile, so review work never falls
    back onto the scarce authoring transport. Falls back to the env constant if
    the config is unavailable.
    """
    if os.environ.get("PROJECT_WATCHDOG_CODEX_SEAT_FALLBACK"):
        return CODEX_SEAT_FALLBACK
    try:
        from . import seat_routing
        resolved = seat_routing.resolve("repair_reviewer", codex_out=True)
        if resolved.get("action") == "dispatch" and resolved.get("model"):
            return str(resolved["model"])
    except Exception:  # noqa: BLE001 - config problems fall back to the constant
        pass
    return CODEX_SEAT_FALLBACK


def substitute_dead_codex_seats(seats: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    """Swap non-authoring gpt-*/codex-* seats onto the fallback while codex is out."""
    if not active_outage("codex"):
        return seats, []
    fallback = _config_review_fallback()
    substitutions: list[dict[str, Any]] = []
    replaced: list[str] = []
    for seat in seats:
        s = seat.strip().lower()
        if s.startswith(("gpt-", "codex-")):
            replaced.append(fallback)
            substitutions.append({"from": seat, "to": fallback, "reason": "codex_transport_outage"})
        else:
            replaced.append(seat)
    # Two identical seats after substitution would break panel independence.
    seen: set[str] = set()
    deduped: list[str] = []
    for seat in replaced:
        if seat in seen:
            continue
        seen.add(seat)
        deduped.append(seat)
    return deduped, substitutions
