"""Attach candidate LinkedIn profiles to people met through Meetup.

A Meetup attendee is a name, a group and an event. That is a lead only once it
can be reached, and reaching people happens on LinkedIn. This composes the
`ops-linkedin` skill rather than reimplementing it: that skill owns the LinkedIn
policy, the no-automation prohibitions, and the lead-gen lane, so identity
resolution belongs there and this module only asks.

The hard rule is that resolution NEVER asserts identity. The first live probe
for one attendee returned five distinct people of the same name - a CISSP at a
security company, a Deloitte managing director, a tig welder. Picking one
automatically would eventually greet a stranger as though Graham knew them, so
every row stays a ranked hypothesis carrying the query and the matched terms,
and the human confirms.

Bounded on purpose: each resolution is a live web search, so by default only
organizers are resolved - the person who convened the room is the one worth
meeting.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

OPS_LINKEDIN_RUN = Path(__file__).resolve().parents[3] / "ops-linkedin" / "run.sh"
DEFAULT_MAX_RESOLUTIONS = 8
RESOLVE_TIMEOUT_SECONDS = 90


def _is_resolvable_name(name: str) -> bool:
    """A name worth spending a live search on.

    A Meetup list yields truncated display names - one attendee was simply "R",
    which resolved to Rob Free and Kayla R: pure noise wearing a confidence
    label. A first name alone is not enough to identify anyone.
    """

    cleaned = " ".join(str(name or "").split())
    if len(cleaned) < 5:
        return False
    parts = [part for part in cleaned.split(" ") if len(part.strip(".")) > 1]
    return len(parts) >= 2


def _resolve_one(name: str, context: str, location: str) -> dict[str, Any] | None:
    if not OPS_LINKEDIN_RUN.is_file():
        return None
    try:
        proc = subprocess.run(
            [
                "bash", str(OPS_LINKEDIN_RUN), "resolve-leads", name,
                "--context", context, "--location", location,
            ],
            capture_output=True, text=True, timeout=RESOLVE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("linkedin resolution skipped for {}: {}", name, exc)
        return None
    start = proc.stdout.find("{")
    if proc.returncode != 0 or start < 0:
        return None
    try:
        return json.loads(proc.stdout[start:])
    except ValueError:
        return None


def attach_linkedin_candidates(
    signals: list[dict[str, Any]],
    *,
    location: str = "Buffalo",
    organizers_only: bool | None = None,
    max_resolutions: int | None = None,
) -> dict[str, Any]:
    """Add `linkedin_candidates` to event_copresence signals. Mutates in place."""

    if organizers_only is None:
        organizers_only = os.environ.get("MONITOR_LINKEDIN_ORGANIZERS_ONLY", "1") != "0"
    if max_resolutions is None:
        max_resolutions = int(os.environ.get("MONITOR_LINKEDIN_MAX_RESOLUTIONS", str(DEFAULT_MAX_RESOLUTIONS)))

    targets = [
        signal
        for signal in signals
        if signal.get("signal_type") == "event_copresence"
        and (signal.get("organizer") or not organizers_only)
        and _is_resolvable_name(str(signal.get("subject") or ""))
    ][:max_resolutions]

    skipped_unresolvable = sum(
        1
        for signal in signals
        if signal.get("signal_type") == "event_copresence"
        and not _is_resolvable_name(str(signal.get("subject") or ""))
    )
    resolved = 0
    strong = 0
    ambiguous = 0
    for signal in targets:
        context = " ".join(
            str(signal.get(field) or "")
            for field in ("organization", "event_title", "provenance")
        )
        result = _resolve_one(str(signal.get("subject") or ""), context, location)
        if not result:
            continue
        resolved += 1
        signal["linkedin_candidates"] = result.get("candidates") or []
        signal["linkedin_query"] = result.get("query")
        signal["linkedin_confirmation_required"] = True
        if result.get("ambiguous"):
            ambiguous += 1
        top = (result.get("candidates") or [{}])[0]
        if top.get("confidence") == "strong":
            strong += 1
            signal["linkedin_top_candidate"] = top.get("profile_url")
    return {
        "schema": "monitor_opportunities.linkedin_lead_resolution.v1",
        "signals_considered": len(signals),
        "resolution_attempted": len(targets),
        "resolved": resolved,
        "strong_top_candidate": strong,
        "ambiguous": ambiguous,
        "skipped_unresolvable_names": skipped_unresolvable,
        "organizers_only": organizers_only,
        "composed_skill": "ops-linkedin resolve-leads",
        "non_claims": [
            "A candidate profile is a hypothesis; no signal asserts an identity without human confirmation.",
            "Public web search only. No LinkedIn login, scraping, connection request, or message.",
        ],
        "external_effects": False,
    }
