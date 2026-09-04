"""Pydantic models for every project-watchdog lifecycle artifact.

The watchdog lifecycle consumes and produces structured data at each step:

    registry.json ->  scan issues  ->  route/lease  ->  dispatch  ->  receipt

Validating only the final receipt (see ``receipt_schema.py``) leaves the
inputs unchecked, so a malformed registry entry, a bad state gate, or a
surprise issue shape reaches routing logic untyped. These models validate the
load-bearing invariant of each artifact at its boundary. All use
``extra="allow"`` so unknown/forward-compat fields never break a load; they are
strict only on the fields the runtime dispatches on.

Each ``validate_*`` returns the parsed model and raises ``ValidationError`` on
a broken artifact — fail-closed, because a watchdog that routes off malformed
config is the failure these guard against.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

STATE_VALUES = ("active", "paused", "stopped")


class ProjectEntry(BaseModel):
    """One registered project. ``project_id`` and ``repo`` are load-bearing:
    routing, lease scoping, and every GitHub mutation address them."""

    model_config = ConfigDict(extra="allow")
    project_id: str = Field(min_length=1)
    repo: str = Field(min_length=1)

    @field_validator("repo")
    @classmethod
    def repo_is_owner_name(cls, value: str) -> str:
        if value.count("/") != 1 or value.startswith("/") or value.endswith("/"):
            raise ValueError(f"repo must be 'owner/name', got {value!r}")
        return value


class RegistryDoc(BaseModel):
    model_config = ConfigDict(extra="allow")
    # The load-bearing authority is the project list and each entry's id/repo,
    # not the schema string. schema is validated only when present so a
    # structurally-valid schema-less doc (internal/minimal) is not refused,
    # while a wrong schema string is still rejected.
    schema_: str | None = Field(default=None, alias="schema")
    projects: list[ProjectEntry]

    @field_validator("schema_")
    @classmethod
    def known_schema(cls, value: str | None) -> str | None:
        if value is not None and value != "agent_skills.project_watchdog.registry.v1":
            raise ValueError(f"unknown registry schema {value!r}")
        return value

    @field_validator("projects")
    @classmethod
    def unique_project_ids(cls, value: list[ProjectEntry]) -> list[ProjectEntry]:
        ids = [p.project_id for p in value]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate project_id(s): {sorted(dupes)}")
        return value


class GateState(BaseModel):
    """A fail-closed state gate. ``state`` must be one of the three known
    values; an unrecognized gate is refused rather than treated as active."""

    model_config = ConfigDict(extra="allow")
    state: Literal[STATE_VALUES]  # type: ignore[valid-type]


class StateDoc(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Authority is the global gate literal, not the schema string; validate
    # schema only when present (see RegistryDoc).
    schema_: str | None = Field(default=None, alias="schema")
    global_: GateState = Field(alias="global")
    projects: dict[str, GateState] = {}

    @field_validator("schema_")
    @classmethod
    def known_schema(cls, value: str | None) -> str | None:
        if value is not None and value != "agent_skills.project_watchdog.state.v1":
            raise ValueError(f"unknown state schema {value!r}")
        return value


class IssueLabel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = Field(min_length=1)


class Issue(BaseModel):
    """A scanned GitHub issue. ``number`` is load-bearing; labels drive
    routability and are normalized to objects with a ``name``."""

    model_config = ConfigDict(extra="allow")
    number: int
    title: str = ""
    body: str | None = ""
    labels: list[IssueLabel] = []
    url: str | None = None


def validate_registry(doc: dict[str, Any]) -> RegistryDoc:
    return RegistryDoc.model_validate(doc)


def validate_state(doc: dict[str, Any]) -> StateDoc:
    return StateDoc.model_validate(doc)


def validate_issue(doc: dict[str, Any]) -> Issue:
    return Issue.model_validate(doc)
