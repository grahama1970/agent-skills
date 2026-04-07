"""
Prompt Lab Skill - LLM Calling with Self-Correction Loop
Handles LLM API calls via scillm paved path with correction capabilities.
"""
import asyncio
import json
import os
import time

from loguru import logger
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable

# Retry configuration via environment variables
MAX_TRANSIENT_RETRIES = int(os.getenv("PROMPT_LAB_MAX_TRANSIENT_RETRIES", "3"))
INITIAL_BACKOFF_S = float(os.getenv("PROMPT_LAB_INITIAL_BACKOFF_S", "1.0"))
BACKOFF_MULTIPLIER = float(os.getenv("PROMPT_LAB_BACKOFF_MULTIPLIER", "2.0"))

# Transient error indicators (connection issues, not LLM content issues)
TRANSIENT_ERROR_PATTERNS = [
    "connection",
    "timeout",
    "timed out",
    "503",
    "502",
    "504",
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "service unavailable",
    "network",
    "dns",
    "reset by peer",
    "broken pipe",
]

from config import (
    SCILLM_API_BASE,
    SCILLM_PROXY_KEY,
    CHUTES_MODEL_ID,
    CHUTES_TEXT_MODEL,
)
# Backwards compat aliases for code below
CHUTES_API_BASE = SCILLM_API_BASE
CHUTES_API_KEY = SCILLM_PROXY_KEY
from models import TaxonomyResponse, parse_llm_response

# ---------------------------------------------------------------------------
# Shadow method gateway: route through /assistant validate() when available
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("PROMPT_LAB_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        import sys as _sys
        _assistant_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assistant")
        if _assistant_dir not in _sys.path:
            _sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False


def _is_transient_error(error: str) -> bool:
    """Check if an error is transient (retryable)."""
    error_lower = error.lower()
    return any(pattern in error_lower for pattern in TRANSIENT_ERROR_PATTERNS)


async def _retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = MAX_TRANSIENT_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF_S,
    backoff_multiplier: float = BACKOFF_MULTIPLIER,
    on_retry: Optional[Callable[[int, str, float], None]] = None,
    **kwargs,
):
    """
    Retry an async function with exponential backoff for transient errors.

    Args:
        func: Async function to call
        *args: Positional arguments for func
        max_retries: Maximum number of retries (default: 3)
        initial_backoff: Initial backoff in seconds (default: 1.0)
        backoff_multiplier: Multiplier for each retry (default: 2.0)
        on_retry: Optional callback(attempt, error, wait_seconds) for monitoring
        **kwargs: Keyword arguments for func

    Returns:
        Result of func on success

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    backoff = initial_backoff

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_str = str(e)

            # Only retry transient errors
            if not _is_transient_error(error_str):
                raise

            # Don't retry if we've exhausted attempts
            if attempt >= max_retries:
                raise

            # Notify monitor if callback provided
            if on_retry:
                on_retry(attempt + 1, error_str, backoff)

            # Wait with exponential backoff
            await asyncio.sleep(backoff)
            backoff *= backoff_multiplier

    # Should not reach here, but if we do, raise last exception
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected exit from retry loop")


@dataclass
class LLMCallResult:
    """Result of LLM call with correction tracking."""
    content: str
    validated: Optional[TaxonomyResponse]
    rejected_tags: List[str]
    correction_rounds: int
    total_latency_ms: float
    success: bool
    error: Optional[str] = None


async def _call_llm_single_impl(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Internal implementation of single LLM call using scillm paved path.
    Use call_llm_single() which wraps this with transient error retry.
    """
    # Gateway path: route through /assistant validate()
    if _gateway_available:
        try:
            start = time.perf_counter()
            gw_result = _gw_validate(
                input_data={"messages": messages},
                task="taxonomy-prompt-evaluator",
            )
            latency = (time.perf_counter() - start) * 1000
            result = gw_result.result
            if isinstance(result, dict):
                return json.dumps(result), latency
            return str(result), latency
        except Exception as e:
            logger.debug("gateway LLM call failed, falling through to scillm: {}", e)

    try:
        from scillm.batch import parallel_acompletions
    except ImportError:
        raise RuntimeError("scillm not installed. Run 'uv sync' or 'pip install scillm'.")

    # Load environment variables
    provider = model_config.get("provider", "chutes")

    # Route "scillm" (and legacy "subagent") provider through the local scillm proxy (handles Gemini, OpenRouter, etc.)
    if provider in ("scillm", "subagent"):
        api_base = os.environ.get("SCILLM_PROXY_URL", "http://localhost:4001/v1")
        api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')
    else:
        api_base = CHUTES_API_BASE or os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1").strip('"\'')
        api_key = CHUTES_API_KEY or os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')
    model_id = (
        model_config.get("model") or
        CHUTES_MODEL_ID or
        CHUTES_TEXT_MODEL or
        os.environ.get("CHUTES_MODEL_ID", "").strip('"\'') or
        os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')
    )

    if not api_base or not api_key:
        raise RuntimeError("SCILLM_API_BASE and SCILLM_PROXY_KEY required")
    if not model_id:
        raise RuntimeError("Model ID required (CHUTES_MODEL_ID or CHUTES_TEXT_MODEL)")

    start = time.perf_counter()

    # Build request per SCILLM_PAVED_PATH_CONTRACT.md
    request = {
        "model": model_id,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 4096,
        "temperature": 0,
    }

    # Use parallel_acompletions with single request
    # wall_time_s=90 prevents hanging on persistent API errors
    # max_retries_5xx=3 limits retries on server errors
    results = await parallel_acompletions(
        [request],
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai",
        concurrency=1,
        timeout=60,
        wall_time_s=90,
        tenacious=True,
        # max_retries_5xx removed from scillm.batch API (2026-03)
    )

    latency = (time.perf_counter() - start) * 1000

    if results and not results[0].get("error"):
        content = results[0].get("content", "")
        # Handle case where content is already parsed dict
        if isinstance(content, dict):
            content = json.dumps(content)
        return content, latency
    else:
        error = results[0].get("error", "Unknown error") if results else "No response"
        raise RuntimeError(f"LLM call failed: {error}")


