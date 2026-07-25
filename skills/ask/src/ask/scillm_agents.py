"""HTTP client for scillm standing agents (/v1/scillm/agents/*).

Coding and visible-subagent turns use the agents API (handoff → lease → turn → result),
not /v1/chat/completions. /ask orchestrates; scillm owns the Codex app-server worker.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

import httpx

from .env import load_dotenv_once
from .ask_config import SCILLM_API_KEY, SCILLM_BASE_URL

load_dotenv_once()

AGENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CODING_INTENT_RE = re.compile(
    r"\b(implement|fix|patch|refactor|write code|add feature|change code|modify code|bugfix|repair code)\b",
    re.IGNORECASE,
)
DEFAULT_CODING_SANDBOX = "workspace-write"
DEFAULT_CODING_PHASE_ID = "ask-dag-implement"
DEFAULT_VISIBLE_PHASE_ID = "ask-visible-subagent"


class ScillmAgentsError(RuntimeError):
    """Raised when scillm agents preflight or delivery fails."""


def default_coding_worker_id(*, persona: str | None = None) -> str:
    configured = os.environ.get("ASK_AGENT_WORKER_ID", "").strip()
    if configured:
        validate_agent_identifier("worker_id", configured, "environment")
        return configured
    if persona:
        cleaned = re.sub(r"[^a-z0-9_-]+", "-", persona.strip().lower()).strip("-")
        if cleaned:
            validate_agent_identifier("worker_id", cleaned, "persona")
            return cleaned
    return "implementation"


def validate_agent_identifier(name: str, value: str, source: str, *, id_prefix: str = "agent") -> None:
    if not AGENT_ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{id_prefix} {name} from {source} must be a safe identifier")


def resolve_agent_ids(
    *,
    operation: str,
    handoff_id: str = "",
    lease_id: str = "",
    ask_id: str = "",
    handoff_env: str = "ASK_AGENT_HANDOFF_ID",
    lease_env: str = "ASK_AGENT_LEASE_ID",
    id_prefix: str = "agent",
) -> tuple[str, str, str, str]:
    """Resolve handoff/lease ids for launch or steer."""
    route_handoff = handoff_id.strip()
    route_lease = lease_id.strip()
    env_handoff = os.environ.get(handoff_env, "").strip()
    env_lease = os.environ.get(lease_env, "").strip()
    for name, route_value, env_value in (
        ("handoff_id", route_handoff, env_handoff),
        ("lease_id", route_lease, env_lease),
    ):
        for source, value in (("route", route_value), ("environment", env_value)):
            if value:
                validate_agent_identifier(name, value, source, id_prefix=id_prefix)
        if route_value and env_value and route_value != env_value:
            raise ValueError(f"{id_prefix} {name} route/env conflict")
    resolved_handoff = route_handoff or env_handoff
    resolved_lease = route_lease or env_lease
    handoff_source = "route" if route_handoff else ("environment" if env_handoff else "")
    lease_source = "route" if route_lease else ("environment" if env_lease else "")

    if operation == "steer":
        if not resolved_handoff or not resolved_lease:
            raise ValueError(f"{id_prefix} steer requires an active handoff_id and lease_id")
        if handoff_source and lease_source and handoff_source != lease_source:
            raise ValueError(f"{id_prefix} handoff_id and lease_id must come from the same source")
        return resolved_handoff, resolved_lease, handoff_source or "route", lease_source or "route"

    if not resolved_handoff:
        resolved_handoff = re.sub(r"[^A-Za-z0-9_-]+", "-", ask_id or f"ask-agent-{int(time.time())}").strip("-")
        if not resolved_handoff:
            resolved_handoff = f"ask-agent-{uuid.uuid4().hex[:12]}"
        handoff_source = "ask_id"
    else:
        validate_agent_identifier("handoff_id", resolved_handoff, handoff_source or "route", id_prefix=id_prefix)
    if not resolved_lease:
        resolved_lease = f"{resolved_handoff}-lease"
        lease_source = "derived"
    else:
        validate_agent_identifier("lease_id", resolved_lease, lease_source or "route", id_prefix=id_prefix)
    return resolved_handoff, resolved_lease, handoff_source, lease_source


def memory_context_from_dag_dependencies(context: dict[str, dict[str, Any]], *, limit: int = 12) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for node_id, node_result in context.items():
        for entry in node_result.get("context_items", [])[:3]:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or entry.get("problem") or node_id)[:120]
            summary = str(entry.get("solution") or entry.get("summary") or entry.get("text") or "")[:1000]
            if key or summary:
                items.append({"key": key or node_id, "summary": summary or key})
            if len(items) >= limit:
                return items
    return items


def run_agent_turn(
    *,
    worker_id: str,
    operation: str,
    goal: str,
    handoff_id: str = "",
    lease_id: str = "",
    phase_id: str = DEFAULT_CODING_PHASE_ID,
    ask_id: str = "",
    service_name: str = "ask",
    caller_skill: str = "ask",
    sandbox: str = DEFAULT_CODING_SANDBOX,
    wait_for_result: bool = True,
    result_timeout_seconds: float = 900.0,
    approval_policy: str = "never",
    memory_context: list[dict[str, str]] | None = None,
    metadata: dict[str, Any] | None = None,
    validation_expectations: list[str] | None = None,
    thread_id: str = "",
    steer_input: str = "",
    timeout: float = 900.0,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run launch (handoff → lease → turn → result) or steer on a standing worker."""
    operation = str(operation or "launch").strip().lower()
    if operation not in {"launch", "steer"}:
        raise ValueError("agent operation must be launch or steer")
    worker_id = worker_id.strip() or default_coding_worker_id()
    validate_agent_identifier("worker_id", worker_id, "request")
    handoff_id, lease_id, _, _ = resolve_agent_ids(
        operation=operation,
        handoff_id=handoff_id,
        lease_id=lease_id,
        ask_id=ask_id,
    )
    resolved_base = (base_url or SCILLM_BASE_URL).rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key or SCILLM_API_KEY}",
        "X-Caller-Skill": caller_skill,
    }
    memory_context = list(memory_context or [])
    expectations = validation_expectations or [
        "Make bounded repo changes only inside the worker worktree allowlist.",
        "Run validation before claiming completion.",
        "If blocked, ask concrete clarifying questions instead of reporting generic status.",
    ]
    with httpx.Client(
        base_url=resolved_base,
        headers=headers,
        timeout=httpx.Timeout(float(timeout), connect=10.0),
    ) as client:
        if operation == "steer":
            steer_text = steer_input.strip() or goal.strip()
            if not steer_text:
                raise ValueError("agent steer requires input_text or goal")
            response = client.post(
                f"/v1/scillm/agents/{worker_id}/steer",
                json={
                    "handoff_id": handoff_id,
                    "lease_id": lease_id,
                    "input_text": steer_text,
                    "actor": "human",
                    "mentioned_skills": (metadata or {}).get("mentioned_skills", []),
                },
            )
            response.raise_for_status()
            delivery = dict(response.json())
        else:
            handoff_response = client.post(
                f"/v1/scillm/agents/{worker_id}/handoffs",
                json={
                    "handoff_id": handoff_id,
                    "phase_id": phase_id,
                    "goal": goal,
                    "memory_context": memory_context,
                    "validation_expectations": expectations,
                    "metadata": metadata or {},
                },
            )
            handoff_response.raise_for_status()
            lease_response = client.post(
                f"/v1/scillm/agents/{worker_id}/leases",
                json={"handoff_id": handoff_id, "lease_id": lease_id, "owner": service_name},
            )
            lease_response.raise_for_status()
            turn_body: dict[str, Any] = {
                "handoff_id": handoff_id,
                "lease_id": lease_id,
                "service_name": service_name,
                "wait_for_result": wait_for_result,
                "result_timeout_seconds": max(5.0, min(float(result_timeout_seconds), float(timeout))),
                "sandbox": sandbox,
                "approval_policy": approval_policy,
            }
            if thread_id.strip():
                turn_body["thread_id"] = thread_id.strip()
            turn_response = client.post(
                f"/v1/scillm/agents/{worker_id}/turn",
                json=turn_body,
            )
            turn_response.raise_for_status()
            delivery = dict(turn_response.json())
            result_response = client.get(
                f"/v1/scillm/agents/{worker_id}/result",
                params={"handoff_id": handoff_id},
            )
            if result_response.status_code == 200:
                result_payload = result_response.json()
                delivery.setdefault("result", result_payload)
                final_text = str(result_payload.get("final_text") or "").strip()
                if final_text:
                    delivery["final_text"] = final_text
                if result_payload.get("event_log"):
                    delivery.setdefault("event_log", result_payload.get("event_log"))
                if result_payload.get("result_path"):
                    delivery.setdefault("result_path", result_payload.get("result_path"))
        delivery.setdefault("worker_id", worker_id)
        delivery.setdefault("handoff_id", handoff_id)
        delivery.setdefault("lease_id", lease_id)
        delivery.setdefault("transport", delivery.get("transport") or "scillm_codex_app_server")
        delivery.setdefault("operation", operation)
        if operation == "launch" and wait_for_result and not str(delivery.get("final_text") or "").strip():
            state = delivery.get("result_state") or delivery.get("state") or "unknown"
            raise ScillmAgentsError(
                f"agent turn did not produce final_text; worker_id={worker_id} handoff_id={handoff_id} state={state}"
            )
        return delivery


