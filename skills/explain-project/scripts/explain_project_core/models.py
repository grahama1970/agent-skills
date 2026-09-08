"""Strict typed contracts for explain-project.

Inputs are explainer JSONL records, cockpit events, Live Evidence question
candidates, and adapter receipts. Outputs are synchronized cockpit projections,
intent-only adapter requests, and deterministic proof artifacts. Every external
boundary rejects unknown fields. This module performs validation only; it does
not execute debugger commands, reveal VS Code, capture audio, or mutate boards.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    """Base model for fail-closed JSON boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class FailureCode(StrEnum):
    """Stable explain-project failure codes."""

    PYDANTIC_VALIDATION_FAILED = "PYDANTIC_VALIDATION_FAILED"
    JSON_DECODE_FAILED = "JSON_DECODE_FAILED"
    STALE_REVISION = "STALE_REVISION"
    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    STALE_ADAPTER_RECEIPT = "STALE_ADAPTER_RECEIPT"
    ADAPTER_RECEIPT_MISMATCH = "ADAPTER_RECEIPT_MISMATCH"
    LIVE_PROVENANCE_REQUIRED = "LIVE_PROVENANCE_REQUIRED"
    LIVE_RECEIPT_MISMATCH = "LIVE_RECEIPT_MISMATCH"
    INVALID_SCRIPT = "INVALID_SCRIPT"


Family: TypeAlias = Literal[
    "walkthrough",
    "scale",
    "failure",
    "optimize",
    "tradeoff",
    "confidence",
    "custom",
]
RouteStatus: TypeAlias = Literal["MATCHED", "AMBIGUOUS", "NO_MATCH"]
QuestionSource: TypeAlias = Literal[
    "manual",
    "live_evidence_replay",
    "live_evidence_live",
]
Confidence: TypeAlias = Literal["high", "medium", "low"]
IntegrationStatus: TypeAlias = Literal[
    "READY",
    "STALE",
    "FAILED",
    "NOT_CONFIGURED",
]


class SourceRange(StrictModel):
    """One source range referenced by an explainer."""

    file: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = None

    @model_validator(mode="after")
    def ordered(self) -> "SourceRange":
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class DebuggerStop(StrictModel):
    """Breakpoint target metadata; never an instruction to run a debugger."""

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    locals: list[str] = Field(default_factory=list)
    watches: list[str] = Field(default_factory=list)
    proves: str = Field(min_length=1)


class Diagram(StrictModel):
    """Editable diagram source plus optional portable SVG projection."""

    source_kind: Literal["excalidraw", "svg"] = "excalidraw"
    source_path: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1)
    rendered_svg_path: str | None = None
    editable: bool = True
    compiled_by: str | None = None
    sha256: str | None = None

    @model_validator(mode="after")
    def diagram_boundary(self) -> "Diagram":
        if self.source_kind == "excalidraw" and not self.editable:
            raise ValueError("excalidraw diagram source must be editable")
        return self


class RuntimeLaunch(StrictModel):
    """Documented runtime launch recipe; not executed by this slice."""

    command: list[str] = Field(min_length=1)
    cwd: str | None = None


class ExplainerStep(StrictModel):
    """One concise, slide-like cockpit step."""

    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    bullets: list[str] = Field(min_length=2, max_length=4)
    source_range_index: int = Field(ge=0)
    source_explanation: str = Field(min_length=1)
    debugger_stop_index: int | None = Field(default=None, ge=0)
    diagram_node_ids: list[str] = Field(min_length=1)
    proof_boundary: str | None = None
    confidence: Confidence | None = None