async def call_llm_single(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
    on_retry: Optional[Callable[[int, str, float], None]] = None,
) -> tuple[str, float]:
    """
    Single LLM call using scillm paved path with transient error retry.

    Args:
        messages: List of message dicts with role and content
        model_config: Model configuration dict
        on_retry: Optional callback(attempt, error, wait_seconds) for monitoring

    Returns:
        Tuple of (content, latency_ms)

    Raises:
        RuntimeError: If scillm not installed or API call fails after retries

    Retry behavior:
        - Retries up to PROMPT_LAB_MAX_TRANSIENT_RETRIES times (default: 3)
        - Uses exponential backoff: 1s, 2s, 4s (configurable via env vars)
        - Only retries transient errors (connection, timeout, 503, rate limit)
        - Non-transient errors (auth, invalid request) fail immediately
    """
    return await _retry_with_backoff(
        _call_llm_single_impl,
        messages,
        model_config,
        on_retry=on_retry,
    )


async def call_llm(
    system: str,
    user: str,
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Single LLM call (no correction loop).

    Args:
        system: System prompt
        user: User message
        model_config: Model configuration

    Returns:
        Tuple of (content, latency_ms)
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return await call_llm_single(messages, model_config)


async def call_vlm(
    system: str,
    user: str,
    images: List[str],
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """Call VLM (vision language model) with text + images.

    Args:
        system: System prompt
        user: User text message
        images: List of image file paths (PNG, JPG)
        model_config: Model configuration (must support vision, e.g. vlm alias in scillm)

    Returns:
        Tuple of (content, latency_ms)
    """
    import base64
    import mimetypes

    # Build multimodal content array
    content_parts: List[Dict[str, Any]] = [{"type": "text", "text": user}]
    for img_path in images:
        path = os.path.abspath(img_path)
        if not os.path.exists(path):
            logger.warning("Image not found, skipping: {}", path)
            continue
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content_parts},
    ]
    return await call_llm_single(messages, model_config)


