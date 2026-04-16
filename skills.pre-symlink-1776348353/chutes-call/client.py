"""
chutes-call client: Importable Python client for the chutes-call gateway.

All retry logic lives server-side. This client is a thin wrapper around
httpx calls to localhost:8630.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator, Optional

import httpx
from pydantic import BaseModel

PORT = int(os.getenv("CHUTES_CALL_PORT", "8630"))
BASE_URL = f"http://localhost:{PORT}"


class ChatResponse(BaseModel):
    """Mirrors the server-side ChatResponse."""

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


class ChutesCallClient:
    """Async client for the chutes-call gateway."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 300.0):
        """Initialize client.

        Args:
            base_url: Gateway URL (default: http://localhost:8630).
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def close(self):
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def chat(
        self,
        messages: list[dict],
        model: str = "deepseek-ai/DeepSeek-V3",
        tenacious: bool = False,
        caller: str = "unknown",
        **kwargs,
    ) -> ChatResponse:
        """Send a single chat request.

        Args:
            messages: OpenAI-format message list.
            model: Model identifier.
            tenacious: Enable tenacious retry mode.
            caller: Caller identifier for dashboard tracking.
            **kwargs: Additional fields (temperature, max_tokens, etc).

        Returns:
            ChatResponse with content and metadata.
        """
        payload = {
            "messages": messages,
            "model": model,
            "tenacious": tenacious,
            "caller": caller,
            **kwargs,
        }
        resp = await self._client.post("/chat", json=payload)
        resp.raise_for_status()
        return ChatResponse(**resp.json())

    async def batch(
        self,
        requests: list[dict],
        concurrency: int = 5,
        tenacious: bool = False,
        stream: bool = True,
        caller: str = "unknown",
    ) -> list[ChatResponse] | AsyncIterator[ChatResponse]:
        """Send a batch of chat requests.

        Args:
            requests: List of ChatRequest dicts.
            concurrency: Max parallel requests within the batch.
            tenacious: Enable tenacious retry mode.
            stream: If True, returns NDJSON stream; if False, returns list.
            caller: Caller identifier for dashboard tracking.

        Returns:
            List of ChatResponse (non-stream) or AsyncIterator (stream).
        """
        payload = {
            "requests": requests,
            "concurrency": concurrency,
            "tenacious": tenacious,
            "stream": stream,
            "caller": caller,
        }

        if not stream:
            resp = await self._client.post("/batch", json=payload)
            resp.raise_for_status()
            return [ChatResponse(**r) for r in resp.json()]

        return self._stream_batch(payload)

    async def _stream_batch(self, payload: dict) -> AsyncIterator[ChatResponse]:
        """Stream batch results as NDJSON."""
        async with self._client.stream("POST", "/batch", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if "summary" in data:
                    break
                yield ChatResponse(**data)

    async def health(self) -> dict:
        """Check gateway health.

        Returns:
            Health status dict with backend availability and circuit states.
        """
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def usage(self) -> dict:
        """Get accumulated usage stats.

        Returns:
            Usage dict with requests, tokens, cost.
        """
        resp = await self._client.get("/usage")
        resp.raise_for_status()
        return resp.json()


def chat_sync(
    messages: list[dict],
    model: str = "deepseek-ai/DeepSeek-V3",
    tenacious: bool = False,
    caller: str = "unknown",
    **kwargs,
) -> ChatResponse:
    """Synchronous single chat call.

    Args:
        messages: OpenAI-format message list.
        model: Model identifier.
        tenacious: Enable tenacious retry mode.
        caller: Caller identifier.
        **kwargs: Additional fields.

    Returns:
        ChatResponse with content and metadata.
    """
    async def _run():
        async with ChutesCallClient() as c:
            return await c.chat(messages, model, tenacious, caller, **kwargs)

    return asyncio.run(_run())


def batch_sync(
    requests: list[dict],
    concurrency: int = 5,
    tenacious: bool = False,
    caller: str = "unknown",
) -> list[ChatResponse]:
    """Synchronous batch call (non-streaming).

    Args:
        requests: List of ChatRequest dicts.
        concurrency: Max parallel requests.
        tenacious: Enable tenacious retry mode.
        caller: Caller identifier.

    Returns:
        List of ChatResponse.
    """
    async def _run():
        async with ChutesCallClient() as c:
            return await c.batch(requests, concurrency, tenacious, stream=False, caller=caller)

    return asyncio.run(_run())