class FeatureExplainer(StrictModel):
    """Canonical project.feature_explainer.v1 record."""

    schema_: Literal["project.feature_explainer.v1"] = Field(alias="schema")
    feature_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question_family: Family
    question: str = Field(min_length=1)
    teleprompter_points: list[str] = Field(min_length=1)
    source_ranges: list[SourceRange] = Field(min_length=1)
    diagram: Diagram
    proof_boundary: str = Field(min_length=1)
    debugger_stops: list[DebuggerStop] = Field(default_factory=list)
    runtime_launch: RuntimeLaunch | None = None
    related_questions: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    last_verified: str | None = None
    steps: list[ExplainerStep] | None = None

    @field_validator("feature_id")
    @classmethod
    def feature_id_shape(cls, value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        if any(char not in allowed for char in value):
            raise ValueError(
                "feature_id must use lowercase letters, digits, "
                "dot, underscore or dash"
            )
        return value

    @model_validator(mode="after")
    def step_refs_exist(self) -> "FeatureExplainer":
        if not self.steps:
            return self

        seen: set[str] = set()
        nodes = set(self.diagram.node_ids)

        for step in self.steps:
            if step.step_id in seen:
                raise ValueError(f"duplicate step_id: {step.step_id}")
            seen.add(step.step_id)

            if step.source_range_index >= len(self.source_ranges):
                raise ValueError(
                    f"step {step.step_id} source_range_index out of range"
                )

            if (
                step.debugger_stop_index is not None
                and step.debugger_stop_index >= len(self.debugger_stops)
            ):
                raise ValueError(
                    f"step {step.step_id} debugger_stop_index out of range"
                )

            missing = [
                node_id
                for node_id in step.diagram_node_ids
                if node_id not in nodes
            ]
            if missing:
                raise ValueError(
                    f"step {step.step_id} unknown diagram_node_ids: {missing}"
                )

        return self


class LiveEvidenceEventSpan(StrictModel):
    """Subset-compatible copy of Live Evidence event-span provenance."""

    event_id: str = Field(min_length=8)
    sequence: int = Field(ge=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self) -> "LiveEvidenceEventSpan":
        if self.end_offset < self.start_offset:
            raise ValueError("end_offset must be >= start_offset")
        return self


class LiveEvidenceQuestionCandidate(StrictModel):
    """Strict mirror of live_evidence.question_candidate.v1."""

    schema_: Literal["live_evidence.question_candidate.v1"] = Field(
        alias="schema"
    )
    question_id: str = Field(min_length=12, max_length=80)
    normalized_question: str = Field(min_length=1, max_length=1_200)
    speaker: Literal["interviewer"] = "interviewer"
    source_event_ids: list[str] = Field(min_length=1, max_length=8)
    source_spans: list[LiveEvidenceEventSpan] = Field(
        min_length=1,
        max_length=8,
    )
    start_sequence: int = Field(ge=0)
    end_sequence: int = Field(ge=0)
    trigger_reason: str = Field(min_length=1, max_length=120)
    fingerprint: str = Field(min_length=12, max_length=96)

    @model_validator(mode="after")
    def lineage_is_consistent(self) -> "LiveEvidenceQuestionCandidate":
        if self.end_sequence < self.start_sequence:
            raise ValueError("end_sequence must be >= start_sequence")

        if [span.event_id for span in self.source_spans] != self.source_event_ids:
            raise ValueError(
                "source_spans must match source_event_ids order"
            )

        return self


class LiveEvidenceReceipt(StrictModel):
    """Receipt proving a question arrived through a live source seam."""

    schema_: Literal["explain_project.live_evidence_receipt.v1"] = Field(
        alias="schema",
        default="explain_project.live_evidence_receipt.v1",
    )
    receipt_id: str = Field(min_length=8)
    candidate_id: str = Field(min_length=12)
    candidate_fingerprint: str = Field(min_length=12)
    source_fingerprint: str = Field(min_length=12)
    source_ref: str | None = None
    captured_live: Literal[True] = True


class QuestionInput(StrictModel):
    """Normalized question accepted by the cockpit reducer."""

    schema_: Literal["explain_project.question_input.v1"] = Field(
        alias="schema",
        default="explain_project.question_input.v1",
    )
    input_id: str = Field(min_length=1)
    source: QuestionSource
    text: str = Field(min_length=1)
    source_ref: str | None = None
    source_fingerprint: str | None = None
    provenance: Literal[
        "manual",
        "replay",
        "live_fingerprint",
        "live_receipt",
    ]

    @model_validator(mode="after")
    def live_needs_provenance(self) -> "QuestionInput":
        if (
            self.source == "live_evidence_live"
            and not self.source_fingerprint
        ):
            raise ValueError(
                "live_evidence_live requires a live receipt "
                "or source_fingerprint"
            )
        return self


class RouteDecision(StrictModel):
    """Deterministic routing result."""

    schema_: Literal["explain_project.route_decision.v1"] = Field(
        alias="schema",
        default="explain_project.route_decision.v1",
    )
    status: RouteStatus
    question: str
    scores: dict[str, int]
    matched_feature: str | None = None
    candidates: list[str] = Field(default_factory=list)


class SourceRevealIntent(StrictModel):
    """Pure debugger-owned source-reveal request; performs no IO."""

    schema_: Literal["explain_project.source_reveal_intent.v1"] = Field(
        alias="schema",
        default="explain_project.source_reveal_intent.v1",
    )
    revision: int = Field(ge=0)
    adapter: Literal["debugger_vscode_bridge"] = "debugger_vscode_bridge"
    operation: Literal["source_reveal"] = "source_reveal"
    target: SourceRange
    preserve_focus: Literal[True] = True
    bridge_required: Literal[True] = True
    execute: Literal[False] = False


class DebuggerTargetIntent(StrictModel):
    """Breakpoint preparation request with execution disabled."""

    schema_: Literal["explain_project.debugger_target_intent.v1"] = Field(
        alias="schema",
        default="explain_project.debugger_target_intent.v1",
    )
    revision: int = Field(ge=0)
    adapter: Literal["debugger"] = "debugger"
    operation: Literal["prepare_target"] = "prepare_target"
    target: DebuggerStop
    execution_allowed: Literal[False] = False
    explicit_user_control_required: Literal[True] = True


class DiagramHighlightIntent(StrictModel):
    """Pure display highlight request for SVG/Excalidraw-bound nodes."""

    schema_: Literal["explain_project.diagram_highlight_intent.v1"] = Field(
        alias="schema",
        default="explain_project.diagram_highlight_intent.v1",
    )
    revision: int = Field(ge=0)
    source_kind: Literal["excalidraw", "svg"]
    source_path: str
    rendered_svg_path: str | None = None
    active_node_ids: list[str] = Field(min_length=1)
    mode: Literal["display_highlight_only"] = "display_highlight_only"
    mutation_allowed: Literal[False] = False


class DebuggerProofReference(StrictModel):
    """Reference to an externally validated debugger proof."""

    schema_: Literal[
        "explain_project.debugger_proof_reference.v1"
    ] = Field(
        alias="schema",
        default="explain_project.debugger_proof_reference.v1",
    )
    proof_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    validated: Literal[True] = True
    proves: str = Field(min_length=1)


class DebuggerRevealLocation(StrictModel):
    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    column: int | None = Field(default=None, ge=1)
    endLine: int | None = Field(default=None, ge=1)
    endColumn: int | None = Field(default=None, ge=1)
    selected: Literal[True]
    api: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def api_proves_preserve_focus_reveal(self) -> "DebuggerRevealLocation":
        required = {
            "window.showTextDocument(preserveFocus)",
            "TextEditor.revealRange",
        }
        if not required.issubset(set(self.api)):
            raise ValueError(
                "debugger reveal must use preserve-focus revealRange API"
            )
        return self


class DebuggerRevealStatus(StrictModel):
    """Debugger VS Code bridge source-reveal status boundary."""

    id: str = Field(min_length=1)
    requestHash: str = Field(min_length=64, max_length=64)
    proofValid: Literal[True]
    status: Literal["revealed"]
    reveal: DebuggerRevealLocation
    authority: dict[str, Any] | None = None
    artifactLocations: dict[str, str] | None = None
    updatedAt: str | None = None


class ExcalidrawProposalStatus(StrictModel):
    """ops-excalidraw safe proposal receipt boundary."""

    schema_: Literal[
        "ops_excalidraw.push_board.v1",
        "ops_excalidraw.describe.v1",
    ] = Field(alias="schema")
    status: Literal["PASS"]
    mode: Literal["proposal"]
    version: int = Field(ge=1)
    elements: int = Field(ge=1)


class AdapterReceipt(StrictModel):
    """External adapter readback bound to the intent revision."""

    schema_: Literal["explain_project.adapter_receipt.v1"] = Field(
        alias="schema",
        default="explain_project.adapter_receipt.v1",
    )
    receipt_id: str = Field(min_length=8)
    adapter: Literal[
        "source_reveal",
        "debugger_prepare",
        "debugger_proof",
        "diagram_highlight",
        "excalidraw_proposal",
    ]
    request_revision: int = Field(ge=0)
    feature_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    status: Literal[
        "PREPARED",
        "REVEALED",
        "BLOCKED",
        "PROOF_RECEIVED",
        "HIGHLIGHTED",
        "PROPOSED",
        "REFUSED",
    ]
    detail: str | None = None
    proof: DebuggerProofReference | None = None

    @model_validator(mode="after")
    def proof_status_matches(self) -> "AdapterReceipt":
        if self.status == "PROOF_RECEIVED" and (
            self.adapter != "debugger_proof"
            or self.proof is None
        ):
            raise ValueError(
                "PROOF_RECEIVED requires debugger_proof adapter and proof"
            )

        if self.proof is not None and self.adapter != "debugger_proof":
            raise ValueError(
                "proof is only valid for debugger_proof receipts"
            )

        return self


class Projection(StrictModel):
    """Base synchronized projection."""

    revision: int = Field(ge=0)


class TeleprompterProjection(Projection):
    title: str | None = None
    bullets: list[str] = Field(default_factory=list)
    proof_boundary: str | None = None
    confidence: Confidence | None = None
    verification: Literal[
        "not_live_proof",
        "debugger_proof_received",
    ] = "not_live_proof"


class SourceProjection(Projection):
    location: SourceRange | None = None
    explanation: str | None = None
    reveal_intent: SourceRevealIntent | None = None


class DebuggerProjection(Projection):
    target: DebuggerStop | None = None
    status: Literal[
        "NONE",
        "TARGET_READY",
        "PREPARE_INTENT",
        "BLOCKED",
        "PROOF_RECEIVED",
    ] = "NONE"
    prepare_intent: DebuggerTargetIntent | None = None
    proof: DebuggerProofReference | None = None


class DiagramProjection(Projection):
    source_kind: Literal["excalidraw", "svg"] | None = None
    source_path: str | None = None
    rendered_svg_path: str | None = None
    node_ids: list[str] = Field(default_factory=list)
    active_node_ids: list[str] = Field(default_factory=list)
    verified_binding: bool = False
    highlight_intent: DiagramHighlightIntent | None = None


class Selection(StrictModel):
    feature_id: str
    step_id: str
    step_index: int = Field(ge=0)
    step_count: int = Field(ge=1)


class IntegrationHealth(StrictModel):
    """Compact adapter health derived from revision-bound state."""

    live_evidence: IntegrationStatus = "NOT_CONFIGURED"
    source_reveal: IntegrationStatus = "NOT_CONFIGURED"
    debugger_target: IntegrationStatus = "NOT_CONFIGURED"
    diagram: IntegrationStatus = "NOT_CONFIGURED"


class CockpitState(StrictModel):
    """Single revisioned cockpit source of truth."""

    schema_: Literal["explain_project.cockpit_state.v1"] = Field(
        alias="schema",
        default="explain_project.cockpit_state.v1",
    )
    revision: int = Field(ge=0)
    route: RouteDecision | None = None
    question: QuestionInput | None = None
    selection: Selection | None = None
    teleprompter: TeleprompterProjection
    source: SourceProjection
    debugger: DebuggerProjection
    diagram: DiagramProjection
    integration_health: IntegrationHealth = Field(
        default_factory=IntegrationHealth,
    )
    adapter_receipts: list[AdapterReceipt] = Field(default_factory=list)

    @model_validator(mode="after")
    def projections_synced(self) -> "CockpitState":
        for name in ("teleprompter", "source", "debugger", "diagram"):
            if getattr(self, name).revision != self.revision:
                raise ValueError(
                    f"{name}.revision must equal root revision"
                )

        for intent in (
            self.source.reveal_intent,
            self.debugger.prepare_intent,
            self.diagram.highlight_intent,
        ):
            if intent is not None and intent.revision != self.revision:
                raise ValueError(
                    "adapter intent revision must equal root revision"
                )

        return self


class EmptyPayload(StrictModel):
    """Payload for events that intentionally carry no fields."""


class ExplainerSelectPayload(StrictModel):
    feature_id: str = Field(min_length=1)


class ManualQuestionPayload(StrictModel):
    text: str = Field(min_length=1, max_length=2_000)


class LiveEvidenceQuestionPayload(StrictModel):
    source: Literal[
        "live_evidence_replay",
        "live_evidence_live",
    ]
    candidate: LiveEvidenceQuestionCandidate
    source_fingerprint: str | None = Field(
        default=None,
        min_length=12,
    )
    live_receipt: LiveEvidenceReceipt | None = None


class AdapterReceiptPayload(StrictModel):
    receipt: AdapterReceipt


class BaseCockpitEvent(StrictModel):
    schema_: Literal["explain_project.cockpit_event.v1"] = Field(
        alias="schema",
        default="explain_project.cockpit_event.v1",
    )
    event_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)


