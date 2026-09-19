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
    NodeStep,
    QuestionInput,
    RouteDecision,
    Selection,
    SourceProjection,
    SourceRevealEvent,
    DebuggerRunEvent,
    StepNextEvent,
    StepPreviousEvent,
    StepSelectEvent,
    TeleprompterProjection,
)
from .routing import _tokens, route


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
    *,
    configured: bool = False,
) -> str:
    if receipt is None:
        return "STALE" if configured else "NOT_CONFIGURED"

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


def _question_intent(question: QuestionInput | None) -> str:
    if question is None:
        return "unknown"
    text = question.text.lower()
    checks = (
        ("comparison", ("compare", "difference between", "versus")),
        ("debugger", ("debugger", "breakpoint", "runtime state")),
        ("diagram", ("diagram", "architecture map", "node")),
        ("source", ("source code", "which file", "where should i start", "start reading")),
        ("flow", ("walk through", "walk me through", "step by step", "end to end", "input to result")),
        ("scale", ("at scale", "bottleneck", "throughput", "workload")),
        ("tradeoff", ("tradeoff", "trade-off", "alternative")),
        ("proof", ("evidence", "prove", "proven", "unproven")),
        ("failure", ("fails", "failure", "crash", "half-written", "prevents")),
    )
    for intent, phrases in checks:
        if any(phrase in text for phrase in phrases):
            return intent
    return "direct"


