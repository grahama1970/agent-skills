#!/usr/bin/env python3
"""Deterministic counterpart-isolation gate with explicit ToM target changes.

The default remains fail closed: claims may target only the selected counterpart
or ``unknown_person``. A different target is admissible only when a
``persona_dream.counterpart_target_change.v1`` object proves that the change is
hook-grounded in a cited source memory, explicitly framed as a model of another
mind, and non-asserting about that person's first-person facts.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

TARGET_CHANGE_SCHEMA = "persona_dream.counterpart_target_change.v1"
TARGET_CHANGE_FRAMING = "theory_of_mind"
TARGET_CHANGE_ASSERTION_MODE = "model_of_other_mind"
TARGET_CHANGE_EPISTEMIC_STATUS = "tentative_model"

SourceResolver = Callable[[str], Mapping[str, Any] | None]


def normalize_persona_id(value: Any) -> str:
    """Normalize person tags, display names, and canonical ids for comparison."""
    text = str(value or "").strip().lower()
    if text.startswith("person:"):
        text = text.split(":", 1)[1]
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    # The current persona-dream contract uses short ids for Lawson family members.
    if text.endswith("_lawson") and text != "embry_lawson":
        text = text[: -len("_lawson")]
    return text


def _as_rows(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        nested = value.get("hooks")
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, Mapping)]
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _candidate_targets(hook: Mapping[str, Any]) -> set[str]:
    raw = hook.get("candidate_counterpart_personas")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    targets: set[str] = set()
    for item in raw:
        if isinstance(item, Mapping):
            item = item.get("persona_id") or item.get("id") or item.get("name")
        target = normalize_persona_id(item)
        if target:
            targets.add(target)
    return targets


def _same_text(left: Any, right: Any) -> bool:
    return str(left or "").strip() == str(right or "").strip()


def _matching_hook(
    document: Mapping[str, Any],
    *,
    target: str,
    change: Mapping[str, Any],
) -> bool:
    for hook in _as_rows(document.get("cross_persona_hooks")):
        if target not in _candidate_targets(hook):
            continue
        if not all(str(hook.get(field) or "").strip() for field in (
            "shared_event", "possible_contrast", "canon_constraint"
        )):
            continue
        if all(_same_text(change.get(field), hook.get(field)) for field in (
            "shared_event", "possible_contrast", "canon_constraint"
        )):
            return True
    return False


def counterpart_violation_reasons(
    claims: list[Mapping[str, Any]],
    counterpart_id: str,
    id_field: str,
    *,
    source_documents: Mapping[str, Mapping[str, Any]] | None = None,
    source_resolver: SourceResolver | None = None,
    model_owner_id: str | None = None,
) -> dict[Any, list[str]]:
    """Return deterministic rejection reasons keyed by claim id.

    A cross-persona target must satisfy every target-change condition. The
    function deliberately does not infer permission from names in prose.
    """
    selected = normalize_persona_id(counterpart_id)
    required_model_owner = normalize_persona_id(model_owner_id) if model_owner_id else None
    ordinary = {selected, "unknown_person"}
    violations: dict[Any, list[str]] = {}

    for index, claim in enumerate(claims):
        claim_id = claim.get(id_field, f"claim-{index:03d}")
        target = normalize_persona_id(claim.get("target"))
        reasons: list[str] = []

        if not target:
            reasons.append("TARGET_MISSING")
        elif target in ordinary:
            continue
        else:
            change = claim.get("target_change")
            if not isinstance(change, Mapping):
                reasons.append("TARGET_CHANGE_SPEC_MISSING")
            else:
                if change.get("schema") != TARGET_CHANGE_SCHEMA:
                    reasons.append("TARGET_CHANGE_SCHEMA_INVALID")
                if normalize_persona_id(change.get("from_counterpart")) != selected:
                    reasons.append("TARGET_CHANGE_FROM_MISMATCH")
                if normalize_persona_id(change.get("to_counterpart")) != target:
                    reasons.append("TARGET_CHANGE_TO_MISMATCH")
                if change.get("framing") != TARGET_CHANGE_FRAMING:
                    reasons.append("TARGET_CHANGE_NOT_TOM_FRAMED")
                if change.get("assertion_mode") != TARGET_CHANGE_ASSERTION_MODE:
                    reasons.append("TARGET_CHANGE_ASSERTION_MODE_INVALID")
                if change.get("epistemic_status") != TARGET_CHANGE_EPISTEMIC_STATUS:
                    reasons.append("TARGET_CHANGE_EPISTEMIC_STATUS_INVALID")
                if change.get("asserts_other_person_fact") is not False:
                    reasons.append("TARGET_CHANGE_ASSERTS_OTHER_PERSON_FACT")
                if claim.get("literal_historical_event") is True:
                    reasons.append("TARGET_CHANGE_LITERAL_EVENT_ASSERTION")
                subject = normalize_persona_id(claim.get("subject"))
                model_owner = normalize_persona_id(change.get("model_owner"))
                if not model_owner:
                    reasons.append("TARGET_CHANGE_MODEL_OWNER_MISSING")
                if required_model_owner and model_owner != required_model_owner:
                    reasons.append("TARGET_CHANGE_MODEL_OWNER_MISMATCH")
                if not subject or subject != model_owner or subject == target:
                    reasons.append("TARGET_CHANGE_SUBJECT_NOT_MODEL_OWNER")

                source_ref = str(change.get("source_memory_ref") or "").strip()
                claim_refs = {str(ref) for ref in (claim.get("source_memory_refs") or [])}
                if not source_ref or source_ref not in claim_refs:
                    reasons.append("TARGET_CHANGE_SOURCE_NOT_CITED")
                else:
                    document = (source_documents or {}).get(source_ref)
                    if document is None and source_resolver is not None:
                        document = source_resolver(source_ref)
                    if document is None:
                        reasons.append("TARGET_CHANGE_SOURCE_UNRESOLVED")
                    elif not _matching_hook(document, target=target, change=change):
                        reasons.append("TARGET_CHANGE_HOOK_MISMATCH")

        if reasons:
            violations[claim_id] = reasons

    return violations


def counterpart_violations(
    claims: list[Mapping[str, Any]],
    counterpart_id: str,
    id_field: str,
    *,
    source_documents: Mapping[str, Mapping[str, Any]] | None = None,
    source_resolver: SourceResolver | None = None,
    model_owner_id: str | None = None,
) -> list[Any]:
    """Compatibility projection used by the autonomous cycle."""
    return list(counterpart_violation_reasons(
        claims,
        counterpart_id,
        id_field,
        source_documents=source_documents,
        source_resolver=source_resolver,
        model_owner_id=model_owner_id,
    ))
