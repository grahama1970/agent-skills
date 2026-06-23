#!/usr/bin/env python3
from __future__ import annotations
"""P2 server callsite bridge for PersonaPlex golden-state chat sessions.

This module is the narrow callsite-integration layer for the existing
``personaplex_golden_state_server.py`` WebSocket route.  It keeps GPU/model
stepping in the server's existing owner loop, while speech-final callbacks are
routed through the P1 turn-aware controller before any factual output is
released.

The module is safe to import without torch, aiohttp, Deepgram, or PersonaPlex.
It is used by deterministic P2 smoke tests and by the patched server callsite.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import asyncio
import json
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
COMPAT_DIR = SCRIPT_DIR / "_p2_compat"
try:
    from personaplex_p1_live_wrapper_integration import (
        DeterministicP1MemoryTransport,
        HttpMemoryTransport,
        P1LiveTurnController,
        P1MemoryClient,
        P1ModelOwnerLoop,
        P1TurnResult,
        utc_now,
    )
except Exception:  # pragma: no cover - used only in isolated bundle sanity
    if COMPAT_DIR.exists() and str(COMPAT_DIR) not in sys.path:
        sys.path.insert(0, str(COMPAT_DIR))
    from personaplex_p1_live_wrapper_integration import (  # type: ignore
        DeterministicP1MemoryTransport,
        HttpMemoryTransport,
        P1LiveTurnController,
        P1MemoryClient,
        P1ModelOwnerLoop,
        P1TurnResult,
        utc_now,
    )


@dataclass(frozen=True)
class P2CallsiteConfig:
    session_id: str
    persona_id: str
    run_root: Path
    memory_url: str = "http://127.0.0.1:8601"
    deterministic: bool = False
    force_ivanti_general_math: bool = False
    user_audio_codec: str = "live/opus"


@dataclass
class P2SpeechFinalReceipt:
    event: str
    session_id: str
    persona_id: str
    turn_id: int
    generation: int
    transcript: str
    source: str
    status: str
    route_action: str | None
    route_endpoint: str | None
    sealed_key: str | None
    gate_receipt: dict[str, Any] | None
    response_text: str | None
    output_blocked_after_route: bool
    created_at_utc: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class P2ServerCallsite:
    """Server-callsite object owned by one WebSocket/session.

    The golden-state server should create one instance per chat session, call
    ``route_speech_final`` from Deepgram/scripted final transcript callbacks,
    and use ``output_blocked``/``should_emit_model_output`` at the audio/text
    emission boundary.
    """

    def __init__(self, *, config: P2CallsiteConfig, memory_client: P1MemoryClient) -> None:
        self.config = config
        self.controller = P1LiveTurnController(
            session_id=config.session_id,
            persona_id=config.persona_id,
            run_root=config.run_root,
            memory_client=memory_client,
        )
        self.events: list[dict[str, Any]] = []
        self.results: list[P1TurnResult] = []
        self.receipts: list[P2SpeechFinalReceipt] = []
        self.route_tasks: set[asyncio.Task] = set()

    @classmethod
    def live(cls, *, session_id: str, persona_id: str, run_root: Path | str, memory_url: str = "http://127.0.0.1:8601") -> "P2ServerCallsite":
        config = P2CallsiteConfig(session_id=session_id, persona_id=persona_id, run_root=Path(run_root), memory_url=memory_url, deterministic=False)
        return cls(config=config, memory_client=P1MemoryClient(HttpMemoryTransport(memory_url), persona_id=persona_id))

    @classmethod
    def deterministic(cls, *, session_id: str, persona_id: str, run_root: Path | str, force_ivanti_general_math: bool = False) -> "P2ServerCallsite":
        config = P2CallsiteConfig(
            session_id=session_id,
            persona_id=persona_id,
            run_root=Path(run_root),
            deterministic=True,
            force_ivanti_general_math=force_ivanti_general_math,
            user_audio_codec="fixture/opus",
        )
        transport = DeterministicP1MemoryTransport(force_ivanti_general_math=force_ivanti_general_math)
        return cls(config=config, memory_client=P1MemoryClient(transport, persona_id=persona_id))

    async def route_speech_final(
        self,
        transcript: str,
        *,
        source: str,
        user_audio_bytes: bytes = b"",
        user_audio_codec: str | None = None,
        route_delay_ms: int = 0,
    ) -> dict[str, Any]:
        ctx = self.controller.start_final_transcript(
            transcript,
            user_audio_bytes=user_audio_bytes or transcript.encode("utf-8"),
            user_audio_codec=user_audio_codec or self.config.user_audio_codec,
            source=source,
        )
        self.events.append({
            "event": "p2_speech_final_callsite_started",
            "turn_id": ctx.token.turn_id,
            "generation": ctx.token.generation,
            "source": source,
            "transcript_hash": ctx.token.transcript_hash,
            "created_at_utc": utc_now(),
        })
        result = await self.controller.run_turn(ctx, route_delay_ms=route_delay_ms)
        self.results.append(result)
        receipt = P2SpeechFinalReceipt(
            event="p2_speech_final_callsite_routed",
            session_id=self.config.session_id,
            persona_id=self.config.persona_id,
            turn_id=result.turn_id,
            generation=result.generation,
            transcript=transcript,
            source=source,
            status=result.status,
            route_action=result.route_action,
            route_endpoint=result.route_endpoint,
            sealed_key=result.sealed_key,
            gate_receipt=result.gate_receipt,
            response_text=self.response_text_for_result(result),
            output_blocked_after_route=self.output_blocked(),
        )
        receipt_dict = receipt.to_dict()
        self.receipts.append(receipt)
        self.events.append(receipt_dict)
        return receipt_dict

    def start_speech_final_task(self, transcript: str, *, source: str, user_audio_bytes: bytes = b"", route_delay_ms: int = 0) -> asyncio.Task:
        task = asyncio.create_task(
            self.route_speech_final(transcript, source=source, user_audio_bytes=user_audio_bytes, route_delay_ms=route_delay_ms),
            name=f"p2_route_speech_final_{len(self.route_tasks)+1}",
        )
        self.route_tasks.add(task)
        task.add_done_callback(self.route_tasks.discard)
        return task

    def output_blocked(self) -> bool:
        return bool(self.controller.gate.closed)

    def should_emit_model_output(self, token_text: str, *, factual: bool = True) -> bool:
        token = self.controller.state.active_token
        if token is None:
            return False
        return self.controller.try_enqueue_live_model_token(token, token_text, factual=factual)

    def response_text_for_result(self, result: P1TurnResult) -> str | None:
        if not result.sealed_key:
            return None
        records = self.controller.store.list_conversation_history_records()
        for record in records:
            if record.get("_key") == result.sealed_key:
                packet = record.get("response_packet") or {}
                return packet.get("text")
        return None

    async def drain(self) -> list[dict[str, Any]]:
        if not self.route_tasks:
            return []
        return list(await asyncio.gather(*list(self.route_tasks)))

    def final_receipt(self) -> dict[str, Any]:
        final = self.controller.final_receipt(self.results)
        final["schema"] = "personaplex.p2_server_callsite.final_receipt.v1"
        final["scope"] = "P2 deterministic server callsite integration; not live Deepgram/GPU/real-upsert proof"
        final["p2_callsite_used_p1_controller"] = True
        final["p2_callsite_events"] = self.events
        final["p2_speech_final_receipts"] = [r.to_dict() for r in self.receipts]
        final["p2_config"] = {
            "session_id": self.config.session_id,
            "persona_id": self.config.persona_id,
            "run_root": str(self.config.run_root),
            "memory_url": self.config.memory_url,
            "deterministic": self.config.deterministic,
            "force_ivanti_general_math": self.config.force_ivanti_general_math,
        }
        return final


def make_p2_callsite_for_server(
    *,
    session_id: str,
    persona_id: str,
    run_root: Path | str,
    memory_url: str = "http://127.0.0.1:8601",
    deterministic: bool = False,
    force_ivanti_general_math: bool = False,
) -> P2ServerCallsite:
    if deterministic:
        return P2ServerCallsite.deterministic(
            session_id=session_id,
            persona_id=persona_id,
            run_root=run_root,
            force_ivanti_general_math=force_ivanti_general_math,
        )
    return P2ServerCallsite.live(
        session_id=session_id,
        persona_id=persona_id,
        run_root=run_root,
        memory_url=memory_url,
    )


async def run_p2_server_callsite_smoke(fixture: dict[str, Any], run_root: Path, *, force_ivanti_general_math: bool = False) -> dict[str, Any]:
    callsite = P2ServerCallsite.deterministic(
        session_id=fixture.get("session_id", "p2-session"),
        persona_id=fixture.get("persona_id", "embry"),
        run_root=run_root,
        force_ivanti_general_math=force_ivanti_general_math,
    )
    tasks: list[asyncio.Task] = []
    elapsed_ms = 0
    for turn in fixture["turns"]:
        wait_ms = int(turn.get("start_after_ms", 0)) - elapsed_ms
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000.0)
            elapsed_ms += wait_ms
        tasks.append(callsite.start_speech_final_task(
            turn["transcript"],
            source=turn.get("source", "deepgram_fixture"),
            user_audio_bytes=(turn.get("user_audio_marker") or turn["transcript"]).encode("utf-8"),
            route_delay_ms=int(turn.get("route_delay_ms", 0)),
        ))
    if tasks:
        await asyncio.gather(*tasks)
    return callsite.final_receipt()


# Re-export for tests that need the owner-loop invariant in this slice.
__all__ = [
    "P1ModelOwnerLoop",
    "P2CallsiteConfig",
    "P2ServerCallsite",
    "P2SpeechFinalReceipt",
    "make_p2_callsite_for_server",
    "run_p2_server_callsite_smoke",
]
