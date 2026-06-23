"""Memory/Brave route helpers for the PersonaPlex wrapper."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

TimedPost = Callable[..., Awaitable[dict[str, Any]]]


def intent_requires_evidence_case(intent: dict[str, Any]) -> bool:
    data = intent.get("json") or {}
    action = str(data.get("action") or "").upper()
    profile = str(data.get("recall_profile") or "").lower()
    artifacts = [str(item).lower() for item in (data.get("required_artifacts") or [])]
    if action == "COMPLIANCE" or "evidence_case" in artifacts or "qra" in artifacts:
        return True
    return "qra" in profile or "sparta" in profile or "compliance" in profile or bool(data.get("frameworks"))


async def memory_route_product_with_sources(
    question: str,
    intent: dict[str, Any],
    recall: dict[str, Any] | None,
    brave: dict[str, Any] | None,
    timed_post: TimedPost,
) -> dict[str, Any]:
    data = intent.get("json") or {}
    action = str(data.get("action") or "").upper()
    scope = str(data.get("scope") or "persona_memory")
    if action == "CLARIFY":
        result = await timed_post("/clarify", {"q": question, "scope": scope, "k": 4})
        result["route_endpoint"] = "/clarify"
    elif action in {"NO_MATCH", "OFF_TOPIC", "UNSAFE", "DEFLECT"}:
        result = await timed_post("/deflect", {"q": question, "persona_id": "embry", "intent_action": action})
        result["route_endpoint"] = "/deflect"
    else:
        answer_args = next((c.get("arguments") or {} for c in data.get("tool_calls") or [] if c.get("endpoint") == "/answer"), {})
        persona_id = answer_args.get("persona_id") or (data.get("query_plan") or {}).get("extracted_entities", [None])[0] or "embry"
        brave_json = (brave or {}).get("json") or {}
        payload = {
            "q": question,
            "scope": answer_args.get("scope") or scope,
            "persona_id": "embry" if str(persona_id).lower() == "embry" else persona_id,
            "source_packets": answer_args.get("source_packets") or ["current_facts", "persona_memory"],
            "external_sources": [{"skill": "brave-search", "domain": "current_facts_research",
                                  "query": brave_json.get("query"), "results": brave_json}] if brave_json else [],
            "recall_snapshot": (recall or {}).get("json") or {},
            "current_facts": brave_json,
            "persona_memory": (recall or {}).get("json") or {},
        }
        result = await timed_post("/answer", payload, timeout=20.0)
        result["route_endpoint"] = "/answer"
    return result


def planned_recall_payload(intent: dict[str, Any]) -> dict[str, Any]:
    data = intent.get("json") or {}
    for call in data.get("tool_calls") or []:
        if call.get("endpoint") == "/recall":
            args = dict(call.get("arguments") or {})
            args.setdefault("k", 12)
            args.setdefault("collections", ["persona_memory"])
            args.setdefault("tags", ["persona:embry"])
            return args
    return {"q": "What persona memories explain how Embry would respond to this question?",
            "k": 12, "collections": ["persona_memory"], "tags": ["persona:embry"]}


def planned_brave_query(intent: dict[str, Any], fallback_query: str) -> str:
    data = intent.get("json") or {}
    for call in data.get("tool_calls") or []:
        if call.get("skill") == "brave-search" and (call.get("arguments") or {}).get("query"):
            return str((call.get("arguments") or {})["query"])
    return fallback_query


async def evidence_case_gate_product(question: str, intent: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0)
    return {
        "ok": False,
        "route_endpoint": "create-evidence-case",
        "requires_evidence_case": True,
        "question": question,
        "intent_action": (intent.get("json") or {}).get("action"),
        "message": "This turn requires an evidence-case branch before any substantive answer may be spoken.",
    }
