"""
Prompt Lab Skill - LLM Calling with Self-Correction Loop
Handles LLM API calls via scillm paved path with correction capabilities.
"""
import json
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from config import (
    TIER0_CONCEPTUAL,
    TIER1_TACTICAL,
    CORRECTION_PROMPT,
    CHUTES_API_BASE,
    CHUTES_API_KEY,
    CHUTES_MODEL_ID,
    CHUTES_TEXT_MODEL,
)
from models import TaxonomyResponse, parse_llm_response


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


async def call_llm_single(
    messages: List[Dict[str, str]],
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Single LLM call using scillm paved path.

    Args:
        messages: List of message dicts with role and content
        model_config: Model configuration dict

    Returns:
        Tuple of (content, latency_ms)

    Raises:
        RuntimeError: If scillm not installed or API call fails
    """
    try:
        from scillm.batch import parallel_acompletions
    except ImportError:
        raise RuntimeError("scillm not installed. Run 'uv sync' or 'pip install scillm'.")

    # Load environment variables
    api_base = CHUTES_API_BASE or os.environ.get("CHUTES_API_BASE", "").strip('"\'')
    api_key = CHUTES_API_KEY or os.environ.get("CHUTES_API_KEY", "").strip('"\'')
    model_id = (
        model_config.get("model") or
        CHUTES_MODEL_ID or
        CHUTES_TEXT_MODEL or
        os.environ.get("CHUTES_MODEL_ID", "").strip('"\'') or
        os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')
    )

    if not api_base or not api_key:
        raise RuntimeError("CHUTES_API_BASE and CHUTES_API_KEY required")
    if not model_id:
        raise RuntimeError("Model ID required (CHUTES_MODEL_ID or CHUTES_TEXT_MODEL)")

    start = time.perf_counter()

    # Build request per SCILLM_PAVED_PATH_CONTRACT.md
    request = {
        "model": model_id,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 256,
        "temperature": 0,
    }

    # Use parallel_acompletions with single request
    results = await parallel_acompletions(
        [request],
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai_like",
        concurrency=1,
        timeout=30,
        wall_time_s=60,
        tenacious=False,
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


async def call_llm_with_correction(
    system: str,
    user: str,
    model_config: Dict[str, Any],
    max_correction_rounds: int = 2,
) -> LLMCallResult:
    """
    Call LLM with self-correction loop.

    If the LLM outputs invalid tags, we send an assistant correction message
    back to the model asking it to fix its output. This gives the model a
    chance to self-correct rather than silently filtering.

    Args:
        system: System prompt
        user: User message
        model_config: Model configuration
        max_correction_rounds: Maximum number of correction attempts (default 2)

    Returns:
        LLMCallResult with validation status and correction tracking
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    total_latency = 0.0
    correction_round = 0
    all_rejected = []

    while correction_round <= max_correction_rounds:
        try:
            content, latency = await call_llm_single(messages, model_config)
            total_latency += latency

            validated, rejected = parse_llm_response(content)

            if not rejected:
                # Success! No invalid tags
                return LLMCallResult(
                    content=content,
                    validated=validated,
                    rejected_tags=all_rejected,
                    correction_rounds=correction_round,
                    total_latency_ms=total_latency,
                    success=True,
                )

            # Invalid tags or parse errors found - track them
            all_rejected.extend(rejected)

            if correction_round >= max_correction_rounds:
                # Max corrections reached - return partial result
                return LLMCallResult(
                    content=content,
                    validated=validated,
                    rejected_tags=all_rejected,
                    correction_rounds=correction_round,
                    total_latency_ms=total_latency,
                    success=False,
                    error=f"Max corrections reached. Still invalid: {rejected}",
                )

            # Send correction message back to LLM
            if "PARSE_ERROR" in rejected:
                correction_msg = (
                    "Your previous response was not valid JSON. Return ONLY valid JSON with this schema: "
                    '{"conceptual": ["tag"], "tactical": ["tag"], "confidence": 0.0}. '
                    "Do not include any prose, only a JSON object."
                )
            else:
                correction_msg = CORRECTION_PROMPT.format(
                    rejected_tags=", ".join(rejected),
                    valid_conceptual=", ".join(sorted(TIER0_CONCEPTUAL)),
                    valid_tactical=", ".join(sorted(TIER1_TACTICAL)),
                )

            # Add the assistant's invalid response and our correction to conversation
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": correction_msg})

            correction_round += 1

        except Exception as e:
            return LLMCallResult(
                content="",
                validated=None,
                rejected_tags=all_rejected,
                correction_rounds=correction_round,
                total_latency_ms=total_latency,
                success=False,
                error=str(e),
            )

    # Should not reach here, but handle it
    return LLMCallResult(
        content="",
        validated=TaxonomyResponse(),
        rejected_tags=all_rejected,
        correction_rounds=correction_round,
        total_latency_ms=total_latency,
        success=False,
        error="Unexpected exit from correction loop",
    )


async def call_llm(
    system: str,
    user: str,
    model_config: Dict[str, Any],
) -> tuple[str, float]:
    """
    Simple LLM call without correction loop.
    Use call_llm_with_correction for production.

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

        api_base = CHUTES_API_BASE or os.environ.get("CHUTES_API_BASE", "").strip('"\'')
        api_key = CHUTES_API_KEY or os.environ.get("CHUTES_API_KEY", "").strip('"\'')
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
            custom_llm_provider="openai_like",
            concurrency=1,
            timeout=60,
            wall_time_s=120,
            tenacious=False,
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
