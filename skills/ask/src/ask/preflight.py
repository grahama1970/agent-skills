"""Deterministic SPARTA preflight routing for /ask.

The decision layer is intentionally pure: it routes on structured extractor and
recall signals, never on relationship wording in the question text.
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
    "space cybersecurity",
}
SUPPORTED_ADJACENT_CORPORA = {
    "cwe",
    "nist",
    "nist_sp_800_53",
    "nist sp 800 53",
    "capec",
    "mitre",
    "attack",
    "mitre_attack",
    "mitre att&ck",
}
GROUNDING_CORPORA = SPARTA_CORPORA | SUPPORTED_ADJACENT_CORPORA
UNRESOLVED_STATUSES = {"unresolved", "missing", "not_found", "not-found", "fabricated", "unknown"}
CORPUS_KEYS = (
    "taxonomy",
    "source_corpus",
    "corpus",
    "collection",
    "framework",
    "source_framework",
    "domain",
    "namespace",
    "scope",
)
IDENTIFIER_KEYS = ("id", "control_id", "_id", "label", "source", "target", "term", "text", "tag")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _entity_values(entity: dict[str, Any], *keys: str) -> set[str]:
    return {_norm(entity.get(key)) for key in keys if _norm(entity.get(key))}


def _contains_corpus(value: str, corpora: set[str]) -> bool:
    return value in corpora or any(corpus in value for corpus in corpora)


def _is_spartaish(entity: dict[str, Any]) -> bool:
    values = _entity_values(entity, *CORPUS_KEYS, *IDENTIFIER_KEYS, "reason", "type")
    return any(_contains_corpus(value, SPARTA_CORPORA | {"sparta"}) for value in values)


def _is_supported_corpus(entity: dict[str, Any]) -> bool:
    values = _entity_values(entity, *CORPUS_KEYS)
    return any(_contains_corpus(value, GROUNDING_CORPORA) for value in values)


def _is_unresolved_or_fabricated(entity: dict[str, Any]) -> bool:
    """True only for explicit extractor non-resolution signals.

    A SPARTA taxonomy tag without a durable control id is still a valid grounded
    signal under the contract, so lack of an id alone must not trigger attention.
    """
    status = _norm(entity.get("status"))
    if status in UNRESOLVED_STATUSES:
        return True
    if entity.get("exists") is False:
        return True
    resolution = entity.get("resolution")
    if isinstance(resolution, dict) and resolution.get("exists") is False:
        return True
    return False


def _has_identifier(entity: dict[str, Any]) -> bool:
    return any(entity.get(key) for key in IDENTIFIER_KEYS)


def _is_grounded_entity(entity: dict[str, Any]) -> bool:
    if _is_unresolved_or_fabricated(entity):
        return False
    if entity.get("grounded") is False:
        return False
    return bool(_has_identifier(entity) and _is_supported_corpus(entity))


def _append_dicts(target: list[dict[str, Any]], value: Any) -> None:
    for item in _as_list(value):
        if isinstance(item, dict):
            target.append(item)


def _entities_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normalize known extractor output shapes into entity-like records."""
    if not isinstance(payload, dict):
        return []

    entities: list[dict[str, Any]] = []
    _append_dicts(entities, payload.get("entities"))

    for meta in _as_list(payload.get("control_metadata")):
        if isinstance(meta, dict):
            entity = dict(meta)
            entity.setdefault("source_corpus", meta.get("source_framework") or meta.get("framework"))
            entity.setdefault("id", meta.get("control_id"))
            entity.setdefault("status", "resolved")
            entities.append(entity)

    for control_id in _as_list(payload.get("all_control_ids")) + _as_list(payload.get("control_ids")) + _as_list(payload.get("phrase_controls")):
        if control_id:
            entities.append({"id": control_id, "source_corpus": "sparta_controls", "status": "resolved"})

    for pair in _as_list(payload.get("related_pairs")) + _as_list(payload.get("crosswalk_pairs")):
        if isinstance(pair, dict):
            entity = dict(pair)
            entity.setdefault("source_corpus", "sparta_controls")
            entity.setdefault("taxonomy", "SPARTA")
            entity.setdefault("status", "resolved")
            entities.append(entity)

    taxonomy_tags = payload.get("taxonomy_tags")
    if isinstance(taxonomy_tags, dict):
        for collection, tags in taxonomy_tags.items():
            for tag in _as_list(tags):
                entities.append({
                    "tag": tag,
                    "collection": collection,
                    "taxonomy": collection,
                    "source_corpus": collection,
                    "status": "resolved",
                })
    elif isinstance(taxonomy_tags, list):
        for tag in taxonomy_tags:
            if isinstance(tag, dict):
                entity = dict(tag)
                entity.setdefault("status", "resolved")
                entities.append(entity)
            elif tag:
                entities.append({"tag": tag, "taxonomy": "sparta", "source_corpus": "sparta", "status": "resolved"})

    for key in ("sparta_recall", "recall_items", "memory_items"):
        for item in _as_list(payload.get(key)):
            if isinstance(item, dict):
                entity = dict(item)
                entity.setdefault("source_corpus", item.get("collection") or item.get("corpus") or "sparta")
                entity.setdefault("status", "resolved")
                entities.append(entity)

    for term in _as_list(payload.get("unresolved_terms")):
        if isinstance(term, dict):
            entity = dict(term)
            entity.setdefault("status", "unresolved")
            entity.setdefault("source_corpus", "sparta_controls")
            entities.append(entity)

    resolution_map = payload.get("resolution_map")
    if isinstance(resolution_map, dict):
        for term, resolution in resolution_map.items():
            if isinstance(resolution, dict) and resolution.get("exists") is False:
                entity = dict(resolution)
                entity.setdefault("term", term)
                entity.setdefault("status", "unresolved")
                entity.setdefault("source_corpus", "sparta_controls")
                entities.append(entity)

    return entities


