#!/usr/bin/env python3
"""Retained deterministic evals for the explain-project cockpit slice."""

from __future__ import annotations

from pydantic import ValidationError

from explain_project_core.adapters import (
    AdapterBoundaryError,
    normalize_live_evidence_question,
)
from explain_project_core.catalog import sample_record
from explain_project_core.models import (
    AdapterReceipt,
    COCKPIT_EVENT_ADAPTER,
    LiveEvidenceQuestionPayload,
    QuestionInput,
)
from explain_project_core.reducer import (
    initial_state,
    reduce_cockpit,
)
from explain_project_core.routing import route
from explain_project_core.server import CockpitSession


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def candidate_payload() -> dict[str, object]:
    return {
        "schema": "live_evidence.question_candidate.v1",
        "question_id": "question-12345",
        "normalized_question": (
            "What happens if a worker crashes "
            "before reporting success?"
        ),
        "speaker": "interviewer",
        "source_event_ids": [
            "event-12345678"
        ],
        "source_spans": [
            {
                "event_id": "event-12345678",
                "sequence": 7,
                "start_offset": 0,
                "end_offset": 60,
            }
        ],
        "start_sequence": 7,
        "end_sequence": 7,
        "trigger_reason": "question_mark",
        "fingerprint": (
            "candidate-fingerprint-12345"
        ),
    }


