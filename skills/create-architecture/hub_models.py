"""Typed hub inputs and source bindings; reject incompatible views and stale evidence.

Inputs are agent-authored JSON requests, not executable commands. Models preserve
backend-native specifications and do not claim that a source citation proves meaning.
"""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class ErrorCode(StrEnum):
    SOURCE_SCOPE = "source_scope"
    SENSITIVE_SOURCE = "sensitive_source"
    SOURCE_SIZE = "source_size"
    SOURCE_DISCOVERY = "source_discovery"
    NO_SOURCES = "no_sources"
    STALE_SOURCE = "stale_source"
    SOURCE_LINES = "source_lines"
    UNSUPPORTED_ROUTE = "unsupported_route"
    MISSING_SKILL = "missing_skill"
    MISSING_ENTRYPOINT = "missing_entrypoint"
    DOWNSTREAM_FAILED = "downstream_failed"
    AGENT_HANDOFF_REQUIRED = "agent_handoff_required"
    NATIVE_INPUT_REQUIRED = "native_input_required"
    INPUT_SIZE = "input_size"
    OUTPUT_EXISTS = "output_exists"
    EMPTY_DIAGRAM = "empty_diagram"
    THEME_SCOPE = "theme_scope"
    RECEIPT_HASH = "receipt_hash"
    INVALID_SVG = "invalid_svg"
    STALE_NATIVE_INPUT = "stale_native_input"
    INVALID_REQUEST = "invalid_request"
    OPERATION_FAILED = "operation_failed"


class View(StrEnum):
    STRUCTURE = "structure"
    DAG = "dag"
    SEQUENCE = "sequence"
    DATAFLOW = "dataflow"
    LIFECYCLE = "lifecycle"
    ASSURANCE = "assurance"


class Surface(StrEnum):
    AUTO = "auto"
    TERMINAL = "terminal"
    SVG = "svg"
    PUBLICATION = "publication"
    INTERACTIVE = "interactive"
    WHITEBOARD = "whiteboard"
    DOCUMENT = "document"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(StrictModel):
    path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def ordered_lines(self) -> "Source":
        if self.end_line is not None and self.end_line < self.start_line:
            raise PydanticCustomError(
                "source_line_order", "end_line precedes start_line", {}
            )
        return self


class Request(StrictModel):
    schema_version: Literal[1] = 1
    target: Path
    question: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=2000)
    view: View = View.STRUCTURE
    surface: Surface = Surface.AUTO
    sources: list[Source] = Field(min_length=1, max_length=80)
    native_input: Path | None = None
    limitations: list[str] = Field(default_factory=list)


class Examination(StrictModel):
    schema_version: Literal["create_architecture.examination.v1"] = (
        "create_architecture.examination.v1"
    )
    status: Literal["NEEDS_SOURCE_READING"] = "NEEDS_SOURCE_READING"
    target: Path
    sources: list[Source] = Field(min_length=1, max_length=80)
    discovered: int = Field(ge=1)
    truncated: bool
    next_action: str = "Read relevant files, explain the system, choose view and surface, author native input, then call render. Do not stop at this inventory."
    proof_scope: str = (
        "File inventory and byte fingerprints only; no semantic architecture analysis."
    )


class Route(StrictModel):
    skill: str
    mode: Literal["executable", "agent-handoff"]
    view: View
    surface: Surface
    reason: str
    instructions: Path


class Artifact(StrictModel):
    path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0)


class SeamValidation(StrictModel):
    kind: Literal["source-to-diagram-draft"] = "source-to-diagram-draft"
    status: Literal["PASS"] = "PASS"


class Delivery(StrictModel):
    schema_version: Literal["create_architecture.delivery.v1"] = (
        "create_architecture.delivery.v1"
    )
    status: Literal["DRAFT"] = "DRAFT"
    route: Route
    request: Artifact
    native_input: Artifact
    artifact: Artifact
    preview: Artifact | None = None
    sources: list[Source]
    commands: list[list[str]]
    created_at: AwareDatetime
    mocked: Literal[False] = False
    live: Literal[True] = True
    visual_review: Literal["NOT_RUN"] = "NOT_RUN"
    semantic_review: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    proof_scope: str
    limitations: list[str]
    seam_validation: SeamValidation = Field(default_factory=SeamValidation)


class SvgValidation(BaseModel):
    """Consume the actual create-svg receipt without discarding its hash binding."""

    status: Literal["PASS"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssuranceSelector(StrictModel):
    # The downstream skill interpolates selectors into a query string. Accept
    # only bounded identifier characters, never quotes or query expressions.
    control: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
    )
    framework: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.: ()-]{0,127}$"
    )

    @model_validator(mode="after")
    def exactly_one(self) -> "AssuranceSelector":
        if bool(self.control) == bool(self.framework):
            raise PydanticCustomError(
                "gsn_selector", "provide control or framework, not both", {}
            )
        return self


class FigureComponent(StrictModel):
    name: str = Field(min_length=1)
    type: Literal["module", "interface", "database", "external", "config"] = "module"
    dependencies: list[str] = Field(default_factory=list, max_length=5)


class FigureInput(StrictModel):
    project_name: str = Field(min_length=1)
    components: list[FigureComponent] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def preserve_graph(self) -> "FigureInput":
        names = [c.name for c in self.components]
        tokens = [
            name.replace(" ", "_").replace("-", "_").replace(".", "_") for name in names
        ]
        if len(set(tokens)) != len(tokens) or not all(
            t.isidentifier() and t.isascii() for t in tokens
        ):
            raise PydanticCustomError(
                "figure_identity",
                "component names need distinct DOT-safe identifiers",
                {},
            )
        if (
            not self.project_name.replace(" ", "_").isidentifier()
            or not self.project_name.isascii()
        ):
            raise PydanticCustomError(
                "figure_project",
                "project_name must be a simple ASCII identifier or words",
                {},
            )
        for component in self.components:
            if any(dep not in names for dep in component.dependencies):
                raise PydanticCustomError(
                    "figure_dependency",
                    "dependency references an unknown component",
                    {},
                )
        return self
