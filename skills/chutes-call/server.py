"""
chutes-call: Centralized Chutes.ai LLM gateway.

Shared Docker FastAPI service (port 8630) that enforces the Chutes.ai
5-concurrent-connection account limit via a global asyncio semaphore,
handles retries with tenacity, implements a per-backend circuit breaker,
and returns structured request/response objects with cleaned JSON.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from _misuse_guard import create_chat_guard, create_batch_guard, ValidationError as MisuseValidationError

BACKENDS_FILE = os.path.join(os.path.dirname(__file__), "backends.yml")
PORT = int(os.getenv("CHUTES_CALL_PORT", "8630"))
MAX_CONCURRENT = int(os.getenv("CHUTES_MAX_CONCURRENT", "5"))
CIRCUIT_TRIP_THRESHOLD = 3
CIRCUIT_OPEN_DURATION = 60  # seconds
DYNAMIC_SHRINK_WINDOW = 30  # seconds
DYNAMIC_SHRINK_THRESHOLD = 3  # consecutive 429s in window



class ChatRequest(BaseModel):
    messages: list[dict]
    model: str = "deepseek-ai/DeepSeek-V3"
    tenacious: bool = False
    timeout: int = 60
    temperature: float = 0.0
    max_tokens: int = 4096
    response_format: Optional[dict] = None
    caller: str = "unknown"


class ChatResponse(BaseModel):
    ok: bool
    content: Optional[str] = None
    json_content: Optional[dict] = None
    raw_content: Optional[str] = None
    model: str = ""
    backend: str = ""
    retries: int = 0
    elapsed_s: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    circuit_state: str = "CLOSED"


class BatchRequest(BaseModel):
    requests: list[ChatRequest]
    tenacious: bool = False
    stream: bool = True
    concurrency: int = 5
    caller: str = "unknown"



class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    name: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def allow_request(self) -> bool:
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.opened_at >= CIRCUIT_OPEN_DURATION:
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit {self.name}: OPEN → HALF_OPEN")
                    return True
                return False
            # HALF_OPEN — allow one probe
            return True

    async def record_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"Circuit {self.name}: HALF_OPEN → CLOSED")
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0

    async def record_failure(self):
        async with self._lock:
            self.consecutive_failures += 1
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
                logger.warning(f"Circuit {self.name}: HALF_OPEN → OPEN")
            elif self.consecutive_failures >= CIRCUIT_TRIP_THRESHOLD:
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
                logger.warning(
                    f"Circuit {self.name}: CLOSED → OPEN "
                    f"({self.consecutive_failures} consecutive failures)"
                )



@dataclass
class Backend:
    name: str
    key: str
    priority: int
    api_base: str
    env_key: str
    default_model: str
    model_patterns: list[str]
    max_concurrent: int
    cost_per_million_in: float
    cost_per_million_out: float
    api_key: str = ""
    circuit: CircuitBreaker = field(default=None)

    def __post_init__(self):
        if self.circuit is None:
            self.circuit = CircuitBreaker(self.key)


BACKENDS: list[Backend] = []


async def load_backends():
    """Load backend configuration from backends.yml."""
    global BACKENDS
    with open(BACKENDS_FILE) as f:
        cfg = yaml.safe_load(f)

    backends = []
    for key, bc in cfg["backends"].items():
        env_key = bc["env_key"]
        api_key = os.getenv(env_key, "")
        if not api_key and "env_key_alt" in bc:
            api_key = os.getenv(bc["env_key_alt"], "")

        backends.append(
            Backend(
                name=bc["name"],
                key=key,
                priority=bc["priority"],
                api_base=bc["api_base"],
                env_key=env_key,
                default_model=bc["default_model"],
                model_patterns=bc.get("model_patterns", []),
                max_concurrent=bc.get("max_concurrent", 10),
                cost_per_million_in=bc.get("cost_per_million_in", 0.0),
                cost_per_million_out=bc.get("cost_per_million_out", 0.0),
                api_key=api_key,
            )
        )

    BACKENDS = sorted(backends, key=lambda b: b.priority)
    available = [b.key for b in BACKENDS if b.api_key]
    logger.info(f"Loaded {len(BACKENDS)} backends, {len(available)} available: {available}")


def resolve_backend(model: str) -> Backend | None:
    """Find the primary backend for a model, or return the first available."""
    import fnmatch

    for b in BACKENDS:
        if not b.api_key:
            continue
        for pattern in b.model_patterns:
            if fnmatch.fnmatch(model.lower(), pattern.lower()):
                return b
    # Fall back to first available backend
    for b in BACKENDS:
        if b.api_key:
            return b
    return None


def get_fallback_chain(exclude: str) -> list[Backend]:
    """Get available backends excluding the named one, in priority order."""
    return [b for b in BACKENDS if b.api_key and b.key != exclude]



def clean_json_string(text: str) -> str:
    """Strip think tags, markdown fences, BOM, and extract JSON from prose."""
    if not text:
        return text
    # BOM
    text = text.lstrip("\ufeff")
    # DeepSeek <think>...</think> reasoning tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    # If result looks like prose with embedded JSON, extract the JSON object
    if text and not text.startswith(("{", "[")):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
    return text


def try_parse_json(text: str) -> dict | None:
    """Attempt to parse cleaned JSON, including truncated recovery."""
    cleaned = clean_json_string(text)
    if not cleaned:
        return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to repair truncated JSON by closing brackets
        for suffix in ["}", "]}", "\"}", "\"]}", "null}"]:
            try:
                return json.loads(cleaned + suffix)
            except json.JSONDecodeError:
                continue
    return None



class GatewayState:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.semaphore_size = MAX_CONCURRENT
        self.active_calls = 0
        self.total_requests = 0
        self.total_errors = 0
        self.total_retries = 0
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost_usd = 0.0
        self.recent_429s: list[float] = []
        self.caller_stats: dict[str, dict] = {}
        self.http_client: httpx.AsyncClient | None = None
        self.started_at = time.time()
        self._lock = asyncio.Lock()

    async def init_client(self):
        self.http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            timeout=httpx.Timeout(180.0, connect=10.0),
        )

    async def close_client(self):
        if self.http_client:
            await self.http_client.aclose()

    async def record_429(self):
        async with self._lock:
            now = time.time()
            self.recent_429s.append(now)
            self.recent_429s = [t for t in self.recent_429s if now - t < DYNAMIC_SHRINK_WINDOW]
            if len(self.recent_429s) >= DYNAMIC_SHRINK_THRESHOLD and self.semaphore_size > 1:
                new_size = max(1, self.semaphore_size - 2)
                logger.warning(
                    f"Dynamic shrink: {self.semaphore_size} → {new_size} "
                    f"({len(self.recent_429s)} 429s in {DYNAMIC_SHRINK_WINDOW}s)"
                )
                self.semaphore_size = new_size
                self.semaphore = asyncio.Semaphore(new_size)

    async def maybe_restore_semaphore(self):
        async with self._lock:
            if self.semaphore_size < MAX_CONCURRENT:
                now = time.time()
                self.recent_429s = [t for t in self.recent_429s if now - t < DYNAMIC_SHRINK_WINDOW]
                if not self.recent_429s:
                    new_size = min(MAX_CONCURRENT, self.semaphore_size + 1)
                    logger.info(f"Semaphore restore: {self.semaphore_size} → {new_size}")
                    self.semaphore_size = new_size
                    self.semaphore = asyncio.Semaphore(new_size)

    def track_caller(self, caller: str, ok: bool, cost: float):
        if caller not in self.caller_stats:
            self.caller_stats[caller] = {"requests": 0, "errors": 0, "cost_usd": 0.0}
        self.caller_stats[caller]["requests"] += 1
        if not ok:
            self.caller_stats[caller]["errors"] += 1
        self.caller_stats[caller]["cost_usd"] += cost


STATE: GatewayState | None = None



class RetryableError(Exception):
    """Error that should trigger a retry."""

    def __init__(self, message: str, status_code: int = 0, retry_after: float = 0):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def parse_retry_after(headers: httpx.Headers) -> float:
    """Extract retry delay from response headers."""
    for header in ["retry-after", "x-ratelimit-reset", "ratelimit-reset"]:
        val = headers.get(header)
        if val:
            try:
                return float(val)
            except ValueError:
                pass
    return 0


async def _call_backend(
    backend: Backend,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
    response_format: dict | None,
) -> dict:
    """Make a single LLM call to a backend. Raises RetryableError on transient failures."""
    payload: dict = {
        "model": model if backend.key == "chutes" else backend.default_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {backend.api_key}",
        "Content-Type": "application/json",
    }

    url = f"{backend.api_base}/chat/completions"
    resp = await STATE.http_client.post(
        url, json=payload, headers=headers, timeout=timeout
    )

    if resp.status_code == 429:
        await STATE.record_429()
        retry_after = parse_retry_after(resp.headers)
        raise RetryableError(
            f"Rate limited by {backend.key}", status_code=429, retry_after=retry_after
        )

    if resp.status_code >= 500:
        raise RetryableError(
            f"Server error {resp.status_code} from {backend.key}",
            status_code=resp.status_code,
        )

    if resp.status_code != 200:
        raise RetryableError(
            f"HTTP {resp.status_code} from {backend.key}: {resp.text[:200]}",
            status_code=resp.status_code,
        )

    data = resp.json()
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = data.get("usage", {})

    # Thinking models (Qwen3-*-Thinking, DeepSeek-R1) put output in
    # reasoning_content when content is empty
    content = message.get("content") or message.get("reasoning_content") or ""

    return {
        "content": content,
        "model": data.get("model", model),
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
    }


async def call_with_retries(req: ChatRequest) -> ChatResponse:
    """Execute an LLM call with retries, circuit breaker, and fallback chain."""
    t0 = time.time()
    retries = 0
    max_attempts = 5 if req.tenacious else 2

    backend = resolve_backend(req.model)
    if not backend:
        return ChatResponse(
            ok=False,
            error="No available backend",
            elapsed_s=time.time() - t0,
        )

    # Build the full chain: primary + fallbacks
    chain = [backend] + get_fallback_chain(backend.key) if req.tenacious else [backend]

    last_error = ""
    for be in chain:
        if not await be.circuit.allow_request():
            logger.debug(f"Circuit {be.key} is OPEN, skipping")
            continue

        for attempt in range(max_attempts):
            timeout = req.timeout
            if req.tenacious and attempt > 0:
                timeout = min(180, req.timeout + (attempt * 60))

            try:
                async with STATE.semaphore:
                    STATE.active_calls += 1
                    try:
                        result = await _call_backend(
                            be,
                            req.messages,
                            req.model,
                            req.temperature,
                            req.max_tokens,
                            timeout,
                            req.response_format,
                        )
                    finally:
                        STATE.active_calls -= 1

                await be.circuit.record_success()
                await STATE.maybe_restore_semaphore()

                raw = result["content"]
                cleaned = clean_json_string(raw) if raw else raw
                json_content = None
                if req.response_format and raw:
                    json_content = try_parse_json(raw)
                    # JSON guard: if caller requested JSON but response
                    # isn't valid JSON, treat as retryable → cascade to
                    # next backend (matches scillm json_guard behavior)
                    if json_content is None:
                        retries += 1
                        last_error = f"JSON guard: {be.key} returned non-JSON for json response_format"
                        logger.warning(f"{last_error}: {(raw or '')[:120]}")
                        break  # break inner retry loop → try next backend

                cost = (
                    result["tokens_in"] * be.cost_per_million_in
                    + result["tokens_out"] * be.cost_per_million_out
                ) / 1_000_000

                STATE.total_requests += 1
                STATE.total_tokens_in += result["tokens_in"]
                STATE.total_tokens_out += result["tokens_out"]
                STATE.total_cost_usd += cost
                STATE.total_retries += retries
                STATE.track_caller(req.caller, True, cost)

                return ChatResponse(
                    ok=True,
                    content=cleaned,
                    json_content=json_content,
                    raw_content=raw,
                    model=result["model"],
                    backend=be.key,
                    retries=retries,
                    elapsed_s=round(time.time() - t0, 3),
                    tokens_in=result["tokens_in"],
                    tokens_out=result["tokens_out"],
                    cost_usd=round(cost, 6),
                    circuit_state=be.circuit.state.value,
                )

            except RetryableError as e:
                retries += 1
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1}/{max_attempts} on {be.key}: {e}")
                await be.circuit.record_failure()

                if e.retry_after > 0:
                    await asyncio.sleep(min(e.retry_after, 30))
                elif req.tenacious:
                    delay = min(60, 2 ** (attempt + 1))
                    await asyncio.sleep(delay)

            except httpx.TimeoutException:
                retries += 1
                last_error = f"Timeout ({timeout}s) on {be.key}"
                logger.warning(last_error)
                await be.circuit.record_failure()

            except Exception as e:
                retries += 1
                last_error = f"Unexpected error on {be.key}: {e}"
                logger.error(last_error)
                await be.circuit.record_failure()
                break  # Don't retry unexpected errors on same backend

    # All backends exhausted
    STATE.total_requests += 1
    STATE.total_errors += 1
    STATE.total_retries += retries
    STATE.track_caller(req.caller, False, 0)

    return ChatResponse(
        ok=False,
        error=last_error,
        retries=retries,
        elapsed_s=round(time.time() - t0, 3),
        backend=chain[0].key if chain else "",
        circuit_state=chain[0].circuit.state.value if chain else "UNKNOWN",
    )



@asynccontextmanager
async def lifespan(app: FastAPI):
    global STATE
    STATE = GatewayState()
    await STATE.init_client()
    await load_backends()
    logger.info(f"chutes-call gateway started on port {PORT}")
    yield
    await STATE.close_client()
    logger.info("chutes-call gateway stopped")


app = FastAPI(title="chutes-call", version="1.0.0", lifespan=lifespan)

# Misuse guards
chat_guard = create_chat_guard()
batch_guard = create_batch_guard()


@app.exception_handler(MisuseValidationError)
async def misuse_validation_handler(request: Request, exc: MisuseValidationError):
    """Handle misuse guard validation errors with helpful messages."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "error_type": exc.error_type},
    )


