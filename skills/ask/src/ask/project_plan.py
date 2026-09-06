"""Strict editable ask.project_plan.v1 proposals, not execution or closure proof.

Pydantic validates external fields before plan logic. The compatibility helper
returns (ok, errors); callers needing machine steering use ValidationError.errors().
"""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

SCHEMA_ID = "ask.project_plan.v1"
SemanticRole = Literal["coordinator", "backend", "frontend", "documentation", "testing", "independent_reviewer"]
HarnessMode = Literal["tau_native_agent_loop", "opaque_agent_compat"]
SEMANTIC_ROLES = frozenset(get_args(SemanticRole))
HARNESS_MODES = frozenset(get_args(HarnessMode))
DEFAULT_HARNESS_MODE = "tau_native_agent_loop"


def _nonblank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank_string", "must be a non-empty string")
    return value  # Preserve immutable goal and identifier bytes, not stripped text.


Nonblank = Annotated[str, AfterValidator(_nonblank)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NativeWorkstream(_StrictModel):
    id: Nonblank
    role: SemanticRole
    prompt: str = ""
    depends_on: list[Nonblank] = Field(default_factory=list)
    allowed_paths: list[Nonblank] = Field(default_factory=list)
    allowed_tools: list[Nonblank] | None = None
    cwd: Nonblank | None = None
    max_turns: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=16, ge=1)
    timeout_seconds: int = Field(default=300, ge=1)
    harness_mode: HarnessMode = DEFAULT_HARNESS_MODE
    compat_justification: str = ""

    @model_validator(mode="after")
    def compatibility_reason(self) -> Self:
        if self.harness_mode == "opaque_agent_compat" and not self.compat_justification.strip():
            raise PydanticCustomError("compat_justification_required", "opaque_agent_compat requires compat_justification")
        return self


class PlanTarget(_StrictModel):
    repo: Nonblank
    workspace: Nonblank | None = None


class PlanDeliverable(_StrictModel):
    name: Nonblank
    acceptance_criteria: list[Nonblank] = Field(min_length=1)


class PlanTeam(_StrictModel):
    preset: Nonblank | None = None
    profile_ids: list[Nonblank] = Field(default_factory=list)
    role_profiles: dict[SemanticRole, Nonblank] = Field(default_factory=dict)
    strength_mode: Literal["premium", "economical"] | None = None

    @model_validator(mode="after")
    def selection_required(self) -> Self:
        if not self.preset and not self.profile_ids:
            raise PydanticCustomError("team_selection_required", "team must set preset or profile_ids (SciLLM transport profile ids)")
        return self


class PlanExecution(_StrictModel):
    topology: Literal["sequential", "concurrent", "hybrid"] = "concurrent"
    max_concurrency: int = Field(default=1, ge=1)
    max_retries: int = Field(default=0, ge=0)


class ProjectPlan(_StrictModel):
    schema_: Literal["ask.project_plan.v1"] = Field(alias="schema")
    goal: Nonblank
    target: PlanTarget
    deliverables: list[PlanDeliverable]
    workstreams: list[NativeWorkstream]
    team: PlanTeam | None = None
    execution: PlanExecution = Field(default_factory=PlanExecution)
    unresolved: list[Nonblank] = Field(default_factory=list)

    @model_validator(mode="after")
    def dependency_contract(self) -> Self:
        # An explicitly unresolved proposal may lack workstreams/deliverables;
        # it is interview input and must never be compiled for execution.
        for field in ("deliverables", "workstreams"):
            if not getattr(self, field) and not self.unresolved:
                raise PydanticCustomError("plan_items_required", "{field} must be a non-empty list", {"field": field})
        graph: dict[str, list[str]] = {}
        for ws in self.workstreams:
            if ws.id in graph:
                raise PydanticCustomError("duplicate_workstream", "workstream id {node_id} is duplicated", {"node_id": ws.id})
            graph[ws.id] = ws.depends_on
        for ws in self.workstreams:
            for dep in ws.depends_on:
                if dep == ws.id:
                    raise PydanticCustomError("self_dependency", "workstream {node_id} depends on itself", {"node_id": ws.id})
                if dep not in graph:
                    raise PydanticCustomError("unknown_dependency", "depends_on references unknown workstream {dependency}", {"node_id": ws.id, "dependency": dep})
        try:
            TopologicalSorter(graph).prepare()
        except CycleError as exc:
            raise PydanticCustomError("dependency_cycle", "workstreams form a dependency cycle: {cycle}", {"cycle": exc.args[1]}) from exc
        return self


def validate_project_plan(plan: Any) -> tuple[bool, list[str]]:
    """Compatibility surface; Pydantic owns field and dependency validation."""
    if not isinstance(plan, dict):
        return False, ["plan must be a mapping"]
    try:
        ProjectPlan.model_validate(plan)
    except ValidationError as exc:
        return False, [
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False)
        ]
    return True, []
