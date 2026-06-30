#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""Current-turn memory route contract and deterministic P0 adapter.

The real wrapper should swap ``DeterministicMemoryAdapter`` for subprocess/API
calls into ``skills/memory/run.sh`` and ``create-evidence-case``.  The schema and
authority checks here are the P0 contract: only the current ``/memory intent``
result can authorize the tools/routes for the active turn.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import asyncio
from typing import Any

from personaplex_turn_state import ResponsePacket, TurnToken, sha256_json, utc_now


class RouteAction(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    DEFLECT = "DEFLECT"
    COMPLIANCE = "COMPLIANCE"
    NO_MATCH = "NO_MATCH"


@dataclass
class MemoryIntent:
    action: RouteAction
    confidence: float
    recall_profile: str
    query_plan: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    allowed_tools: list[str]
    disallowed_tools: list[str]
    required_artifacts: list[str]
    extracted_entities: list[dict[str, Any]]
    depends_on: list[str]
    route_endpoint: str = "/memory /intent"
    created_at_utc: str = field(default_factory=utc_now)

    def to_product(self, token: TurnToken) -> dict[str, Any]:
        data = {
            "ok": True,
            "route_endpoint": self.route_endpoint,
            "turn_id": token.turn_id,
            "generation": token.generation,
            "authority_key": token.authority_key,
            "json": {
                "action": self.action.value,
                "confidence": self.confidence,
                "recall_profile": self.recall_profile,
                "query_plan": self.query_plan,
                "tool_calls": self.tool_calls,
                "allowed_tools": self.allowed_tools,
                "disallowed_tools": self.disallowed_tools,
                "required_artifacts": self.required_artifacts,
                "extracted_entities": self.extracted_entities,
                "depends_on": self.depends_on,
                "historical_tool_recommendations_authoritative": False,
            },
            "created_at_utc": self.created_at_utc,
        }
        data["receipt_hash"] = sha256_json(data)
        return data


@dataclass
class RouteProduct:
    ok: bool
    route_endpoint: str
    action: str
    text: str
    can_answer: bool
    factual_claims_allowed: bool
    required_artifacts: list[str]
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_packet: dict[str, Any] | None = None
    recall_snapshot: dict[str, Any] | None = None
    safety_outcome: str = "bounded"
    created_at_utc: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["receipt_hash"] = sha256_json(data)
        return data

    def to_response_packet(self, token: TurnToken, current_intent_authority_hash: str) -> ResponsePacket:
        product = self.to_dict()
        return ResponsePacket(
            session_id=token.session_id,
            turn_id=token.turn_id,
            generation=token.generation,
            route_endpoint=self.route_endpoint,
            text=self.text,
            factual_claims_allowed=self.factual_claims_allowed,
            source_product_hash=product["receipt_hash"],
            current_intent_authority_hash=current_intent_authority_hash,
        )


def intent_requires_evidence_case(intent_product: dict[str, Any]) -> bool:
    data = intent_product.get("json") or {}
    action = str(data.get("action") or "").upper()
    profile = str(data.get("recall_profile") or "").lower()
    artifacts = [str(item).lower() for item in (data.get("required_artifacts") or [])]
    if action == RouteAction.COMPLIANCE.value or "evidence_case" in artifacts:
        return True
    return any(marker in profile for marker in ("qra", "sparta", "compliance", "security")) or bool(data.get("frameworks"))


def validate_current_tool_plan(intent_product: dict[str, Any], requested_tools: list[str]) -> dict[str, Any]:
    data = intent_product.get("json") or {}
    allowed = set(data.get("allowed_tools") or [])
    disallowed = set(data.get("disallowed_tools") or [])
    requested = set(requested_tools)
    denied = sorted((requested - allowed) | (requested & disallowed))
    result = {
        "ok": not denied,
        "requested_tools": sorted(requested),
        "allowed_tools": sorted(allowed),
        "disallowed_tools": sorted(disallowed),
        "denied_tools": denied,
        "authority_key": intent_product.get("authority_key"),
        "intent_hash": intent_product.get("receipt_hash"),
        "created_at_utc": utc_now(),
    }
    if denied:
        result["error"] = "requested tools were not authorized by the current /memory intent response"
    return result


class DeterministicMemoryAdapter:
    """Fixture-backed adapter for isolated greenfield sanity checks.

    This adapter deliberately returns structured route products.  It does not
    assert that the live memory service is implemented; it gives the project
    agent a deterministic harness to port and then replace with real calls.
    """

    async def intent(self, question: str, token: TurnToken, preintent_context: dict[str, Any] | None = None, delay_ms: int = 0) -> dict[str, Any]:
        await _sleep_ms(delay_ms)
        lower = question.lower()
        context_text = " ".join(str(item.get("question") or "") for item in (preintent_context or {}).get("superseded_user_turns", []))
        combined = f"{lower} {context_text.lower()}"
        if "ivanti" in combined or "cve-2025-0282" in combined or "west gateway" in combined or "compliance" in combined or "security" in combined:
            entities = [
                {"type": "product", "text": "Ivanti Connect Secure"},
                {"type": "vulnerability", "text": "CVE-2025-0282"},
            ]
            if "west gateway" in combined:
                entities.append({"type": "asset_scope", "text": "west gateway"})
            intent = MemoryIntent(
                action=RouteAction.COMPLIANCE,
                confidence=0.96,
                recall_profile="compliance.security.sparta.qra",
                query_plan={
                    "question_shaped_query": question,
                    "requires_current_turn_authority": True,
                    "historical_recommendations_are_context_only": True,
                },
                tool_calls=[
                    {"tool": "memory.recall", "purpose": "retrieve scoped assets, controls, prior turn context, and evidence refs"},
                    {"tool": "create-evidence-case", "purpose": "judge compliance/security evidence before factual speech"},
                    {"tool": "memory.clarify", "purpose": "ask one targeted follow-up when evidence or entity bridge is weak"},
                ],
                allowed_tools=["memory.recall", "create-evidence-case", "memory.clarify", "memory.answer"],
                disallowed_tools=["unbounded_personaplex_generation", "historical_tool_replay"],
                required_artifacts=["recall_snapshot", "evidence_case"],
                extracted_entities=entities,
                depends_on=["speech_final", "current_intent_authority"],
            )
        elif "unsafe" in lower or "ignore memory" in lower:
            intent = MemoryIntent(
                action=RouteAction.DEFLECT,
                confidence=0.93,
                recall_profile="safety.deflect",
                query_plan={"question_shaped_query": question},
                tool_calls=[{"tool": "memory.deflect", "purpose": "bounded refusal or redirect"}],
                allowed_tools=["memory.deflect"],
                disallowed_tools=["memory.answer", "create-evidence-case", "unbounded_personaplex_generation"],
                required_artifacts=["deflection_packet"],
                extracted_entities=[],
                depends_on=["speech_final", "current_intent_authority"],
            )
        elif "which" in lower or "what one" in lower:
            intent = MemoryIntent(
                action=RouteAction.CLARIFY,
                confidence=0.81,
                recall_profile="clarify.scope",
                query_plan={"question_shaped_query": question},
                tool_calls=[{"tool": "memory.clarify", "purpose": "resolve scope"}],
                allowed_tools=["memory.clarify"],
                disallowed_tools=["memory.answer", "unbounded_personaplex_generation"],
                required_artifacts=["clarification_packet"],
                extracted_entities=[],
                depends_on=["speech_final", "current_intent_authority"],
            )
        else:
            intent = MemoryIntent(
                action=RouteAction.ANSWER,
                confidence=0.88,
                recall_profile="persona.embry.current_fact_blend",
                query_plan={"question_shaped_query": question, "persona_tags": ["persona:embry"]},
                tool_calls=[
                    {"tool": "memory.recall", "purpose": "retrieve persona-scoped context"},
                    {"tool": "memory.answer", "purpose": "bounded answer from recall snapshot"},
                ],
                allowed_tools=["memory.recall", "memory.answer"],
                disallowed_tools=["create-evidence-case", "unbounded_personaplex_generation", "historical_tool_replay"],
                required_artifacts=["recall_snapshot", "answer_packet"],
                extracted_entities=[],
                depends_on=["speech_final", "current_intent_authority"],
            )
        return intent.to_product(token)

    async def recall(self, question: str, intent_product: dict[str, Any], delay_ms: int = 0) -> dict[str, Any]:
        await _sleep_ms(delay_ms)
        data = intent_product.get("json") or {}
        profile = data.get("recall_profile")
        items = [
            {
                "id": "memory:asset-west-gateway-candidate",
                "collection": "conversation_history",
                "text": "West gateway scope is mentioned, but the canonical asset identifier and latest exposure scan are not present in the P0 fixture.",
                "scores": {"bm25": 0.74, "dense": 0.70, "graph": 0.41, "freshness": 0.55},
                "source_hash": "fixture-west-gateway-scope",
            },
            {
                "id": "memory:vuln-cve-2025-0282",
                "collection": "compliance_sources",
                "text": "Ivanti Connect Secure CVE-2025-0282 requires evidence-case handling before claims about exposure or exploitation.",
                "scores": {"bm25": 0.86, "dense": 0.81, "graph": 0.52, "freshness": 0.77},
                "source_hash": "fixture-cve-2025-0282",
            },
        ]
        return {
            "ok": True,
            "route_endpoint": "/memory /recall",
            "recall_profile": profile,
            "items": items,
            "confidence": 0.78,
            "query_plan": data.get("query_plan") or {},
            "created_at_utc": utc_now(),
            "receipt_hash": sha256_json({"items": items, "profile": profile}),
        }

    async def answer(self, question: str, intent_product: dict[str, Any], recall_snapshot: dict[str, Any] | None = None, delay_ms: int = 0) -> RouteProduct:
        await _sleep_ms(delay_ms)
        return RouteProduct(
            ok=True,
            route_endpoint="/memory /answer",
            action="ANSWER",
            text="I can answer from the current memory packet, and I will keep it bounded to the active turn.",
            can_answer=True,
            factual_claims_allowed=True,
            required_artifacts=["recall_snapshot"],
            recall_snapshot=recall_snapshot,
            source_refs=(recall_snapshot or {}).get("items", [])[:2],
            safety_outcome="bounded_answer",
        )

    async def clarify(self, question: str, intent_product: dict[str, Any], evidence_packet: dict[str, Any] | None = None, delay_ms: int = 0) -> RouteProduct:
        await _sleep_ms(delay_ms)
        if evidence_packet:
            text = "I need one more detail before I can answer safely: which canonical west-gateway asset record or scan window should I use?"
        else:
            text = "I need one specific detail before I can continue: which asset, scope, or timeframe should I use?"
        return RouteProduct(
            ok=True,
            route_endpoint="/memory /clarify",
            action="CLARIFY",
            text=text,
            can_answer=False,
            factual_claims_allowed=False,
            required_artifacts=["clarification_packet"],
            evidence_packet=evidence_packet,
            safety_outcome="clarify_before_answer",
        )

    async def deflect(self, question: str, intent_product: dict[str, Any], delay_ms: int = 0) -> RouteProduct:
        await _sleep_ms(delay_ms)
        return RouteProduct(
            ok=True,
            route_endpoint="/memory /deflect",
            action="DEFLECT",
            text="I cannot do that from this route, but I can help with a bounded memory-backed question instead.",
            can_answer=False,
            factual_claims_allowed=False,
            required_artifacts=["deflection_packet"],
            safety_outcome="deflected",
        )

    async def create_evidence_case(self, question: str, intent_product: dict[str, Any], recall_snapshot: dict[str, Any], delay_ms: int = 0) -> dict[str, Any]:
        await _sleep_ms(delay_ms)
        data = intent_product.get("json") or {}
        entities = data.get("extracted_entities") or []
        has_west_scope = any(str(item.get("text", "")).lower() == "west gateway" for item in entities)
        packet = {
            "ok": True,
            "route_endpoint": "create-evidence-case",
            "can_answer": False,
            "evidence_quality": "insufficient_for_factual_speech",
            "uncertainty": "asset identity and scan/exploitation evidence are not sufficiently bridged in the P0 fixture",
            "next_route": "/memory /clarify",
            "extracted_entities": entities,
            "has_west_scope": has_west_scope,
            "source_refs": (recall_snapshot or {}).get("items", []),
            "created_at_utc": utc_now(),
        }
        packet["receipt_hash"] = sha256_json(packet)
        return packet


async def _sleep_ms(delay_ms: int) -> None:
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)
    else:
        await asyncio.sleep(0)
