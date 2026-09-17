"""Jev shadow classifier for triage-error.

Shadow mode ONLY: runs alongside the deterministic catalog classifier, logs
both verdicts to memory collection `jev_shadow_log`, and never changes the
decision. Criteria are generated from the LIVE failure_codes.json catalog at
call time (house rule: no stale inline copies).

Enabled when JEV_API_KEY is set and JEV_SHADOW != "0". Fail-closed: any
transport/validation problem logs an abstain, never fabricates.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from loguru import logger

from classifier import load_catalog

JEV_API_URL = "https://api.typesafe.ai/v1/systemone"
MEMORY_URL = "http://127.0.0.1:8601"  # house rule: Docker daemon, never unix sockets
SHADOW_COLLECTION = "jev_shadow_log"
BLOCKED_MARKERS = ("CUI//", "controlled unclassified", "ITAR", "export-controlled")


def shadow_enabled() -> bool:
    return bool(os.getenv("JEV_API_KEY")) and os.getenv("JEV_SHADOW", "1") not in {"0", "false", "no"}


def _criteria_from_catalog() -> dict[str, str]:
    criteria = {
        entry["code"]: (entry.get("cause") or entry["code"])[:220]
        for entry in load_catalog()
    }
    criteria["no_match"] = "No catalog code is established by the supplied evidence."
    return criteria


def shadow_classify(signal: str, layer: str | None) -> dict[str, Any]:
    """Ask Jev to classify against the live catalog. Returns a shadow record."""
    t0 = time.time()
    first_line = signal.strip().splitlines()[0][:500] if signal.strip() else ""
    state = {"error": first_line, "layer": layer or "unknown", "full_context": signal[:2000]}
    out: dict[str, Any] = {
        "shadow": "jev",
        "signal_sha_prefix": str(hash(first_line) & 0xFFFFFFFFFFFFFFFF)[:12],
        "layer": layer or "",
    }
    low = json.dumps(state).lower()
    marker = next((m for m in BLOCKED_MARKERS if m in low), None)
    if marker:
        return {**out, "jev_decision": "abstain", "jev_reason": f"egress blocked: {marker}"}
    api_key = os.getenv("JEV_API_KEY")
    if not api_key:
        return {**out, "jev_decision": "abstain", "jev_reason": "no JEV_API_KEY"}
    try:
        resp = httpx.post(
            JEV_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "state": state,
                "model": os.getenv("JEV_MODEL", "jev-latest"),
                "questions": {
                    "failure_code": {
                        "type": "choice",
                        "instructions": (
                            "Select the most specific failure code established by the supplied "
                            "diagnostic evidence. Classify the observed failure mechanism; do not "
                            "invent an upstream root cause. Use no_match when no catalog "
                            "definition is supported."
                        ),
                        "criteria": _criteria_from_catalog(),
                    }
                },
            },
            timeout=float(os.getenv("JEV_TIMEOUT_S", "10")),
        )
        resp.raise_for_status()
        answer = resp.json().get("answers", {}).get("failure_code", {})
        out.update(
            jev_decision="accept",
            jev_code=answer.get("choice"),
            jev_confidence=answer.get("confidence"),
            jev_top_probs=dict(
                sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])[:3]
            ),
            took_ms=int((time.time() - t0) * 1000),
        )
    except Exception as exc:
        out.update(jev_decision="abstain", jev_reason=f"transport: {type(exc).__name__}: {exc}"[:200])
    return out


def log_shadow(record: dict[str, Any]) -> None:
    """Best-effort write to memory jev_shadow_log. Never raises."""
    import hashlib
    digest = hashlib.sha256(
        f"{record.get('signal_sha_prefix')}|{record.get('deterministic_code')}|{time.time()}".encode()
    ).hexdigest()[:24]
    record["_key"] = f"shadow_{digest}"
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["retrieval_text"] = f"jev shadow {record.get('layer','')} deterministic={record.get('deterministic_code')} jev={record.get('jev_code')} agree={record.get('agree')}"
    try:
        httpx.post(
            f"{MEMORY_URL}/store",
            json={"collection": SHADOW_COLLECTION, "document": record},
            timeout=5.0,
        )
    except Exception as exc:  # telemetry must never fail the shadow
        logger.debug("jev shadow log skipped: {}", exc)
