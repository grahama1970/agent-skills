#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""P0 PersonaPlex turn-aware memory/compliance harness.

The harness is a greenfield slice that exercises the control-plane contract
without importing the GPU-backed PersonaPlex model or requiring Deepgram/API
credentials.  It accepts final transcripts, treats them as Deepgram
``speech_final`` turns, runs deterministic memory/evidence route products, and
persists local JSON artifacts shaped like the live ``/memory /upsert`` contract.
"""

from dataclasses import dataclass, field
import asyncio
from pathlib import Path
from typing import Any

from personaplex_memory_contract import (
    DeterministicMemoryAdapter,
    RouteAction,
    intent_requires_evidence_case,
    validate_current_tool_plan,
)
from personaplex_persistence_contract import (
    LocalMemoryUpsertStore,
    build_conversation_history_record,
)
from personaplex_turn_state import (
    ResponsePacket,
    TurnAwareOutputGate,
    TurnStateMachine,
    TurnToken,
    sha256_json,
    utc_now,
)


@dataclass
class TurnRuntimeContext:
    token: TurnToken
    transcript: str
    expected_session_head_generation: int
    preintent_context: dict[str, Any]
    historical_tool_recommendations: list[dict[str, Any]]
    user_audio_bytes: bytes = b""
    user_audio_codec: str = "fixture/opus"
    started_at_utc: str = field(default_factory=utc_now)


@dataclass
class TurnPipelineResult:
    turn_id: int
    generation: int
    status: str
    reason: str
    sealed_key: str | None = None
    route_action: str | None = None
    route_endpoint: str | None = None
    gate_receipt: dict[str, Any] | None = None
    memory_upsert_receipt: dict[str, Any] | None = None
    stale_rejections_seen: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "generation": self.generation,
            "status": self.status,
            "reason": self.reason,
            "sealed_key": self.sealed_key,
            "route_action": self.route_action,
            "route_endpoint": self.route_endpoint,
            "gate_receipt": self.gate_receipt,
            "memory_upsert_receipt": self.memory_upsert_receipt,
            "stale_rejections_seen": self.stale_rejections_seen,
        }


class PersonaPlexP0Harness:
    """Turn-aware orchestration harness for the P0 implementation slice."""

    def __init__(
        self,
        *,
        session_id: str,
        persona_id: str,
        run_root: Path | str,
        memory: DeterministicMemoryAdapter | None = None,
        policy_version: str = "p0-live-turn-aware-memory-compliance-harness.v1",
    ) -> None:
        self.session_id = session_id
        self.persona_id = persona_id
        self.state = TurnStateMachine(session_id=session_id, persona_id=persona_id, policy_version=policy_version)
        self.gate = TurnAwareOutputGate(self.state)
        self.store = LocalMemoryUpsertStore(run_root)
        self.memory = memory or DeterministicMemoryAdapter()
        self.superseded_user_turns: list[dict[str, Any]] = []
        self._turn_tasks: dict[int, asyncio.Task[Any]] = {}

    def start_speech_final_turn(self, transcript: str, *, user_audio_bytes: bytes = b"", user_audio_codec: str = "fixture/opus") -> TurnRuntimeContext:
        previous = self.state.active_token
        if previous is not None:
            self.superseded_user_turns.append(
                {
                    "turn_id": previous.turn_id,
                    "generation": previous.generation,
                    "question": getattr(previous, "_transcript_for_context", ""),
                    "note": "superseded user text only; old route/tool recommendations cannot authorize this turn",
                }
            )
        token = self.state.start_turn(transcript)
        # The dataclass is frozen, so stash only non-authoritative context on the object via object.__setattr__.
        object.__setattr__(token, "_transcript_for_context", transcript)
        historical = self.state.consume_historical_authorities_for_active_turn()
        preintent_context = {
            "session_id": self.session_id,
            "persona_id": self.persona_id,
            "session_head_generation": self.store.session_generation(self.session_id),
            "superseded_user_turns": list(self.superseded_user_turns[-3:]),
            "historical_tool_recommendations": historical,
            "historical_recommendations_authoritative": False,
        }
        self.gate.close_for_turn(token, "new speech_final turn; close gate before memory/evidence routing")
        self.store.append_event(
            {
                "event": "deepgram_speech_final_turn_started",
                "turn_id": token.turn_id,
                "generation": token.generation,
                "transcript_hash": token.transcript_hash,
                "preintent_context_hash": sha256_json(preintent_context),
            }
        )
        return TurnRuntimeContext(
            token=token,
            transcript=transcript,
            expected_session_head_generation=self.store.session_generation(self.session_id),
            preintent_context=preintent_context,
            historical_tool_recommendations=historical,
            user_audio_bytes=user_audio_bytes,
            user_audio_codec=user_audio_codec,
        )

    def create_turn_task(self, ctx: TurnRuntimeContext, **pipeline_kwargs: Any) -> asyncio.Task[TurnPipelineResult]:
        task = asyncio.create_task(self.run_turn_pipeline(ctx, **pipeline_kwargs))
        self._turn_tasks[ctx.token.turn_id] = task
        return task

    async def run_turn_pipeline(
        self,
        ctx: TurnRuntimeContext,
        *,
        intent_delay_ms: int = 0,
        route_delay_ms: int = 0,
        recall_delay_ms: int = 0,
        evidence_delay_ms: int = 0,
        answer_delay_ms: int = 0,
    ) -> TurnPipelineResult:
        token = ctx.token
        intent_product = await self.memory.intent(ctx.transcript, token, ctx.preintent_context, delay_ms=intent_delay_ms)
        if not self.state.require_active(token, "memory_intent_callback", {"intent_hash": intent_product.get("receipt_hash")}):
            self._flush_stale_receipts()
            return self._stale_result(token, "intent callback returned after a newer turn became active")
        authority = self.state.attach_current_intent_authority(token, intent_product)
        if authority is None:
            self._flush_stale_receipts()
            return self._stale_result(token, "could not attach current intent authority")
        self.store.append_event(
            {
                "event": "memory_intent_product",
                "turn_id": token.turn_id,
                "generation": token.generation,
                "intent_hash": intent_product.get("receipt_hash"),
                "action": (intent_product.get("json") or {}).get("action"),
            }
        )
        if route_delay_ms:
            await asyncio.sleep(route_delay_ms / 1000.0)
        if not self.state.require_active(token, "route_plan_callback_after_delay", {"route_delay_ms": route_delay_ms}):
            self._flush_stale_receipts()
            return self._stale_result(token, "route work finished after a newer turn became active")

        requested_tools = _requested_tools_for_intent(intent_product)
        tool_plan = validate_current_tool_plan(intent_product, requested_tools)
        if not tool_plan["ok"]:
            route_product = await self.memory.deflect(ctx.transcript, intent_product)
        else:
            route_product, recall_snapshot, evidence_packet, route_receipts = await self._route_current_turn(
                ctx,
                intent_product,
                recall_delay_ms=recall_delay_ms,
                evidence_delay_ms=evidence_delay_ms,
                answer_delay_ms=answer_delay_ms,
            )
            if route_product is None:
                self._flush_stale_receipts()
                return self._stale_result(token, "route product callback was fenced")
            return await self._seal_active_turn(
                ctx=ctx,
                intent_product=intent_product,
                tool_plan=tool_plan,
                route_product=route_product,
                route_receipts=route_receipts,
                recall_snapshot=recall_snapshot,
                evidence_packet=evidence_packet,
                authority_hash=authority.intent_hash,
            )

        return await self._seal_active_turn(
            ctx=ctx,
            intent_product=intent_product,
            tool_plan=tool_plan,
            route_product=route_product,
            route_receipts=[route_product.to_dict()],
            recall_snapshot=None,
            evidence_packet=None,
            authority_hash=authority.intent_hash,
        )

    async def _route_current_turn(
        self,
        ctx: TurnRuntimeContext,
        intent_product: dict[str, Any],
        *,
        recall_delay_ms: int,
        evidence_delay_ms: int,
        answer_delay_ms: int,
    ) -> tuple[Any | None, dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
        token = ctx.token
        data = intent_product.get("json") or {}
        action = str(data.get("action") or "").upper()
        route_receipts: list[dict[str, Any]] = []
        recall_snapshot: dict[str, Any] | None = None
        evidence_packet: dict[str, Any] | None = None

        if action == RouteAction.DEFLECT.value or action == RouteAction.NO_MATCH.value:
            product = await self.memory.deflect(ctx.transcript, intent_product, delay_ms=answer_delay_ms)
            if not self.state.require_active(token, "memory_deflect_callback", {"route_endpoint": product.route_endpoint}):
                return None, None, None, []
            route_receipts.append(product.to_dict())
            return product, None, None, route_receipts

        if action == RouteAction.CLARIFY.value:
            product = await self.memory.clarify(ctx.transcript, intent_product, delay_ms=answer_delay_ms)
            if not self.state.require_active(token, "memory_clarify_callback", {"route_endpoint": product.route_endpoint}):
                return None, None, None, []
            route_receipts.append(product.to_dict())
            return product, None, None, route_receipts

        if intent_requires_evidence_case(intent_product):
            recall_snapshot = await self.memory.recall(ctx.transcript, intent_product, delay_ms=recall_delay_ms)
            if not self.state.require_active(token, "memory_recall_callback", {"recall_hash": recall_snapshot.get("receipt_hash")}):
                return None, None, None, []
            route_receipts.append(recall_snapshot)
            evidence_packet = await self.memory.create_evidence_case(
                ctx.transcript, intent_product, recall_snapshot, delay_ms=evidence_delay_ms
            )
            if not self.state.require_active(token, "create_evidence_case_callback", {"evidence_hash": evidence_packet.get("receipt_hash")}):
                return None, recall_snapshot, evidence_packet, route_receipts
            route_receipts.append(evidence_packet)
            if evidence_packet.get("can_answer") is True:
                product = await self.memory.answer(ctx.transcript, intent_product, recall_snapshot, delay_ms=answer_delay_ms)
                if not self.state.require_active(token, "memory_answer_from_evidence_callback", {"route_endpoint": product.route_endpoint}):
                    return None, recall_snapshot, evidence_packet, route_receipts
            else:
                product = await self.memory.clarify(ctx.transcript, intent_product, evidence_packet=evidence_packet, delay_ms=answer_delay_ms)
                if not self.state.require_active(token, "memory_clarify_from_evidence_callback", {"route_endpoint": product.route_endpoint}):
                    return None, recall_snapshot, evidence_packet, route_receipts
            route_receipts.append(product.to_dict())
            return product, recall_snapshot, evidence_packet, route_receipts

        recall_snapshot = await self.memory.recall(ctx.transcript, intent_product, delay_ms=recall_delay_ms)
        if not self.state.require_active(token, "memory_recall_callback", {"recall_hash": recall_snapshot.get("receipt_hash")}):
            return None, None, None, []
        route_receipts.append(recall_snapshot)
        product = await self.memory.answer(ctx.transcript, intent_product, recall_snapshot, delay_ms=answer_delay_ms)
        if not self.state.require_active(token, "memory_answer_callback", {"route_endpoint": product.route_endpoint}):
            return None, recall_snapshot, None, route_receipts
        route_receipts.append(product.to_dict())
        return product, recall_snapshot, None, route_receipts

    async def _seal_active_turn(
        self,
        *,
        ctx: TurnRuntimeContext,
        intent_product: dict[str, Any],
        tool_plan: dict[str, Any],
        route_product: Any,
        route_receipts: list[dict[str, Any]],
        recall_snapshot: dict[str, Any] | None,
        evidence_packet: dict[str, Any] | None,
        authority_hash: str,
    ) -> TurnPipelineResult:
        token = ctx.token
        # Simulate unauthorized PersonaPlex output while the gate is closed.  It is discarded, not queued.
        self.gate.enqueue_model_token(token, "unauthorized factual model token while grounding is pending", factual=True)
        packet: ResponsePacket = route_product.to_response_packet(token, current_intent_authority_hash=authority_hash)
        if not self.gate.stage_response_packet(token, packet):
            self._flush_stale_receipts()
            return self._stale_result(token, "response packet stage was fenced")
        gate_receipt = self.gate.open_for_active_packet(token)
        if gate_receipt is None:
            self._flush_stale_receipts()
            return self._stale_result(token, "gate open was fenced")
        user_audio = self.store.record_audio_bytes(
            session_id=token.session_id,
            turn_id=token.turn_id,
            role="user",
            data=ctx.user_audio_bytes or ctx.transcript.encode("utf-8"),
            codec=ctx.user_audio_codec,
        )
        assistant_audio = self.store.record_audio_bytes(
            session_id=token.session_id,
            turn_id=token.turn_id,
            role="assistant",
            data=packet.text.encode("utf-8"),
            codec="fixture/text-as-audio",
        )
        record = build_conversation_history_record(
            token=token,
            transcript=ctx.transcript,
            route_action=str((intent_product.get("json") or {}).get("action") or ""),
            intent_product=intent_product,
            tool_plan_validation=tool_plan,
            route_products=route_receipts,
            recall_snapshot=recall_snapshot,
            evidence_packet=evidence_packet,
            response_packet=packet,
            gate_receipt=gate_receipt,
            user_audio=user_audio,
            assistant_audio=assistant_audio,
            historical_tool_recommendations=ctx.historical_tool_recommendations,
            preintent_context_hash=sha256_json(ctx.preintent_context),
            safety_outcome=route_product.safety_outcome,
        )
        if not self.state.require_active(token, "conversation_history_upsert", {"key": record["_key"]}):
            self._flush_stale_receipts()
            return self._stale_result(token, "conversation history write was fenced")
        upsert_receipt = self.store.upsert_conversation_history(record)
        self.store.write_derived_personaplex_turn_projection(record)
        self.store.update_session_head_cas(
            session_id=token.session_id,
            expected_generation=ctx.expected_session_head_generation,
            update={
                "latest_conversation_key": record["_key"],
                "latest_turn_id": token.turn_id,
                "latest_route_action": record["route_action"],
                "latest_response_packet_hash": packet.packet_hash,
                "turn_count": ctx.expected_session_head_generation + 1,
                "current_context_window": [
                    {
                        "conversation_key": record["_key"],
                        "turn_id": token.turn_id,
                        "retrieval_text_hash": record["qdrant_pointer_metadata"]["text_hash"],
                        "route_action": record["route_action"],
                    }
                ],
                "historical_tool_recommendations_authoritative": False,
            },
        )
        self._flush_stale_receipts()
        return TurnPipelineResult(
            turn_id=token.turn_id,
            generation=token.generation,
            status="sealed",
            reason="active bounded response released and canonical conversation_history record written",
            sealed_key=record["_key"],
            route_action=record["route_action"],
            route_endpoint=packet.route_endpoint,
            gate_receipt=gate_receipt.to_dict(),
            memory_upsert_receipt=upsert_receipt,
            stale_rejections_seen=len(self.state.stale_rejections),
        )

    def _stale_result(self, token: TurnToken, reason: str) -> TurnPipelineResult:
        return TurnPipelineResult(
            turn_id=token.turn_id,
            generation=token.generation,
            status="stale_fenced",
            reason=reason,
            stale_rejections_seen=len(self.state.stale_rejections),
        )

    def _flush_stale_receipts(self) -> None:
        # Idempotent enough for a short-lived probe: append all receipts, then let
        # final-receipt consumers de-duplicate by tuple/hash if needed.
        for receipt in self.state.stale_rejections:
            self.store.append_stale_callback(receipt.to_dict())

    def final_receipt(self, results: list[TurnPipelineResult]) -> dict[str, Any]:
        history = self.store.list_conversation_history_records()
        session_head = self.store.read_session_head(self.session_id)
        release_receipts = [receipt.to_dict() for receipt in self.gate.release_receipts]
        stale = [receipt.to_dict() for receipt in self.state.stale_rejections]
        ok = bool(history) and all(item.get("gate_receipt", {}).get("queue_depth_at_release") == 0 for item in history)
        ok = ok and any(result.status == "stale_fenced" for result in results)
        ok = ok and bool(session_head and session_head.get("latest_turn_id") == max(item["turn_id"] for item in history))
        final = {
            "ok": ok,
            "scope": "greenfield P0 harness sanity only; not live Deepgram or PersonaPlex GPU proof",
            "session_id": self.session_id,
            "persona_id": self.persona_id,
            "active_turn_id": self.state.active_token.turn_id if self.state.active_token else None,
            "sealed_turn_keys": [item["_key"] for item in history],
            "sealed_turn_count": len(history),
            "stale_rejection_count": len(stale),
            "stale_rejections": stale,
            "release_receipts": release_receipts,
            "session_head": session_head,
            "results": [result.to_dict() for result in results],
            "created_at_utc": utc_now(),
        }
        self.store.append_event({"event": "final_receipt_built", "ok": ok, "sealed_turn_count": len(history)})
        return final


def _requested_tools_for_intent(intent_product: dict[str, Any]) -> list[str]:
    data = intent_product.get("json") or {}
    tools = []
    for item in data.get("tool_calls") or []:
        if isinstance(item, dict) and item.get("tool"):
            tools.append(str(item["tool"]))
    return tools
