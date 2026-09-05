"""Watchdog-owned persistence boundaries. Native Tau/ticket retain their schemas."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class FileVersion(StrictRecord):
    kind: Literal["file", "symlink", "absent"]
    oid: str | None = None
    sha256: str | None = None
    mode: str | None = None

    @model_validator(mode="after")
    def complete_version(self):
        if self.kind == "absent":
            if any(x is not None for x in (self.oid, self.sha256, self.mode)):
                raise ValueError("absent paths have no content")
        elif not self.oid or not self.sha256 or self.mode not in {"100644", "100755", "120000"}:
            raise ValueError("content must have a blob, digest and Git mode")
        return self


class TargetSnapshot(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.target_snapshot.v2"] = Field(
        default="agent_skills.project_watchdog.target_snapshot.v2", alias="schema")
    targets: list[str]
    files: dict[str, FileVersion]
    index_entries: dict[str, str]
    remote_sha: str
    head: str


class OwnedTargets(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.owned_targets.v2"] = Field(
        default="agent_skills.project_watchdog.owned_targets.v2", alias="schema")
    repo: str
    issue_number: int = Field(gt=0)
    task_sha256: str
    run_id: str
    targets: list[str]
    files: dict[str, FileVersion]
    provenance: Literal["authored_checkpoint", "settled_attempt", "verified_publication"]


class QueueState(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.queue.v2"] = Field(
        default="agent_skills.project_watchdog.queue.v2", alias="schema")
    sequence: int = Field(default=0, ge=0)
    attempts: dict[str, int] = Field(default_factory=dict)


class LeaseEvent(StrictRecord):
    id: int
    event: Literal["labeled", "unlabeled"]
    actor: str
    created_at: str


class VerificationPlan(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.verification_plan.v1"] = Field(
        default="agent_skills.project_watchdog.verification_plan.v1", alias="schema")
    commands: list[str] = Field(min_length=1)
    artifacts: list[str] = Field(min_length=1)
    # Each required-proof clause must be addressed explicitly by independent review.
    coverage: dict[str, str] = Field(min_length=1)


class NativeClosure(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.native_closure.v1"] = Field(
        default="agent_skills.project_watchdog.native_closure.v1", alias="schema")
    proof_path: str
    proof_sha256: str
    review_path: str
    review_sha256: str
    commit: str
    remote_required: bool
    scope: list[str]
    content: TargetSnapshot


class Operation(StrictRecord):
    schema_: Literal["agent_skills.project_watchdog.primary_operation.v2"] = Field(
        default="agent_skills.project_watchdog.primary_operation.v2", alias="schema")
    phase: Literal["reserved", "acquiring_lease", "leased", "launching", "running",
                   "uncertain", "settled", "closing", "releasing", "finished", "retryable"]
    run_id: str
    repo: str
    project_id: str
    issue_number: int = Field(gt=0)
    action: str
    owner_token: str
    root: str
    journal: str
    result_path: str
    receipt_dir: str
    targets: list[str] = Field(min_length=1)
    task_sha256: str
    scheduler_pid: int
    worker_pid: int | None = None
    worker_start_ticks: str | None = None
    boot_id: str
    lease_actor: str | None = None
    lease_before_event: LeaseEvent | None = None
    lease_event: LeaseEvent | None = None
    lease_agent: str | None = None
    lease_released: bool = False
    ask_pid: int | None = None
    ask_run_dir: str | None = None
    dispatched_at: float | None = None
    launch_failed_before_exec: bool = False
    tau_settled: bool = False
    closure: NativeClosure | None = None
    # Command results/proof payloads are evidence, never unvalidated authority.
    result: dict[str, Any] | None = None
    recovery: str | None = None

    @model_validator(mode="after")
    def phase_authority(self):
        if self.phase in {"leased", "launching", "running", "uncertain", "settled", "closing", "releasing"} and not self.lease_event:
            raise ValueError("execution requires a confirmed native lease generation")
        if self.phase == "settled" and not self.tau_settled:
            raise ValueError("settled phase requires native settlement evidence")
        if self.closure is not None and (self.closure.scope != self.targets or self.closure.content.targets != self.targets):
            raise ValueError("closure cannot widen its operation's target scope")
        if self.phase == "closing" and (not self.tau_settled or self.closure is None):
            raise ValueError("closure requires settled Tau and a durable proof outbox")
        return self


def encoded(record: StrictRecord) -> dict:
    return record.model_dump(mode="json", by_alias=True)
