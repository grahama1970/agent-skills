"""
Embry Agent D-Bus client library.

Provides a Python interface to the org.embry.Agent D-Bus service,
allowing any Python skill or surface to invoke the agent daemon.

Usage:
    from common.embry_agent_client import EmbryAgentClient

    async with EmbryAgentClient() as client:
        # Synchronous ask (blocks until complete)
        response = await client.ask("What files are in this project?")
        print(response)

        # Async ask (returns request ID, listen for signals)
        request_id = await client.ask_async("Refactor the auth module")

        # Stream events
        async for event_type, data in client.stream_events():
            print(f"{event_type}: {data}")
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from dbus_next.aio import MessageBus
from dbus_next import BusType, Variant
from loguru import logger

DBUS_BUS_NAME = "org.embry.Agent"
DBUS_OBJECT_PATH = "/org/embry/Agent"
DBUS_INTERFACE_NAME = "org.embry.Agent"


class EmbryAgentClient:
    """Async D-Bus client for the Embry Agent daemon."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._proxy = None
        self._interface = None

    async def connect(self) -> None:
        """Connect to the session bus and get the agent proxy."""
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await self._bus.introspect(DBUS_BUS_NAME, DBUS_OBJECT_PATH)
        self._proxy = self._bus.get_proxy_object(
            DBUS_BUS_NAME, DBUS_OBJECT_PATH, introspection
        )
        self._interface = self._proxy.get_interface(DBUS_INTERFACE_NAME)
        logger.debug("Connected to {}", DBUS_BUS_NAME)

    async def disconnect(self) -> None:
        """Disconnect from the session bus."""
        if self._bus:
            self._bus.disconnect()
            self._bus = None
            self._interface = None
            self._proxy = None

    async def __aenter__(self) -> EmbryAgentClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    def _ensure_connected(self) -> None:
        if not self._interface:
            raise RuntimeError("Not connected. Use 'async with EmbryAgentClient()' or call connect() first.")

    async def ask(self, prompt: str) -> str:
        """Send a prompt and wait for the complete response."""
        self._ensure_connected()
        return await self._interface.call_ask(prompt)

    async def ask_async(self, prompt: str) -> str:
        """Send a prompt and return a request ID immediately. Listen for signals to get results."""
        self._ensure_connected()
        return await self._interface.call_ask_async(prompt)

    async def steer(self, instruction: str) -> None:
        """Inject a steering instruction into the current conversation."""
        self._ensure_connected()
        await self._interface.call_steer(instruction)

    async def follow_up(self, prompt: str) -> None:
        """Send a follow-up prompt in the current conversation."""
        self._ensure_connected()
        await self._interface.call_follow_up(prompt)

    async def abort(self) -> None:
        """Abort the current operation."""
        self._ensure_connected()
        await self._interface.call_abort()

    async def get_state(self) -> dict:
        """Get the current agent state as a dict."""
        self._ensure_connected()
        raw = await self._interface.call_get_state()
        return json.loads(raw)

    async def set_model(self, provider: str, model: str) -> None:
        """Switch the agent's model."""
        self._ensure_connected()
        await self._interface.call_set_model(provider, model)

    async def respond_to_ui(self, request_id: str, response_json: str) -> None:
        """Respond to an extension UI request."""
        self._ensure_connected()
        await self._interface.call_respond_to_ui(request_id, response_json)

    async def ping(self) -> str:
        """Health check."""
        self._ensure_connected()
        return await self._interface.call_ping()

    async def ask_with_hints(self, prompt: str, hints: dict | None = None) -> str:
        """Send a prompt with model/thinking hints.

        Args:
            prompt: The user prompt.
            hints: Optional dict with keys: model, provider, thinking.
        """
        self._ensure_connected()
        hints_json = json.dumps(hints or {})
        return await self._interface.call_ask_with_hints(prompt, hints_json)

    async def ask_as(self, persona: str, prompt: str) -> str:
        """Send a prompt as a specific persona.

        Args:
            persona: Persona name (e.g. "brandon-bailey").
            prompt: The user prompt.
        """
        self._ensure_connected()
        return await self._interface.call_ask_as(persona, prompt)

    @property
    async def is_streaming(self) -> bool:
        """Whether the agent is currently streaming a response."""
        self._ensure_connected()
        return await self._interface.get_is_streaming()

    @property
    async def current_model(self) -> str:
        """The current model identifier."""
        self._ensure_connected()
        return await self._interface.get_current_model()

    @property
    async def session_name(self) -> str:
        """The current session name."""
        self._ensure_connected()
        return await self._interface.get_session_name()

    async def stream_events(
        self, request_id: str | None = None
    ) -> AsyncIterator[tuple[str, str]]:
        """
        Yield (event_type, data_json) tuples from D-Bus signals.

        All signals now carry a requestId as their first argument for event
        correlation in multi-tenant mode.

        Args:
            request_id: If provided, only yield events matching this request ID.
                        If None, yield all events (backward compatible).

        Listens for MessageUpdate, ToolExecution, AgentEnd, ExtensionUIRequest,
        and Error signals. Stops when AgentEnd is received.
        """
        self._ensure_connected()
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        def _should_emit(event_req_id: str) -> bool:
            return request_id is None or event_req_id == request_id

        def on_message_update(req_id: str, data: str) -> None:
            if _should_emit(req_id):
                queue.put_nowait(("message_update", json.dumps({"requestId": req_id, "text": data})))

        def on_tool_execution(req_id: str, tool: str, data: str) -> None:
            if _should_emit(req_id):
                queue.put_nowait(("tool_execution", json.dumps({"requestId": req_id, "tool": tool, "data": data})))

        def on_agent_end(req_id: str, data: str) -> None:
            if _should_emit(req_id):
                queue.put_nowait(("agent_end", json.dumps({"requestId": req_id, "response": data})))
                queue.put_nowait(None)  # sentinel

        def on_extension_ui(req_id: str, ui_id: str, ui_type: str, title: str, body: str) -> None:
            if _should_emit(req_id):
                queue.put_nowait((
                    "extension_ui_request",
                    json.dumps({"requestId": req_id, "id": ui_id, "type": ui_type, "title": title, "body": body}),
                ))

        def on_error(req_id: str, msg: str) -> None:
            if _should_emit(req_id):
                queue.put_nowait(("error", json.dumps({"requestId": req_id, "message": msg})))

        self._interface.on_message_update(on_message_update)
        self._interface.on_tool_execution(on_tool_execution)
        self._interface.on_agent_end(on_agent_end)
        self._interface.on_extension_ui_request(on_extension_ui)
        self._interface.on_error(on_error)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            self._interface.off_message_update(on_message_update)
            self._interface.off_tool_execution(on_tool_execution)
            self._interface.off_agent_end(on_agent_end)
            self._interface.off_extension_ui_request(on_extension_ui)
            self._interface.off_error(on_error)
