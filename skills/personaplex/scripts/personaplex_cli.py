"""PersonaPlex bridge CLI.

Purpose:
    Convert Orpheus-TTS persona reference packs into PersonaPlex-native voice
    prompt artifacts and bidirectional offline conversation receipts.

Inputs:
    An Orpheus reference-pack JSON with clean reference WAVs, a PersonaPlex
    checkout, and a real human-input WAV for offline bidirectional evaluation.

Outputs:
    PersonaPlex-native `.pt` files, output conversation WAV/text files,
    `personaplex-publish-receipt.json`, and an HTML review page.

Failure modes:
    Fails closed when reference WAVs are missing, PersonaPlex runtime files are
    absent, model execution fails, or generated `.pt` files do not contain the
    native `embeddings` and `cache` keys expected by PersonaPlex.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import os
import re
import shutil
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

app = typer.Typer(no_args_is_help=True)
load_dotenv()

DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/personaplex/outputs")
REQUIRED_PT_KEYS = {"embeddings", "cache"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
MAX_PT_BYTES = 512 * 1024 * 1024
MEMORY_BASE_URL = "http://127.0.0.1:8601"
SCILLM_CHAT_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_DEV_TOKEN = "sk-dev-proxy-123"
SKILLS_ROOT = Path(__file__).resolve().parents[2]
BRAVE_SEARCH_PY = SKILLS_ROOT / "brave-search" / "brave_search.py"
EXTRACT_ENTITIES_RUN = SKILLS_ROOT / "extract-entities" / "run.sh"


class Reference(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    register_name: str = Field(alias="register", min_length=1)
    wav: str = Field(min_length=1)
    text_prompt: str | None = None
    source_receipt: str | None = None
    source_receipt_sha256: str | None = None
    wav_sha256: str | None = None
    source_status: str | None = None
    verified: bool | None = None
    review_status: str | None = None
    duration_s: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    transcript: str | None = None

    @property
    def register(self) -> str:
        return self.register_name

    @field_validator("register_name")
    @classmethod
    def validate_register_slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("register must be a lowercase slug, not a path")
        return value


class ReferencePack(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_name: str = Field(alias="schema")
    persona: str = Field(min_length=1)
    source: str | None = None
    orpheus_checkpoint: str | None = None
    upstream_receipts: list[str] = Field(default_factory=list)
    references: list[Reference]

    @property
    def schema(self) -> str:
        return self.schema_name

    @field_validator("persona")
    @classmethod
    def validate_persona_slug(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError("persona must be a lowercase slug, not a path")
        return value

    @model_validator(mode="after")
    def validate_unique_registers(self) -> "ReferencePack":
        registers = [ref.register for ref in self.references]
        if len(registers) != len(set(registers)):
            raise ValueError("reference registers must be unique")
        return self


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_pack(path: Path, *, allow_empty: bool = False) -> ReferencePack:
    if not path.exists():
        raise typer.BadParameter(f"reference pack not found: {path}")
    try:
        pack = ReferencePack.model_validate_json(path.read_text())
    except Exception as exc:
        raise typer.BadParameter(f"invalid reference pack JSON: {exc}") from exc
    if pack.schema != "orpheus.personaplex_reference_pack.v1":
        raise typer.BadParameter(
            "reference pack schema must be "
            "orpheus.personaplex_reference_pack.v1"
        )
    if not allow_empty and not pack.references:
        raise typer.BadParameter("reference pack contains no references")
    return pack


def validate_reference_files(pack: ReferencePack) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in pack.references:
        wav = Path(ref.wav)
        rows.append(
            {
                "register": ref.register,
                "wav": str(wav),
                "exists": wav.exists(),
                "size_bytes": wav.stat().st_size if wav.exists() else 0,
            }
        )
    return rows


def resolve_orpheus_path(path_text: str, checkpoint_root: Path) -> Path:
    path = Path(path_text)
    if path.exists():
        return path
    if path.is_absolute() and len(path.parts) > 2 and path.parts[1] == "checkpoints":
        mapped = checkpoint_root.joinpath(*path.parts[2:])
        if mapped.exists():
            return mapped
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = path.with_suffix(path.suffix + ".tmp")
    temporary_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary_output, path)


def timed_post_json(
    client: httpx.Client,
    endpoint: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST JSON and capture a receipt-safe response envelope."""
    started = time.monotonic()
    try:
        response = client.post(endpoint, json=payload)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        content_type = response.headers.get("content-type", "")
        parsed: Any | None = None
        text_excerpt: str | None = None
        if "application/json" in content_type:
            try:
                parsed = response.json()
            except ValueError as exc:
                text_excerpt = f"invalid json response: {exc}; {response.text[:1000]}"
        else:
            text_excerpt = response.text[:1000]
        return {
            "ok": response.is_success,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "request": payload,
            "json": parsed,
            "text_excerpt": text_excerpt,
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "request": payload,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_extract_entities(transcript: str) -> dict[str, Any]:
    """Run the existing extract-entities skill as a subprocess."""
    started = time.monotonic()
    if not EXTRACT_ENTITIES_RUN.exists():
        return {
            "ok": False,
            "elapsed_ms": 0,
            "error": f"extract-entities runner not found: {EXTRACT_ENTITIES_RUN}",
        }
    try:
        completed = subprocess.run(
            [
                "bash",
                str(EXTRACT_ENTITIES_RUN),
                "extract",
                "--json",
                transcript,
            ],
            cwd=EXTRACT_ENTITIES_RUN.parent,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "requested_model": model,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "stderr_excerpt": completed.stderr[-2000:] if completed.stderr else "",
    }
    try:
        result["json"] = json.loads(completed.stdout)
    except ValueError:
        result["ok"] = False
        result["stdout_excerpt"] = completed.stdout[:2000]
        result["error"] = "extract-entities did not return JSON"
    return result


def run_brave_web_search(query: str, *, count: int) -> dict[str, Any]:
    """Run Brave Search through the existing skill module."""
    started = time.monotonic()
    if not BRAVE_SEARCH_PY.exists():
        return {
            "ok": False,
            "elapsed_ms": 0,
            "query": query,
            "error": f"brave_search.py not found: {BRAVE_SEARCH_PY}",
        }
    try:
        spec = importlib.util.spec_from_file_location("personaplex_brave_search", BRAVE_SEARCH_PY)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load brave_search.py module spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = module.web_search(query, count=count)
        return {
            "ok": True,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "query": query,
            "result_count": len(data.get("results", [])),
            "json": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "query": query,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def should_run_brave_from_intent(intent: dict[str, Any]) -> bool:
    action = str(intent.get("action") or "").upper()
    domains = intent.get("question_domains") or []
    response_mode = str(intent.get("response_mode") or "")
    if action == "RESEARCH":
        return True
    if isinstance(domains, list) and "current_facts_research" in domains:
        return True
    return "research" in response_mode


def skipped_brave_search(query: str, reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "elapsed_ms": 0,
        "query": query,
        "result_count": 0,
        "json": {
            "query": query,
            "results": [],
            "skipped": True,
            "reason": reason,
        },
    }


def compact_memory_items(data: dict[str, Any] | None, *, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows: list[dict[str, Any]] = []
    for item in data.get("items", [])[:limit]:
        rows.append(
            {
                "_key": item.get("_key"),
                "persona_id": item.get("persona_id"),
                "tags": item.get("tags"),
                "scores": item.get("scores"),
                "retrieval_text": str(item.get("retrieval_text") or item.get("text") or item.get("problem") or "")[:700],
            }
        )
    return rows


def truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def build_planner_digest(injection_packet: dict[str, Any]) -> dict[str, Any]:
    """Build the small evidence digest sent to SciLLM.

    The full PersonaPlex injection packet is intentionally richer than the
    planner needs and can be tens of KB. Sending that whole packet through an
    OpenCode-backed one-shot model made the planner step take ~55s. This digest
    preserves the decision-relevant facts while keeping the model call small.
    """
    facts = injection_packet.get("facts_for_next_answer_only")
    facts = facts if isinstance(facts, dict) else {}
    memory_items = facts.get("persona_memory_items") or []
    brave_sources = facts.get("brave_sources") or []
    clarify = facts.get("clarify_product") if isinstance(facts.get("clarify_product"), dict) else {}
    deflect = facts.get("deflect_product") if isinstance(facts.get("deflect_product"), dict) else {}
    return {
        "persona": injection_packet.get("persona"),
        "mode": injection_packet.get("mode"),
        "user_latest_turn": facts.get("user_latest_turn"),
        "intent": {
            "action": facts.get("memory_intent_action"),
            "confidence": facts.get("memory_intent_confidence"),
            "question_kind": (facts.get("memory_intent_raw") or {}).get("question_kind")
            if isinstance(facts.get("memory_intent_raw"), dict)
            else None,
            "question_domains": (facts.get("memory_intent_raw") or {}).get("question_domains")
            if isinstance(facts.get("memory_intent_raw"), dict)
            else None,
            "response_mode": (facts.get("memory_intent_raw") or {}).get("response_mode")
            if isinstance(facts.get("memory_intent_raw"), dict)
            else None,
        },
        "clarify": {
            "needs_clarification": clarify.get("needs_clarification"),
            "final_response_origin": clarify.get("final_response_origin"),
        },
        "deflect": {
            "should_deflect": deflect.get("should_deflect"),
            "deflection_type": deflect.get("deflection_type"),
        },
        "memory_answer": truncate_text(facts.get("memory_answer"), 500),
        "persona_memory": [
            {
                "_key": row.get("_key"),
                "persona_id": row.get("persona_id"),
                "retrieval_text": truncate_text(row.get("retrieval_text"), 260),
            }
            for row in memory_items[:3]
            if isinstance(row, dict)
        ],
        "brave_sources": [
            {
                "title": truncate_text(row.get("title"), 120),
                "description": truncate_text(row.get("description"), 220),
                "url": row.get("url"),
            }
            for row in brave_sources[:3]
            if isinstance(row, dict)
        ],
        "constraints": {
            "allowed_filler_before_research": injection_packet.get("allowed_filler_before_research"),
            "must_not_say": injection_packet.get("not_allowed_before_research"),
        },
    }


def normalize_intent_for_persona_turn(
    *,
    intent: dict[str, Any],
    transcript: str,
    persona: str,
    scope: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Preserve memory's raw route while correcting wrapper-obvious persona turns.

    This wrapper is intentionally not the owner of memory's classifier. It does,
    however, know when a turn is being used as a PersonaPlex persona conversation
    gate. If memory returns a SPARTA/compliance route because words like
    "weather" or "surfing" match security taxonomy, the wrapper records that as a
    route anomaly and keeps the PersonaPlex flow on QUERY so the response planner
    can combine persona recall and web evidence instead of treating it as a
    security evidence case.
    """
    raw = dict(intent.get("json") or {}) if isinstance(intent.get("json"), dict) else {}
    normalized = dict(raw)
    anomalies: list[dict[str, Any]] = []
    action = str(raw.get("action") or "").upper()
    classifier_source = str(raw.get("classifier_source") or "")
    lower_text = transcript.lower()
    persona_markers = {
        persona.lower(),
        "persona",
        "personaplex",
        "embry",
        "horus",
        "kai",
    }
    conversational_markers = {
        "feel",
        "weather",
        "surf",
        "hawaii",
        "today",
        "respond",
        "answer",
    }
    is_persona_surface = scope in {"personaplex", "persona", "persona_memory"}
    has_persona_signal = any(marker in lower_text for marker in persona_markers)
    has_conversation_signal = any(marker in lower_text for marker in conversational_markers)
    if (
        is_persona_surface
        and action == "COMPLIANCE"
        and has_persona_signal
        and has_conversation_signal
    ):
        normalized["action"] = "QUERY"
        normalized["classifier_source"] = f"{classifier_source}|personaplex_wrapper_normalized"
        normalized["recall_profile"] = "persona_memory_recall"
        normalized["recall_profile_source"] = "personaplex_wrapper"
        anomalies.append(
            {
                "type": "memory_intent_persona_turn_misrouted_as_compliance",
                "raw_action": raw.get("action"),
                "raw_classifier_source": raw.get("classifier_source"),
                "normalized_action": "QUERY",
                "reason": (
                    "PersonaPlex persona/weather/surfing turn was routed into "
                    "security compliance taxonomy; wrapper kept raw result but "
                    "uses persona QUERY for downstream planning."
                ),
            }
        )
    return normalized, anomalies


def build_personaplex_injection_packet(
    *,
    persona: str,
    transcript: str,
    memory_intent: dict[str, Any],
    normalized_intent: dict[str, Any],
    route_anomalies: list[dict[str, Any]],
    entity_context: dict[str, Any],
    persona_recall: dict[str, Any],
    clarify: dict[str, Any],
    deflect: dict[str, Any],
    answer: dict[str, Any],
    brave: dict[str, Any],
    scillm_planner: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the compact context packet intended for PersonaPlex conditioning."""
    intent_json = memory_intent.get("json") if isinstance(memory_intent, dict) else {}
    intent_action = normalized_intent.get("action") if isinstance(normalized_intent, dict) else None
    recall_json = persona_recall.get("json") if isinstance(persona_recall, dict) else {}
    answer_json = answer.get("json") if isinstance(answer, dict) else {}
    brave_json = brave.get("json") if isinstance(brave, dict) else {}
    brave_results = brave_json.get("results", []) if isinstance(brave_json, dict) else []
    grounded_answer = None
    if isinstance(answer_json, dict):
        grounded_answer = answer_json.get("final_response") or answer_json.get("source_answer")
    facts = {
        "user_latest_turn": transcript,
        "memory_intent_raw": intent_json if isinstance(intent_json, dict) else {},
        "memory_intent_action": intent_action,
        "memory_intent_confidence": intent_json.get("confidence") if isinstance(intent_json, dict) else None,
        "route_anomalies": route_anomalies,
        "entity_context": {
            "control_ids": entity_context.get("control_ids"),
            "phrases": entity_context.get("phrases"),
            "unresolved_terms": entity_context.get("unresolved_terms"),
            "proof_packet": entity_context.get("proof_packet"),
        } if isinstance(entity_context, dict) else {},
        "persona_memory_items": compact_memory_items(recall_json, limit=5),
        "memory_answer": grounded_answer,
        "clarify_product": clarify.get("json") if isinstance(clarify, dict) else None,
        "deflect_product": deflect.get("json") if isinstance(deflect, dict) else None,
        "brave_sources": [
            {
                "title": row.get("title"),
                "description": row.get("description"),
                "url": row.get("url"),
            }
            for row in brave_results[:5]
        ],
    }
    return {
        "schema": "personaplex.research_injection_packet.v1",
        "persona": persona,
        "mode": "research_first_persona_conditioning",
        "allowed_filler_before_research": [
            "One moment.",
            "Let me check that.",
            "I am pulling that up.",
        ],
        "not_allowed_before_research": [
            "factual claims",
            "invented memory",
            "unsupported current facts",
            "vulnerability or weather conclusions without retrieved evidence",
        ],
        "facts_for_next_answer_only": facts,
        "persona_conditioning_text": (
            "For the next answer only, use the verified backend context below. "
            "Keep Embry's voice intimate, grounded, lightly guarded, and concise. "
            "Do not invent facts missing from memory, entity extraction, answer, or search. "
            "If facts are insufficient, say so plainly.\n\n"
            + json.dumps(facts, ensure_ascii=False, indent=2)
        ),
        "scillm_planner": scillm_planner,
    }


def summarize_response(name: str, response: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"name": name, "ok": False, "error": "missing_response"}
    data = response.get("json")
    summary: dict[str, Any] = {
        "name": name,
        "ok": response.get("ok"),
        "status_code": response.get("status_code"),
        "elapsed_ms": response.get("elapsed_ms"),
        "error": response.get("error") or response.get("error_type"),
    }
    if name == "intent" and isinstance(data, dict):
        summary.update(
            {
                "action": data.get("action"),
                "question_kind": data.get("question_kind"),
                "question_domains": data.get("question_domains"),
                "response_mode": data.get("response_mode"),
                "confidence": data.get("confidence"),
                "recall_profile": data.get("recall_profile"),
                "entity_count": len(data.get("entities") or []),
            }
        )
    elif name == "extract_entities" and isinstance(data, dict):
        summary.update(
            {
                "grounding_ok": data.get("grounding_ok"),
                "needs_clarification": (data.get("agent_decision") or {}).get("needs_clarification"),
                "suggested_action": (data.get("agent_decision") or {}).get("suggested_action"),
                "counts": data.get("counts"),
            }
        )
    elif name == "persona_recall" and isinstance(data, dict):
        summary.update(
            {
                "found": data.get("found"),
                "confidence": data.get("confidence"),
                "item_count": len(data.get("items") or []),
                "keys": [item.get("_key") for item in (data.get("items") or [])[:8]],
            }
        )
    elif name in {"clarify", "deflect", "answer"} and isinstance(data, dict):
        detail = data.get("detail") if isinstance(data.get("detail"), dict) else {}
        scillm = detail.get("scillm") if isinstance(detail.get("scillm"), dict) else {}
        summary.update(
            {
                "schema": data.get("schema"),
                "can_answer": data.get("can_answer"),
                "should_deflect": data.get("should_deflect"),
                "needs_clarification": data.get("needs_clarification"),
                "detail_code": detail.get("code"),
                "scillm_status_code": scillm.get("status_code"),
                "scillm_requested_model": scillm.get("requested_model"),
            }
        )
    elif name == "brave" and isinstance(data, dict):
        summary.update(
            {
                "query": data.get("query"),
                "result_count": len(data.get("results") or []),
                "urls": [row.get("url") for row in (data.get("results") or [])[:5]],
            }
        )
    elif name == "scillm_planner":
        summary.update(
            {
                "text_excerpt": response.get("text_excerpt"),
                "requested_model": response.get("requested_model"),
                "served_model": response.get("served_model"),
                "stream": response.get("stream"),
                "first_event_ms": response.get("first_event_ms"),
                "stream_event_count": response.get("stream_event_count"),
                "planner_recovery": response.get("planner_recovery"),
                "schema_warning": response.get("schema_warning"),
            }
        )
    return summary


def run_scillm_planner(
    injection_packet: dict[str, Any],
    *,
    model: str,
    timeout_s: float = 45.0,
) -> dict[str, Any]:
    started = time.monotonic()
    planner_digest = build_planner_digest(injection_packet)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a PersonaPlex response planner. Return compact JSON only. "
                    "Do not invent facts. Use only the supplied evidence digest. "
                    "Write Embry's answer as friendly, concise, natural speech. "
                    "Keep answer_draft to one or two short sentences."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "required_schema": {
                            "filler": "short acknowledgement allowed before research",
                            "answer_draft": "grounded next answer text or insufficiency statement",
                            "persona_context_update": "short summary to inject after controlled answer",
                            "must_not_say": ["unsupported claims"],
                            "limitations": ["missing evidence"],
                        },
                        "evidence_digest": planner_digest,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "stream": True,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0)) as client:
            with client.stream(
                "POST",
                SCILLM_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {SCILLM_DEV_TOKEN}",
                    "X-Caller-Skill": "personaplex",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                result: dict[str, Any] = {
                    "ok": response.is_success,
                    "status_code": response.status_code,
                    "requested_model": model,
                    "stream": True,
                    "planner_input_bytes": len(
                        json.dumps(planner_digest, ensure_ascii=False).encode("utf-8")
                    ),
                }
                if not response.is_success:
                    result["text_excerpt"] = response.read().decode("utf-8", errors="replace")[:2000]
                    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
                    return result

                content_parts: list[str] = []
                raw_events: list[dict[str, Any]] = []
                first_event_ms: int | None = None
                served_model: str | None = None
                for line in response.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    if first_event_ms is None:
                        first_event_ms = int((time.monotonic() - started) * 1000)
                    try:
                        event = json.loads(data)
                    except ValueError:
                        raw_events.append({"unparsed": data[:500]})
                        continue
                    if len(raw_events) < 5:
                        raw_events.append(event)
                    served_model = served_model or event.get("model")
                    choice = (event.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    if isinstance(delta, dict) and delta.get("content"):
                        content_parts.append(str(delta["content"]))
                    message = choice.get("message") or {}
                    if isinstance(message, dict) and message.get("content"):
                        content_parts.append(str(message["content"]))
                content = "".join(content_parts)
                result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
                result["first_event_ms"] = first_event_ms
                result["served_model"] = served_model
                result["stream_event_count"] = len(raw_events)
                result["raw_stream_sample"] = raw_events
                result["raw_content"] = content
                try:
                    result["json"] = json.loads(content)
                except ValueError as exc:
                    stripped = content.strip()
                    if stripped:
                        result["json"] = {
                            "filler": "Let me check that.",
                            "answer_draft": stripped,
                            "persona_context_update": stripped[:700],
                            "must_not_say": ["unsupported claims"],
                            "limitations": [
                                "planner returned non-JSON text; wrapper preserved it as answer_draft"
                            ],
                        }
                        result["planner_recovery"] = "wrapped_non_json_text"
                        result["schema_warning"] = f"planner did not return JSON: {exc}"
                    else:
                        result["ok"] = False
                        result["error"] = f"planner did not return JSON: {exc}"
        return result
    except Exception as exc:
        return {
            "ok": False,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def run_deterministic_planner(injection_packet: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    digest = build_planner_digest(injection_packet)
    persona = str(digest.get("persona") or "persona")
    turn = truncate_text(digest.get("user_latest_turn"), 240)
    brave_sources = digest.get("brave_sources") if isinstance(digest.get("brave_sources"), list) else []
    memory_items = digest.get("persona_memory") if isinstance(digest.get("persona_memory"), list) else []
    source_lines = []
    for row in brave_sources[:2]:
        if isinstance(row, dict):
            title = truncate_text(row.get("title"), 90)
            description = truncate_text(row.get("description"), 180)
            if title or description:
                source_lines.append(f"{title}: {description}".strip(": "))
    memory_line = ""
    for row in memory_items[:1]:
        if isinstance(row, dict) and row.get("retrieval_text"):
            memory_line = truncate_text(row.get("retrieval_text"), 220)
            break

    current_fact_sentence = (
        "The current surf/weather evidence I found is limited: "
        + (" ".join(source_lines) if source_lines else "no current external source summary was available.")
    )
    persona_sentence = (
        f"For {persona}, the relevant memory signal is: {memory_line}"
        if memory_line
        else f"I do not have a strong {persona} memory anchor for the emotional part."
    )
    answer_draft = (
        f"{current_fact_sentence} {persona_sentence} "
        "I would answer cautiously and avoid pretending the current conditions are more certain than the retrieved sources show."
    )
    return {
        "ok": True,
        "status_code": None,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "requested_model": None,
        "served_model": "deterministic-local",
        "planner_type": "deterministic",
        "planner_input_bytes": len(json.dumps(digest, ensure_ascii=False).encode("utf-8")),
        "json": {
            "filler": "Let me check that.",
            "answer_draft": answer_draft,
            "persona_context_update": (
                f"The user asked: {turn}. Current sources were consulted, and the answer should "
                f"blend limited surf/weather evidence with scoped {persona} memory without overclaiming."
            ),
            "must_not_say": [
                "unsupported current weather claims",
                "invented persona memory",
                "claims beyond the retrieved Brave Search snippets",
            ],
            "limitations": [
                "deterministic planner used; no LLM paraphrase on critical path",
                "Brave Search snippets discover sources but do not fetch full page contents",
            ],
        },
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_child(root: Path, *parts: str | Path) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"path escapes output root: {candidate}")
    return candidate


def tensor_report(value: Any) -> dict[str, Any]:
    import torch

    if torch.is_tensor(value):
        return {
            "type": "tensor",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "numel": int(value.numel()),
            "finite": bool(torch.isfinite(value.detach().float()).all().item())
            if value.numel()
            else False,
        }
    if isinstance(value, (list, tuple)):
        children = [tensor_report(item) for item in value[:8]]
        return {
            "type": type(value).__name__,
            "length": len(value),
            "children": children,
            "finite": all(child.get("finite", False) for child in children),
            "numel": sum(int(child.get("numel", 0)) for child in children),
        }
    if isinstance(value, dict):
        children = {str(key): tensor_report(item) for key, item in list(value.items())[:16]}
        return {
            "type": "dict",
            "keys": sorted(str(key) for key in value.keys()),
            "children": children,
            "finite": all(child.get("finite", False) for child in children.values()),
            "numel": sum(int(child.get("numel", 0)) for child in children.values()),
        }
    return {"type": type(value).__name__, "finite": False, "numel": 0}


def python_nvidia_env(python_bin: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    site_packages_candidates = sorted((python_bin.parent.parent / "lib").glob("python*/site-packages"))
    site_packages = next(
        (candidate for candidate in site_packages_candidates if (candidate / "nvidia").exists()),
        None,
    )
    bundled_nvidia_libs = [
        site_packages / "nvidia" / package / "lib"
        for package in [
            "cudnn",
            "cublas",
            "cuda_runtime",
            "cuda_nvrtc",
            "cufft",
            "curand",
            "cusolver",
            "cusparse",
            "nccl",
            "nvtx",
        ]
    ] if site_packages else []
    existing_library_path = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(path) for path in bundled_nvidia_libs if path.exists()]
        + ([existing_library_path] if existing_library_path else [])
    )
    if env.get("LD_PRELOAD") == "/usr/NX/lib/libnxegl.so":
        env.pop("LD_PRELOAD", None)
    return env


def validate_pt_schema(
    path: Path,
    *,
    python_bin: Path | None = None,
) -> tuple[bool, dict[str, Any], str | None]:
    if not path.exists():
        return False, {}, f"pt file not found: {path}"
    size = path.stat().st_size
    if size <= 0 or size > MAX_PT_BYTES:
        return False, {}, f"pt file size invalid: {size}"
    if python_bin is not None:
        validator = r'''
import hashlib
import json
import sys
from pathlib import Path

import torch

REQUIRED_PT_KEYS = {"embeddings", "cache"}

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def tensor_report(value):
    if torch.is_tensor(value):
        return {
            "type": "tensor",
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "numel": int(value.numel()),
            "finite": bool(torch.isfinite(value.detach().float()).all().item())
            if value.numel()
            else False,
        }
    if isinstance(value, (list, tuple)):
        children = [tensor_report(item) for item in value[:8]]
        return {
            "type": type(value).__name__,
            "length": len(value),
            "children": children,
            "finite": all(child.get("finite", False) for child in children),
            "numel": sum(int(child.get("numel", 0)) for child in children),
        }
    if isinstance(value, dict):
        children = {str(key): tensor_report(item) for key, item in list(value.items())[:16]}
        return {
            "type": "dict",
            "keys": sorted(str(key) for key in value.keys()),
            "children": children,
            "finite": all(child.get("finite", False) for child in children.values()),
            "numel": sum(int(child.get("numel", 0)) for child in children.values()),
        }
    return {"type": type(value).__name__, "finite": False, "numel": 0}

path = Path(sys.argv[1])
state = torch.load(path, map_location="cpu", weights_only=True)
if not isinstance(state, dict):
    raise SystemExit(json.dumps({"ok": False, "error": "pt payload is not a dict"}))
keys = sorted(str(k) for k in state.keys())
missing = REQUIRED_PT_KEYS - set(keys)
if missing:
    raise SystemExit(json.dumps({"ok": False, "report": {"keys": keys}, "error": f"missing required keys: {sorted(missing)}"}))
report = {
    "keys": keys,
    "size_bytes": path.stat().st_size,
    "sha256": sha256_file(path),
    "embeddings": tensor_report(state["embeddings"]),
    "cache": tensor_report(state["cache"]),
}
for key in REQUIRED_PT_KEYS:
    item = report[key]
    if int(item.get("numel", 0)) <= 0:
        raise SystemExit(json.dumps({"ok": False, "report": report, "error": f"{key} contains no tensor values"}))
    if not bool(item.get("finite", False)):
        raise SystemExit(json.dumps({"ok": False, "report": report, "error": f"{key} contains non-finite or unsupported tensor values"}))
print(json.dumps({"ok": True, "report": report}))
'''
        result = subprocess.run(
            [str(python_bin), "-c", validator, str(path)],
            text=True,
            capture_output=True,
            timeout=120,
            env=python_nvidia_env(python_bin),
            check=False,
        )
        try:
            payload = json.loads((result.stdout or result.stderr).strip().splitlines()[-1])
        except Exception:
            return False, {}, (
                "pt validation subprocess failed: "
                f"returncode={result.returncode} stdout={result.stdout[:1000]!r} "
                f"stderr={result.stderr[:1000]!r}"
            )
        if result.returncode != 0 or not payload.get("ok"):
            return False, payload.get("report", {}), payload.get("error", "pt validation failed")
        return True, payload["report"], None
    try:
        import torch
    except Exception as exc:  # pragma: no cover - depends on local env
        return False, {}, f"torch unavailable for pt validation: {exc}"
    try:
        state = torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        return False, {}, f"safe torch.load failed: {exc}"
    if not isinstance(state, dict):
        return False, {}, "pt payload is not a dict"
    keys = sorted(str(k) for k in state.keys())
    missing = REQUIRED_PT_KEYS - set(keys)
    if missing:
        return False, {"keys": keys}, f"missing required keys: {sorted(missing)}"
    report = {
        "keys": keys,
        "size_bytes": size,
        "sha256": sha256_file(path),
        "embeddings": tensor_report(state["embeddings"]),
        "cache": tensor_report(state["cache"]),
    }
    for key in REQUIRED_PT_KEYS:
        item = report[key]
        if int(item.get("numel", 0)) <= 0:
            return False, report, f"{key} contains no tensor values"
        if not bool(item.get("finite", False)):
            return False, report, f"{key} contains non-finite or unsupported tensor values"
    return True, report, None


def validate_wav(path: Path, *, min_duration_s: float = 0.2) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"WAV missing or empty: {path}")
    import soundfile as sf

    info = sf.info(str(path))
    sample_rate = int(info.samplerate)
    frames = int(info.frames)
    channels = int(info.channels)
    subtype = str(info.subtype)
    duration_s = frames / sample_rate if sample_rate else 0.0
    if duration_s < min_duration_s:
        raise RuntimeError(f"WAV duration too short: {duration_s:.3f}s")
    data, _ = sf.read(str(path), dtype="float32", always_2d=True)
    if data.size == 0:
        raise RuntimeError("WAV has no audio samples")
    peak = float(abs(data).max())
    rms = float((data * data).mean() ** 0.5)
    if peak < 1e-5 or rms < 1e-6:
        raise RuntimeError("WAV appears silent")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "channels": channels,
        "sample_rate": sample_rate,
        "frames": frames,
        "duration_s": duration_s,
        "subtype": subtype,
        "peak": peak,
        "rms": rms,
    }


def stage_human_input_wav(
    source_wav: Path,
    out_dir: Path,
    *,
    max_seconds: float | None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Stage a real human-input WAV, optionally cropping it for bounded E2E checks.

    The PersonaPlex offline runner emits artifacts only after processing the
    entire input WAV. For CI/smoke gates, use this to crop a real fixture instead
    of feeding a long conversation file and waiting blindly. The receipt keeps
    both original and effective input metrics so the provenance is explicit.
    """
    original_metrics = validate_wav(source_wav)
    if max_seconds is None:
        return source_wav, original_metrics, original_metrics
    if max_seconds < 0.2:
        raise typer.BadParameter("--max-human-input-seconds must be >= 0.2")
    import soundfile as sf

    data, sample_rate = sf.read(str(source_wav), dtype="float32", always_2d=True)
    max_frames = max(1, int(round(float(max_seconds) * int(sample_rate))))
    if data.shape[0] <= max_frames:
        cropped = data
    else:
        mono = data.mean(axis=1)
        hop = max(1, int(round(0.25 * int(sample_rate))))
        best_start = 0
        best_rms = -1.0
        for start in range(0, data.shape[0] - max_frames + 1, hop):
            window = mono[start : start + max_frames]
            rms = float((window * window).mean() ** 0.5)
            if rms > best_rms:
                best_rms = rms
                best_start = start
        cropped = data[best_start : best_start + max_frames]
    if cropped.size == 0:
        raise RuntimeError(f"cannot crop empty human input WAV: {source_wav}")
    staged = safe_child(out_dir, "human-input-cropped.wav")
    sf.write(str(staged), cropped, sample_rate)
    effective_metrics = validate_wav(staged)
    effective_metrics["crop_source_path"] = str(source_wav)
    effective_metrics["crop_start_s"] = (
        0.0 if data.shape[0] <= max_frames else best_start / float(sample_rate)
    )
    effective_metrics["crop_duration_s"] = effective_metrics["duration_s"]
    return staged, original_metrics, effective_metrics


def validate_text_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"output text JSON missing or empty: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise RuntimeError("output text JSON must be a token list")
    if not data:
        raise RuntimeError("output text JSON token list is empty")
    if not all(isinstance(token, str) for token in data):
        raise RuntimeError("output text JSON tokens must all be strings")
    preview = "".join(data[:200])[:1000]
    if not re.search(r"[A-Za-z0-9]", preview):
        raise RuntimeError("output text JSON contains no lexical token content")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "tokens": len(data),
        "preview": preview[:500],
    }


def personaplex_python(personaplex_root: Path, requested: Path | None = None) -> Path:
    if requested:
        if not requested.exists():
            raise FileNotFoundError(f"requested PersonaPlex python not found: {requested}")
        return requested
    for candidate in [
        personaplex_root / ".venv" / "bin" / "python",
        personaplex_root / "venv" / "bin" / "python",
    ]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "PersonaPlex python is required; expected --personaplex-python or "
        "a venv under the PersonaPlex checkout"
    )


def runtime_identity(personaplex_root: Path, python_bin: Path, out_dir: Path) -> dict[str, Any]:
    def run_capture(args: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        return {
            "command": args,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:4000],
            "stderr": result.stderr.strip()[:4000],
        }

    freeze_path = out_dir / "personaplex-python-freeze.txt"
    freeze = run_capture([str(python_bin), "-m", "pip", "freeze"])
    freeze_path.write_text(freeze["stdout"] + "\n")
    return {
        "personaplex_git_head": run_capture(["git", "rev-parse", "HEAD"], cwd=personaplex_root),
        "personaplex_git_status": run_capture(["git", "status", "--short"], cwd=personaplex_root),
        "personaplex_offline_patch_sha256": sha256_file(personaplex_root / "moshi" / "moshi" / "offline.py"),
        "python_version": run_capture([str(python_bin), "-c", "import sys; print(sys.version)"]),
        "pip_freeze": str(freeze_path),
    }


def validate_reference_provenance(
    pack: ReferencePack,
    *,
    checkpoint_root: Path,
    allow_provisional_reference: bool,
) -> list[dict[str, Any]]:
    provenance_rows: list[dict[str, Any]] = []
    for ref in pack.references:
        wav = Path(ref.wav)
        wav_metrics = validate_wav(wav)
        row: dict[str, Any] = {
            "register": ref.register,
            "wav": str(wav),
            "wav_metrics": wav_metrics,
        }
        if ref.wav_sha256 and ref.wav_sha256 != wav_metrics["sha256"]:
            raise RuntimeError(f"{ref.register}: wav_sha256 mismatch")
        for field_name, measured in [
            ("duration_s", wav_metrics["duration_s"]),
            ("sample_rate", wav_metrics["sample_rate"]),
            ("channels", wav_metrics["channels"]),
        ]:
            expected = getattr(ref, field_name)
            if expected is None:
                continue
            if field_name == "duration_s":
                if abs(float(expected) - float(measured)) > 0.02:
                    raise RuntimeError(f"{ref.register}: duration_s mismatch")
            elif int(expected) != int(measured):
                raise RuntimeError(f"{ref.register}: {field_name} mismatch")

        if not ref.source_receipt:
            if allow_provisional_reference:
                row["provenance_status"] = "PROVISIONAL_NO_SOURCE_RECEIPT"
                provenance_rows.append(row)
                continue
            raise RuntimeError(f"{ref.register}: source_receipt is required")
        source_receipt = resolve_orpheus_path(ref.source_receipt, checkpoint_root)
        if not source_receipt.exists():
            raise RuntimeError(f"{ref.register}: source_receipt not found: {source_receipt}")
        source_receipt_hash = sha256_file(source_receipt)
        if ref.source_receipt_sha256 and ref.source_receipt_sha256 != source_receipt_hash:
            raise RuntimeError(f"{ref.register}: source_receipt_sha256 mismatch")
        receipt_payload = json.loads(source_receipt.read_text())
        if receipt_payload.get("status") != "PASS":
            raise RuntimeError(f"{ref.register}: upstream Orpheus receipt is not PASS")
        source_verified = receipt_payload.get("verified") is True
        ref_verified = ref.verified is True
        human_accepted = str(ref.review_status or "").lower() in {
            "accepted",
            "human_accepted",
            "approved",
            "human_review_accepted",
        }
        if not (source_verified or ref_verified or human_accepted or allow_provisional_reference):
            raise RuntimeError(
                f"{ref.register}: reference is not verified or human accepted"
            )
        row.update(
            {
                "source_receipt": str(source_receipt),
                "source_receipt_sha256": source_receipt_hash,
                "source_status": str(receipt_payload.get("status")),
                "source_verified": source_verified,
                "reference_verified": ref_verified,
                "human_accepted": human_accepted,
                "provenance_status": "STRICT_PASS"
                if source_verified or ref_verified or human_accepted
                else "PROVISIONAL_ALLOWED",
            }
        )
        lora_dir = receipt_payload.get("lora_dir")
        if lora_dir and pack.orpheus_checkpoint:
            resolved_lora = str(resolve_orpheus_path(str(lora_dir), checkpoint_root))
            if str(Path(pack.orpheus_checkpoint)) != resolved_lora:
                raise RuntimeError(f"{ref.register}: checkpoint identity mismatch")
        provenance_rows.append(row)
    return provenance_rows


def run_personaplex_offline_cli(
    *,
    personaplex_root: Path,
    python_bin: Path,
    voice_prompt_path: Path,
    human_input_wav: Path,
    text_prompt: str,
    output_wav: Path,
    output_text: Path,
    device: str,
    seed: int,
    cpu_offload: bool,
    save_voice_embeddings: bool,
) -> dict[str, Any]:
    if not (personaplex_root / "moshi" / "moshi" / "offline.py").exists():
        raise FileNotFoundError(
            f"PersonaPlex offline module not found under: {personaplex_root}"
        )
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    output_text.parent.mkdir(parents=True, exist_ok=True)
    env = python_nvidia_env(python_bin, os.environ.copy())
    env["PYTHONPATH"] = str(personaplex_root / "moshi") + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        str(python_bin),
        "-m",
        "moshi.offline",
        "--input-wav",
        str(human_input_wav),
        "--output-wav",
        str(output_wav),
        "--output-text",
        str(output_text),
        "--text-prompt",
        text_prompt,
        "--voice-prompt",
        voice_prompt_path.name,
        "--voice-prompt-dir",
        str(voice_prompt_path.parent),
        "--device",
        device,
        "--seed",
        str(seed),
    ]
    if cpu_offload:
        command.append("--cpu-offload")
    if save_voice_embeddings:
        command.append("--save-voice-embeddings")
    result = subprocess.run(
        command,
        cwd=str(personaplex_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )
    log_dir = output_wav.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{output_wav.stem}.stdout.log").write_text(result.stdout)
    (log_dir / f"{output_wav.stem}.stderr.log").write_text(result.stderr)
    receipt = {
        "command": command,
        "cwd": str(personaplex_root),
        "python": str(python_bin),
        "returncode": result.returncode,
        "stdout_log": str(log_dir / f"{output_wav.stem}.stdout.log"),
        "stderr_log": str(log_dir / f"{output_wav.stem}.stderr.log"),
    }
    if result.returncode != 0:
        raise RuntimeError(f"PersonaPlex offline CLI failed: {receipt}")
    return receipt


def render_review_html(receipt_path: Path, out_html: Path | None = None) -> Path:
    receipt = json.loads(receipt_path.read_text())
    if out_html is None:
        out_html = receipt_path.parent / "index.html"
    rows = []
    for item in receipt.get("generated_voice_prompts", []):
        wav = item.get("replay_output_wav", "")
        text_path = item.get("replay_output_text", "")
        output_text = ""
        if text_path and Path(text_path).exists():
            output_text = Path(text_path).read_text()[:4000]
        audio_src = Path(wav).as_uri() if wav and Path(wav).exists() else ""
        rows.append(
            f"""
            <section class="card">
              <h2>{html.escape(str(item.get('register', 'unknown')))}</h2>
              <dl>
                <dt>Voice prompt WAV</dt><dd>{html.escape(str(item.get('wav', '')))}</dd>
                <dt>PersonaPlex PT</dt><dd>{html.escape(str(item.get('pt', '')))}</dd>
                <dt>PT schema</dt><dd>{html.escape(', '.join(item.get('pt_schema', {}).get('keys', [])))}</dd>
              </dl>
              <audio controls src="{html.escape(audio_src, quote=True)}"></audio>
              <pre>{html.escape(output_text)}</pre>
            </section>
            """
        )
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PersonaPlex Review - {html.escape(str(receipt.get('persona', 'unknown')))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #111; color: #eee; }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 4px; background: #173; }}
    .card {{ border: 1px solid #333; border-radius: 8px; padding: 16px; margin: 16px 0; background: #181818; }}
    dt {{ color: #8ab4f8; font-weight: 700; margin-top: 8px; }}
    dd {{ margin-left: 0; overflow-wrap: anywhere; color: #ccc; }}
    audio {{ width: 100%; margin-top: 12px; }}
    pre {{ white-space: pre-wrap; background: #080808; border: 1px solid #333; padding: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>PersonaPlex Review: {html.escape(str(receipt.get('persona', 'unknown')))}</h1>
  <p>Status: <span class="status">{html.escape(str(receipt.get('status', 'UNKNOWN')))}</span></p>
  <p>Input pack: {html.escape(str(receipt.get('input_reference_pack', '')))}</p>
  {''.join(rows)}
</body>
</html>
"""
    out_html.write_text(html_doc)
    return out_html


@app.command("validate-pack")
def validate_pack_command(
    reference_pack: Annotated[Path, typer.Option("--reference-pack", exists=True)],
    allow_empty: Annotated[bool, typer.Option("--allow-empty")] = False,
) -> None:
    """Validate an Orpheus PersonaPlex reference pack."""
    pack = read_pack(reference_pack, allow_empty=allow_empty)
    refs = validate_reference_files(pack)
    missing = [row for row in refs if not row["exists"]]
    payload = {
        "schema": "personaplex.reference_pack_validation.v1",
        "status": "PASS" if not missing else "FAIL",
        "persona": pack.persona,
        "reference_pack": str(reference_pack),
        "references": refs,
        "missing": missing,
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if missing:
        raise typer.Exit(1)


@app.command("pack-from-receipt")
def pack_from_receipt_command(
    receipt: Annotated[Path, typer.Option("--receipt", exists=True)],
    out: Annotated[Path, typer.Option("--out")],
    persona: Annotated[str | None, typer.Option("--persona")] = None,
    register: Annotated[str, typer.Option("--register")] = "neutral",
    checkpoint_root: Annotated[
        Path,
        typer.Option("--checkpoint-root"),
    ] = Path("/mnt/storage12tb/skills/voice-segment-selector/checkpoints"),
    text_prompt: Annotated[str | None, typer.Option("--text-prompt")] = None,
    allow_unverified_smoke: Annotated[
        bool,
        typer.Option("--allow-unverified-smoke"),
    ] = False,
) -> None:
    """Create a PersonaPlex reference pack from one Orpheus PASS inference receipt."""
    payload = json.loads(receipt.read_text())
    if payload.get("status") != "PASS":
        raise typer.BadParameter("Orpheus receipt status must be PASS")
    source_verified = payload.get("verified") is True
    if not source_verified and not allow_unverified_smoke:
        raise typer.BadParameter(
            "Orpheus receipt must include verified=true, or use "
            "--allow-unverified-smoke for a non-publication smoke reference"
        )
    inferred_persona = persona or str(payload.get("speaker") or "")
    if not SLUG_RE.match(inferred_persona):
        raise typer.BadParameter("persona must be supplied or present as a slug in receipt.speaker")
    if not SLUG_RE.match(register):
        raise typer.BadParameter("register must be a lowercase slug")
    wav_field = payload.get("stable_wav_path") or payload.get("wav_path")
    if not wav_field:
        raise typer.BadParameter("receipt must include stable_wav_path or wav_path")
    wav = resolve_orpheus_path(str(wav_field), checkpoint_root)
    if not wav.exists():
        raise typer.BadParameter(f"resolved receipt WAV does not exist: {wav}")
    wav_metrics = validate_wav(wav)
    lora_dir = payload.get("lora_dir")
    checkpoint = (
        str(resolve_orpheus_path(str(lora_dir), checkpoint_root))
        if lora_dir
        else None
    )
    pack = {
        "schema": "orpheus.personaplex_reference_pack.v1",
        "persona": inferred_persona,
        "source": "orpheus-tts-voice-trainer",
        "orpheus_checkpoint": checkpoint,
        "upstream_receipts": [str(receipt)],
        "references": [
            {
                "register": register,
                "wav": str(wav),
                "text_prompt": text_prompt
                or f"You are {inferred_persona} speaking naturally in a calm conversational register.",
                "source_receipt": str(receipt),
                "source_receipt_sha256": sha256_file(receipt),
                "wav_sha256": wav_metrics["sha256"],
                "source_status": str(payload.get("status")),
                "verified": source_verified,
                "review_status": "source_verified"
                if source_verified
                else "unverified_smoke",
                "duration_s": wav_metrics["duration_s"],
                "sample_rate": wav_metrics["sample_rate"],
                "channels": wav_metrics["channels"],
                "transcript": str(payload.get("prompt") or ""),
            }
        ],
    }
    # Validate before writing so the command cannot emit a malformed pack.
    ReferencePack.model_validate(pack)
    write_json(out, pack)
    typer.echo(json.dumps(pack, indent=2, sort_keys=True))


@app.command("from-orpheus")
def from_orpheus_command(
    reference_pack: Annotated[Path, typer.Option("--reference-pack", exists=True)],
    personaplex_root: Annotated[Path, typer.Option("--personaplex-root", exists=True)],
    human_input_wav: Annotated[Path, typer.Option("--human-input-wav", exists=True)],
    out_dir: Annotated[Path | None, typer.Option("--out-dir")] = None,
    personaplex_python_bin: Annotated[Path | None, typer.Option("--personaplex-python")] = None,
    device: Annotated[str, typer.Option("--device")] = "cuda",
    seed: Annotated[int, typer.Option("--seed")] = 42424242,
    cpu_offload: Annotated[bool, typer.Option("--cpu-offload")] = False,
    checkpoint_root: Annotated[
        Path,
        typer.Option("--checkpoint-root"),
    ] = Path("/mnt/storage12tb/skills/voice-segment-selector/checkpoints"),
    allow_provisional_reference: Annotated[
        bool,
        typer.Option("--allow-provisional-reference"),
    ] = False,
    max_human_input_seconds: Annotated[
        float | None,
        typer.Option("--max-human-input-seconds"),
    ] = None,
) -> None:
    """Create PersonaPlex-native prompts and conversation artifacts from Orpheus reference audio."""
    pack = read_pack(reference_pack)
    refs = validate_reference_files(pack)
    missing = [row for row in refs if not row["exists"]]
    if missing:
        raise typer.BadParameter(f"missing reference WAVs: {missing}")

    provenance = validate_reference_provenance(
        pack,
        checkpoint_root=checkpoint_root,
        allow_provisional_reference=allow_provisional_reference,
    )

    if out_dir is None:
        out_dir = DEFAULT_OUTPUT_ROOT / pack.persona / utc_run_id()
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise typer.BadParameter(f"out-dir already exists and is not empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    copied_pack = safe_child(out_dir, "input-reference-pack.json")
    shutil.copy2(reference_pack, copied_pack)
    effective_human_input_wav, original_human_input_metrics, effective_human_input_metrics = stage_human_input_wav(
        human_input_wav,
        out_dir,
        max_seconds=max_human_input_seconds,
    )
    python_bin = personaplex_python(personaplex_root, personaplex_python_bin)
    runtime = runtime_identity(personaplex_root, python_bin, out_dir)

    generated: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for ref in pack.references:
        wav = Path(ref.wav)
        register_dir = safe_child(out_dir, ref.register)
        voice_wav = safe_child(register_dir, "voice-prompt.wav")
        register_dir.mkdir(parents=True, exist_ok=True)
        if voice_wav.exists():
            raise RuntimeError(f"refusing to reuse existing voice prompt: {voice_wav}")
        shutil.copy2(wav, voice_wav)
        build_wav = safe_child(register_dir, "build-from-wav-output.wav")
        build_text = safe_child(register_dir, "build-from-wav-output.json")
        replay_wav = safe_child(register_dir, "replay-from-pt-output.wav")
        replay_text = safe_child(register_dir, "replay-from-pt-output.json")
        text_prompt = ref.text_prompt or f"You are {pack.persona} speaking naturally in the {ref.register} register."
        try:
            source_wav_metrics = validate_wav(voice_wav)
            pt_path = voice_wav.with_suffix(".pt")
            if pt_path.exists():
                raise RuntimeError(f"refusing to reuse preexisting pt file: {pt_path}")
            build_started_at = datetime.now(timezone.utc)
            build_run = run_personaplex_offline_cli(
                personaplex_root=personaplex_root,
                python_bin=python_bin,
                voice_prompt_path=voice_wav,
                human_input_wav=effective_human_input_wav,
                text_prompt=text_prompt,
                output_wav=build_wav,
                output_text=build_text,
                device=device,
                seed=seed,
                cpu_offload=cpu_offload,
                save_voice_embeddings=True,
            )
            build_wav_metrics = validate_wav(build_wav)
            build_text_metrics = validate_text_json(build_text)
            if not pt_path.exists():
                raise RuntimeError(f"PersonaPlex build did not create pt file: {pt_path}")
            pt_mtime = datetime.fromtimestamp(pt_path.stat().st_mtime, timezone.utc)
            if pt_mtime < build_started_at:
                raise RuntimeError(f"pt file predates this build: {pt_path}")
            ok, pt_report, error = validate_pt_schema(pt_path, python_bin=python_bin)
            if not ok:
                raise RuntimeError(error)
            replay_run = run_personaplex_offline_cli(
                personaplex_root=personaplex_root,
                python_bin=python_bin,
                voice_prompt_path=pt_path,
                human_input_wav=effective_human_input_wav,
                text_prompt=text_prompt,
                output_wav=replay_wav,
                output_text=replay_text,
                device=device,
                seed=seed,
                cpu_offload=cpu_offload,
                save_voice_embeddings=False,
            )
            replay_wav_metrics = validate_wav(replay_wav)
            replay_text_metrics = validate_text_json(replay_text)
            generated.append(
                {
                    "register": ref.register,
                    "wav": str(voice_wav),
                    "wav_metrics": source_wav_metrics,
                    "pt": str(pt_path),
                    "pt_schema": pt_report,
                    "build_run": build_run,
                    "build_output_wav": str(build_wav),
                    "build_output_wav_metrics": build_wav_metrics,
                    "build_output_text": str(build_text),
                    "build_output_text_metrics": build_text_metrics,
                    "replay_run": replay_run,
                    "replay_output_wav": str(replay_wav),
                    "replay_output_wav_metrics": replay_wav_metrics,
                    "replay_output_text": str(replay_text),
                    "replay_output_text_metrics": replay_text_metrics,
                    "original_human_input_wav_metrics": original_human_input_metrics,
                    "effective_human_input_wav_metrics": effective_human_input_metrics,
                    "text_prompt": text_prompt,
                }
            )
        except Exception as exc:  # pragma: no cover - live runtime dependent
            logger.exception("PersonaPlex conversion failed for {}", ref.register)
            failures.append(
                {
                    "register": ref.register,
                    "wav": str(voice_wav),
                    "error": str(exc),
                }
            )

    status = "PASS" if generated and not failures else "FAIL"
    receipt_path = out_dir / "personaplex-publish-receipt.json"
    pending_path = out_dir / "personaplex-publish-receipt.pending.json"
    payload = {
        "schema": "personaplex.publish_receipt.v1",
        "status": "CACHE_REPLAY_PASS" if generated and not failures else "FAIL",
        "publication_status": "NOT_PUBLISHED",
        "human_review_status": "NOT_REVIEWED",
        "persona": pack.persona,
        "input_reference_pack": str(copied_pack),
        "source_reference_pack": str(reference_pack),
        "orpheus_checkpoint": pack.orpheus_checkpoint,
        "personaplex_root": str(personaplex_root),
        "personaplex_python": str(python_bin),
        "runtime_identity": runtime,
        "reference_provenance": provenance,
        "allow_provisional_reference": allow_provisional_reference,
        "human_input_wav": str(human_input_wav),
        "effective_human_input_wav": str(effective_human_input_wav),
        "max_human_input_seconds": max_human_input_seconds,
        "generated_voice_prompts": generated,
        "failures": failures,
    }
    atomic_write_json(pending_path, payload | {"status": "PENDING_REVIEW_RENDER"})
    html_path = render_review_html(pending_path, out_dir / "index.html")
    payload["review_html"] = str(html_path)
    atomic_write_json(receipt_path, payload)
    pending_path.unlink(missing_ok=True)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if failures or not generated:
        raise typer.Exit(1)


@app.command("verify-e2e")
def verify_e2e_command(
    reference_pack: Annotated[Path, typer.Option("--reference-pack", exists=True)],
    personaplex_root: Annotated[Path, typer.Option("--personaplex-root", exists=True)],
    human_input_wav: Annotated[Path, typer.Option("--human-input-wav", exists=True)],
    out_dir: Annotated[Path | None, typer.Option("--out-dir")] = None,
    personaplex_python_bin: Annotated[Path | None, typer.Option("--personaplex-python")] = None,
    device: Annotated[str, typer.Option("--device")] = "cuda",
    seed: Annotated[int, typer.Option("--seed")] = 42424242,
    cpu_offload: Annotated[bool, typer.Option("--cpu-offload")] = False,
    checkpoint_root: Annotated[
        Path,
        typer.Option("--checkpoint-root"),
    ] = Path("/mnt/storage12tb/skills/voice-segment-selector/checkpoints"),
    allow_provisional_reference: Annotated[
        bool,
        typer.Option("--allow-provisional-reference"),
    ] = False,
    max_human_input_seconds: Annotated[
        float | None,
        typer.Option("--max-human-input-seconds"),
    ] = None,
) -> None:
    """Run the non-mocked release-relevant PersonaPlex E2E gate."""
    from_orpheus_command(
        reference_pack=reference_pack,
        personaplex_root=personaplex_root,
        human_input_wav=human_input_wav,
        out_dir=out_dir,
        personaplex_python_bin=personaplex_python_bin,
        device=device,
        seed=seed,
        cpu_offload=cpu_offload,
        checkpoint_root=checkpoint_root,
        allow_provisional_reference=allow_provisional_reference,
        max_human_input_seconds=max_human_input_seconds,
    )


@app.command("research-gate-sanity")
def research_gate_sanity_command(
    transcript: Annotated[
        str,
        typer.Option(
            "--transcript",
            help="Final ASR transcript from the human turn.",
        ),
    ],
    persona: Annotated[str, typer.Option("--persona")] = "embry",
    scope: Annotated[str, typer.Option("--scope")] = "personaplex",
    out_dir: Annotated[Path | None, typer.Option("--out-dir")] = None,
    memory_base_url: Annotated[str, typer.Option("--memory-base-url")] = MEMORY_BASE_URL,
    memory_timeout_s: Annotated[float, typer.Option("--memory-timeout-s", min=5.0)] = 75.0,
    brave_query: Annotated[str | None, typer.Option("--brave-query")] = None,
    brave_count: Annotated[int, typer.Option("--brave-count", min=1, max=10)] = 5,
    k: Annotated[int, typer.Option("--k", min=1, max=20)] = 8,
    with_scillm_planner: Annotated[
        bool,
        typer.Option("--with-scillm-planner/--no-scillm-planner"),
    ] = True,
    scillm_model: Annotated[
        str,
        typer.Option("--scillm-model", help="SciLLM model or alias for the response planner."),
    ] = "opencode-go/deepseek-v4-flash",
    scillm_timeout_s: Annotated[
        float,
        typer.Option("--scillm-timeout-s", min=5.0, help="Timeout for the planner model call."),
    ] = 120.0,
    print_full_receipt: Annotated[
        bool,
        typer.Option("--print-full-receipt/--summary-only"),
    ] = False,
) -> None:
    """Run a non-mocked PersonaPlex research-gate sanity check for one Embry turn.

    This command does not start the PersonaPlex WebSocket server and does not
    claim full-duplex audio readiness. It proves the upstream turn gate:
    memory intent, deterministic entity extraction, persona memory recall,
    clarify/deflect/answer products, Brave Search, and the compact packet that
    would be injected before PersonaPlex is allowed to make factual claims.
    """
    if not transcript.strip():
        raise typer.BadParameter("transcript must not be empty")
    if not SLUG_RE.match(persona):
        raise typer.BadParameter("persona must be a lowercase slug")
    if out_dir is None:
        out_dir = DEFAULT_OUTPUT_ROOT / "research-gate-sanity" / persona / utc_run_id()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    persona_tag = f"persona:{persona}"
    persona_question = (
        f"What persona memories explain how {persona} should answer this user turn: "
        f"{transcript}"
    )
    effective_brave_query = brave_query or (
        f"{transcript} current factual context reliable sources"
    )

    client = httpx.Client(
        base_url=memory_base_url,
        timeout=httpx.Timeout(memory_timeout_s, connect=3.0),
    )
    try:
        intent_payload = {
            "q": transcript,
            "scope": scope,
            "session_id": f"personaplex:{persona}",
            "fast": True,
            "app": "personaplex",
        }
        intent = timed_post_json(client, "/intent", intent_payload)
        normalized_intent, route_anomalies = normalize_intent_for_persona_turn(
            intent=intent,
            transcript=transcript,
            persona=persona,
            scope=scope,
        )

        entity_extraction = run_extract_entities(transcript)
        entity_context = entity_extraction.get("json") if entity_extraction.get("ok") else {}

        recall_payload = {
            "q": persona_question,
            "k": k,
            "collections": ["persona_memory"],
            "tags": [persona_tag],
        }
        persona_recall = timed_post_json(client, "/recall", recall_payload)

        intent_action = normalized_intent.get("action") or "QUERY"
        clarify_payload = {
            "q": transcript,
            "scope": scope,
            "context": (
                f"PersonaPlex research gate for persona {persona}; "
                "ask only if required evidence or entity scope is ambiguous."
            ),
            "k": min(k, 5),
        }
        clarify = timed_post_json(client, "/clarify", clarify_payload)

        deflect_payload = {
            "q": transcript,
            "persona_id": persona,
            "intent_action": intent_action,
        }
        deflect = timed_post_json(client, "/deflect", deflect_payload)

        answer_payload = {
            "q": transcript,
            "scope": scope,
            "k": min(k, 5),
            "collections": ["persona_memory"],
        }
        answer = timed_post_json(client, "/answer", answer_payload)
    finally:
        client.close()

    brave_required = should_run_brave_from_intent(normalized_intent)
    brave = (
        run_brave_web_search(effective_brave_query, count=brave_count)
        if brave_required
        else skipped_brave_search(
            effective_brave_query,
            "memory intent did not request current-facts research",
        )
    )
    injection_packet = build_personaplex_injection_packet(
        persona=persona,
        transcript=transcript,
        memory_intent=intent,
        normalized_intent=normalized_intent,
        route_anomalies=route_anomalies,
        entity_context=entity_context if isinstance(entity_context, dict) else {},
        persona_recall=persona_recall,
        clarify=clarify,
        deflect=deflect,
        answer=answer,
        brave=brave,
    )
    scillm_planner = (
        run_scillm_planner(injection_packet, model=scillm_model, timeout_s=scillm_timeout_s)
        if with_scillm_planner
        else run_deterministic_planner(injection_packet)
    )
    if scillm_planner is not None:
        injection_packet["scillm_planner"] = scillm_planner

    recall_json = persona_recall.get("json") if isinstance(persona_recall.get("json"), dict) else {}
    recall_items = recall_json.get("items", []) if isinstance(recall_json, dict) else []
    persona_scoped_items = [
        item
        for item in recall_items
        if item.get("persona_id") == persona or persona_tag in (item.get("tags") or [])
    ]
    gates = {
        "memory_intent_http_ok": bool(intent.get("ok")),
        "extract_entities_ok": bool(entity_extraction.get("ok")),
        "persona_recall_http_ok": bool(persona_recall.get("ok")),
        "persona_recall_has_items": bool(recall_items),
        "persona_recall_scoped_to_persona": bool(persona_scoped_items),
        "memory_clarify_http_ok": bool(clarify.get("ok")),
        "memory_deflect_http_ok": bool(deflect.get("ok")),
        "memory_answer_http_ok": bool(answer.get("ok")),
        "brave_search_ok": bool(brave.get("ok")),
        "brave_search_has_results": (not brave_required) or int(brave.get("result_count") or 0) > 0,
        "scillm_planner_ok": True if scillm_planner is None else bool(scillm_planner.get("ok")),
        "injection_packet_built": bool(injection_packet.get("persona_conditioning_text")),
        "memory_intent_not_sparta_compliance": normalized_intent.get("action") != "COMPLIANCE",
    }
    status = "PASS" if all(gates.values()) else "FAIL"

    injection_path = out_dir / "personaplex-research-injection.json"
    receipt_path = out_dir / "personaplex-research-gate-sanity.json"
    atomic_write_json(injection_path, injection_packet)
    receipt = {
        "schema": "personaplex.research_gate_sanity.v1",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "persona": persona,
        "transcript": transcript,
        "scope": scope,
        "memory_base_url": memory_base_url,
        "memory_timeout_s": memory_timeout_s,
        "brave_query": effective_brave_query,
        "brave_required": brave_required,
        "scillm_model": scillm_model,
        "scillm_timeout_s": scillm_timeout_s,
        "route_anomalies": route_anomalies,
        "outputs": {
            "receipt": str(receipt_path),
            "personaplex_injection_packet": str(injection_path),
        },
        "gates": gates,
        "requests": {
            "intent": intent_payload,
            "extract_entities": {
                "command": [
                    "bash",
                    str(EXTRACT_ENTITIES_RUN),
                    "extract",
                    "--json",
                    transcript,
                ],
            },
            "persona_recall": recall_payload,
            "clarify": clarify_payload,
            "deflect": deflect_payload,
            "answer": answer_payload,
            "brave": {
                "query": effective_brave_query,
                "count": brave_count,
            },
        },
        "responses": {
            "intent": intent,
            "extract_entities": entity_extraction,
            "persona_recall": persona_recall,
            "clarify": clarify,
            "deflect": deflect,
            "answer": answer,
            "brave": brave,
            "scillm_planner": scillm_planner,
        },
        "response_summaries": {
            "intent": summarize_response("intent", intent),
            "extract_entities": summarize_response("extract_entities", entity_extraction),
            "persona_recall": summarize_response("persona_recall", persona_recall),
            "clarify": summarize_response("clarify", clarify),
            "deflect": summarize_response("deflect", deflect),
            "answer": summarize_response("answer", answer),
            "brave": summarize_response("brave", brave),
            "scillm_planner": summarize_response("scillm_planner", scillm_planner),
        },
        "persona_recall_scoped_item_count": len(persona_scoped_items),
        "persona_recall_returned_item_count": len(recall_items),
        "claim_boundary": {
            "this_proves": [
                "live research products can be collected for one turn",
                "a PersonaPlex conditioning packet can be written",
            ],
            "this_does_not_prove": [
                "PersonaPlex WebSocket server is patched",
                "PersonaPlex audio gate is enforced",
                "PersonaPlex speaks the packet correctly",
                "full-duplex live interaction works",
            ],
        },
    }
    atomic_write_json(receipt_path, receipt)
    terminal_payload = receipt if print_full_receipt else {
        "schema": receipt["schema"],
        "status": receipt["status"],
        "persona": receipt["persona"],
        "transcript": receipt["transcript"],
        "outputs": receipt["outputs"],
        "gates": receipt["gates"],
        "response_summaries": receipt["response_summaries"],
        "claim_boundary": receipt["claim_boundary"],
    }
    typer.echo(json.dumps(terminal_payload, indent=2, sort_keys=True))
    if status != "PASS":
        raise typer.Exit(1)


@app.command("render-review")
def render_review_command(
    receipt: Annotated[Path, typer.Option("--receipt", exists=True)],
    out_html: Annotated[Path | None, typer.Option("--out-html")] = None,
) -> None:
    """Render an HTML review page from an existing PersonaPlex receipt."""
    path = render_review_html(receipt, out_html)
    typer.echo(str(path))


if __name__ == "__main__":
    app()
