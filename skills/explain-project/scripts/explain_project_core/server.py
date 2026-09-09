"""Small local HTTP API for the explain-project cockpit.

The server binds to loopback by default, stores only session state in memory,
and uses optimistic revision checks through the reducer. It does not expose
WebSockets, cockpit persistence, microphone capture, debugger execution, or
board mutation. QuerySpec action registration is forwarded to Memory's
app_actions collection when available and degrades without blocking the UI.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from typing import Any
from urllib.parse import urlsplit

import httpx
from loguru import logger
from pydantic import ValidationError

from .catalog import summaries
from .models import (
    ActionDefinition,
    ActionRegistrationBatch,
    BootstrapResponse,
    COCKPIT_EVENT_ADAPTER,
    ExplainerImportRequest,
    FailureCode,
    FeatureExplainer,
    LiveEvidenceIntakeRequest,
    LiveEvidenceIntakeResponse,
    LiveEvidenceQuestionCandidate,
    TriagedFailure,
)
from .reducer import (
    CockpitReducerError,
    initial_state,
    project_state,
    reduce_cockpit,
)

MAX_BODY_BYTES = 2_000_000


def _dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(
            by_alias=True,
            mode="json",
        )
    return model


def _validation_errors(
    error: ValidationError,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []

    for item in error.errors():
        entry = dict(item)

        if "ctx" in entry:
            entry["ctx"] = {
                key: str(value)
                for key, value in entry["ctx"].items()
            }

        cleaned.append(entry)

    return cleaned


class ActionRegistry:
    """Deduplicate UI actions and publish them through Memory."""

    def __init__(
        self,
        memory_url: str,
    ) -> None:
        self._memory_url = memory_url.rstrip("/")
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _key(
        action: ActionDefinition,
    ) -> str:
        return (
            f"{action.app}::"
            f"{action.action}::"
            f"{action.element_id}"
        )

    @staticmethod
    def _document(
        action: ActionDefinition,
    ) -> dict[str, Any]:
        raw_key = ActionRegistry._key(action)
        digest = hashlib.sha256(
            raw_key.encode("utf-8")
        ).hexdigest()[:40]

        return {
            "_key": f"explain_project_{digest}",
            "doc_type": "action_registration",
            "app": action.app,
            "action": action.action,
            "element_id": action.element_id,
            "label": action.label,
            "description": action.description,
            "problem": (
                f"{action.label}: {action.description}"
            ),
            "solution": json.dumps(
                {
                    "ui_action": action.action,
                    "params": action.params,
                },
                sort_keys=True,
            ),
            "tags": [
                "queryspec-action",
                action.app,
                f"action:{action.action}",
                *action.tags,
            ],
            "scope": action.app,
            "registered_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    def register(
        self,
        actions: list[ActionDefinition],
    ) -> dict[str, Any]:
        with self._lock:
            unseen = [
                action
                for action in actions
                if self._key(action) not in self._seen
            ]

            for action in unseen:
                self._seen.add(self._key(action))

        if not unseen:
            return {
                "status": "ok",
                "registered": 0,
                "memory_written": False,
            }

        documents = [
            self._document(action)
            for action in unseen
        ]

        try:
            with httpx.Client(
                timeout=3.0,
                trust_env=False,
            ) as client:
                response = client.post(
                    f"{self._memory_url}/upsert",
                    json={
                        "collection": "app_actions",
                        "documents": documents,
                    },
                    headers={
                        "X-Caller-Skill": "explain-project",
                    },
                )
                response.raise_for_status()

            return {
                "status": "ok",
                "registered": len(unseen),
                "memory_written": True,
            }

        except (
            httpx.HTTPError,
            OSError,
            ValueError,
        ) as error:
            logger.warning(
                "action registration degraded: {}",
                type(error).__name__,
            )

            return {
                "status": "degraded",
                "registered": len(unseen),
                "memory_written": False,
                "detail": type(error).__name__,
            }


class CockpitSession:
    """In-memory catalog and reducer state for one local process."""

    def __init__(
        self,
        rows: list[FeatureExplainer],
        memory_url: str,
    ) -> None:
        self._rows = list(rows)
        self._state = initial_state(self._rows)
        self._seen_live_questions: set[str] = set()
        self._lock = threading.Lock()
        self.actions = ActionRegistry(memory_url)

    def bootstrap(self) -> BootstrapResponse:
        with self._lock:
            return BootstrapResponse(
                state=self._state,
                explainers=summaries(self._rows),
            )

    def dispatch(
        self,
        raw_event: dict[str, Any],
    ):
        event = COCKPIT_EVENT_ADAPTER.validate_python(
            raw_event
        )

        with self._lock:
            self._state = reduce_cockpit(
                self._state,
                event,
                self._rows,
            )
            return self._state

    @staticmethod
    def _live_intake_request(
        body: dict[str, Any],
    ) -> LiveEvidenceIntakeRequest:
        if (
            body.get("schema")
            == "live_evidence.question_candidate.v1"
        ):
            return LiveEvidenceIntakeRequest(
                candidate=(
                    LiveEvidenceQuestionCandidate
                    .model_validate(body)
                ),
            )

        return LiveEvidenceIntakeRequest.model_validate(body)

    def intake_live_evidence(
        self,
        body: dict[str, Any],
    ) -> LiveEvidenceIntakeResponse:
        request = self._live_intake_request(body)
        question_key = (
            f"{request.candidate.question_id}:"
            f"{request.candidate.fingerprint}"
        )

        with self._lock:
            if question_key in self._seen_live_questions:
                return LiveEvidenceIntakeResponse(
                    status="DUPLICATE",
                    duplicate=True,
                    question_id=request.candidate.question_id,
                    state=self._state,
                )

            event = COCKPIT_EVENT_ADAPTER.validate_python(
                {
                    "schema": "explain_project.cockpit_event.v1",
                    "event_id": (
                        "live-evidence:"
                        f"{request.candidate.question_id}"
                    ),
                    "type": "question.live_evidence",
                    "expected_revision": self._state.revision,
                    "payload": request.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude={"schema_"},
                    ),
                }
            )
            self._state = reduce_cockpit(
                self._state,
                event,
                self._rows,
            )
            self._seen_live_questions.add(question_key)

            return LiveEvidenceIntakeResponse(
                status="ACCEPTED",
                duplicate=False,
                question_id=request.candidate.question_id,
                state=self._state,
            )

    def import_explainer(
        self,
        request: ExplainerImportRequest,
    ) -> BootstrapResponse:
        with self._lock:
            replacement_index = next(
                (
                    index
                    for index, row in enumerate(self._rows)
                    if (
                        row.feature_id
                        == request.record.feature_id
                    )
                ),
                None,
            )

            if replacement_index is None:
                self._rows.append(request.record)
            else:
                self._rows[replacement_index] = request.record

            feature_id = (
                self._state.selection.feature_id
                if self._state.selection
                else None
            )
            step_index = (
                self._state.selection.step_index
                if self._state.selection
                else 0
            )

            # Import changes cockpit-visible catalog state.
            # Advance one root revision and re-project all panes.
            self._state = project_state(
                self._state.revision + 1,
                self._rows,
                question=self._state.question,
                route_decision=self._state.route,
                feature_id=feature_id,
                step_index=step_index,
                receipts=self._state.adapter_receipts,
            )

            return BootstrapResponse(
                state=self._state,
                explainers=summaries(self._rows),
            )


def _handler_factory(
    session: CockpitSession,
):
    class Handler(BaseHTTPRequestHandler):
        server_version = "explain-project/1"

        def log_message(
            self,
            format_string: str,
            *args: Any,
        ) -> None:
            logger.debug(
                format_string,
                *args,
            )

        def _json(
            self,
            status: int,
            payload: Any,
        ) -> None:
            body = json.dumps(
                _dump(payload),
                separators=(",", ":"),
            ).encode("utf-8")

            self.send_response(status)
            self.send_header(
                "content-type",
                "application/json; charset=utf-8",
            )
            self.send_header(
                "content-length",
                str(len(body)),
            )
            self.send_header(
                "cache-control",
                "no-store",
            )
            self.end_headers()
            self.wfile.write(body)

        def _read_json(
            self,
        ) -> dict[str, Any]:
            loopback = {'127.0.0.1', 'localhost', '::1'}
            host = self.headers.get('host', '')
            origin = self.headers.get('origin')
            # The dev/preview proxy rewrites Host, so require loopback on both
            # sides rather than exact equality. Foreign-site origins still 403.
            if (urlsplit(f'http://{host}').hostname not in loopback
                    or (origin is not None
                        and urlsplit(origin).hostname not in loopback)):
                raise PermissionError('Cross-origin cockpit mutation refused')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('application/json required for cockpit mutations')
            raw_length = self.headers.get(
                "content-length"
            )

            if raw_length is None:
                raise ValueError(
                    "content-length is required"
                )

            length = int(raw_length)

            if (
                length < 0
                or length > MAX_BODY_BYTES
            ):
                raise ValueError(
                    "request body is too large"
                )

            raw = self.rfile.read(length)
            value = json.loads(
                raw.decode("utf-8")
            )

            if not isinstance(value, dict):
                raise ValueError(
                    "JSON body must be an object"
                )

            return value

        def do_GET(self) -> None:
            if self.path == "/api/cockpit/bootstrap":
                self._json(
                    HTTPStatus.OK,
                    session.bootstrap(),
                )
                return

            if self.path == "/api/health":
                self._json(
                    HTTPStatus.OK,
                    {"status": "ok", "mutation_policy": "loopback-same-origin-json"},
                )
                return

            self._json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found"},
            )

        def do_POST(self) -> None:
            try:
                body = self._read_json()

                if self.path == "/api/cockpit/event":
                    self._json(
                        HTTPStatus.OK,
                        session.dispatch(body),
                    )
                    return

                if (
                    self.path
                    == "/api/cockpit/explainers"
                ):
                    request = (
                        ExplainerImportRequest
                        .model_validate(body)
                    )
                    self._json(
                        HTTPStatus.OK,
                        session.import_explainer(
                            request
                        ),
                    )
                    return

                if (
                    self.path
                    == "/api/intake/live-evidence"
                ):
                    self._json(
                        HTTPStatus.OK,
                        session.intake_live_evidence(body),
                    )
                    return

                if (
                    self.path
                    == "/api/actions/register"
                ):
                    batch = (
                        ActionRegistrationBatch
                        .model_validate(body)
                    )
                    self._json(
                        HTTPStatus.OK,
                        session.actions.register(
                            batch.actions
                        ),
                    )
                    return

                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "not_found"},
                )

            except PermissionError as error:
                self._json(HTTPStatus.FORBIDDEN, {
                    'status': 'FAIL', 'failure_code': 'ORIGIN_REFUSED', 'message': str(error),
                })

            except ValidationError as error:
                failure = TriagedFailure(
                    failure_code=(
                        FailureCode
                        .PYDANTIC_VALIDATION_FAILED
                    ),
                    message=(
                        "Pydantic boundary "
                        "validation failed"
                    ),
                    errors=_validation_errors(error),
                )
                self._json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    failure,
                )

            except CockpitReducerError as error:
                status = (
                    HTTPStatus.CONFLICT
                    if error.code
                    == FailureCode.STALE_REVISION
                    else HTTPStatus.BAD_REQUEST
                )

                self._json(
                    status,
                    TriagedFailure(
                        failure_code=error.code,
                        message=str(error),
                    ),
                )

            except (
                ValueError,
                json.JSONDecodeError,
                UnicodeDecodeError,
            ) as error:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "status": "FAIL",
                        "failure_code": "BAD_REQUEST",
                        "message": str(error),
                    },
                )

    return Handler


def serve(
    rows: list[FeatureExplainer],
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    memory_url: str = "http://127.0.0.1:8601",
) -> None:
    """Run the local JSON API until interrupted."""

    session = CockpitSession(
        rows,
        memory_url,
    )

    server = ThreadingHTTPServer(
        (host, port),
        _handler_factory(session),
    )

    logger.info(
        "explain-project API listening on "
        "http://{}:{}",
        host,
        port,
    )

    try:
        server.serve_forever()
    finally:
        server.server_close()
