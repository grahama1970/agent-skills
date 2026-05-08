"""Task and result schemas for code-runner.

Inputs are JSON task specifications from project agents. Outputs are JSON
artifacts consumed by project agents and regression tests. Validation failures
are explicit and occur before backend calls or git mutations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .adapters import supported_backends


class DefinitionOfDone(BaseModel):
    """Deterministic command plus machine-checkable assertion."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., min_length=1)
    assertion: str = Field(..., min_length=1)


class TaskSpec(BaseModel):
    """Validated input contract for one code-runner task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=20)
    backend: str = Field("codex")
    cwd: str = Field(..., min_length=1)
    output_dir: str = Field(..., min_length=1)
    allowlist: list[str] = Field(..., min_length=1)
    definition_of_done: DefinitionOfDone
    read_context: list[str] = Field(default_factory=list)
    max_rounds: int = Field(8, ge=1, le=20)
    timeout_seconds: int = Field(1800, ge=60, le=7200)
    dirty_worktree_policy: Literal["isolated_worktree"] = "isolated_worktree"
    apply_to_source: bool = False
    commit_on_success: bool = False
    rollback_on_failure: bool = True

    @field_validator("cwd")
    @classmethod
    def cwd_must_exist(cls, value: str) -> str:
        if not Path(value).exists():
            raise ValueError(f"cwd does not exist: {value}")
        return value

    @field_validator("backend")
    @classmethod
    def backend_must_be_known(cls, value: str) -> str:
        known = supported_backends()
        if value not in known:
            raise ValueError(f"unknown backend: {value}")
        return value

    @field_validator("allowlist", "read_context")
    @classmethod
    def paths_must_be_relative_and_normalized(cls, value: list[str]) -> list[str]:
        for item in value:
            path = Path(item)
            if not item or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"path must be relative and normalized: {item!r}")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_removed_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        removed = [
            name
            for name in (
                "predecessor_patches",
                "escalation_chain",
                "hidden_tests",
                "skills",
                "memory",
                "planner",
                "reviewer",
                "backend_racing",
            )
            if data.get(name)
        ]
        if removed:
            raise ValueError(f"unsupported code-runner field(s): {', '.join(removed)}")
        return data

    @model_validator(mode="after")
    def validate_cross_field_contract(self) -> "TaskSpec":
        if self.commit_on_success and not self.apply_to_source:
            raise ValueError("commit_on_success requires apply_to_source")
        cwd = Path(self.cwd).expanduser().resolve()
        output_dir = Path(self.output_dir).expanduser().resolve()
        if (cwd / ".git").exists():
            try:
                output_dir.relative_to(cwd)
            except ValueError:
                pass
            else:
                raise ValueError("output_dir must not be inside cwd/source repo")
        return self


class RoundDetail(BaseModel):
    """One attempt at satisfying the DoD."""

    round: int
    status: str
    dod_passed: bool
    score: float
    written_files: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    error: str = ""


class TaskResult(BaseModel):
    """Final result artifact."""

    task_id: str
    title: str
    status: str
    dod_passed: bool
    backend: str
    rounds: int
    best_score: float
    error: str = ""
    execution_mode: str = "isolated_worktree"
    patch_artifact: str = ""
    worktree_path: str = ""
    worktree_removed: bool = False
    source_head_before: str = ""
    source_head_after: str = ""
    source_status_before: list[str] = Field(default_factory=list)
    source_status_after: list[str] = Field(default_factory=list)
    source_unchanged: bool = False
    round_details: list[dict[str, Any]] = Field(default_factory=list)
    apply_to_source: bool = False
    source_patch_applied: bool = False
    source_dod_passed: bool = False
    source_commit: str = ""
    source_rollback_applied: bool = False
    source_apply_error: str = ""