class ExplainerSelectEvent(BaseCockpitEvent):
    type: Literal["explainer.select"]
    payload: ExplainerSelectPayload


class ManualQuestionEvent(BaseCockpitEvent):
    type: Literal["question.manual"]
    payload: ManualQuestionPayload


class LiveEvidenceQuestionEvent(BaseCockpitEvent):
    type: Literal["question.live_evidence"]
    payload: LiveEvidenceQuestionPayload


class StepNextEvent(BaseCockpitEvent):
    type: Literal["step.next"]
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class StepPreviousEvent(BaseCockpitEvent):
    type: Literal["step.previous"]
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class SourceRevealEvent(BaseCockpitEvent):
    type: Literal["source.reveal.request"]
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class DebuggerPrepareEvent(BaseCockpitEvent):
    type: Literal["debugger.prepare.request"]
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class AdapterReceiptEvent(BaseCockpitEvent):
    type: Literal["adapter.receipt"]
    payload: AdapterReceiptPayload


CockpitEvent: TypeAlias = Annotated[
    ExplainerSelectEvent
    | ManualQuestionEvent
    | LiveEvidenceQuestionEvent
    | StepNextEvent
    | StepPreviousEvent
    | SourceRevealEvent
    | DebuggerPrepareEvent
    | AdapterReceiptEvent,
    Field(discriminator="type"),
]

