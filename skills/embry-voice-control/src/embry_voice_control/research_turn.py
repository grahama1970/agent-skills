"""Research turn sanity runner for Embry voice control.

This runner proves the narrow route:

    memory /intent RESEARCH -> brave-search -> Embry live-turn -> Chatterbox

It does not use browser mic, UI input, mocked search results, or typed Chat UX
state as proof. The typed query is only the controlled test stimulus.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import httpx

from embry_voice_control.listener_turn import DEFAULT_BASE_URL
from embry_voice_control.listener_turn import DEFAULT_OUTPUT_ROOT
from embry_voice_control.listener_turn import compact_value
from embry_voice_control.listener_turn import nested_value
from embry_voice_control.listener_turn import normalize_url
from embry_voice_control.listener_turn import write_json


DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_QUERY = "Search the web for the latest Chatterbox TTS release notes"


def now_iso() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    """Return a stable run id for receipt directories."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-research-turn-" + uuid4().hex[:8]


def normalize_text(text: str) -> str:
    """Normalize text for deterministic matching."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def action_from(value: Any) -> str:
    """Extract a memory action from a response object."""
    if not isinstance(value, dict):
        return ""
    for key in ("action", "intent", "route", "decision"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip().upper()
    return ""


def tool_names_from(value: Any) -> list[str]:
    """Extract tool or skill names from a memory intent response."""
    if not isinstance(value, dict):
        return []
    names: list[str] = []
    for key in ("tool_calls", "toolCalls"):
        calls = value.get(key)
        if not isinstance(calls, list):
            continue
        for call in calls:
            if isinstance(call, str):
                names.append(call)
            elif isinstance(call, dict):
                for field in ("name", "skill", "tool", "id"):
                    item = call.get(field)
                    if isinstance(item, str) and item.strip():
                        names.append(item.strip())
                        break
    for key in ("recommended_skills", "recommendedSkills", "skill_chain", "skillChain", "allowed_tools", "allowedTools"):
        items = value.get(key)
        if isinstance(items, list):
            names.extend(item.strip() for item in items if isinstance(item, str) and item.strip())
    return sorted(set(names))


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int | None, dict[str, Any], str | None]:
    """POST JSON and return status, JSON object, and error."""
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            response = client.post(url, json=payload)
            try:
                body = response.json()
            except ValueError as exc:
                body = {"_parse_error": str(exc), "_text_prefix": response.text[:500]}
            return response.status_code, body if isinstance(body, dict) else {"_json_value": body}, None
    except httpx.HTTPError as exc:
        return None, {}, str(exc)


def build_live_turn_payload(run_id: str, query: str) -> dict[str, Any]:
    """Build a controlled Embry research turn payload."""
    return {
        "sessionId": f"embry-research-turn-{run_id}",
        "turnId": f"embry-research-turn-{run_id}",
        "text": query,
        "inputMode": "text",
        "voiceEnabled": True,
        "chatEnabled": True,
        "replayEnabled": True,
        "requireMemoryIntentVoicePolicy": True,
        "requireInterruptPolicy": True,
    }


def evaluate_acceptance(
    *,
    intent_status_code: int | None,
    intent: dict[str, Any],
    intent_error: str | None,
    live_status_code: int | None,
    live_response: dict[str, Any],
    live_error: str | None,
) -> dict[str, Any]:
    """Return deterministic acceptance checks for the research route."""
    intent_tools = tool_names_from(intent)
    response_intent = nested_value(live_response, "memory.intent") or nested_value(live_response, "turnAuthority.memoryTrace.intent")
    response_action = action_from(response_intent)
    brave = nested_value(live_response, "research.brave_search") or nested_value(live_response, "memory.research")
    brave_status = brave.get("status") if isinstance(brave, dict) else None
    brave_results = brave.get("results") if isinstance(brave, dict) else None
    answer_text = str(live_response.get("answerText") or nested_value(live_response, "turnAuthority.assistantText") or "")
    normalized_answer = normalize_text(answer_text)
    audio_path = live_response.get("audioPath") or nested_value(live_response, "audioAuthority.path")
    receipt_path = live_response.get("receiptPath") or nested_value(live_response, "turnAuthority.receiptPath")
    checks = {
        "memory_intent_http_2xx": intent_status_code is not None and 200 <= intent_status_code < 300,
        "memory_intent_action_research": action_from(intent) == "RESEARCH",
        "memory_intent_recommends_brave_search": "brave-search" in intent_tools,
        "live_turn_http_2xx": live_status_code is not None and 200 <= live_status_code < 300,
        "live_turn_status_ok": live_response.get("status") == "ok",
        "live_turn_not_mocked": live_response.get("mocked") is False,
        "live_turn_live": live_response.get("live") is True,
        "live_turn_memory_intent_research": response_action == "RESEARCH",
        "brave_search_called": isinstance(brave, dict) and brave.get("called") is True,
        "brave_search_live": isinstance(brave, dict) and brave.get("live") is True and brave.get("mocked") is False,
        "brave_search_status_ok": brave_status == "ok",
        "brave_search_results_seen": isinstance(brave_results, list) and len(brave_results) > 0,
        "answer_uses_research": "searched current web results" in normalized_answer or "source" in normalized_answer,
        "audio_authority_returned": bool(live_response.get("audioAuthority") or nested_value(live_response, "turnAuthority.audioAuthority")),
        "audio_path_returned": isinstance(audio_path, str) and bool(audio_path),
        "receipt_path_returned": isinstance(receipt_path, str) and bool(receipt_path),
    }
    return {
        "pass": all(checks.values()) and intent_error is None and live_error is None,
        "checks": checks,
        "intent_tools": intent_tools,
        "response_action": response_action,
        "brave_search": compact_value(brave),
        "answer_text": answer_text,
        "audio_path": audio_path,
        "receipt_path": receipt_path,
        "errors": {
            "intent": intent_error,
            "live_turn": live_error,
        },
    }


def run_research_turn_live(
    *,
    base_url: str = DEFAULT_BASE_URL,
    memory_url: str = DEFAULT_MEMORY_URL,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    query: str = DEFAULT_QUERY,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run memory intent research -> Embry live-turn -> Brave/Chatterbox proof."""
    run_id = new_run_id()
    output_dir = output_root / "research-turn-live" / run_id
    receipt_path = output_dir / "receipt.json"
    intent_payload = {
        "q": query,
        "query": query,
        "scope": "embry_voice",
        "session_id": f"embry-research-turn-{run_id}",
        "channel": "voice-chat",
        "fast": True,
    }
    intent_status_code, intent, intent_error = post_json(
        normalize_url(memory_url, "intent"),
        intent_payload,
        timeout=min(timeout, 30.0),
    )
    live_payload = build_live_turn_payload(run_id, query)
    live_status_code, live_response, live_error = post_json(
        normalize_url(base_url, "live-turn"),
        live_payload,
        timeout=timeout,
    )
    acceptance = evaluate_acceptance(
        intent_status_code=intent_status_code,
        intent=intent,
        intent_error=intent_error,
        live_status_code=live_status_code,
        live_response=live_response,
        live_error=live_error,
    )
    receipt = {
        "schema": "embry_voice_control.research_turn_live_receipt.v1",
        "run_id": run_id,
        "created_at": now_iso(),
        "mocked": False,
        "live": True,
        "used_ui": False,
        "used_browser_mic": False,
        "used_mock_transcript": False,
        "used_typed_prompt_as_transcript": False,
        "query": query,
        "memory_url": memory_url,
        "base_url": base_url,
        "intent_request": intent_payload,
        "intent_status_code": intent_status_code,
        "intent_response": compact_value(intent),
        "live_turn_request": live_payload,
        "live_turn_status_code": live_status_code,
        "live_turn_response": compact_value(live_response),
        "acceptance": acceptance,
        "receipt_path": str(receipt_path),
        "claims": {
            "proves": [
                "Memory /intent classified the controlled non-compliance query as RESEARCH with brave-search.",
                "The configured Embry live-turn endpoint consumed that route and invoked live brave-search.",
                "If acceptance.pass is true, the same live turn returned Chatterbox audio authority.",
            ],
            "does_not_prove": [
                "Browser microphone or WebRTC capture.",
                "RealtimeSTT listener input.",
                "Speaker identity or diarization.",
                "Shared Chat UX rendering.",
                "Orb sync.",
                "Replay.",
                "Interruption or barge-in.",
            ],
        },
    }
    write_json(receipt_path, receipt)
    write_json(
        output_root / "research-turn-live" / "latest.json",
        {
            "run_id": run_id,
            "pass": acceptance["pass"],
            "receipt_path": str(receipt_path),
            "query": query,
            "answer_text": acceptance["answer_text"],
            "brave_search": acceptance["brave_search"],
        },
    )
    return receipt
