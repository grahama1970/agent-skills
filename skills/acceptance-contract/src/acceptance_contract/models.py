"""Typed contracts for acceptance-contract.

Inputs are local brief files, directories, or zip bundles. Outputs are strict
JSON records: a source-backed acceptance bundle, optional immutable-goal draft,
and a create-report-compatible report. Invalid inputs fail closed with pydantic
errors instead of partial prose.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    ZIP = "zip"


class GoalMode(StrEnum):
    CREATE = "create"
    AMEND = "amend"
    NONE = "none"


class RequirementKind(StrEnum):
    MUST = "must"
    FORBIDDEN = "forbidden"
    ACCEPTANCE = "acceptance"
    SHOULD = "should"


class CaseKind(StrEnum):
    MUST_ACCEPT = "MUST_ACCEPT"
    MUST_REJECT = "MUST_REJECT"
    MUST_VERIFY = "MUST_VERIFY"


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    bytes: int = Field(ge=0)
    lines: int = Field(ge=0)


class SourceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: SourceKind
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    files: list[SourceFile] = Field(default_factory=list)


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^REQ-[0-9]{3}$")
    kind: RequirementKind
    statement: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_line: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)


class AcceptanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^AC-[0-9]{3}$")
    requirement_id: str = Field(pattern=r"^REQ-[0-9]{3}$")
    kind: CaseKind
    predicate: str = Field(min_length=1)
    deterministic_check: str = Field(min_length=1)
    proof_artifacts: list[str] = Field(min_length=1)


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^Q-[0-9]{3}$")
    question: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_line: int = Field(ge=1)


class ImmutableGoalDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: GoalMode
    path: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    mutation_policy: Literal["draft_only_human_approval_required"]


class AcceptanceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["acceptance_contract.bundle.v1"] = Field(alias="schema")
    project_name: str = Field(min_length=1)
    source: SourceBundle
    requirements: list[Requirement] = Field(default_factory=list)
    acceptance_cases: list[AcceptanceCase] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    immutable_goal: ImmutableGoalDraft | None = None
    non_claims: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def check_case_requirements(self) -> "AcceptanceBundle":
        req_ids = {req.id for req in self.requirements}
        missing = [case.requirement_id for case in self.acceptance_cases if case.requirement_id not in req_ids]
        if missing:
            raise ValueError(f"acceptance cases reference missing requirements: {missing}")
        if not self.requirements and not self.open_questions:
            raise ValueError("empty extraction must carry at least one open question")
        return self