COCKPIT_EVENT_ADAPTER = TypeAdapter(CockpitEvent)


class ExplainerImportRequest(StrictModel):
    record: FeatureExplainer


class ExplainerSummary(StrictModel):
    feature_id: str
    title: str
    question_family: Family
    question: str
    steps: int = Field(ge=1)


class BootstrapResponse(StrictModel):
    schema_: Literal["explain_project.bootstrap.v1"] = Field(
        alias="schema",
        default="explain_project.bootstrap.v1",
    )
    state: CockpitState
    explainers: list[ExplainerSummary]


class LiveEvidenceIntakeRequest(StrictModel):
    """Cockpit-owned wrapper for live-evidence question intake."""

    schema_: Literal["explain_project.live_evidence_intake.v1"] = Field(
        alias="schema",
        default="explain_project.live_evidence_intake.v1",
    )
    source: Literal[
        "live_evidence_replay",
        "live_evidence_live",
    ] = "live_evidence_replay"
    candidate: LiveEvidenceQuestionCandidate
    source_fingerprint: str | None = Field(
        default=None,
        min_length=12,
    )
    live_receipt: LiveEvidenceReceipt | None = None


class LiveEvidenceIntakeResponse(StrictModel):
    """Result of a Live Evidence question intake post."""

    schema_: Literal["explain_project.live_evidence_intake_response.v1"] = Field(
        alias="schema",
        default="explain_project.live_evidence_intake_response.v1",
    )
    status: Literal["ACCEPTED", "DUPLICATE"]
    duplicate: bool
    question_id: str
    state: CockpitState