@app.post("/chat")
async def chat_endpoint(req: ChatRequest, request: Request) -> ChatResponse:
    caller = request.headers.get("x-caller-skill", req.caller)
    chat_guard.validate(req.model_dump(), endpoint="/chat", caller=caller)
    return await call_with_retries(req)


@app.post("/batch")
async def batch_endpoint(req: BatchRequest, request: Request):
    caller = request.headers.get("x-caller-skill", req.caller)
    batch_guard.validate(req.model_dump(), endpoint="/batch", caller=caller)

    # Apply batch-level tenacious/caller to individual requests
    for r in req.requests:
        if req.tenacious:
            r.tenacious = True
        if req.caller != "unknown":
            r.caller = req.caller

    if req.stream:
        return StreamingResponse(
            _stream_batch(req.requests, req.concurrency),
            media_type="application/x-ndjson",
        )

    results = await _run_batch(req.requests, req.concurrency)
    return JSONResponse([r.model_dump() for r in results])


async def _run_batch(requests: list[ChatRequest], concurrency: int) -> list[ChatResponse]:
    sem = asyncio.Semaphore(concurrency)
    results: list[ChatResponse | None] = [None] * len(requests)

    async def _run_one(idx: int, r: ChatRequest):
        async with sem:
            results[idx] = await call_with_retries(r)

    await asyncio.gather(*[_run_one(i, r) for i, r in enumerate(requests)])
    return results