def _spoken_answer(
    row: FeatureExplainer,
    step_index: int,
    question: QuestionInput | None,
) -> tuple[str, str, str]:
    """Build a truthful presenter answer from authored, typed evidence only."""
    steps = steps_for(row)
    step = steps[step_index]
    intent = _question_intent(question)
    missing = (
        "I found the relevant explainer, but it does not contain an authored "
        "answer to this question. The record supplies a source reference, not "
        "a complete explanation. The spoken answer still needs authoring."
    )
    if intent == "comparison":
        return (
            "This question asks for a comparison, but the current route selected "
            "only one explainer. I can show this explainer's evidence, but I need "
            "both records before I can make a source-backed comparison.",
            "PARTIAL", intent,
        )
    if intent == "flow":
        authored = [item.spoken for item in steps if item.spoken]
        if len(authored) != len(steps):
            return missing, "PARTIAL", intent
        stages = "; then ".join(item.title.lower() for item in steps)
        return (
            f"The flow has {len(steps)} stages: {stages}. "
            + " ".join(text.split(".", 1)[0] + "." for text in authored),
            "READY", intent,
        )
    if intent == "source":
        source = row.source_ranges[step.source_range_index]
        detail = step.spoken or missing
        return (
            f"Start in {source.file}, lines {source.start_line} through "
            f"{source.end_line}. {step.source_explanation} {detail}",
            "READY" if step.spoken else "PARTIAL", intent,
        )
    if intent == "debugger":
        if step.debugger_stop_index is None:
            return (
                "This explainer does not define a debugger target for the selected "
                "step. I can show the source range, but a runtime breakpoint and "
                "observed variable state are still missing.",
                "PARTIAL", intent,
            )
        target = row.debugger_stops[step.debugger_stop_index]
        return (
            f"Use the configured breakpoint at {target.file}, line {target.line}. "
            f"It is intended to prove {target.proves} The cockpit distinguishes "
            "this configured target from a debugger proof captured at runtime.",
            "READY", intent,
        )
    if intent == "diagram":
        nodes = ", then ".join(step.diagram_node_ids)
        return (
            f"Read the editable architecture board through {nodes}. These are the "
            "nodes bound to the selected source step; the highlight is navigation, "
            "not proof that the code executed.",
            "READY", intent,
        )
    if intent in {"scale", "tradeoff"}:
        return (
            f"The selected explainer is relevant, but it does not record a "
            f"source-backed {intent} answer. I will not infer one from the feature "
            "title; the missing constraint or rationale must be authored first.",
            "PARTIAL", intent,
        )
    if step.spoken:
        return step.spoken, "READY", intent
    return missing, "PARTIAL", intent


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
    emit_debugger_run: bool = False,
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
                spoken=(
                    "I do not have a source-backed explainer for that question. "
                    "I cleared the source, debugger, and diagram selections rather "
                    "than showing unrelated evidence."
                    if question is not None
                    else None
                ),
                answer_status="NO_MATCH" if question is not None else "PARTIAL",
                question_intent=_question_intent(question),
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
    spoken, answer_status, question_intent = _spoken_answer(
        row,
        bounded_index,
        question,
    )

    node_steps: list[NodeStep] = []
    for node_id in row.diagram.node_ids:
        for owning_index, owning_step in enumerate(steps):
            if node_id in owning_step.diagram_node_ids:
                node_steps.append(
                    NodeStep(node_id=node_id, step_index=owning_index)
                )
                break

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
    diagram_receipt = (
        _latest_step_receipt(
            safe_receipts,
            row.feature_id,
            step.step_id,
            "diagram_highlight",
        )
        or _latest_step_receipt(
            safe_receipts,
            row.feature_id,
            step.step_id,
            "excalidraw_proposal",
        )
    )

    debugger_status = "NONE"
    prepare_intent = None
    run_intent = None

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

        if emit_debugger_run:
            run_intent = debugger_target_intent(
                revision,
                debugger_target,
            )
            debugger_status = "RUN_INTENT"

    active_diagram_nodes = (
        row.diagram.node_ids
        if question_intent == "flow"
        else step.diagram_node_ids
    )

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
            spoken=spoken,
            answer_status=answer_status,
            question_intent=question_intent,
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
            run_intent=run_intent,
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
            active_node_ids=active_diagram_nodes,
            verified_binding=bool(row.diagram.sha256),
            highlight_intent=diagram_highlight_intent(
                revision,
                row.diagram,
                active_diagram_nodes,
            ),
            node_steps=node_steps,
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
                configured=True,
            ),
            debugger_target=(
                "READY"
                if proof is not None
                else _receipt_health(
                    debugger_receipt,
                    revision,
                    configured=debugger_target is not None,
                )
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


def _best_step_index(
    row: "FeatureExplainer",
    question: str,
) -> int:
    """Land on the step whose content best answers the asked question.

    Haystack is title+bullets only: source_explanation is shared code
    narration (e.g. "before any output is marked ready" on the *receive*
    step) that talks about the pipeline in general and steals report-last
    tokens like "ready"/"marked" from other steps' questions. Title/bullets
    are authored per-step and stay distinctive.

    With that cleaner haystack a single matched token is trustworthy, so
    ties and zero overlap fall back to step 0; the first strictly-better
    step wins.
    """
    from .catalog import steps_for

    qtokens = _tokens(question)
    scores = []
    for step in steps_for(row):
        haystack = " ".join([step.title, *step.bullets])
        scores.append(len(qtokens & _tokens(haystack)))
    best = max(scores, default=0)
    winners = [index for index, value in enumerate(scores) if value == best]
    return winners[0] if best > 0 and len(winners) == 1 else 0


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

    row = (
        _row_by_feature(rows, feature_id)
        if feature_id
        else None
    )

    return project_state(
        state.revision + 1,
        rows,
        question=question,
        route_decision=decision,
        feature_id=feature_id,
        step_index=(
            _best_step_index(row, question.text)
            if row is not None
            else 0
        ),
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

    if isinstance(event, StepSelectEvent):
        if state.selection is None:
            return state

        return project_state(
            state.revision + 1,
            rows,
            question=question,
            route_decision=decision,
            feature_id=feature_id,
            step_index=event.payload.step_index,
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

    if isinstance(event, DebuggerRunEvent):
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
            emit_debugger_run=True,
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
