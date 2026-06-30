#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""P1 live-wrapper integration control plane for PersonaPlex/Deepgram/memory.

This file is the P1 bridge between the P0 turn-aware control-plane harness and
current live wrapper callbacks.  It is deliberately usable in two modes:

* deterministic local transport for sanity/probe tests;
* HTTP transport against the live `$memory` daemon for mechanical integration.

The GPU PersonaPlex owner loop still lives in the real wrapper.  This slice
provides the turn token, stale callback fence, route-product normalization,
bounded-packet gate, and canonical persistence boundary that the wrapper must
call from Deepgram `speech_final` callbacks and output-token callbacks.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
import asyncio
import json
import urllib.error
import urllib.request

from personaplex_turn_state import (
    GateStateError,
    ResponsePacket,
    TurnAwareOutputGate,
    TurnStateMachine,
    TurnToken,
    sha256_json,
    utc_now,
)
from personaplex_memory_contract import RouteProduct, intent_requires_evidence_case, validate_current_tool_plan
from personaplex_persistence_contract import LocalMemoryUpsertStore, build_conversation_history_record

COMPLIANCE_TERMS = (
    "ivanti", "connect secure", "cve-", "cve ", "gateway", "gateways",
    "exploit", "exploitation", "vulnerability", "security", "compliance",
    "control", "sparta", "qra", "internet-facing", "internet facing",
)
POLICY_VERSION = "p1-live-wrapper-integration.v1"


class MemoryTransport(Protocol):
    async def post(self, endpoint: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]: ...