async def _stream_batch(requests: list[ChatRequest], concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    total_ok = 0
    total_errors = 0
    total_retries = 0
    total_cost = 0.0

    async def _run_one(idx: int, r: ChatRequest) -> tuple[int, ChatResponse]:
        async with sem:
            return idx, await call_with_retries(r)

    tasks = [asyncio.create_task(_run_one(i, r)) for i, r in enumerate(requests)]

    for coro in asyncio.as_completed(tasks):
        idx, resp = await coro
        row = resp.model_dump()
        row["index"] = idx
        yield json.dumps(row, default=str) + "\n"

        if resp.ok:
            total_ok += 1
        else:
            total_errors += 1
        total_retries += resp.retries
        total_cost += resp.cost_usd

    summary = {
        "summary": {
            "total": len(requests),
            "ok": total_ok,
            "errors": total_errors,
            "retries": total_retries,
            "cost_usd": round(total_cost, 6),
        }
    }
    yield json.dumps(summary) + "\n"


@app.get("/health")
async def health_endpoint():
    backends_health = {}
    for b in BACKENDS:
        backends_health[b.key] = {
            "available": bool(b.api_key),
            "circuit_state": b.circuit.state.value,
        }

    return {
        "status": "ok",
        "port": PORT,
        "semaphore_size": STATE.semaphore_size,
        "active_calls": STATE.active_calls,
        "backends": backends_health,
    }


@app.get("/queue")
async def queue_endpoint():
    uptime = time.time() - STATE.started_at
    cost_per_min = (STATE.total_cost_usd / (uptime / 60)) if uptime > 60 else 0

    return {
        "active_calls": STATE.active_calls,
        "semaphore_size": STATE.semaphore_size,
        "queue_depth": MAX_CONCURRENT - STATE.semaphore._value,
        "total_requests": STATE.total_requests,
        "total_errors": STATE.total_errors,
        "error_rate": (
            round(STATE.total_errors / STATE.total_requests, 3)
            if STATE.total_requests > 0
            else 0
        ),
        "total_retries": STATE.total_retries,
        "cost_per_min": round(cost_per_min, 6),
        "uptime_s": round(uptime, 1),
        "callers": STATE.caller_stats,
    }


@app.get("/usage")
async def usage_endpoint():
    return {
        "requests": STATE.total_requests,
        "errors": STATE.total_errors,
        "retries": STATE.total_retries,
        "tokens_in": STATE.total_tokens_in,
        "tokens_out": STATE.total_tokens_out,
        "cost_usd": round(STATE.total_cost_usd, 6),
        "uptime_s": round(time.time() - STATE.started_at, 1),
    }


@app.delete("/usage")
async def reset_usage_endpoint():
    STATE.total_requests = 0
    STATE.total_errors = 0
    STATE.total_retries = 0
    STATE.total_tokens_in = 0
    STATE.total_tokens_out = 0
    STATE.total_cost_usd = 0.0
    STATE.caller_stats = {}
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