async def call_llm_raw(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
    max_tokens: int = 512,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """
    Raw LLM call for custom use cases (optimization, analysis).

    Args:
        messages: Full message list
        model_config: Model configuration
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Parsed JSON response or error dict
    """
    try:
        from scillm.batch import parallel_acompletions

        api_base = CHUTES_API_BASE or os.environ.get("SCILLM_API_BASE", "http://localhost:4001").strip('"\'')
        api_key = CHUTES_API_KEY or os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')
        model_id = model_config.get("model", "")

        req = {
            "model": model_id,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        results = await parallel_acompletions(
            [req],
            api_base=api_base,
            api_key=api_key,
            custom_llm_provider="openai",
            concurrency=1,
            timeout=120,
            wall_time_s=180,
            tenacious=True,
            # max_retries_5xx removed from scillm.batch API (2026-03)
        )

        if results and not results[0].get("error"):
            content = results[0].get("content", "{}")
            if isinstance(content, str):
                return json.loads(content)
            return content
        else:
            return {"error": results[0].get("error", "Unknown error") if results else "No response"}

    except Exception as e:
        return {"error": str(e)}


async def call_ollama(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> tuple[str, float]:
    """
    Call Ollama API for local model inference.

    Args:
        messages: List of message dicts with role and content
        model_config: Model configuration with 'model' key for Ollama model name
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature

    Returns:
        Tuple of (content, latency_ms)
    """
    import httpx

    model_name = model_config.get("model", "qwen3:8b")
    ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    # Combine messages into a prompt (Ollama uses simpler format)
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            prompt_parts.append(content)
        elif role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")
    prompt = "\n\n".join(prompt_parts)

    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{ollama_base}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()

    latency = (time.perf_counter() - start) * 1000
    data = response.json()
    content = data.get("response", "")

    return content, latency


async def call_provider(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
    max_tokens: int = 512,
    temperature: float = 0.1,
) -> tuple[str, float]:
    """
    Route to appropriate provider based on model_config.

    Supports:
        - provider: "chutes" (default) - Chutes API via scillm
        - provider: "ollama" - Local Ollama
        - provider: "openai" - OpenAI API

    Args:
        messages: List of message dicts
        model_config: Model configuration with 'provider' key
        max_tokens: Maximum tokens
        temperature: Sampling temperature

    Returns:
        Tuple of (content, latency_ms)
    """
    provider = model_config.get("provider", "chutes")

    if provider == "ollama":
        return await call_ollama(messages, model_config, max_tokens, temperature)
    elif provider in ("chutes", "scillm"):
        return await call_llm_single(messages, model_config)
    else:
        # Default to Chutes/scillm for backwards compatibility
        return await call_llm_single(messages, model_config)


async def call_llm_with_correction(
    system: str,
    user: str,
    model_config: Dict[str, Any],
    max_correction_rounds: int = 2,
) -> LLMCallResult:
    """
    LLM call with self-correction loop.

    If the initial response contains rejected (invalid) tags, sends a correction
    message back to the model asking it to fix its output.  Repeats up to
    ``max_correction_rounds`` times.

    Args:
        system: System prompt
        user: User message
        model_config: Model configuration
        max_correction_rounds: Maximum correction attempts

    Returns:
        LLMCallResult with validation info and correction tracking
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    total_latency = 0.0
    correction_rounds = 0

    # Initial call
    content, latency = await call_llm_single(messages, model_config)
    total_latency += latency
    validated, rejected = parse_llm_response(content)

    # Self-correction loop
    while rejected and correction_rounds < max_correction_rounds:
        correction_rounds += 1
        correction_msg = (
            f"Your response contained invalid tags: {rejected}. "
            f"Please fix your output to only use valid tags from the vocabulary. "
            f"Return corrected JSON."
        )
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": correction_msg})

        content, latency = await call_llm_single(messages, model_config)
        total_latency += latency
        validated, rejected = parse_llm_response(content)

    return LLMCallResult(
        content=content,
        validated=validated,
        rejected_tags=rejected,
        correction_rounds=correction_rounds,
        total_latency_ms=total_latency,
        success=len(rejected) == 0,
    )


async def call_llm_batch(
    requests: List[Dict[str, Any]],
    model_config: Dict[str, Any],
    concurrency: int = 5,
) -> List[LLMCallResult]:
    """
    Execute batch LLM calls with self-correction using parallel_acompletions_iter.
    
    Args:
        requests: List of dicts with {"system": str, "user": str}
        model_config: Model configuration
        concurrency: Max concurrent requests
        
    Returns:
        List of LLMCallResult objects in same order as input
    """
    from scillm.batch import parallel_acompletions_iter

    api_base = CHUTES_API_BASE or os.environ.get("SCILLM_API_BASE", "http://localhost:4001").strip('"\'')
    api_key = CHUTES_API_KEY or os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')
    model_id = model_config.get("model", "")

    # Map original index to results to maintain order
    results_map = {}
    
    formatted_requests = []
    for i, req in enumerate(requests):
        formatted_requests.append({
            "model": model_id,
            "messages": [
                {"role": "system", "content": req["system"]},
                {"role": "user", "content": req["user"]},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
            "temperature": 0,
            "metadata": {"index": i}
        })

    start_time = time.perf_counter()
    
    async for result in parallel_acompletions_iter(
        formatted_requests,
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai",
        concurrency=concurrency,
        timeout=120,
        wall_time_s=300,
        tenacious=True,
        # max_retries_5xx removed from scillm.batch API (2026-03)
    ):
        # Extract index from request metadata
        req_metadata = result.get("request", {}).get("metadata", {})
        idx = req_metadata.get("index")
        
        if idx is None:
            # Fallback for systems that don't pass back metadata correctly
            continue
            
        content = result.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content)
            
        error = result.get("error")
        
        if error:
            results_map[idx] = LLMCallResult(
                content="",
                validated=None,
                rejected_tags=[],
                correction_rounds=0,
                total_latency_ms=0,
                success=False,
                error=error
            )
            continue

        validated, rejected = parse_llm_response(content)
        
        results_map[idx] = LLMCallResult(
            content=content,
            validated=validated,
            rejected_tags=rejected,
            correction_rounds=0, 
            total_latency_ms=(time.perf_counter() - start_time) * 1000 / len(requests),
            success=not rejected
        )

    return [results_map[i] for i in range(len(requests))]
