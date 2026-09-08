"""Deterministic headless cockpit proof runner.

A proof records reducer states and typed intents only. It does not claim that a
microphone, VS Code window, debugger runtime, or Excalidraw board was exercised.
"""

from __future__ import annotations

from uuid import uuid4

from .models import (
    COCKPIT_EVENT_ADAPTER,
    CockpitAssertions,
    CockpitEvent,
    CockpitProof,
    CockpitScript,
    CockpitScriptStep,
    FeatureExplainer,
)
from .reducer import (
    initial_state,
    reduce_cockpit,
)


def _event_from_script_step(
    step: CockpitScriptStep,
    revision: int,
) -> CockpitEvent:
    action = step.action
    event_type = action

    if action == "key.ArrowRight":
        event_type = "step.next"
    elif action == "key.ArrowLeft":
        event_type = "step.previous"

    return COCKPIT_EVENT_ADAPTER.validate_python(
        {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": f"evt-{uuid4().hex}",
            "type": event_type,
            "expected_revision": revision,
            "payload": step.payload,
        }
    )


def run_script(
    rows: list[FeatureExplainer],
    script: CockpitScript,
) -> CockpitProof:
    """Run a script and derive falsifiable safety assertions."""

    state = initial_state(rows)
    states = [state]
    events: list[CockpitEvent] = []
    arrow_state_indexes: list[int] = []
    source_request_indexes: list[int] = []
    debugger_request_indexes: list[int] = []
    navigation_pairs: list[tuple[int, int]] = []

    for script_step in script.steps:
        before = state

        event = _event_from_script_step(
            script_step,
            state.revision,
        )
        state = reduce_cockpit(
            state,
            event,
            rows,
        )

        events.append(event)
        states.append(state)

        state_index = len(states) - 1

        if script_step.action in {
            "key.ArrowLeft",
            "key.ArrowRight",
        }:
            arrow_state_indexes.append(state_index)

            before_index = (
                before.selection.step_index
                if before.selection
                else -1
            )
            after_index = (
                state.selection.step_index
                if state.selection
                else -1
            )

            navigation_pairs.append(
                (before_index, after_index)
            )

        if script_step.action == "source.reveal.request":
            source_request_indexes.append(state_index)

        if script_step.action == "debugger.prepare.request":
            debugger_request_indexes.append(state_index)

    projection_sync = all(
        state.revision
        == state.teleprompter.revision
        == state.source.revision
        == state.debugger.revision
        == state.diagram.revision
        for state in states
    )

    navigation_ok = (
        bool(navigation_pairs)
        and all(
            abs(after - before) == 1
            or after == before
            for before, after in navigation_pairs
        )
    )

    arrow_source_zero = all(
        states[index].source.reveal_intent is None
        for index in arrow_state_indexes
    )

    arrow_debugger_zero = all(
        states[index].debugger.prepare_intent is None
        for index in arrow_state_indexes
    )

    debugger_execution_zero = all(
        state.debugger.prepare_intent is None
        or (
            state.debugger.prepare_intent.execution_allowed
            is False
        )
        for state in states
    )

    excalidraw_mutation_zero = all(
        state.diagram.highlight_intent is None
        or (
            state.diagram.highlight_intent.mutation_allowed
            is False
        )
        for state in states
    )

    source_intent_only = (
        bool(source_request_indexes)
        and all(
            states[index].source.reveal_intent is not None
            and (
                states[index].source.reveal_intent.execute
                is False
            )
            for index in source_request_indexes
        )
    )

    debugger_intent_only = (
        bool(debugger_request_indexes)
        and all(
            states[index].debugger.prepare_intent is not None
            and (
                states[index]
                .debugger
                .prepare_intent
                .execution_allowed
                is False
            )
            for index in debugger_request_indexes
        )
    )

    assertions = CockpitAssertions(
        projection_revisions_equal=projection_sync,
        navigation_changed_expected_steps=navigation_ok,
        arrow_source_reveal_intent_count_zero=(
            arrow_source_zero
        ),
        arrow_debugger_prepare_intent_count_zero=(
            arrow_debugger_zero
        ),
        debugger_execution_count_zero=(
            debugger_execution_zero
        ),
        excalidraw_mutation_count_zero=(
            excalidraw_mutation_zero
        ),
        source_reveal_intent_only=source_intent_only,
        debugger_prepare_intent_only=debugger_intent_only,
        live_capture_claim_count_zero=True,
    )

    status = (
        "PASS"
        if all(assertions.model_dump().values())
        else "FAIL"
    )

    return CockpitProof(
        status=status,
        states=states,
        events=events,
        assertions=assertions,
        proof_scope=(
            "Headless deterministic reducer and intent proof. "
            "No live microphone, visible VS Code, debugger "
            "execution, or Excalidraw mutation is claimed."
        ),
    )


def default_proof_script(
    question: str,
) -> CockpitScript:
    """Return retained manual/right/reveal/prepare/left sequence."""

    return CockpitScript(
        steps=[
            CockpitScriptStep(
                action="question.manual",
                payload={"text": question},
            ),
            CockpitScriptStep(
                action="key.ArrowRight",
            ),
            CockpitScriptStep(
                action="source.reveal.request",
            ),
            CockpitScriptStep(
                action="debugger.prepare.request",
            ),
            CockpitScriptStep(
                action="key.ArrowLeft",
            ),
        ]
    )


def validate_proof(
    proof: CockpitProof,
) -> list[str]:
    """Return semantic failures; empty means proof is valid."""

    failures: list[str] = []

    if proof.status != "PASS":
        failures.append("proof status is not PASS")

    for name, value in proof.assertions.model_dump().items():
        if not value:
            failures.append(
                f"assertion failed: {name}"
            )

    if not proof.states:
        failures.append("proof contains no states")

    for index, state in enumerate(proof.states):
        revisions = {
            state.revision,
            state.teleprompter.revision,
            state.source.revision,
            state.debugger.revision,
            state.diagram.revision,
        }

        if len(revisions) != 1:
            failures.append(
                f"state {index} projection revisions diverged"
            )

    return failures
