"""FastAPI application for Live Evidence REST, SSE, and production UI serving."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from . import __version__
from .action_registry import ActionRegistry
from .config import AppSettings, InterviewProfile, public_settings
from .coordinator import EvidenceCoordinator
from .models import (
    ActionRegistrationBatch,
    AppSnapshot,
    EvidenceCard,
    HealthResponse,
    ManualSearchRequest,
    SessionStartRequest,
    TranscriptEvent,
    ClarificationAnswerRequest,
    VoiceUtteranceRequest,
)
from .persistence import SessionJournal
from .state import RuntimeState


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create a fully wired application with explicit runtime dependencies."""

    resolved = settings or AppSettings.from_env()
    resolved.prepare_runtime()
    profile = resolved.load_profile()
    state = RuntimeState(resolved, profile)
    journal = SessionJournal(resolved.data_dir)
    coordinator = EvidenceCoordinator(resolved, profile, state, journal)
    action_registry = ActionRegistry(resolved)

    app = FastAPI(
        title="Live Evidence",
        version=__version__,
        description="Local-first realtime interview evidence copilot",
    )
    app.state.settings = resolved
    app.state.profile = profile
    app.state.runtime = state
    app.state.coordinator = coordinator
    app.state.action_registry = action_registry
    _add_shutdown_handler(app, coordinator.close)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    _register_api_routes(app, resolved, profile, state, coordinator, action_registry)
    _register_ui_routes(app, resolved.skill_root / "ui" / "dist")
    return app


def _add_shutdown_handler(app: FastAPI, handler: Any) -> None:
    """Register shutdown cleanup across FastAPI/Starlette API versions."""

    add_event_handler = getattr(app, "add_event_handler", None)
    if callable(add_event_handler):
        add_event_handler("shutdown", handler)
        return
    app.router.add_event_handler("shutdown", handler)