def _grounded_memory_items(memory_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grounded: list[dict[str, Any]] = []
    for item in memory_items:
        if not isinstance(item, dict):
            continue
        values = {_norm(item.get(key)) for key in CORPUS_KEYS}
        tags = {_norm(tag) for tag in _as_list(item.get("tags"))}
        if any(_contains_corpus(value, GROUNDING_CORPORA) for value in values | tags):
            grounded.append(item)
    return grounded


def decide_sparta_preflight(
    question: str,
    extractor_payload: dict[str, Any] | None,
    memory_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Return the deterministic SPARTA preflight route."""
    _ = question  # Do not route by relationship phrases in prompt text.
    entities = _entities_from_payload(extractor_payload)

    unresolved = [entity for entity in entities if _is_unresolved_or_fabricated(entity) and _is_spartaish(entity)]
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
    _record(run_state, "extract_entities_started", scope=scope)
    extractor_result = run_extract_entities(question, scope=scope)
    extractor_payload = extractor_result.get("payload") if isinstance(extractor_result, dict) else None
    extractor_metadata = {
        "returncode": extractor_result.get("returncode"),
        "skipped": extractor_result.get("skipped"),
        "stderr_preview": str(extractor_result.get("stderr", ""))[:500],
        "entity_count": len(_entities_from_payload(extractor_payload)),
    }
    _record(run_state, "extract_entities_finished", **extractor_metadata)

    _record(run_state, "memory_recall_started", scope=scope, k=k)
    recall_result = run_memory_recall(question, scope=scope, k=k)
    memory_items = parse_memory_output(recall_result.get("stdout", "")) if isinstance(recall_result, dict) else []
    recall_metadata = {
        "returncode": recall_result.get("returncode"),
        "skipped": recall_result.get("skipped"),
        "stderr_preview": str(recall_result.get("stderr", ""))[:500],
        "item_count": len(memory_items),
    }
    _record(run_state, "memory_recall_finished", **recall_metadata)

    decision = decide_sparta_preflight(question, extractor_payload, memory_items)
    decision["extractor_metadata"] = extractor_metadata
    decision["recall_metadata"] = recall_metadata
    _record(run_state, "preflight_decision", route=decision.get("route"), reason=decision.get("reason"))
    if decision.get("route") == NEEDS_ATTENTION:
        _record(run_state, "needs_attention", reason=decision.get("reason"), unresolved_entities=decision.get("unresolved_entities", []))
    return decision
