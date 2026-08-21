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

    @app.post("/api/turns/{turn_id}/reassign")
    async def reassign_turn(turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Attributable manual speaker correction (#1477); journaled; never
        regenerates semantic content."""

        actor = str(payload.get("actor") or "")
        speaker_slot = str(payload.get("speaker_slot") or "")
        if not actor or not speaker_slot:
            raise HTTPException(status_code=422, detail="actor and speaker_slot required")
        count = await state.reassign_turn(turn_id, speaker_slot)
        if count == 0:
            raise HTTPException(status_code=404, detail="unknown turn")
        await coordinator.journal.append(
            state.session_id() or "no-session", "turn_reassigned",
            {"turn_id": turn_id, "speaker_slot": speaker_slot, "actor": actor,
             "events_updated": count},
            policy_digest=state.session_policy_digest(),
        )
        return {"turn_id": turn_id, "speaker_slot": speaker_slot, "events_updated": count}

    @app.post("/api/briefing/load", status_code=202)
    async def briefing_load(payload: dict[str, Any]) -> dict[str, Any]:
        """Load a briefing pack for this call. A recognition assist for the
        HUMAN's own meeting -- refused for formal_assessment sessions."""

        from .briefing import BriefingMatcher, BriefingPack

        if state.session_purpose().value == "formal_assessment":
            raise HTTPException(status_code=403,
                                detail="briefing packs are not available in formal_assessment")
        try:
            pack = BriefingPack(**{k: v for k, v in payload.items() if k != "schema"})
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid briefing pack: {exc}") from exc
        coordinator.briefing = BriefingMatcher(pack)
        await coordinator.journal.append(
            state.session_id() or "no-session", "briefing_pack_loaded",
            {"pack_id": pack.pack_id, "points": len(pack.points),
             "pack_digest": coordinator.briefing.digest},
            policy_digest=state.session_policy_digest(),
        )
        return {"status": "loaded", "pack_id": pack.pack_id,
                "points": len(pack.points), "pack_digest": coordinator.briefing.digest}

    @app.get("/api/briefing")
    async def briefing_state() -> dict[str, Any]:
        matcher = coordinator.briefing
        if matcher is None:
            return {"loaded": False, "surfaced": []}
        return {
            "loaded": True,
            "pack_id": matcher.pack.pack_id,
            "audience": matcher.pack.audience,
            "core_concepts": matcher.pack.core_concepts,
            "closing_sentence": matcher.pack.closing_sentence,
            "surfaced": matcher.surfaced[-10:][::-1],
        }

    @app.post("/api/rubric/load", status_code=202)
    async def rubric_load(payload: dict[str, Any]) -> dict[str, Any]:
        """Load a role rubric for authorship (#1474). interviewer_assist and
        post_interview_review purposes only -- enforced here, not in the UI."""

        from .rubric import RoleRubric, RubricEngine

        purpose = state.session_purpose().value
        if purpose not in {"interviewer_assist", "post_interview_review"}:
            raise HTTPException(status_code=403,
                                detail=f"rubric authorship not available for purpose {purpose}")
        try:
            rubric = RoleRubric(**{k: v for k, v in payload.items() if k != "schema"})
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid rubric: {exc}") from exc
        app.state.rubric_engine = RubricEngine(rubric)
        return {"status": "loaded", "rubric_digest": app.state.rubric_engine.rubric_digest}

    @app.post("/api/rubric/author")
    async def rubric_author(payload: dict[str, Any]) -> dict[str, Any]:
        """Run one LIVE authorship pass over candidate answer events and apply
        it through the deterministic floor; rejections journal, never render."""

        import asyncio as _asyncio

        from .rubric_author import RubricAuthor, apply_authored

        engine = getattr(app.state, "rubric_engine", None)
        if engine is None:
            raise HTTPException(status_code=409, detail="no rubric loaded")
        purpose = state.session_purpose().value
        if purpose not in {"interviewer_assist", "post_interview_review"}:
            raise HTTPException(status_code=403, detail="purpose does not permit authorship")
        snapshot = await state.snapshot()
        events = [
            {"event_id": e.event_id, "text": e.text}
            for e in snapshot.transcript
            if e.speaker.value == "candidate" and e.kind.value == "final"
        ][-24:]
        if not events:
            raise HTTPException(status_code=409, detail="no candidate answer events yet")
        question_id = str(payload.get("question_id") or state.active_question() or "q-rubric-live")
        question_revision = int(payload.get("question_revision")
                                or state.active_question_revision() or 1)
        author = RubricAuthor()
        authored = await _asyncio.to_thread(author.author, engine._rubric, events)
        if authored is None:
            raise HTTPException(status_code=502, detail="authorship call unavailable")
        outcome = apply_authored(engine, authored, events,
                                 question_id=question_id,
                                 question_revision=question_revision)
        for entry in engine.journal:
            await coordinator.journal.append(
                state.session_id() or "no-session", entry.pop("kind"), entry,
                policy_digest=state.session_policy_digest(),
            )
        engine.journal.clear()
        coverage = engine.coverage(question_id, question_revision)
        suggestions = engine._suggestions.get(
            (question_id, question_revision, engine.rubric_digest), [])
        if not hasattr(app.state, "insights"):
            app.state.insights = {}
        app.state.insights["rubric"] = {
            "coverage": [{"criterion_id": c.criterion_id, "state": c.state.value,
                           "evidence_event_ids": c.evidence_event_ids}
                          for c in coverage],
            "suggestions": [{"criterion_id": s.criterion_id,
                              "question_text": s.question_text,
                              "why_this_is_still_open": s.why_this_is_still_open,
                              "unsupported": s.unsupported}
                             for s in suggestions],
        }
        return {"outcome": outcome, "coverage": app.state.insights["rubric"]}

    @app.get("/api/actions/pending")
    async def actions_pending() -> dict[str, Any]:
        engine = coordinator.actions
        return {"pending": [c.model_dump(mode="json", by_alias=True)
                             for c in (engine.pending() if engine else [])]}

    @app.post("/api/actions/{action_id}/approve")
    async def approve_action(action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Human approval executes exactly one candidate (#1475): journaled,
        revision-fenced, policy-gated in the backend."""

        actor = str(payload.get("actor") or "")
        if not actor:
            raise HTTPException(status_code=422, detail="actor required")
        engine = coordinator.actions
        if engine is None:
            raise HTTPException(status_code=404, detail="no action candidates in this session")
        active = (state.active_question(), state.active_question_revision())
        try:
            candidate = await engine.approve(
                action_id, actor=actor, active_question=active,
                coordinator=coordinator, state=state,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown action") from exc
        for entry in engine.journal:
            await coordinator.journal.append(
                state.session_id() or "no-session", entry.pop("kind"), entry,
                policy_digest=state.session_policy_digest(),
            )
        engine.journal.clear()
        return candidate.model_dump(mode="json", by_alias=True)

    @app.get("/api/provenance")
    async def provenance() -> dict[str, Any]:
        """Clause-level provenance for current cards (#1476), recomputed from
        the filesystem on every call -- a mutated source shows up immediately."""

        from .provenance import card_provenance

        snapshot = await state.snapshot()
        return {
            "cards": [
                card_provenance(card.model_dump(mode="json", by_alias=True))
                for card in snapshot.cards
                if not card.dismissed
            ][:6]
        }

    @app.post("/api/insights/{kind}", status_code=202)
    async def publish_insight(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Publish a review dossier, rubric coverage, or rehearsal state for the
        reviewer UI (#1451/#1452/#1453). Review payloads are validated against
        the ReviewBundle contract; publication is journaled and attributable."""

        if kind not in {"review", "rubric", "rehearsal"}:
            raise HTTPException(status_code=404, detail="unknown insight kind")
        if kind == "review":
            from .review import ReviewBundle

            try:
                payload = ReviewBundle(**payload).model_dump(mode="json", by_alias=True)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"invalid review bundle: {exc}") from exc
        if not hasattr(app.state, "insights"):
            app.state.insights = {}
        app.state.insights[kind] = payload
        await coordinator.journal.append(
            state.session_id() or "no-session", "insight_published",
            {"kind": kind, "size": len(str(payload))},
            policy_digest=state.session_policy_digest(),
        )
        return {"status": "published", "kind": kind}

    @app.get("/api/insights")
    async def get_insights() -> dict[str, Any]:
        return getattr(app.state, "insights", {}) or {}

    @app.get("/api/insights/media")
    async def insights_media() -> FileResponse:
        """Serve the review bundle's locally retained media for clip seeking."""

        insights = getattr(app.state, "insights", {}) or {}
        locator = str((insights.get("review") or {}).get("media_locator") or "")
        path = Path(locator.removeprefix("file://"))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="review media not available locally")
        return FileResponse(path)

    @app.post("/api/insights/rubric/dismiss")
    async def dismiss_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
        """Journaled, attributable dismissal; coverage evidence is untouched --
        dismissing a suggestion is never evidence the criterion was covered."""

        criterion_id = str(payload.get("criterion_id") or "")
        actor = str(payload.get("actor") or "")
        if not criterion_id or not actor:
            raise HTTPException(status_code=422, detail="criterion_id and actor required")
        insights = getattr(app.state, "insights", {}) or {}
        rubric = insights.get("rubric") or {}
        before = rubric.get("suggestions") or []
        rubric["suggestions"] = [s for s in before if s.get("criterion_id") != criterion_id]
        await coordinator.journal.append(
            state.session_id() or "no-session", "suggestion_dismissed",
            {"criterion_id": criterion_id, "actor": actor},
            policy_digest=state.session_policy_digest(),
        )
        return {"status": "dismissed", "remaining": len(rubric["suggestions"])}

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
