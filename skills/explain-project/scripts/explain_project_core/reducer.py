"""Single-revision reducer for the explain-project cockpit.

Every state transition is deterministic. Arrow navigation only changes the
selected step and synchronized projections; it never emits source-reveal or
debugger-prepare intents. Diagram highlights are display-only intents with
mutation explicitly disabled.
"""

from __future__ import annotations

from .adapters import (
    AdapterBoundaryError,
    debugger_target_intent,
    diagram_highlight_intent,
    normalize_live_evidence_question,
    normalize_manual_question,
    source_reveal_intent,
)
from .catalog import steps_for
from .models import (
    AdapterReceipt,
    AdapterReceiptEvent,
    CockpitEvent,
    CockpitState,
    DebuggerPrepareEvent,
    DebuggerProjection,
    DiagramProjection,
    ExplainerSelectEvent,
    FailureCode,
    FeatureExplainer,
    IntegrationHealth,
    LiveEvidenceQuestionEvent,
    ManualQuestionEvent,
    QuestionInput,
    RouteDecision,
    Selection,
    SourceProjection,
    SourceRevealEvent,
    StepNextEvent,
    StepPreviousEvent,
    TeleprompterProjection,
)
from .routing import route


class CockpitReducerError(ValueError):
    """Deterministic reducer failure with stable code."""

    def __init__(
        self,
        code: FailureCode,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


def _row_by_feature(
    rows: list[FeatureExplainer],
    feature_id: str | None,
) -> FeatureExplainer | None:
    if feature_id is None:
        return None

    return next(
        (
            row
            for row in rows
            if row.feature_id == feature_id
        ),
        None,
    )


def _latest_step_receipt(
    receipts: list[AdapterReceipt],
    feature_id: str,
    step_id: str,
    adapter: str,
) -> AdapterReceipt | None:
    matching = [
        receipt
        for receipt in receipts
        if receipt.adapter == adapter
        and receipt.feature_id == feature_id
        and receipt.step_id == step_id
    ]
    return matching[-1] if matching else None


def _receipt_health(
    receipt: AdapterReceipt | None,
    revision: int,
) -> str:
    if receipt is None:
        return "NOT_CONFIGURED"

    if receipt.request_revision != revision - 1:
        return "STALE"

    if receipt.status in {"BLOCKED", "REFUSED"}:
        return "FAILED"

    return "READY"


def _latest_debugger_proof(
    receipts: list[AdapterReceipt],
    feature_id: str,
    step_id: str,
):
    matching = [
        receipt
        for receipt in receipts
        if receipt.adapter == "debugger_proof"
        and receipt.status == "PROOF_RECEIVED"
        and receipt.feature_id == feature_id
        and receipt.step_id == step_id
        and receipt.proof is not None
    ]
    return matching[-1].proof if matching else None


def project_state(
    revision: int,
    rows: list[FeatureExplainer],
    *,
    question: QuestionInput | None = None,
    route_decision: RouteDecision | None = None,
    feature_id: str | None = None,
    step_index: int = 0,
    receipts: list[AdapterReceipt] | None = None,
    emit_source_reveal: bool = False,
    emit_debugger_prepare: bool = False,
) -> CockpitState:
    """Project every cockpit pane from one revision and selected step."""

    safe_receipts = list(receipts or [])
    row = _row_by_feature(rows, feature_id)

    if row is None:
        return CockpitState(
            revision=revision,
            route=route_decision,
            question=question,
            selection=None,
            teleprompter=TeleprompterProjection(
                revision=revision,
            ),
            source=SourceProjection(
                revision=revision,
            ),
            debugger=DebuggerProjection(
                revision=revision,
            ),
            diagram=DiagramProjection(
                revision=revision,
            ),
            integration_health=IntegrationHealth(
                live_evidence=(
                    "READY"
                    if question is not None
                    and question.source.startswith("live_evidence")
                    else "NOT_CONFIGURED"
                ),
            ),
            adapter_receipts=safe_receipts,
        )

    steps = steps_for(row)
    bounded_index = min(
        max(step_index, 0),
        len(steps) - 1,
    )
    step = steps[bounded_index]

    source = row.source_ranges[
        step.source_range_index
    ]

    debugger_target = (
        row.debugger_stops[
            step.debugger_stop_index
        ]
        if step.debugger_stop_index is not None
        else None
    )

    proof = _latest_debugger_proof(
        safe_receipts,
        row.feature_id,
        step.step_id,
    )
    source_receipt = _latest_step_receipt(
        safe_receipts,
        row.feature_id,
        step.step_id,
        "source_reveal",
    )
    debugger_receipt = _latest_step_receipt(
        safe_receipts,
        row.feature_id,
        step.step_id,
        "debugger_prepare",
    )
    diagram_receipt = _latest_step_receipt(
        safe_receipts,
        row.feature_id,
        step.step_id,
        "diagram_highlight",
    )

    debugger_status = "NONE"
    prepare_intent = None

    if debugger_target is not None:
        debugger_status = (
            "PROOF_RECEIVED"
            if proof is not None
            else "TARGET_READY"
        )

        if emit_debugger_prepare:
            prepare_intent = debugger_target_intent(
                revision,
                debugger_target,
            )
            debugger_status = "PREPARE_INTENT"

    return CockpitState(
        revision=revision,
        route=route_decision,
        question=question,
        selection=Selection(
            feature_id=row.feature_id,
            step_id=step.step_id,
            step_index=bounded_index,
            step_count=len(steps),
        ),
        teleprompter=TeleprompterProjection(
            revision=revision,
            title=step.title,
            bullets=step.bullets,
            proof_boundary=(
                step.proof_boundary
                or row.proof_boundary
            ),
            confidence=(
                step.confidence
                or row.confidence
            ),
            verification=(
                "debugger_proof_received"
                if proof is not None
                else "not_live_proof"
            ),
        ),
        source=SourceProjection(
            revision=revision,
            location=source,
            explanation=step.source_explanation,
            reveal_intent=(
                source_reveal_intent(
                    revision,
                    source,
                )
                if emit_source_reveal
                else None
            ),
        ),
        debugger=DebuggerProjection(
            revision=revision,
            target=debugger_target,
            status=debugger_status,
            prepare_intent=prepare_intent,
            proof=proof,
        ),
        diagram=DiagramProjection(
            revision=revision,
            source_kind=row.diagram.source_kind,
            source_path=row.diagram.source_path,
            rendered_svg_path=(
                row.diagram.rendered_svg_path
            ),
            node_ids=row.diagram.node_ids,
            active_node_ids=step.diagram_node_ids,
            verified_binding=bool(row.diagram.sha256),
            highlight_intent=diagram_highlight_intent(
                revision,
                row.diagram,
                step.diagram_node_ids,
            ),
        ),
        integration_health=IntegrationHealth(
            live_evidence=(
                "READY"
                if question is not None
                and question.source.startswith("live_evidence")
                else "NOT_CONFIGURED"
            ),
            source_reveal=_receipt_health(
                source_receipt,
                revision,
            ),
            debugger_target=(
                "READY"
                if proof is not None
                else _receipt_health(debugger_receipt, revision)
            ),
            diagram=(
                _receipt_health(diagram_receipt, revision)
                if diagram_receipt is not None
                else (
                    "READY"
                    if row.diagram.sha256
                    else "NOT_CONFIGURED"
                )
            ),
        ),
        adapter_receipts=safe_receipts,
    )


def initial_state(
    rows: list[FeatureExplainer],
) -> CockpitState:
    """Return an unselected synchronized revision-zero state."""

    return project_state(0, rows)


def _project_routed_question(
    state: CockpitState,
    rows: list[FeatureExplainer],
    question: QuestionInput,
) -> CockpitState:
    decision = route(rows, question.text)

    feature_id = (
        decision.matched_feature
        if decision.status == "MATCHED"
        else None
    )

    return project_state(
        state.revision + 1,
        rows,
        question=question,
        route_decision=decision,
        feature_id=feature_id,
        step_index=0,
        receipts=state.adapter_receipts,
    )


def reduce_cockpit(
    state: CockpitState,
    event: CockpitEvent,
    rows: list[FeatureExplainer],
) -> CockpitState:
    """Apply one event against the expected state revision."""

    if event.expected_revision != state.revision:
        raise CockpitReducerError(
            FailureCode.STALE_REVISION,
            (
                f"stale expected_revision "
                f"{event.expected_revision}; "
                f"current {state.revision}"
            ),
        )

    feature_id = (
        state.selection.feature_id
        if state.selection
        else None
    )
    step_index = (
        state.selection.step_index
        if state.selection
        else 0
    )
    question = state.question
    decision = state.route
    receipts = list(state.adapter_receipts)

    if isinstance(event, ManualQuestionEvent):
        return _project_routed_question(
            state,
            rows,
            normalize_manual_question(
                event.event_id,
                event.payload.text,
            ),
        )

    if isinstance(event, LiveEvidenceQuestionEvent):
        try:
            normalized = normalize_live_evidence_question(
                event.event_id,
                event.payload,
            )
        except AdapterBoundaryError as error:
            raise CockpitReducerError(
                error.code,
                str(error),
            ) from error

        return _project_routed_question(
            state,
            rows,
            normalized,
        )

    if isinstance(event, ExplainerSelectEvent):
        row = _row_by_feature(
            rows,
            event.payload.feature_id,
        )

        if row is None:
            raise CockpitReducerError(
                FailureCode.UNKNOWN_FEATURE,
                (
                    "unknown feature_id: "
                    f"{event.payload.feature_id}"
                ),
            )

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=row.feature_id,
            step_index=0,
            receipts=receipts,
        )

    if isinstance(event, StepNextEvent):
        if (
            state.selection is None
            or step_index
            >= state.selection.step_count - 1
        ):
            return state

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=step_index + 1,
            receipts=receipts,
        )

    if isinstance(event, StepPreviousEvent):
        if (
            state.selection is None
            or step_index == 0
        ):
            return state

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=step_index - 1,
            receipts=receipts,
        )

    if isinstance(event, SourceRevealEvent):
        if state.source.location is None:
            return state

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=step_index,
            receipts=receipts,
            emit_source_reveal=True,
        )

    if isinstance(event, DebuggerPrepareEvent):
        if state.debugger.target is None:
            return state

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=step_index,
            receipts=receipts,
            emit_debugger_prepare=True,
        )

    if isinstance(event, AdapterReceiptEvent):
        receipt = event.payload.receipt

        if receipt.request_revision != state.revision:
            raise CockpitReducerError(
                FailureCode.STALE_ADAPTER_RECEIPT,
                (
                    "adapter receipt request_revision "
                    f"{receipt.request_revision} != "
                    f"current {state.revision}"
                ),
            )

        if state.selection is None or (
            receipt.feature_id
            != state.selection.feature_id
            or receipt.step_id
            != state.selection.step_id
        ):
            raise CockpitReducerError(
                FailureCode.ADAPTER_RECEIPT_MISMATCH,
                (
                    "adapter receipt does not bind to "
                    "the active feature/step"
                ),
            )

        receipts.append(receipt)

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=step_index,
            receipts=receipts,
        )

    return state
