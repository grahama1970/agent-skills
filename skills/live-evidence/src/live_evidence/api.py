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
