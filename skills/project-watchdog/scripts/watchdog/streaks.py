"""Consecutive-idle tracking so prolonged silence escalates instead of looking healthy.

Purpose
    A watchdog that reports ``NOOP / ok: true`` every minute forever is
    indistinguishable from a working one. On 2026-07-27 this skill was found to
    have logged **41,607** consecutive ``no_routable_issues`` ticks over roughly
    a month while a label-vocabulary mismatch meant nothing could ever match.
    Every one of those ticks was reported as a success.

    This module makes silence measurable: an idle streak that outlives
    ``config.NOOP_ESCALATION_SECONDS`` stops being a steady state and becomes
    ``NEEDS_ATTENTION`` with a concrete diagnosis.

Inputs
    A project id and the outcome of each tick. Streak state persists at
    ``config.state_root()/streaks.json`` — runtime state, deliberately separate
    from the operator-owned ``registry/state.json``.

Outputs
    A ``StreakStatus`` describing the current idle run, whether it has crossed
    the escalation threshold, and whether this particular tick should persist a
    receipt (so escalation does not reintroduce one receipt directory per
    minute).

Failure modes
    An unreadable or malformed ``streaks.json`` is logged at ERROR and treated
    as empty. Losing streak history must never stop a tick: the safe default is
    "start counting again", not "refuse to run".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from . import config

SCHEMA = "agent_skills.project_watchdog.streaks.v1"

#: What an operator should check when a project has been idle far too long.
#: Mirrors the troubleshooting section of SKILL.md.
IDLE_DIAGNOSIS = [
    "Label vocabulary: routing needs 'agent-work' plus either "
    "('next:coder' + 'executor:local' + repair marker) or "
    "('executor:local' + handoff marker). Tickets filed by /ticket carry "
    "'type:*' and 'route:*' labels and will never match. Check with: "
    "gh issue list --repo <repo> --label agent-work",
    "Lease labels: issues carrying 'agent-active' or 'agent-blocked' are "
    "skipped by design until a human clears them.",
    "Queue really is empty: if the above check out, this is expected and the "
    "escalation threshold should be raised.",
]


@dataclass
class StreakStatus:
    """One project's current idle run and what the tick should do about it."""

    project_id: str
    consecutive_ticks: int = 0
    idle_seconds: float = 0.0
    first_idle_at: str | None = None
    escalated: bool = False
    should_persist_receipt: bool = False
    diagnosis: list[str] = field(default_factory=list)

    def as_receipt_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {
            "consecutive_idle_ticks": self.consecutive_ticks,
            "idle_seconds": round(self.idle_seconds, 1),
            "idle_since": self.first_idle_at,
            "escalation_threshold_seconds": config.NOOP_ESCALATION_SECONDS,
            "escalated": self.escalated,
        }
        if self.escalated:
            block["diagnosis"] = self.diagnosis
        return block


def _streaks_path() -> Path:
    return config.state_root() / "streaks.json"


def _load() -> dict[str, Any]:
    path = _streaks_path()
    if not path.is_file():
        return {"schema": SCHEMA, "projects": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("root must be a JSON object")
        payload.setdefault("projects", {})
        return payload
    except (OSError, ValueError) as exc:
        logger.error("unreadable streak state {}, starting fresh: {}", path, exc)
        return {"schema": SCHEMA, "projects": {}}


def _save(payload: dict[str, Any]) -> None:
    payload["schema"] = SCHEMA
    path = _streaks_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.error("could not persist streak state {}: {}", path, exc)


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.error("unparseable streak timestamp {!r}; treating as absent", value)
        return None


def record_idle(project_id: str) -> StreakStatus:
    """Count one idle tick for ``project_id`` and decide whether to escalate."""
    payload = _load()
    entry = payload["projects"].setdefault(project_id, {})
    now = _now()

    entry["consecutive_idle_ticks"] = int(entry.get("consecutive_idle_ticks", 0)) + 1
    first_idle = _parse(entry.get("first_idle_at")) or now
    entry["first_idle_at"] = _iso(first_idle)
    entry["last_idle_at"] = _iso(now)

    idle_seconds = (now - first_idle).total_seconds()
    escalated = idle_seconds >= config.NOOP_ESCALATION_SECONDS

    should_persist = False
    if escalated:
        last_escalated = _parse(entry.get("last_escalated_at"))
        if last_escalated is None:
            should_persist = True
        else:
            since = (now - last_escalated).total_seconds()
            should_persist = since >= config.NOOP_RENOTIFY_SECONDS
        if should_persist:
            entry["last_escalated_at"] = _iso(now)
            logger.warning(
                "project {} has been idle for {:.0f}s across {} ticks; escalating",
                project_id,
                idle_seconds,
                entry["consecutive_idle_ticks"],
            )

    _save(payload)
    return StreakStatus(
        project_id=project_id,
        consecutive_ticks=int(entry["consecutive_idle_ticks"]),
        idle_seconds=idle_seconds,
        first_idle_at=entry["first_idle_at"],
        escalated=escalated,
        should_persist_receipt=should_persist,
        diagnosis=list(IDLE_DIAGNOSIS) if escalated else [],
    )


def clear_idle(project_id: str) -> None:
    """Reset the idle streak because routable work was found."""
    payload = _load()
    if payload["projects"].pop(project_id, None) is not None:
        _save(payload)


def peek(project_id: str) -> dict[str, Any]:
    """Return the stored streak entry without mutating it."""
    return dict(_load()["projects"].get(project_id, {}))


def all_streaks() -> dict[str, Any]:
    """Return every stored streak entry, for ``status`` reporting."""
    return dict(_load()["projects"])