class ActionDefinition(StrictModel):
    """QuerySpec-compatible UI action registration."""

    element_id: str = Field(min_length=3, max_length=240)
    app: str = Field(min_length=2, max_length=120)
    action: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]+$",
        max_length=160,
    )
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=30)


class ActionRegistrationBatch(StrictModel):
    actions: list[ActionDefinition] = Field(
        min_length=1,
        max_length=200,
    )


class TriagedFailure(StrictModel):
    schema_: Literal["explain_project.triaged_failure.v1"] = Field(
        alias="schema",
        default="explain_project.triaged_failure.v1",
    )
    status: Literal["FAIL"] = "FAIL"
    failure_code: FailureCode
    message: str
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CockpitScriptStep(StrictModel):
    action: Literal[
        "question.manual",
        "question.live_evidence",
        "explainer.select",
        "key.ArrowRight",
        "key.ArrowLeft",
        "source.reveal.request",
        "debugger.prepare.request",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)


class CockpitScript(StrictModel):
    schema_: Literal["explain_project.cockpit_script.v1"] = Field(
        alias="schema",
        default="explain_project.cockpit_script.v1",
    )
    steps: list[CockpitScriptStep] = Field(min_length=1)


class CockpitAssertions(StrictModel):
    projection_revisions_equal: bool
    navigation_changed_expected_steps: bool
    arrow_source_reveal_intent_count_zero: bool
    arrow_debugger_prepare_intent_count_zero: bool
    debugger_execution_count_zero: bool
    excalidraw_mutation_count_zero: bool
    source_reveal_intent_only: bool
    debugger_prepare_intent_only: bool
    live_capture_claim_count_zero: bool


class CockpitProof(StrictModel):
    schema_: Literal["explain_project.cockpit_proof.v1"] = Field(
        alias="schema",
        default="explain_project.cockpit_proof.v1",
    )
    status: Literal["PASS", "FAIL"]
    states: list[CockpitState]
    events: list[CockpitEvent]
    assertions: CockpitAssertions
    proof_scope: str