def _register_api_routes(
    app: FastAPI,
    settings: AppSettings,
    profile: InterviewProfile,
    state: RuntimeState,
    coordinator: EvidenceCoordinator,
    action_registry: ActionRegistry,
) -> None:
    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        ui_built = (settings.skill_root / "ui" / "dist" / "index.html").exists()
        return HealthResponse(
            version=__version__,
            ui_built=ui_built,
            memory_configured=bool(settings.memory_url),
            repo_count=len(settings.repo_roots),
        )

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return public_settings(settings, profile)

    @app.get("/api/state", response_model=AppSnapshot)
    async def get_state() -> AppSnapshot:
        return await state.snapshot()

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(
            state.events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/session/start", response_model=AppSnapshot)
    async def start_session(request: SessionStartRequest) -> AppSnapshot:
        return await state.start_session(
            request.consent_confirmed,
            purpose=request.purpose,
            actor_role=request.actor_role,
            policy=request.policy,
        )

    @app.post("/api/session/pause", response_model=AppSnapshot)
    async def pause_session() -> AppSnapshot:
        return await state.pause_session()

    @app.post("/api/session/stop", response_model=AppSnapshot)
    async def stop_session() -> AppSnapshot:
        return await state.stop_session()

    @app.post("/api/questions/{question_id}/clarifications/{clarification_id}/answer")
    async def answer_clarification(
        question_id: str, clarification_id: str, request: ClarificationAnswerRequest
    ) -> dict[str, Any]:
        """Bind one clarification answer to an exact question revision (#1454)."""

        outcome = await coordinator.apply_clarification_answer(
            question_id,
            request.question_revision,
            clarification_id,
            request.answer,
            request.source,
            request.answer_event_ids,
        )
        if outcome["result"] == "stale_revision":
            raise HTTPException(status_code=409, detail="answer targets a stale question revision")
        if outcome["result"] == "unknown_clarification":
            raise HTTPException(status_code=404, detail="unknown question or clarification id")
        return outcome

    @app.post("/api/voice/utterance", status_code=202)
    async def register_voice_utterance(request: VoiceUtteranceRequest) -> dict[str, Any]:
        """Register text the assistant is speaking, for echo suppression (#1453)."""

        if not state.session_policy().voice_output:
            raise HTTPException(status_code=403, detail="voice_output disabled by session policy")
        coordinator.register_assistant_utterance(request.text)
        return {"status": "registered"}

    @app.post("/api/debug/request")
    async def debug_request(payload: dict[str, Any]) -> dict[str, Any]:
        """Read-only debugger escalation (#1450), policy-gated in the backend.

        Runs the DebuggerLane adapter off the event loop; only a supported,
        independently validated outcome may publish a card, and that card goes
        through the same compare-and-swap revision fence as every other lane.
        """

        import asyncio as _asyncio

        from .debugger_lane import DebugRequest, DebuggerLane
        from .models import CardStatus, EvidenceSource, RetrievalLane

        policy = state.session_policy()
        try:
            request = DebugRequest(
                session_id=state.session_id() or "no-session",
                session_policy_digest=state.session_policy_digest() or "0" * 64,
                **payload,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid debug request: {exc}") from exc
        if not hasattr(app.state, "debugger_lane"):
            app.state.debugger_lane = DebuggerLane()
        lane: DebuggerLane = app.state.debugger_lane
        outcome = await _asyncio.to_thread(
            lane.run, request, debugger_invocation_allowed=policy.debugger_invocation
        )
        journal = coordinator.journal
        await journal.append(
            request.session_id, "debugger_outcome",
            {k: v for k, v in outcome.items() if k != "captured_locals"},
            policy_digest=state.session_policy_digest(),
        )
        published = False
        if outcome["result"] == "supported":
            card = EvidenceCard(
                query=request.technical_question[:8_000],
                thread="Debugger",
                question=request.technical_question[:8_000],
                talking_point=(
                    f"Stopped at {outcome['stopped_file']}:{outcome['stopped_line']}; "
                    f"captured {', '.join(outcome['captured_variable_names'][:6])}"
                )[:800],
                proof=str(outcome["proof_path"])[:1_200],
                qualifier="Observed run/state only; not a semantic guarantee beyond this run.",
                confidence=0.85,
                status=CardStatus.SUPPORTED,
                sources=[EvidenceSource(
                    lane=RetrievalLane.DEBUGGER,
                    label=f"debugger proof {outcome['request_digest'][:12]}",
                    excerpt=f"stop {outcome['stopped_file']}:{outcome['stopped_line']}",
                    path=str(outcome["canonical_path"]),
                    metadata={
                        "proof_path": str(outcome["proof_path"]),
                        "canonical_path": str(outcome["canonical_path"]),
                        "request_digest": outcome["request_digest"],
                        "repository_digest": outcome["repository_digest"],
                    },
                )],
                lanes=[RetrievalLane.DEBUGGER],
                question_id=request.question_id,
                question_revision=request.question_revision,
                policy_digest=state.session_policy_digest(),
            )
            published = await state.publish_card_fenced(card) is not None
            if not published:
                await journal.append(
                    request.session_id, "debugger_card_discarded_stale_revision",
                    {"request_digest": outcome["request_digest"],
                     "question_id": request.question_id,
                     "question_revision": request.question_revision},
                    policy_digest=state.session_policy_digest(),
                )
        return {"result": outcome["result"], "request_digest": outcome["request_digest"],
                "published": published,
                "detail": outcome.get("detail"),
                "stopped_file": outcome.get("stopped_file"),
                "stopped_line": outcome.get("stopped_line"),
                "captured_variable_names": outcome.get("captured_variable_names"),
                "proof_path": outcome.get("proof_path")}

    @app.post("/api/transcript", status_code=202)
    async def transcript(event: TranscriptEvent) -> dict[str, Any]:
        await coordinator.accept_transcript(event)
        return {"status": "accepted", "event_id": event.event_id}

    @app.post("/api/search", response_model=EvidenceCard)
    async def manual_search(request: ManualSearchRequest) -> EvidenceCard:
        # Backend policy enforcement (#1449): a disabled capability fails
        # closed on the manual route too. Hiding the button is presentation;
        # this is the authority, and it holds when a caller bypasses the UI.
        policy = state.session_policy()
        lane = request.lane.value
        if lane in ("brave", "dogpile") and not policy.external_search:
            raise HTTPException(status_code=403, detail="external_search disabled by session policy")
        if lane == "ask" and not policy.candidate_answer_generation:
            raise HTTPException(status_code=403, detail="candidate_answer_generation disabled by session policy")
        if lane in ("memory", "ripgrep", "code") and not policy.retrieve_local_evidence:
            raise HTTPException(status_code=403, detail="retrieve_local_evidence disabled by session policy")
        return await coordinator.manual_search(request)

    @app.post("/api/cards/{card_id}/pin", response_model=AppSnapshot)
    async def pin_card(card_id: str) -> AppSnapshot:
        try:
            snapshot = await state.snapshot()
            card = next(item for item in snapshot.cards if item.card_id == card_id)
            return await state.set_card_flag(card_id, pinned=not card.pinned)
        except (KeyError, StopIteration) as exc:
            raise HTTPException(status_code=404, detail="card not found") from exc

    @app.post("/api/cards/{card_id}/dismiss", response_model=AppSnapshot)
    async def dismiss_card(card_id: str) -> AppSnapshot:
        try:
            return await state.set_card_flag(card_id, dismissed=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="card not found") from exc

    @app.post("/api/actions/register")
    async def register_actions(batch: ActionRegistrationBatch) -> dict[str, Any]:
        return await action_registry.register(batch.actions)


def _register_ui_routes(app: FastAPI, dist_dir: Path) -> None:
    if not dist_dir.exists():
        @app.get("/")
        async def development_root() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "Live Evidence",
                    "status": "api-ready-ui-not-built",
                    "next": "./run.sh setup && ./run.sh ui-build",
                }
            )
        return

    assets = dist_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(dist_dir / "index.html")

    @app.get("/{route:path}")
    async def spa_fallback(route: str) -> FileResponse:
        candidate = (dist_dir / route).resolve()
        if candidate.is_file() and dist_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        logger.debug("SPA fallback route={}", route)
        return FileResponse(dist_dir / "index.html")
