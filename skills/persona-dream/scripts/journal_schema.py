#!/usr/bin/env python3
"""Strict validation for persona journal entries.

A journal is not just prose (operator 2026-07-24): every entry is a strict JSON
schema and must validate before it is written to disk or persisted to the
persona_journal /memory collection. Persona-agnostic — no persona is baked in.

Uses jsonschema (a declared dependency) for full draft-2020-12 validation. Falls
back to a deterministic core check if jsonschema is ever unavailable, so the gate
fails closed regardless of environment rather than silently passing.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "persona_journal.v1.schema.json"
SCHEMA_ID = "persona_dream.persona_journal.v1"

_REQUIRED = (
    "schema", "persona_id", "cycle", "journal", "unresolved_tension",
    "expanded_understanding", "session_mood", "affect_source",
    "dream_provenance", "memory_kind", "canon_status",
    "never_promote_to_event_fact", "asserts_only_own_inner_state",
    "memory_web_entities", "tom_summary", "memory_web_size", "source_memory_ids",
)


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _fallback_errors(entry: dict) -> list[str]:
    """Deterministic core check used only if jsonschema cannot be imported."""
    errs = []
    if not isinstance(entry, dict):
        return ["entry_is_not_an_object"]
    for f in _REQUIRED:
        if f not in entry:
            errs.append(f"missing_required_field:{f}")
    if entry.get("schema") != SCHEMA_ID:
        errs.append(f"schema_must_be:{SCHEMA_ID}")
    for f in ("persona_id", "cycle", "journal", "unresolved_tension",
              "expanded_understanding"):
        if not str(entry.get(f) or "").strip():
            errs.append(f"empty_required_string:{f}")
    if not isinstance(entry.get("source_memory_ids"), list):
        errs.append("source_memory_ids_must_be_array")
    sm = entry.get("session_mood")
    if not isinstance(sm, dict) or not str(sm.get("mood_label") or "").strip():
        errs.append("session_mood.mood_label_required")
    return sorted(set(errs))


def validate_journal_entry(entry: dict) -> list[str]:
    """Return a sorted list of validation errors; empty list == valid.

    Validates the JSON-normalized form (what actually gets written to disk and
    persisted), so Python tuples serialize to arrays exactly as they will on
    disk rather than tripping jsonschema's list-only 'array' type check."""
    try:
        entry = json.loads(json.dumps(entry, default=str))
    except (TypeError, ValueError) as e:
        return [f"<root>: entry is not JSON-serializable: {e}"]
    try:
        from jsonschema import Draft202012Validator
    except Exception:  # noqa: BLE001 - fail closed with the core check
        return _fallback_errors(entry)
    schema = load_schema()
    validator = Draft202012Validator(schema)
    errs = []
    try:
        from pydantic_step_gate import pydantic_error_messages
        errs.extend(pydantic_error_messages(schema, entry))
    except Exception:  # noqa: BLE001 - jsonschema path below still fails closed
        pass
    for e in validator.iter_errors(entry):
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append(f"{loc}: {e.message}")
    return sorted(errs)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        obj = json.loads(Path(sys.argv[1]).read_text())
        problems = validate_journal_entry(obj)
        print(json.dumps({"schema": SCHEMA_ID, "valid": not problems,
                          "errors": problems}, indent=2))
        raise SystemExit(1 if problems else 0)
    print(f"schema: {SCHEMA_PATH}")
