"""Real $memory pipeline HTTP client for sparta-stress-test.

Replaces the embedded pipeline copy (in-process IntentMapper + bespoke
routing/answer composition) with calls to the REAL first-class products:

    POST /intent    -> route + entities + recall_profile
    POST /answer    -> can_answer / final_response / sources (grounded answer product)
    POST /clarify   -> clarifying question product
    POST /deflect   -> off-topic/no-match product

Fail-closed: if the daemon is unreachable, callers get a typed
`pipeline_unreachable` error -- NEVER a silent fallback to the old embedded
copy (a silent fallback is what made this suite test a copy of the pipeline
instead of the pipeline).

Shapes are mapped to the dicts `run_single` and the grading cascade already
consume (intent_result / answer), so the grader is unchanged.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from loguru import logger

MEMORY_BASE = os.environ.get("SPARTA_MEMORY_BASE", "http://127.0.0.1:8601")
CALLER = "sparta-stress-test"
TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(base_url=MEMORY_BASE, timeout=TIMEOUT) as client:
        r = client.post(path, json=payload, headers={"X-Caller-Skill": CALLER})
        r.raise_for_status()
        return r.json()


def _unreachable(path: str, e: Exception) -> dict[str, Any]:
    logger.warning(f"real pipeline {path} unreachable: {e}")
    return {"pipeline_error": "pipeline_unreachable", "detail": str(e)[:200],
            "base": MEMORY_BASE}


def pipeline_intent(question_text: str, scope: str = "", session_id: str = "sparta-stress-test",
                    fast: bool = True) -> dict[str, Any]:
    """REAL /intent product -> intent_result-compatible dict (action, confidence, entities...)."""
    try:
        d = _post("/intent", {"q": question_text, "scope": scope, "session_id": session_id,
                              "fast": fast})
    except Exception as e:  # fail closed, never fall back to an embedded classifier
        return _unreachable("/intent", e)
    d.setdefault("action", "QUERY")
    d["pipeline_source"] = "http:/intent"
    return d


def pipeline_answer(question_text: str, scope: str = "", k: int = 10) -> Optional[dict[str, Any]]:
    """REAL /answer product -> the same answer dict shape _ask_brandon_via_qra produced.

    can_answer=false maps to answered=False (the honest hold/draft signal) with
    answer_type preserved (e.g. insufficient_memory_evidence).
    """
    try:
        d = _post("/answer", {"q": question_text, "scope": scope, "k": k})
    except Exception as e:
        return _unreachable("/answer", e)

    can_answer = bool(d.get("can_answer"))
    sources = d.get("sources") or []
    recall = d.get("recall") or {}
    items = recall.get("items") or []
    keys = []
    for s in sources:
        key = s.get("_key") or s.get("key") or ""
        if key:
            keys.append(key)

    return {
        "answered": can_answer,
        "answer_text": (d.get("final_response") or d.get("source_answer") or ""),
        "answer_type": d.get("answer_type", ""),
        "confidence": d.get("confidence", 0.0),
        "source_qra_keys": keys,
        "qra_count": len(keys) or len(items),
        "search_scores": [{"key": it.get("_key", ""),
                           "score": (it.get("scores") or {}).get("bm25", 0)} for it in items[:5]],
        "pipeline_source": "http:/answer",
    }


def pipeline_clarify(question_text: str, scope: str = "", context: str = "",
                     k: int = 5) -> dict[str, Any]:
    """REAL /clarify product -> {needs_clarification, clarifying question text...}."""
    payload: dict[str, Any] = {"q": question_text, "scope": scope, "k": k}
    if context:
        payload["context"] = context
    try:
        d = _post("/clarify", payload)
    except Exception as e:
        return _unreachable("/clarify", e)
    d["pipeline_source"] = "http:/clarify"
    return d


def pipeline_deflect(question_text: str, intent_action: str = "NO_MATCH") -> dict[str, Any]:
    """REAL /deflect product -> {should_deflect, deflection text, deflection_type...}."""
    try:
        d = _post("/deflect", {"q": question_text, "intent_action": intent_action})
    except Exception as e:
        return _unreachable("/deflect", e)
    d["pipeline_source"] = "http:/deflect"
    return d


def demo() -> None:
    """Live self-check: the four REAL products answer through HTTP, fail-closed shape held."""
    i = pipeline_intent("What countermeasures address GPS spoofing on the F-36?", scope="sparta")
    assert i.get("pipeline_source") == "http:/intent" and "action" in i, i
    a = pipeline_answer("What countermeasures address GPS spoofing on the F-36?", scope="sparta")
    assert a is not None and a.get("pipeline_source") == "http:/answer", a
    assert isinstance(a.get("answered"), bool), a  # can_answer mapped, never composed by us
    c = pipeline_clarify("How do I secure it?", scope="sparta")
    assert c.get("pipeline_source") == "http:/clarify", c
    d = pipeline_deflect("what is the weather")
    assert d.get("pipeline_source") == "http:/deflect", d
    print("pipeline_client demo: OK (intent/answer/clarify/deflect all via REAL HTTP products)")


if __name__ == "__main__":
    demo()