def main() -> None:
    row = sample_record()
    rows = [row]

    matched = route(
        rows,
        (
            "worker crashes before success "
            "incomplete release"
        ),
    )

    require(
        (
            matched.status == "MATCHED"
            and matched.matched_feature
            == row.feature_id
        ),
        "MATCHED routing failed",
    )

    duplicate_data = row.model_dump(
        by_alias=True,
        mode="json",
    )
    duplicate_data["feature_id"] = (
        "publish.report_last_alt"
    )

    duplicate = type(row).model_validate(
        duplicate_data
    )

    ambiguous = route(
        [row, duplicate],
        "worker crashes before reporting success",
    )

    require(
        (
            ambiguous.status == "AMBIGUOUS"
            and len(ambiguous.candidates) == 2
        ),
        "AMBIGUOUS routing failed",
    )

    require(
        (
            route(
                rows,
                "oauth calendar webhook aliens",
            ).status
            == "NO_MATCH"
        ),
        "NO_MATCH routing failed",
    )

    state = initial_state(rows)

    manual = COCKPIT_EVENT_ADAPTER.validate_python(
        {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": "evt-manual",
            "type": "question.manual",
            "expected_revision": 0,
            "payload": {
                "text": (
                    "worker crashes before success "
                    "incomplete release"
                )
            },
        }
    )

    state = reduce_cockpit(
        state,
        manual,
        rows,
    )

    require(
        (
            state.selection is not None
            and state.selection.step_index == 0
        ),
        "manual route did not select step zero",
    )

    right = COCKPIT_EVENT_ADAPTER.validate_python(
        {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": "evt-right",
            "type": "step.next",
            "expected_revision": state.revision,
            "payload": {},
        }
    )

    right_state = reduce_cockpit(
        state,
        right,
        rows,
    )

    require(
        (
            right_state.selection is not None
            and right_state.selection.step_index == 1
        ),
        "ArrowRight reducer failed",
    )

    require(
        len(
            {
                right_state.revision,
                right_state.teleprompter.revision,
                right_state.source.revision,
                right_state.debugger.revision,
                right_state.diagram.revision,
            }
        )
        == 1,
        "ArrowRight projection revisions diverged",
    )

    require(
        right_state.debugger.prepare_intent is None,
        "ArrowRight emitted debugger prepare intent",
    )

    require(
        right_state.source.reveal_intent is None,
        "ArrowRight emitted source reveal intent",
    )

    require(
        (
            right_state.diagram.highlight_intent
            is not None
            and (
                right_state
                .diagram
                .highlight_intent
                .mutation_allowed
                is False
            )
        ),
        "ArrowRight diagram intent could mutate",
    )

    require(
        (
            right_state.integration_health.diagram == "READY"
            and right_state.integration_health.source_reveal
            == "NOT_CONFIGURED"
            and right_state.integration_health.debugger_target
            == "NOT_CONFIGURED"
        ),
        "integration health is not state-derived",
    )

    left = COCKPIT_EVENT_ADAPTER.validate_python(
        {
            "schema": "explain_project.cockpit_event.v1",
            "event_id": "evt-left",
            "type": "step.previous",
            "expected_revision": (
                right_state.revision
            ),
            "payload": {},
        }
    )

    left_state = reduce_cockpit(
        right_state,
        left,
        rows,
    )

    require(
        (
            left_state.selection is not None
            and left_state.selection.step_index == 0
        ),
        "ArrowLeft reducer failed",
    )

    require(
        len(
            {
                left_state.revision,
                left_state.teleprompter.revision,
                left_state.source.revision,
                left_state.debugger.revision,
                left_state.diagram.revision,
            }
        )
        == 1,
        "ArrowLeft projection revisions diverged",
    )

    require(
        left_state.debugger.prepare_intent is None,
        "ArrowLeft emitted debugger prepare intent",
    )

    require(
        left_state.source.reveal_intent is None,
        "ArrowLeft emitted source reveal intent",
    )

    reveal_event = (
        COCKPIT_EVENT_ADAPTER
        .validate_python(
            {
                "schema": (
                    "explain_project."
                    "cockpit_event.v1"
                ),
                "event_id": "evt-reveal",
                "type": "source.reveal.request",
                "expected_revision": (
                    left_state.revision
                ),
                "payload": {},
            }
        )
    )

    reveal_state = reduce_cockpit(
        left_state,
        reveal_event,
        rows,
    )

    require(
        (
            reveal_state.source.reveal_intent
            is not None
            and (
                reveal_state
                .source
                .reveal_intent
                .execute
                is False
            )
        ),
        "source reveal was not intent-only",
    )

    reveal_receipt_event = (
        COCKPIT_EVENT_ADAPTER
        .validate_python(
            {
                "schema": (
                    "explain_project."
                    "cockpit_event.v1"
                ),
                "event_id": "evt-source-receipt",
                "type": "adapter.receipt",
                "expected_revision": reveal_state.revision,
                "payload": {
                    "receipt": AdapterReceipt(
                        receipt_id="source-reveal-receipt-12345",
                        adapter="source_reveal",
                        request_revision=reveal_state.revision,
                        feature_id=(
                            reveal_state.selection.feature_id
                        ),
                        step_id=reveal_state.selection.step_id,
                        status="REVEALED",
                        detail=(
                            "debugger_status=/tmp/status.json; "
                            "revealed=src/anonymization_trial/"
                            "pipeline.py:210"
                        ),
                    ).model_dump(
                        by_alias=True,
                        mode="json",
                    )
                },
            }
        )
    )

    receipt_state = reduce_cockpit(
        reveal_state,
        reveal_receipt_event,
        rows,
    )

    require(
        (
            receipt_state.integration_health.source_reveal
            == "READY"
        ),
        "source reveal receipt did not mark source health READY",
    )

    prepare_event = (
        COCKPIT_EVENT_ADAPTER
        .validate_python(
            {
                "schema": (
                    "explain_project."
                    "cockpit_event.v1"
                ),
                "event_id": "evt-prepare",
                "type": "debugger.prepare.request",
                "expected_revision": (
                    reveal_state.revision
                ),
                "payload": {},
            }
        )
    )

    prepare_state = reduce_cockpit(
        reveal_state,
        prepare_event,
        rows,
    )

    require(
        (
            prepare_state
            .debugger
            .prepare_intent
            is not None
        ),
        "debugger prepare intent missing",
    )

    require(
        (
            prepare_state
            .debugger
            .prepare_intent
            .execution_allowed
            is False
        ),
        "debugger prepare could execute",
    )

    replay_payload = (
        LiveEvidenceQuestionPayload
        .model_validate(
            {
                "source": "live_evidence_replay",
                "candidate": candidate_payload(),
            }
        )
    )

    replay = normalize_live_evidence_question(
        "evt-replay",
        replay_payload,
    )

    require(
        (
            replay.source
            == "live_evidence_replay"
            and replay.provenance == "replay"
        ),
        "replay normalization failed",
    )

    live_payload = (
        LiveEvidenceQuestionPayload
        .model_validate(
            {
                "source": "live_evidence_live",
                "candidate": candidate_payload(),
            }
        )
    )

    try:
        normalize_live_evidence_question(
            "evt-live",
            live_payload,
        )
    except AdapterBoundaryError:
        pass
    else:
        raise RuntimeError(
            "live_evidence_live without "
            "live receipt/fingerprint was accepted"
        )

    live_ok = (
        LiveEvidenceQuestionPayload
        .model_validate(
            {
                "source": "live_evidence_live",
                "candidate": candidate_payload(),
                "source_fingerprint": (
                    "live-source-fingerprint-12345"
                ),
            }
        )
    )

    normalized_live = (
        normalize_live_evidence_question(
            "evt-live-ok",
            live_ok,
        )
    )

    require(
        (
            normalized_live.provenance
            == "live_fingerprint"
        ),
        "live fingerprint normalization failed",
    )

    session = CockpitSession(
        rows,
        "http://127.0.0.1:8601",
    )
    accepted = session.intake_live_evidence(
        candidate_payload()
    )
    duplicate_response = session.intake_live_evidence(
        candidate_payload()
    )

    require(
        accepted.status == "ACCEPTED"
        and accepted.state.revision == 1
        and accepted.state.question is not None
        and accepted.state.question.source
        == "live_evidence_replay"
        and accepted.state.integration_health.live_evidence
        == "READY",
        "raw Live Evidence candidate intake failed",
    )

    require(
        duplicate_response.status == "DUPLICATE"
        and duplicate_response.duplicate is True
        and duplicate_response.state.revision
        == accepted.state.revision,
        "Live Evidence duplicate changed state",
    )

    try:
        QuestionInput.model_validate(
            {
                "schema": (
                    "explain_project."
                    "question_input.v1"
                ),
                "input_id": "bad-live",
                "source": "live_evidence_live",
                "text": "question",
                "provenance": "live_fingerprint",
            }
        )
    except ValidationError:
        pass
    else:
        raise RuntimeError(
            "strict live QuestionInput accepted "
            "missing fingerprint"
        )

    print(
        "EXPLAIN_PROJECT_COCKPIT_CONTRACT_EVAL_OK"
    )


if __name__ == "__main__":
    main()
