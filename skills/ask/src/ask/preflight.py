"""Deterministic SPARTA preflight routing for /ask.

This module is intentionally pure at the decision layer. It routes only on
structured extractor and recall signals, never on relationship wording in the
question text.
"""

from __future__ import annotations

from typing import Any

from .skills_exec import parse_memory_output, run_extract_entities, run_memory_recall

EVIDENCE_CASE = "evidence_case"
NORMAL_ANSWER = "normal_answer"
NEEDS_ATTENTION = "needs_attention"

# Lowercase route aliases requested by the preflight contract.
evidence_case = EVIDENCE_CASE
normal_answer = NORMAL_ANSWER
needs_attention = NEEDS_ATTENTION

SPARTA_CORPORA = {
    "sparta",
    "sparta_controls",
    "sparta-control",
    "sparta_control",
    "space-cybersecurity",
}
SUPPORTED_ADJACENT_CORPORA = {
    "cwe",
    "nist",
    "nist_sp_800_53",
    "capec",
    "mitre",
    "attack",
    "mitre_attack",
    "mitre att&ck",
}
GROUNDING_CORPORA = SPARTA_CORPORA | SUPPORTED_ADJACENT_CORPORA
UNRESOLVED_STATUSES = {"unresolved", "missing", "not_found", "not-found", "fabricated", "unknown"}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _entity_values(entity: dict[str, Any], *keys: str) -> set[str]:
    return {_norm(entity.get(key)) for key in keys if _norm(entity.get(key))}


def _is_spartaish(entity: dict[str, Any]) -> bool:
    values = _entity_values(
        entity,
        "taxonomy",
        "source_corpus",
        "corpus",
        "collection",
        "framework",
        "source_framework",
        "domain",
        "namespace",
    )
    return bool(values & (SPARTA_CORPORA | {"sparta"})) or any("sparta" in value for value in values)


def _is_supported_corpus(entity: dict[str, Any]) -> bool:
    values = _entity_values(
        entity,
        "taxonomy",
        "source_corpus",
        "corpus",
        "collection",
        "framework",
        "source_framework",
        "domain",
        "namespace",
    )
    if values & GROUNDING_CORPORA:
        return True
    return any(any(corpus in value for corpus in GROUNDING_CORPORA) for value in values)


def _is_unresolved_or_fabricated(entity: dict[str, Any]) -> bool:
    status = _norm(entity.get("status"))
    if status in UNRESOLVED_STATUSES:
        return True
    if entity.get("exists") is False:
        return True
    # An extractor entity with SPARTA taxonomy/text but no durable id is a
    # SPARTA-looking mention that failed grounding.
    return _is_spartaish(entity) and not any(entity.get(key) for key in ("id", "control_id", "_id"))


def _is_grounded_entity(entity: dict[str, Any]) -> bool:
    if _is_unresolved_or_fabricated(entity):
        return False
    has_identifier = any(entity.get(key) for key in ("id", "control_id", "_id", "label"))
    return bool(has_identifier and _is_supported_corpus(entity))


def _entities_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    entities = [e for e in _as_list(payload.get("entities")) if isinstance(e, dict)]
    for meta in _as_list(payload.get("control_metadata")):
        if isinstance(meta, dict):
            entity = dict(meta)
            entity.setdefault("source_corpus", meta.get("source_framework") or meta.get("framework"))
            entity.setdefault("id", meta.get("control_id"))
            entities.append(entity)
    for control_id in _as_list(payload.get("all_control_ids")) + _as_list(payload.get("control_ids")):
        if control_id:
            entities.append({"id": control_id, "source_corpus": "sparta_controls", "status": "resolved"})
    return entities


def _grounded_memory_items(memory_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    for item in memory_items:
        if not isinstance(item, dict):
            continue
        values = {_norm(item.get(key)) for key in ("collection", "source_corpus", "corpus", "taxonomy", "scope")}
        tags = {_norm(tag) for tag in _as_list(item.get("tags"))}
        if (values | tags) & GROUNDING_CORPORA:
            grounded.append(item)
    return grounded


def decide_sparta_preflight(
    question: str,
    extractor_payload: dict[str, Any] | None,
    memory_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return the deterministic SPARTA preflight route.

    Routing rules:
    - grounded SPARTA/supported-corpora extractor signals => evidence_case;
    - unresolved/fabricated SPARTA-looking extractor identifiers => needs_attention;
    - no SPARTA-corpora match => normal_answer.
    """
    _ = question  # The decision does not regex relationship phrases from text.
    entities = _entities_from_payload(extractor_payload)
    unresolved = [entity for entity in entities if _is_unresolved_or_fabricated(entity)]
    if unresolved:
        return {
            "route": NEEDS_ATTENTION,
            "reason": "unresolved_or_fabricated_sparta_identifier",
            "unresolved_entities": unresolved,
            "grounded_entities": [],
        }

    grounded_entities = [entity for entity in entities if _is_grounded_entity(entity)]
    grounded_memory = _grounded_memory_items(memory_items or [])
    if grounded_entities:
        return {
            "route": EVIDENCE_CASE,
            "reason": "grounded_sparta_corpora_signal",
            "grounded_entities": grounded_entities,
            "memory_grounding_count": len(grounded_memory),
        }

    return {
        "route": NORMAL_ANSWER,
        "reason": "no_sparta_corpora_match",
        "grounded_entities": [],
        "memory_grounding_count": len(grounded_memory),
    }


def _record(run_state: Any, event: str, **fields: Any) -> None:
    if run_state is not None and hasattr(run_state, "event"):
        run_state.event(event, **fields)


def run_sparta_preflight(
    question: str,
    scope: str,
    k: int,
    run_state: Any = None,
) -> dict[str, Any]:
    """Run extractor and memory recall, record metadata, then decide the route."""
    extractor_result = run_extract_entities(question, scope=scope)
    extractor_payload = extractor_result.get("payload") if isinstance(extractor_result, dict) else None
    extractor_metadata = {
        "returncode": extractor_result.get("returncode"),
        "skipped": extractor_result.get("skipped"),
        "stderr_preview": str(extractor_result.get("stderr", ""))[:500],
        "entity_count": len(_entities_from_payload(extractor_payload)),
    }
    _record(run_state, "sparta_preflight.extract_entities", **extractor_metadata)

    recall_result = run_memory_recall(question, scope=scope, k=k)
    memory_items = parse_memory_output(recall_result.get("stdout", "")) if isinstance(recall_result, dict) else []
    recall_metadata = {
        "returncode": recall_result.get("returncode"),
        "skipped": recall_result.get("skipped"),
        "stderr_preview": str(recall_result.get("stderr", ""))[:500],
        "item_count": len(memory_items),
    }
    _record(run_state, "sparta_preflight.memory_recall", **recall_metadata)

    decision = decide_sparta_preflight(question, extractor_payload, memory_items)
    decision["extractor_metadata"] = extractor_metadata
    decision["recall_metadata"] = recall_metadata
    _record(run_state, "sparta_preflight.decision", route=decision.get("route"), reason=decision.get("reason"))
    return decision