class HttpMemoryTransport:
    """Small stdlib HTTP transport for the live memory daemon.

    The transport intentionally returns raw response envelopes instead of hiding
    endpoint errors.  P1 route code can then fail closed with a bounded packet.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8601") -> None:
        self.base_url = base_url.rstrip("/")
        self.calls: list[dict[str, Any]] = []

    async def post(self, endpoint: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
        self.calls.append({"endpoint": endpoint, "payload": payload, "created_at_utc": utc_now()})
        return await asyncio.to_thread(self._post_sync, endpoint, payload, timeout)

    def _post_sync(self, endpoint: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST", headers={"content-type": "application/json", "accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = int(response.status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return {"ok": False, "status_code": exc.code, "text": body, "error_type": "HTTPError"}
        except Exception as exc:
            return {"ok": False, "status_code": None, "error_type": type(exc).__name__, "error": str(exc)}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None
        return {"ok": 200 <= status_code < 300, "status_code": status_code, "json": parsed, "text": None if parsed is not None else body}


class DeterministicP1MemoryTransport:
    """Fixture transport that mimics live `$memory` route products for P1 tests."""

    def __init__(self, *, force_ivanti_general_math: bool = False) -> None:
        self.force_ivanti_general_math = force_ivanti_general_math
        self.calls: list[dict[str, Any]] = []

    async def post(self, endpoint: str, payload: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
        self.calls.append({"endpoint": endpoint, "payload": payload, "created_at_utc": utc_now()})
        await asyncio.sleep(float(payload.get("delay_ms") or 0) / 1000.0)
        q = str(payload.get("q") or payload.get("question") or "")
        if endpoint == "/intent":
            return {"ok": True, "status_code": 200, "json": self._intent(q)}
        if endpoint == "/recall":
            return {"ok": True, "status_code": 200, "json": self._recall(q, payload)}
        if endpoint == "/answer":
            return {"ok": True, "status_code": 200, "json": {"schema": "memory.answer.v1", "ok": True, "can_answer": True, "final_response": "I can answer from the current memory packet, after the active-turn route has finished.", "source_packet_included": True}}
        if endpoint == "/clarify":
            return {"ok": True, "status_code": 200, "json": {"schema": "memory.clarify.v1", "ok": True, "needs_clarification": True, "blocking": True, "final_response": "Which canonical asset record, scan window, or control scope should I use?"}}
        if endpoint == "/deflect":
            return {"ok": True, "status_code": 200, "json": {"schema": "memory.deflect.v1", "ok": True, "should_deflect": True, "final_response": "I cannot do that from this memory route; ask a bounded project or compliance question instead."}}
        return {"ok": False, "status_code": 404, "json": {"error": "unknown deterministic endpoint"}}

    def _intent(self, q: str) -> dict[str, Any]:
        lower = q.lower()
        if self.force_ivanti_general_math and "ivanti" in lower:
            return {"action": "GENERAL_MATH", "query_type": "general_math", "recall_profile": "general_math", "confidence": 0.96, "allowed_tools": [], "tool_calls": [], "required_artifacts": [], "entities": []}
        if any(term in lower for term in COMPLIANCE_TERMS):
            return {
                "action": "COMPLIANCE",
                "confidence": 0.95,
                "recall_profile": "compliance.security.sparta.qra",
                "allowed_tools": ["memory.recall", "create-evidence-case", "memory.clarify", "memory.answer"],
                "disallowed_tools": ["unbounded_personaplex_generation", "historical_tool_replay"],
                "required_artifacts": ["recall_snapshot", "evidence_case"],
                "tool_calls": [
                    {"tool": "memory.recall", "endpoint": "/recall", "arguments": {"q": q, "scope": "sparta", "k": 8}},
                    {"tool": "create-evidence-case", "endpoint": "create-evidence-case", "arguments": {"q": q}},
                    {"tool": "memory.clarify", "endpoint": "/clarify", "arguments": {"q": q, "scope": "sparta"}},
                ],
                "query_plan": {"question_shaped_query": q, "requires_current_turn_authority": True},
                "extracted_entities": _extract_compliance_entities(q),
            }
        if "deflect" in lower or "ignore memory" in lower:
            return {"action": "DEFLECT", "confidence": 0.92, "recall_profile": "safety.deflect", "allowed_tools": ["memory.deflect"], "disallowed_tools": ["memory.answer"], "tool_calls": [{"tool": "memory.deflect", "endpoint": "/deflect", "arguments": {"q": q}}], "required_artifacts": ["deflection_packet"], "query_plan": {"question_shaped_query": q}, "extracted_entities": []}
        if "which" in lower or "what asset" in lower or "clarify" in lower:
            return {"action": "CLARIFY", "confidence": 0.82, "recall_profile": "clarify.scope", "allowed_tools": ["memory.clarify"], "disallowed_tools": ["memory.answer"], "tool_calls": [{"tool": "memory.clarify", "endpoint": "/clarify", "arguments": {"q": q}}], "required_artifacts": ["clarification_packet"], "query_plan": {"question_shaped_query": q}, "extracted_entities": []}
        return {"action": "ANSWER", "confidence": 0.89, "recall_profile": "persona.embry.current_fact_blend", "allowed_tools": ["memory.recall", "memory.answer"], "disallowed_tools": ["create-evidence-case", "unbounded_personaplex_generation"], "required_artifacts": ["recall_snapshot", "answer_packet"], "tool_calls": [{"tool": "memory.recall", "endpoint": "/recall", "arguments": {"q": q, "scope": "persona_memory", "tags": ["persona:embry"]}}, {"tool": "memory.answer", "endpoint": "/answer", "arguments": {"q": q, "scope": "persona_memory"}}], "query_plan": {"question_shaped_query": q, "persona_tags": ["persona:embry"]}, "extracted_entities": []}

    def _recall(self, q: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "route_endpoint": "/memory /recall", "confidence": 0.78, "recall_profile": payload.get("recall_profile") or payload.get("scope") or "sparta", "items": [
            {"id": "memory:west-gateway-candidate", "collection": "conversation_history", "text": "West gateway is referenced, but the exact canonical asset and scan window are not fully bridged.", "source_hash": "fixture-west-gateway", "scores": {"bm25": 0.74, "dense": 0.70, "graph": 0.41, "freshness": 0.55}},
            {"id": "memory:cve-2025-0282", "collection": "compliance_sources", "text": "Ivanti Connect Secure CVE-2025-0282 needs evidence-case handling before exposure claims.", "source_hash": "fixture-cve-2025-0282", "scores": {"bm25": 0.86, "dense": 0.81, "graph": 0.52, "freshness": 0.77}},
        ]}


@dataclass
class P1TurnContext:
    token: TurnToken
    transcript: str
    preintent_context: dict[str, Any]
    expected_session_head_generation: int
    historical_tool_recommendations: list[dict[str, Any]]
    user_audio_bytes: bytes = b""
    user_audio_codec: str = "live/opus"
    source: str = "deepgram"
    created_at_utc: str = field(default_factory=utc_now)


@dataclass
class P1TurnResult:
    turn_id: int
    generation: int
    status: str
    reason: str
    route_action: str | None = None
    route_endpoint: str | None = None
    sealed_key: str | None = None
    gate_receipt: dict[str, Any] | None = None
    upsert_receipt: dict[str, Any] | None = None
    stale_rejections_seen: int = 0
    endpoint_mismatch: dict[str, Any] | None = None
    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class P1MemoryClient:
    def __init__(self, transport: MemoryTransport, *, persona_id: str = "embry") -> None:
        self.transport = transport
        self.persona_id = persona_id

    async def intent(self, question: str, token: TurnToken, preintent_context: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = await self.transport.post("/intent", {"q": question, "scope": "sparta" if _looks_compliance(question) else "persona_memory", "fast": True, "preintent_context": preintent_context or {}})
        product = normalize_memory_intent(question, raw, token)
        return product

    async def recall(self, question: str, intent_product: dict[str, Any]) -> dict[str, Any]:
        data = intent_product.get("json") or {}
        payload = _payload_for_tool(data, "memory.recall") or {"q": question, "scope": data.get("recall_profile") or "memory", "k": 8}
        raw = await self.transport.post("/recall", payload)
        body = _body(raw)
        out = {"ok": bool(raw.get("ok")), "route_endpoint": "/memory /recall", "raw": raw, "items": body.get("items") or [], "confidence": body.get("confidence", 0.0), "recall_profile": body.get("recall_profile") or data.get("recall_profile"), "created_at_utc": utc_now()}
        out["receipt_hash"] = sha256_json(out)
        return out

    async def answer(self, question: str, intent_product: dict[str, Any], recall_snapshot: dict[str, Any] | None) -> RouteProduct:
        data = intent_product.get("json") or {}
        payload = _payload_for_tool(data, "memory.answer") or {"q": question, "scope": "persona_memory", "persona_id": self.persona_id, "recall_snapshot": recall_snapshot or {}}
        raw = await self.transport.post("/answer", payload, timeout=25.0)
        body = _body(raw)
        text = str(body.get("final_response") or body.get("source_answer") or "I can answer only from the current bounded source packet.")
        return RouteProduct(True, "/memory /answer", "ANSWER", text, True, True, ["recall_snapshot"], source_refs=(recall_snapshot or {}).get("items", [])[:4], recall_snapshot=recall_snapshot, safety_outcome="bounded_answer")

    async def clarify(self, question: str, intent_product: dict[str, Any], *, evidence_packet: dict[str, Any] | None = None) -> RouteProduct:
        data = intent_product.get("json") or {}
        payload = _payload_for_tool(data, "memory.clarify") or {"q": question, "scope": "sparta" if _looks_compliance(question) else "memory", "k": 4}
        raw = await self.transport.post("/clarify", payload)
        body = _body(raw)
        text = str(body.get("final_response") or (body.get("clarify_questions") or [{}])[0].get("question") if body.get("clarify_questions") else "I need one more grounded detail before I can answer safely.")
        return RouteProduct(True, "/memory /clarify", "CLARIFY", text, False, False, ["clarification_packet"], evidence_packet=evidence_packet, safety_outcome="clarify_before_answer")

    async def deflect(self, question: str, intent_product: dict[str, Any]) -> RouteProduct:
        data = intent_product.get("json") or {}
        payload = _payload_for_tool(data, "memory.deflect") or {"q": question, "persona_id": self.persona_id, "intent_action": data.get("action") or "NO_MATCH"}
        raw = await self.transport.post("/deflect", payload)
        body = _body(raw)
        text = str(body.get("final_response") or "I cannot safely do that from this route.")
        return RouteProduct(True, "/memory /deflect", "DEFLECT", text, False, False, ["deflection_packet"], safety_outcome="deflected")

    async def evidence_case(self, question: str, intent_product: dict[str, Any], recall_snapshot: dict[str, Any] | None) -> dict[str, Any]:
        # P1 intentionally keeps CAE as an adapter boundary.  With no real CAE
        # transport supplied, compliance routes fail closed to clarify.
        packet = {
            "ok": False,
            "route_endpoint": "create-evidence-case",
            "integration_mode": "stub_fail_closed_until_real_create_evidence_case_is_wired",
            "can_answer": False,
            "evidence_quality": "missing_or_inconclusive",
            "next_route": "/memory /clarify",
            "question": question,
            "source_refs": (recall_snapshot or {}).get("items", []),
            "uncertainty": "P1 did not receive a real create-evidence-case verdict; factual compliance speech remains blocked.",
            "created_at_utc": utc_now(),
        }
        packet["receipt_hash"] = sha256_json(packet)
        return packet


def normalize_memory_intent(question: str, raw: dict[str, Any], token: TurnToken) -> dict[str, Any]:
    body = _body(raw)
    action = str(body.get("action") or body.get("intent_action") or "NO_MATCH").upper()
    mismatch = None
    if _looks_compliance(question) and (action in {"GENERAL_MATH", "ANSWER"} and not body.get("tool_calls")):
        mismatch = {
            "type": "memory_intent_endpoint_mismatch",
            "raw_action": action,
            "raw_recall_profile": body.get("recall_profile"),
            "reason": "compliance/security query was not routed to compliance tools by current /memory intent",
            "fail_closed": True,
        }
        normalized = {
            "action": "COMPLIANCE_ENDPOINT_MISMATCH",
            "confidence": min(float(body.get("confidence") or 0.0), 0.5),
            "recall_profile": "fail_closed.intent_endpoint_mismatch",
            "query_plan": {"question_shaped_query": question, "requires_current_turn_authority": True, "memory_endpoint_mismatch": True, "endpoint_mismatch": True},
            "tool_calls": [{"tool": "fixed_fallback", "purpose": "bounded fail-closed response because current intent did not authorize compliance tools"}],
            "allowed_tools": ["fixed_fallback"],
            "disallowed_tools": ["memory.answer", "unbounded_personaplex_generation", "historical_tool_replay"],
            "required_artifacts": ["intent_endpoint_mismatch_receipt", "fixed_fallback_packet"],
            "extracted_entities": _extract_compliance_entities(question),
            "depends_on": ["speech_final", "current_intent_authority"],
            "endpoint_mismatch": mismatch,
        }
    else:
        normalized = {
            "action": action,
            "confidence": body.get("confidence"),
            "recall_profile": body.get("recall_profile") or body.get("recall_profile_spec", {}).get("name"),
            "query_plan": body.get("query_plan") or {"question_shaped_query": question, "requires_current_turn_authority": True},
            "tool_calls": [_normalize_tool_call(call) for call in (body.get("tool_calls") or [])],
            "allowed_tools": list(body.get("allowed_tools") or []),
            "disallowed_tools": list(body.get("disallowed_tools") or []),
            "required_artifacts": list(body.get("required_artifacts") or []),
            "extracted_entities": body.get("extracted_entities") or body.get("entities") or _extract_compliance_entities(question),
            "depends_on": list(body.get("depends_on") or ["speech_final", "current_intent_authority"]),
        }
        if not normalized["tool_calls"] and normalized["action"] == "CLARIFY":
            normalized["tool_calls"] = [{"tool": "memory.clarify", "endpoint": "/clarify", "arguments": {"q": question}}]
        if not normalized["tool_calls"] and normalized["action"] in {"DEFLECT", "NO_MATCH"}:
            normalized["tool_calls"] = [{"tool": "memory.deflect", "endpoint": "/deflect", "arguments": {"q": question}}]
        allowed = set(normalized.get("allowed_tools") or [])
        for call in normalized.get("tool_calls") or []:
            tool = call.get("tool") or _tool_from_endpoint(call.get("endpoint") or call.get("skill"))
            if tool:
                allowed.add(str(tool))
        normalized["allowed_tools"] = sorted(allowed)
    product = {"ok": bool(raw.get("ok", True)), "route_endpoint": "/memory /intent", "turn_id": token.turn_id, "generation": token.generation, "authority_key": token.authority_key, "json": normalized, "raw_memory_intent": raw, "created_at_utc": utc_now()}
    product["receipt_hash"] = sha256_json(product)
    return product


def requested_tools_for_intent(intent_product: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for call in (intent_product.get("json") or {}).get("tool_calls") or []:
        tool = call.get("tool") or _tool_from_endpoint(call.get("endpoint"))
        if tool:
            out.append(str(tool))
    return out


class P1LiveTurnController:
    def __init__(self, *, session_id: str, persona_id: str, run_root: Path | str, memory_client: P1MemoryClient, policy_version: str = POLICY_VERSION) -> None:
        self.session_id = session_id
        self.persona_id = persona_id
        self.state = TurnStateMachine(session_id=session_id, persona_id=persona_id, policy_version=policy_version)
        self.gate = TurnAwareOutputGate(self.state)
        self.store = LocalMemoryUpsertStore(run_root)
        self.memory = memory_client
        self.superseded_user_turns: list[dict[str, Any]] = []

    def start_final_transcript(self, transcript: str, *, user_audio_bytes: bytes = b"", user_audio_codec: str = "live/opus", source: str = "deepgram") -> P1TurnContext:
        previous = self.state.active_token
        if previous is not None:
            self.superseded_user_turns.append({"turn_id": previous.turn_id, "generation": previous.generation, "note": "superseded transcript context only; not tool authority"})
        token = self.state.start_turn(transcript)
        historical = self.state.consume_historical_authorities_for_active_turn()
        preintent_context = {
            "session_id": self.session_id,
            "persona_id": self.persona_id,
            "session_head_generation": self.store.session_generation(self.session_id),
            "superseded_user_turns": list(self.superseded_user_turns[-3:]),
            "historical_tool_recommendations": historical,
            "historical_recommendations_authoritative": False,
        }
        self.gate.close_for_turn(token, "new speech_final turn; close gate before current memory/evidence routing")
        self.store.append_event({"event": "p1_speech_final_turn_started", "source": source, "turn_id": token.turn_id, "generation": token.generation, "transcript_hash": token.transcript_hash, "preintent_context_hash": sha256_json(preintent_context)})
        return P1TurnContext(token=token, transcript=transcript, preintent_context=preintent_context, expected_session_head_generation=self.store.session_generation(self.session_id), historical_tool_recommendations=historical, user_audio_bytes=user_audio_bytes or transcript.encode("utf-8"), user_audio_codec=user_audio_codec, source=source)

    async def run_turn(self, ctx: P1TurnContext, *, intent_delay_ms: int = 0, route_delay_ms: int = 0) -> P1TurnResult:
        token = ctx.token
        if intent_delay_ms:
            await asyncio.sleep(intent_delay_ms / 1000.0)
        intent = await self.memory.intent(ctx.transcript, token, ctx.preintent_context)
        if not self.state.require_active(token, "p1_memory_intent_callback", {"intent_hash": intent.get("receipt_hash")}):
            self._flush_stale_receipts()
            return self._stale(token, "intent callback returned after a newer turn became active")
        authority = self.state.attach_current_intent_authority(token, intent)
        if authority is None:
            self._flush_stale_receipts()
            return self._stale(token, "could not attach current-turn intent authority")
        self.store.append_event({"event": "p1_memory_intent_product", "turn_id": token.turn_id, "generation": token.generation, "action": (intent.get("json") or {}).get("action"), "intent_hash": intent.get("receipt_hash"), "endpoint_mismatch": (intent.get("json") or {}).get("endpoint_mismatch")})
        if route_delay_ms:
            await asyncio.sleep(route_delay_ms / 1000.0)
        if not self.state.require_active(token, "p1_route_callback_after_delay", {"route_delay_ms": route_delay_ms}):
            self._flush_stale_receipts()
            return self._stale(token, "route work finished after a newer turn became active")
        requested = requested_tools_for_intent(intent)
        tool_plan = validate_current_tool_plan(intent, requested)
        if not tool_plan.get("ok"):
            product = fixed_fallback_product(ctx.transcript, intent, "current /memory intent did not authorize the requested route tools")
            route_receipts, recall_snapshot, evidence_packet = [product.to_dict()], None, None
        else:
            product, route_receipts, recall_snapshot, evidence_packet = await self._route(ctx, intent)
            if product is None:
                self._flush_stale_receipts()
                return self._stale(token, "route product was fenced before packet stage")
        return await self._seal(ctx, intent, tool_plan, product, route_receipts, recall_snapshot, evidence_packet, authority.intent_hash)

    async def _route(self, ctx: P1TurnContext, intent: dict[str, Any]) -> tuple[RouteProduct | None, list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
        token = ctx.token
        data = intent.get("json") or {}
        action = str(data.get("action") or "").upper()
        if action == "COMPLIANCE_ENDPOINT_MISMATCH":
            product = fixed_fallback_product(ctx.transcript, intent, "memory intent endpoint mismatch for compliance query")
            return product, [product.to_dict()], None, None
        if action in {"DEFLECT", "NO_MATCH", "OFF_TOPIC", "UNSAFE"}:
            product = await self.memory.deflect(ctx.transcript, intent)
            if not self.state.require_active(token, "p1_memory_deflect_callback", {"route_endpoint": product.route_endpoint}):
                return None, [], None, None
            return product, [product.to_dict()], None, None
        if action == "CLARIFY":
            product = await self.memory.clarify(ctx.transcript, intent)
            if not self.state.require_active(token, "p1_memory_clarify_callback", {"route_endpoint": product.route_endpoint}):
                return None, [], None, None
            return product, [product.to_dict()], None, None
        recall = await self.memory.recall(ctx.transcript, intent)
        if not self.state.require_active(token, "p1_memory_recall_callback", {"recall_hash": recall.get("receipt_hash")}):
            return None, [], recall, None
        receipts = [recall]
        if intent_requires_evidence_case(intent):
            evidence = await self.memory.evidence_case(ctx.transcript, intent, recall)
            if not self.state.require_active(token, "p1_create_evidence_case_callback", {"evidence_hash": evidence.get("receipt_hash")}):
                return None, receipts, recall, evidence
            receipts.append(evidence)
            if evidence.get("can_answer") is True:
                product = await self.memory.answer(ctx.transcript, intent, recall)
            else:
                product = await self.memory.clarify(ctx.transcript, intent, evidence_packet=evidence)
            if not self.state.require_active(token, "p1_memory_route_product_callback", {"route_endpoint": product.route_endpoint}):
                return None, receipts, recall, evidence
            receipts.append(product.to_dict())
            return product, receipts, recall, evidence
        product = await self.memory.answer(ctx.transcript, intent, recall)
        if not self.state.require_active(token, "p1_memory_answer_callback", {"route_endpoint": product.route_endpoint}):
            return None, receipts, recall, None
        receipts.append(product.to_dict())
        return product, receipts, recall, None

    async def _seal(self, ctx: P1TurnContext, intent: dict[str, Any], tool_plan: dict[str, Any], product: RouteProduct, route_receipts: list[dict[str, Any]], recall_snapshot: dict[str, Any] | None, evidence_packet: dict[str, Any] | None, authority_hash: str) -> P1TurnResult:
        token = ctx.token
        # Data stop: any free PersonaPlex token emitted while facts/evidence are pending is discarded.
        self.gate.enqueue_model_token(token, "ungrounded PersonaPlex token while P1 route pending", factual=True)
        packet = product.to_response_packet(token, current_intent_authority_hash=authority_hash)
        if not self.gate.stage_response_packet(token, packet):
            self._flush_stale_receipts(); return self._stale(token, "bounded packet stage was fenced")
        receipt = self.gate.open_for_active_packet(token)
        if receipt is None:
            self._flush_stale_receipts(); return self._stale(token, "gate open was fenced")
        user_audio = self.store.record_audio_bytes(session_id=token.session_id, turn_id=token.turn_id, role="user", data=ctx.user_audio_bytes, codec=ctx.user_audio_codec, retention_class="p1_live_wrapper_sanity")
        assistant_audio = self.store.record_audio_bytes(session_id=token.session_id, turn_id=token.turn_id, role="assistant", data=packet.text.encode("utf-8"), codec="p1/bounded-text-as-audio", retention_class="p1_live_wrapper_sanity")
        record = build_conversation_history_record(token=token, transcript=ctx.transcript, route_action=str((intent.get("json") or {}).get("action") or ""), intent_product=intent, tool_plan_validation=tool_plan, route_products=route_receipts, recall_snapshot=recall_snapshot, evidence_packet=evidence_packet, response_packet=packet, gate_receipt=receipt, user_audio=user_audio, assistant_audio=assistant_audio, historical_tool_recommendations=ctx.historical_tool_recommendations, preintent_context_hash=sha256_json(ctx.preintent_context), safety_outcome=product.safety_outcome)
        record["p1_live_wrapper_integration"] = {"adapter_mode": "local_stand_in_until_real_memory_upsert_is_wired", "source_callback": ctx.source, "claim_boundary": "P1 deterministic wrapper integration receipt; not live Deepgram ASR/VAD or GPU PersonaPlex proof."}
        if not self.state.require_active(token, "p1_conversation_history_upsert", {"key": record["_key"]}):
            self._flush_stale_receipts(); return self._stale(token, "conversation_history write was fenced")
        upsert = self.store.upsert_conversation_history(record)
        self.store.write_derived_personaplex_turn_projection(record)
        self.store.update_session_head_cas(session_id=token.session_id, expected_generation=ctx.expected_session_head_generation, update={"latest_conversation_key": record["_key"], "latest_turn_id": token.turn_id, "latest_route_action": record["route_action"], "latest_response_packet_hash": packet.packet_hash, "turn_count": ctx.expected_session_head_generation + 1, "current_context_window": [{"conversation_key": record["_key"], "turn_id": token.turn_id, "retrieval_text_hash": record["qdrant_pointer_metadata"]["text_hash"], "route_action": record["route_action"]}], "historical_tool_recommendations_authoritative": False})
        self._flush_stale_receipts()
        return P1TurnResult(token.turn_id, token.generation, "sealed", "active bounded packet released and canonical conversation_history write completed through P1 adapter boundary", route_action=record["route_action"], route_endpoint=packet.route_endpoint, sealed_key=record["_key"], gate_receipt=receipt.to_dict(), upsert_receipt=upsert, stale_rejections_seen=len(self.state.stale_rejections), endpoint_mismatch=(intent.get("json") or {}).get("endpoint_mismatch"))

    def try_enqueue_live_model_token(self, token: TurnToken, token_text: str, *, factual: bool = True) -> bool:
        return self.gate.enqueue_model_token(token, token_text, factual=factual)

    def final_receipt(self, results: list[P1TurnResult]) -> dict[str, Any]:
        history = self.store.list_conversation_history_records()
        stale = [r.to_dict() for r in self.state.stale_rejections]
        release_receipts = [r.to_dict() for r in self.gate.release_receipts]
        ok = bool(history) and all((item.get("gate_receipt") or {}).get("queue_depth_at_release") == 0 for item in history)
        if len(results) > 1:
            ok = ok and any(r.status == "stale_fenced" for r in results)
        final = {"schema": "personaplex.p1_live_wrapper_probe.final_receipt.v1", "ok": bool(ok), "scope": "P1 deterministic live-wrapper integration slice; not live Deepgram two-turn proof and not GPU PersonaPlex proof", "session_id": self.session_id, "persona_id": self.persona_id, "active_turn_id": self.state.active_token.turn_id if self.state.active_token else None, "sealed_turn_keys": [x["_key"] for x in history], "sealed_turn_count": len(history), "stale_rejection_count": len(stale), "stale_rejections": stale, "release_receipts": release_receipts, "session_head": self.store.read_session_head(self.session_id), "results": [r.to_dict() for r in results], "events_jsonl": str(self.store.events_jsonl), "created_at_utc": utc_now()}
        self.store.append_event({"event": "p1_final_receipt_built", "ok": final["ok"], "sealed_turn_count": len(history)})
        return final

    def _stale(self, token: TurnToken, reason: str) -> P1TurnResult:
        return P1TurnResult(token.turn_id, token.generation, "stale_fenced", reason, stale_rejections_seen=len(self.state.stale_rejections))

    def _flush_stale_receipts(self) -> None:
        for receipt in self.state.stale_rejections:
            self.store.append_stale_callback(receipt.to_dict())


class P1ModelOwnerLoop:
    """Serialize PersonaPlex model work so research tasks never call LMGen.step."""

    def __init__(self, step_func: Callable[[dict[str, Any]], Awaitable[Any] | Any]) -> None:
        self.step_func = step_func
        self.queue: asyncio.Queue[tuple[dict[str, Any] | None, asyncio.Future | None]] = asyncio.Queue()
        self.owner_task: asyncio.Task | None = None
        self.active_calls = 0
        self.max_parallel_calls = 0
        self.closed = False

    async def start(self) -> None:
        if self.owner_task is None:
            self.owner_task = asyncio.create_task(self._run(), name="p1_personaplex_model_owner_loop")

    async def submit(self, op: dict[str, Any]) -> Any:
        if self.closed:
            raise RuntimeError("model owner loop is closed")
        if self.owner_task is None:
            await self.start()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        await self.queue.put((op, fut))
        return await fut

    async def close(self) -> None:
        self.closed = True
        if self.owner_task is not None:
            await self.queue.put((None, None))
            await self.owner_task

    async def _run(self) -> None:
        while True:
            op, fut = await self.queue.get()
            if op is None:
                return
            try:
                self.active_calls += 1
                self.max_parallel_calls = max(self.max_parallel_calls, self.active_calls)
                result = self.step_func(op)
                if hasattr(result, "__await__"):
                    result = await result  # type: ignore[assignment]
                if fut and not fut.done():
                    fut.set_result(result)
            except Exception as exc:
                if fut and not fut.done():
                    fut.set_exception(exc)
            finally:
                self.active_calls -= 1


class P1GoldenStateSessionAdapter:
    """Drop-in hook object for `personaplex_golden_state_server.py` chat sessions."""

    def __init__(self, controller: P1LiveTurnController) -> None:
        self.controller = controller
        self.tasks: set[asyncio.Task] = set()

    async def on_speech_final(self, transcript: str, *, source: str, user_audio_bytes: bytes = b"") -> dict[str, Any]:
        ctx = self.controller.start_final_transcript(transcript, user_audio_bytes=user_audio_bytes or transcript.encode("utf-8"), source=source)
        task = asyncio.create_task(self.controller.run_turn(ctx), name=f"p1_route_turn_{ctx.token.turn_id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return {"event": "p1_turn_started", "turn_id": ctx.token.turn_id, "generation": ctx.token.generation, "gate_closed": self.controller.gate.closed, "source": source}

    def should_emit_model_output(self, token_text: str, *, factual: bool = True) -> bool:
        token = self.controller.state.active_token
        if token is None:
            return False
        return self.controller.try_enqueue_live_model_token(token, token_text, factual=factual)

    async def drain(self) -> list[P1TurnResult]:
        if not self.tasks:
            return []
        return list(await asyncio.gather(*list(self.tasks)))


def fixed_fallback_product(question: str, intent_product: dict[str, Any], reason: str) -> RouteProduct:
    mismatch = (intent_product.get("json") or {}).get("endpoint_mismatch")
    text = "I need to stop and re-route this safely: the current memory intent did not authorize a grounded compliance answer."
    if mismatch:
        text = "I need to stop here: the current memory intent classified this compliance-looking request incorrectly, so I cannot provide a factual answer from this route."
    return RouteProduct(True, "fixed_fallback.intent_endpoint_mismatch", "FIXED_FALLBACK", text, False, False, ["fixed_fallback_packet"], evidence_packet={"reason": reason, "endpoint_mismatch": mismatch, "created_at_utc": utc_now()}, safety_outcome="fixed_fallback_fail_closed")


def _body(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("json") if isinstance(raw, dict) else raw
    if isinstance(data, dict) and "response" in data and isinstance(data["response"], dict):
        return data["response"]
    return data if isinstance(data, dict) else {}


def _looks_compliance(question: str) -> bool:
    lower = question.lower()
    return any(term in lower for term in COMPLIANCE_TERMS)


def _normalize_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    out = dict(call)
    if not out.get("tool"):
        out["tool"] = _tool_from_endpoint(out.get("endpoint") or out.get("route_endpoint") or out.get("skill"))
    out.setdefault("arguments", {})
    return out


def _tool_from_endpoint(endpoint: Any) -> str | None:
    if endpoint is None:
        return None
    e = str(endpoint)
    mapping = {
        "/recall": "memory.recall",
        "/answer": "memory.answer",
        "/clarify": "memory.clarify",
        "/deflect": "memory.deflect",
        "create-evidence-case": "create-evidence-case",
        "brave-search": "brave-search",
    }
    if e in mapping:
        return mapping[e]
    if e.startswith("/"):
        return mapping.get(e)
    if e in {"fixed_fallback"} or "." in e or "-" in e:
        return e
    return None


def _payload_for_tool(data: dict[str, Any], tool: str) -> dict[str, Any] | None:
    for call in data.get("tool_calls") or []:
        norm = _normalize_tool_call(call)
        if norm.get("tool") == tool:
            return dict(norm.get("arguments") or {})
    return None


def _extract_compliance_entities(q: str) -> list[dict[str, str]]:
    lower = q.lower()
    entities: list[dict[str, str]] = []
    if "ivanti" in lower:
        entities.append({"type": "product", "text": "Ivanti Connect Secure"})
    if "cve-2025-0282" in lower:
        entities.append({"type": "vulnerability", "text": "CVE-2025-0282"})
    if "west gateway" in lower:
        entities.append({"type": "asset_scope", "text": "west gateway"})
    return entities
