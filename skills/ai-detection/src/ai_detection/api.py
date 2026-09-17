"""Loopback-first FastAPI application; same-origin, bounded requests, private session tokens."""
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ai_detection.contracts import Edit, Health, Policy, SessionRequest, Strict, Submit
from ai_detection.errors import Code, DetectionError, envelope
from ai_detection.io import read_json, strict_json
from ai_detection.model import load_model
from ai_detection.store import Store

T = TypeVar("T", bound=Strict)



load_dotenv(override=False)
def home_path() -> Path:
    explicit = os.environ.get("AI_DETECTION_HOME")
    if explicit:
        return Path(explicit).expanduser().resolve()
    storage = Path("/mnt/storage12tb")
    if storage.is_dir() and os.access(storage, os.W_OK):
        return storage / "skills" / "ai-detection"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "ai-detection"


def load_policy(path: Path | None = None) -> Policy:
    return Policy.model_validate(read_json(path) if path else
                                 strict_json(files("ai_detection").joinpath("resources/policy.json").read_bytes()))


def token_from(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or not 20 <= len(header[7:]) <= 200:
        raise DetectionError(Code.UNAUTHORIZED, "Bearer session authorization is required.", 401)
    return header[7:]


async def body_model(request: Request, cls: type[T]) -> T:
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise DetectionError(Code.INVALID_INPUT, "Use application/json.", 415)
    return cls.model_validate(strict_json(await request.body(), 786432))

class BodyLimit:
    """ASGI byte budget including chunked bodies; never relies on Content-Length alone."""
    def __init__(self, app, limit: int = 786432):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        consumed = 0
        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.limit:
                raise DetectionError(Code.LIMIT, "HTTP request exceeds the body byte budget.", 413)
            return message
        await self.app(scope, bounded_receive, send)


def create_app(db_path: Path | None = None, policy: Policy | None = None,
               model_path: Path | None = None, model_sha256: str | None = None) -> FastAPI:
    selected_policy = policy or load_policy(Path(os.environ["AI_DETECTION_POLICY"])
                                           if "AI_DETECTION_POLICY" in os.environ else None)
    store = Store(db_path or home_path() / "sessions.sqlite3", selected_policy)
    configured = model_path or (Path(os.environ["AI_DETECTION_MODEL"]) if "AI_DETECTION_MODEL" in os.environ else None)
    pin = model_sha256 or os.environ.get("AI_DETECTION_MODEL_SHA256")
    if configured and not pin:
        raise DetectionError(Code.MODEL, "Serving a model requires its canonical SHA-256 pin.")
    model = load_model(configured, pin) if configured else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def retention_loop():
            while True:
                await run_in_threadpool(store.purge)
                await asyncio.sleep(30)
        task = asyncio.create_task(retention_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="ai-detection", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

    @app.middleware("http")
    async def headers_and_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and origin:
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin != expected:
                return JSONResponse(envelope(DetectionError(Code.UNAUTHORIZED,
                                    "Cross-origin mutations are not allowed.", 403)).model_dump(), status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        return response

    @app.exception_handler(DetectionError)
    async def classified_error(_: Request, exc: DetectionError):
        return JSONResponse(envelope(exc).model_dump(), status_code=exc.status)

    async def validation_error(_: Request, exc):
        # Deliberately omit Pydantic input and ctx values: they can contain source or credentials.
        issues = [{"type": item["type"], "loc": list(item["loc"]),
                   "msg": "Field failed typed validation.", "ctx": {}} for item in exc.errors()]
        result = envelope(DetectionError(Code.INVALID_INPUT, "Request failed typed validation.", 422)).model_dump()
        result["validation_errors"] = issues
        return JSONResponse(result, status_code=422)
    app.add_exception_handler(ValidationError, validation_error)
    app.add_exception_handler(RequestValidationError, validation_error)

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception):
        logger.error("request_failed exception_type={}", type(exc).__name__)
        return JSONResponse(envelope(DetectionError(Code.INTERNAL,
                            "Internal operation failed; no submission was adjudicated.", 500)).model_dump(), status_code=500)

    @app.get("/api/health")
    def health():
        return Health().model_dump(mode="json")

    @app.get("/api/policy")
    def policy_read():
        return selected_policy.model_dump(mode="json")

    @app.post("/api/sessions", status_code=201)
    async def create(request: Request):
        parsed = await body_model(request, SessionRequest)
        return await run_in_threadpool(store.create, parsed)

    @app.post("/api/sessions/{session_id}/events")
    async def append(session_id: str, request: Request):
        token = token_from(request)
        parsed = await body_model(request, Edit)
        result = await run_in_threadpool(store.append, session_id, token, parsed)
        return result.model_dump(mode="json")

    @app.post("/api/sessions/{session_id}/submit")
    async def submit(session_id: str, request: Request):
        token = token_from(request)
        parsed = await body_model(request, Submit)
        result = await run_in_threadpool(store.submit, session_id, token, parsed, model)
        return result.model_dump(mode="json")

    @app.get("/api/sessions/{session_id}/export")
    def export(session_id: str, request: Request):
        return store.export(session_id, token_from(request)).model_dump(mode="json")

    @app.delete("/api/sessions/{session_id}")
    def delete(session_id: str, request: Request):
        return store.delete(session_id, token_from(request))

    static = Path(str(files("ai_detection").joinpath("static")))
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")
    return app