def run_visible_subagent_turn(
    *,
    question: str,
    route: dict[str, Any],
    memory_items: list[dict[str, Any]],
    mentioned_skills: list[str],
    ask_id: str = "",
    timeout: float = 900.0,
) -> dict[str, Any]:
    """Launch or steer a visible collaborator through the agents API."""
    operation = str(route.get("operation") or "launch")
    worker_id = os.environ.get("ASK_VISIBLE_SUBAGENT_WORKER_ID", "").strip()
    if not worker_id:
        persona = str(route.get("persona") or "nico").strip().lower()
        worker_id = re.sub(r"[^a-z0-9_-]+", "-", persona).strip("-") or "nico"
    try:
        validate_agent_identifier("worker_id", worker_id, "environment" if os.environ.get("ASK_VISIBLE_SUBAGENT_WORKER_ID", "").strip() else "route")
    except ValueError as exc:
        source = "environment" if os.environ.get("ASK_VISIBLE_SUBAGENT_WORKER_ID", "").strip() else "route"
        raise ValueError(f"visible_subagent worker_id from {source} must be a safe identifier") from exc
    handoff_id, lease_id, _, _ = resolve_agent_ids(
        operation=operation,
        handoff_id=str(route.get("handoff_id") or ""),
        lease_id=str(route.get("lease_id") or ""),
        ask_id=ask_id,
        handoff_env="ASK_VISIBLE_SUBAGENT_HANDOFF_ID",
        lease_env="ASK_VISIBLE_SUBAGENT_LEASE_ID",
        id_prefix="visible_subagent",
    )
    memory_context: list[dict[str, str]] = []
    for item in memory_items[:8]:
        key = str(item.get("key") or item.get("_key") or item.get("id") or item.get("problem") or "")[:120]
        summary = str(item.get("summary") or item.get("solution") or item.get("text") or item.get("problem") or "")[:1000]
        if key or summary:
            memory_context.append({"key": key or f"memory-{len(memory_context) + 1}", "summary": summary or key})
    prompt_payload = {
        "persona": route.get("persona", "Nico"),
        "question": question,
        "turn_type": route.get("turn_type", "advisory"),
        "operation": operation,
        "mentioned_skills": mentioned_skills,
        "memory_first": bool(route.get("memory_first", True)),
        "memory_context": memory_context,
        "original_utterance": route.get("original_utterance", ""),
        "ask_id": ask_id,
    }
    if operation == "steer":
        return run_agent_turn(
            worker_id=worker_id,
            operation="steer",
            goal=question,
            handoff_id=handoff_id,
            lease_id=lease_id,
            phase_id=DEFAULT_VISIBLE_PHASE_ID,
            ask_id=ask_id,
            service_name="ask-visible-subagent",
            steer_input=question,
            sandbox="read-only",
            wait_for_result=True,
            result_timeout_seconds=max(5.0, min(float(timeout), 120.0)),
            memory_context=memory_context,
            metadata={**prompt_payload, "visible_subagent": route},
            timeout=timeout,
        )
    goal = (
        f"{route.get('persona', 'Nico')} visible collaborator turn.\n\n"
        f"Question from project agent/human:\n{question}"
    )
    delivery = run_agent_turn(
        worker_id=worker_id,
        operation="launch",
        goal=goal,
        handoff_id=handoff_id,
        lease_id=lease_id,
        phase_id=DEFAULT_VISIBLE_PHASE_ID,
        ask_id=ask_id,
        service_name="ask-visible-subagent",
        sandbox="read-only",
        wait_for_result=True,
        result_timeout_seconds=max(5.0, min(float(timeout), 120.0)),
        memory_context=memory_context,
        metadata={**prompt_payload, "visible_subagent": route},
        validation_expectations=[
            "Return an actual visible collaborator response suitable for the project-agent terminal.",
            "If blocked, ask concrete clarifying questions instead of reporting generic status.",
        ],
        timeout=timeout,
    )
    delivery.setdefault("persona", route.get("persona", "Nico"))
    return delivery
