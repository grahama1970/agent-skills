"""Pure fleet admission policy for the single-cron replacement.

REFERENCE IMPLEMENTATION: not wired into commands.tick by this bundle.
No GitHub, subprocess, locks, leases, clock, persistent state, or provider calls.
The production adapter MUST preserve the native reservation/dispatch protocol.
An attempt is one complete, synchronous native ticket operation, not a daemon.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


@dataclass(frozen=True)
class TicketRef:
    repo: str
    number: int

    def __post_init__(self) -> None:
        _text(self.repo, "repo")
        if self.repo.count("/") != 1 or not all(self.repo.split("/")):
            raise ValueError("repo must be owner/name")
        if type(self.number) is not int or self.number < 1:
            raise ValueError("number must be a positive integer, not bool")

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class ProjectScan:
    project_id: str
    candidates: tuple[TicketRef, ...] = ()
    open_count: int | None = None
    complete: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        _text(self.project_id, "project_id")
        if type(self.complete) is not bool:
            raise ValueError("complete must be bool")
        if type(self.candidates) is not tuple or not all(
            isinstance(item, TicketRef) for item in self.candidates
        ):
            raise ValueError("candidates must be a tuple of TicketRef")
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError("duplicate candidate within project")
        if self.open_count is not None and (
            type(self.open_count) is not int or self.open_count < len(self.candidates)
        ):
            raise ValueError("open_count must cover all candidates")
        if self.complete and self.open_count is None:
            raise ValueError("complete scan requires open_count")
        if not self.complete and not self.reason:
            raise ValueError("incomplete scan requires a reason")
        if self.reason is not None:
            _text(self.reason, "reason")


class AttemptState(str, Enum):
    STARTED = "STARTED"
    NOT_STARTED = "NOT_STARTED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class AttemptResult:
    state: AttemptState
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, AttemptState):
            raise ValueError("state must be AttemptState")
        _text(self.reason, "reason")


@dataclass(frozen=True)
class AttemptRecord:
    project_id: str
    ticket: TicketRef
    result: AttemptResult


@dataclass(frozen=True)
class FleetResult:
    scans: tuple[ProjectScan, ...]
    attempts: tuple[AttemptRecord, ...]
    charged_slots: int
    scan_complete: bool
    queue_observation: str
    stop_reason: str
    last_served_project: str | None
    last_scanned_project: str | None


class ScanUnavailable(RuntimeError):
    """Expected observation failure; never translate to an empty queue."""


def run_fleet_policy(
    project_ids: tuple[str, ...],
    *,
    max_tickets: int,
    scan: Callable[[str], ProjectScan],
    attempt: Callable[[str, TicketRef], AttemptResult],
    budget_available: Callable[[], bool] = lambda: True,
) -> FleetResult:
    """Observe projects, then admit serially and fairly from their candidates.

    Input order is the authoritative registry rotation order. Scan must be
    observational; dependency maintenance is separate tick work and not service.
    Production supplies bounded calls and an admission deadline. The tick owns
    finalization outside this function, including on exceptions.

    STARTED means the native creator was durably accepted, even when its later
    proof/review failed. NOT_STARTED requires affirmative native evidence that
    no creator started. An ambiguous send consumes a slot and stops admission;
    the native operation journal, not this policy, owns its reconciliation.
    """
    if type(max_tickets) is not int or max_tickets < 1:
        raise ValueError("max_tickets must be a positive integer")
    if type(project_ids) is not tuple:
        raise ValueError("project_ids must be a tuple")
    for project_id in project_ids:
        _text(project_id, "project_id")
    if len(set(project_ids)) != len(project_ids):
        raise ValueError("duplicate registered project id")

    scans: list[ProjectScan] = []
    records: list[AttemptRecord] = []
    charged = 0
    last_served: str | None = None
    stop_reason = "CANDIDATES_EXHAUSTED"

    def has_budget() -> bool:
        available = budget_available()
        if type(available) is not bool:
            raise ValueError("budget_available must return bool")
        return available

    for project_id in project_ids:
        if not has_budget():
            stop_reason = "ADMISSION_DEADLINE"
            break
        try:
            result = scan(project_id)
        except ScanUnavailable as exc:
            result = ProjectScan(project_id, reason=f"SCAN_ERROR:{type(exc).__name__}")
        if not isinstance(result, ProjectScan) or result.project_id != project_id:
            raise ValueError("scan result project identity mismatch")
        scans.append(result)

    # Complete scans first keep queue evidence independent of admission. A scan
    # adapter may return validated candidates from partial pagination, but must
    # mark that scan incomplete. Do not sum per-project counts: scopes can overlap.
    queues = [(row.project_id, deque(row.candidates)) for row in scans]
    seen: set[str] = set()
    halt = False
    while not halt and any(queue for _, queue in queues) and charged < max_tickets:
        for project_id, queue in queues:
            # One charged admission per project per round. Races and unavailable
            # routes are not service and must not burn the project's slot.
            while queue:
                if charged >= max_tickets:
                    stop_reason = "MAX_TICKETS"
                    halt = True
                    break
                if not has_budget():
                    stop_reason = "ADMISSION_DEADLINE"
                    halt = True
                    break
                ticket = queue.popleft()
                if ticket.key in seen:
                    continue
                seen.add(ticket.key)
                try:
                    result = attempt(project_id, ticket)
                    if not isinstance(result, AttemptResult):
                        raise ValueError("attempt returned no validated result")
                except Exception as exc:
                    # The call may already have sent a dispatch. Never infer
                    # NOT_STARTED from an exception or retry it in this tick.
                    result = AttemptResult(
                        AttemptState.INDETERMINATE,
                        f"ADAPTER_EXCEPTION:{type(exc).__name__}",
                    )
                records.append(AttemptRecord(project_id, ticket, result))
                if result.state is not AttemptState.NOT_STARTED:
                    charged += 1
                    last_served = project_id
                    if result.state is AttemptState.INDETERMINATE:
                        stop_reason = "RECONCILE_REQUIRED"
                        halt = True
                    break
            if halt:
                break

    if charged >= max_tickets and stop_reason != "RECONCILE_REQUIRED":
        stop_reason = "MAX_TICKETS"
    complete = bool(project_ids) and len(scans) == len(project_ids) and all(
        row.complete for row in scans
    )
    if not project_ids:
        queue_observation = "NO_REGISTERED_PROJECTS"
    elif not complete:
        queue_observation = "NOT_FULLY_OBSERVED"
    elif all(row.open_count == 0 for row in scans):
        queue_observation = "OBSERVED_EMPTY"
    else:
        queue_observation = "OBSERVED_OPEN"
    # This is scan-time evidence, not a post-repair emptiness assertion. The
    # adapter records observed_at and a full block/dependency breakdown.
    return FleetResult(
        scans=tuple(scans), attempts=tuple(records), charged_slots=charged,
        scan_complete=complete, queue_observation=queue_observation,
        stop_reason=stop_reason, last_served_project=last_served,
        last_scanned_project=scans[-1].project_id if scans else None,
    )
