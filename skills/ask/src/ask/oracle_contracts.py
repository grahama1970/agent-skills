"""Typed oracle adapter contract helpers."""

from __future__ import annotations

from typing import Any


ORACLE_ADAPTER_RESPONSE_SCHEMA_VERSION = "ask.oracle_adapter_response.v1"


def normalize_oracle_turns(
    *,
    backend: str,
    model_served: str,
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Normalize backend-specific oracle turn metadata into one response schema."""
    normalized_turns = [
        {
            "iteration": int(turn.get("iteration") or index + 1),
            "backend": str(turn.get("backend") or backend),
            "model": str(turn.get("model") or model_served or ""),
            "persona": str(turn.get("persona") or ""),
            "artifact_dir": str(turn.get("artifact_dir") or ""),
            "latency_ms": int(turn.get("took_ms") or turn.get("latency_ms") or 0),
            "content_chars": len(str(turn.get("content") or "")),
            "controlled_tab_id": str(turn.get("controlled_tab_id") or ""),
            "controlled_view_id": str(turn.get("controlled_view_id") or ""),
            "raw_contains_sentinel": bool(turn.get("raw_contains_sentinel")),
            "focus_changed": bool(turn.get("focus_changed")),
        }
        for index, turn in enumerate(turns)
    ]
    artifacts = [
        turn["artifact_dir"]
        for turn in normalized_turns
        if turn.get("artifact_dir")
    ]
    sentinel_required = backend in {
        "webgpt",
        "webgemini",
        "webkimi",
        "webperplexity",
        "cursor-browser",
    }
    return {
        "schema_version": ORACLE_ADAPTER_RESPONSE_SCHEMA_VERSION,
        "backend": backend,
        "model_served": model_served,
        "status": "ok",
        "turns": normalized_turns,
        "turns_count": len(normalized_turns),
        "artifacts": artifacts,
        "sentinel_required": sentinel_required,
        "failure": None,
    }


def normalize_oracle_failure(
    *,
    backend: str,
    model: str,
    error: BaseException | str,
    error_code: str = "adapter_error",
) -> dict[str, Any]:
    message = str(error)
    return {
        "schema_version": ORACLE_ADAPTER_RESPONSE_SCHEMA_VERSION,
        "backend": backend,
        "model_served": model,
        "status": "error",
        "turns": [],
        "turns_count": 0,
        "artifacts": [],
        "sentinel_required": backend in {
            "webgpt",
            "webgemini",
            "webkimi",
            "webperplexity",
            "cursor-browser",
        },
        "failure": {
            "code": error_code,
            "message": message,
        },
    }
