#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "skills" / "memory"
SCILLM_STREAM_SCRIPT = ROOT / "skills" / "scillm" / "scripts" / "stream_call_with_monitor.py"

SEED = "persona-dream-horus-extract-v1"
SAMPLE_PLAN_ID = "horus-extract-fixture-v1"
SCHEMA_VERSION = "persona_lore_extract.v1"
DEFAULT_MODEL = "chutes-deepseek"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_db() -> Any:
    sys.path.insert(0, str(MEMORY_DIR))
    from db import get_db as memory_get_db  # type: ignore

    return memory_get_db()


def collection_count(db: Any, name: str) -> int | None:
    if not db.has_collection(name):
        return None
    return int(db.collection(name).count())


def fetch_horus_persona(db: Any) -> dict[str, Any] | None:
    if not db.has_collection("personas"):
        return None
    return db.collection("personas").get("horus")


def fetch_candidate_chunks(db: Any) -> list[dict[str, Any]]:
    query = """
    FOR c IN horus_lore_chunks
      RETURN {
        _id: c._id,
        _key: c._key,
        doc_id: c.doc_id,
        parent_book_id: c.parent_book_id,
        chunk_index: c.chunk_index,
        source: c.source,
        source_meta: c.source_meta,
        entities: c.entities,
        is_chapter: c.is_chapter,
        text: c.text
      }
    """
    return list(db.aql.execute(query))


def entity_text(chunk: dict[str, Any]) -> str:
    entities = chunk.get("entities")
    if isinstance(entities, list):
        return " ".join(str(x) for x in entities)
    return ""


def chunk_text(chunk: dict[str, Any]) -> str:
    return str(chunk.get("text") or "")


def contains_any(value: str, terms: list[str]) -> bool:
    low = value.lower()
    return any(term.lower() in low for term in terms)


def appears_dialogue_rich(text: str) -> bool:
    if '"' in text or "'" in text:
        return True
    return bool(re.search(r"\b(said|asked|replied|whispered|shouted|answered|murmured)\b", text, re.I))


def sparse_or_weak(chunk: dict[str, Any]) -> bool:
    text = chunk_text(chunk).strip()
    entities = chunk.get("entities")
    return (
        not isinstance(entities, list)
        or not entities
        or len(text) < 400
        or contains_any(text, ["[music]", "subscribe", "patreon", "sponsor", "transcript"])
    )


def matches_stratum(chunk: dict[str, Any], stratum_id: str) -> bool:
    text = chunk_text(chunk)
    ents = entity_text(chunk)
    both = f"{ents}\n{text}"
    if stratum_id == "S1":
        return contains_any(ents, ["Horus"])
    if stratum_id == "S2":
        return contains_any(both, ["Emperor", "father", "judgment", "judgement"])
    if stratum_id == "S3":
        return contains_any(both, ["Sanguinius", "guilt", "brother"])
    if stratum_id == "S4":
        return contains_any(both, ["Davin", "Erebus", "Chaos", "corruption", "wound", "fall"])
    if stratum_id == "S5":
        return bool(chunk.get("is_chapter"))
    if stratum_id == "S6":
        return appears_dialogue_rich(text) and contains_any(both, ["Horus", "Warmaster", "Lupercal"])
    if stratum_id == "S7":
        return sparse_or_weak(chunk)
    if stratum_id == "S8":
        return not contains_any(both, ["Horus", "Emperor", "Sanguinius", "Davin", "Erebus", "Chaos"])
    raise ValueError(f"Unknown stratum {stratum_id}")


def selection_hash(stratum_id: str, chunk_id: str) -> str:
    return sha256_text(f"{SEED}|{stratum_id}|{chunk_id}")


def sample_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strata = [
        ("S1", "Horus explicit entity", 2),
        ("S2", "Emperor/father-judgment context", 2),
        ("S3", "Sanguinius/guilt/brother context", 2),
        ("S4", "Davin/Erebus/Chaos/corruption/fall context", 2),
        ("S5", "Chapter-level records", 2),
        ("S6", "Dialogue/voice-rich chunks", 2),
        ("S7", "Metadata/transcript weak-quality chunks", 2),
        ("S8", "No-obvious-persona negative controls", 2),
    ]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for stratum_id, label, count in strata:
        candidates = [c for c in chunks if c.get("_id") not in selected_ids and matches_stratum(c, stratum_id)]
        candidates.sort(key=lambda c: selection_hash(stratum_id, str(c.get("_id"))))
        for c in candidates[:count]:
            selected_ids.add(str(c.get("_id")))
            item = dict(c)
            item["stratum_id"] = stratum_id
            item["stratum_label"] = label
            item["selection_hash"] = selection_hash(stratum_id, str(c.get("_id")))
            item["text_sha256"] = sha256_text(chunk_text(c))
            selected.append(item)
        if len([x for x in selected if x["stratum_id"] == stratum_id]) != count:
            raise RuntimeError(f"Insufficient chunks for {stratum_id}: needed {count}, found {len(candidates)}")
    return selected


def schema() -> dict[str, Any]:
    required_top = [
        "schema_version",
        "batch_id",
        "item_id",
        "persona_id",
        "input_hashes",
        "source_chunk",
        "evidence",
        "entities",
        "lore_facts",
        "tom_states",
        "style_examples",
        "canon_rules",
        "graph_edges",
        "retrieval_units",
        "warnings",
        "empty_reason",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "persona_lore_extract.v1.schema.json",
        "title": "Persona lore extraction response",
        "type": "object",
        "additionalProperties": False,
        "required": required_top,
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "batch_id": {"type": "string", "minLength": 1},
            "item_id": {"type": "string", "minLength": 1},
            "persona_id": {"const": "horus"},
            "input_hashes": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_text_sha256", "source_metadata_sha256", "persona_card_sha256"],
                "properties": {
                    "source_text_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "source_metadata_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "persona_card_sha256": {"type": ["string", "null"]},
                },
            },
            "source_chunk": {"type": "object"},
            "evidence": {"type": "array"},
            "entities": {"type": "array"},
            "lore_facts": {"type": "array"},
            "tom_states": {"type": "array"},
            "style_examples": {"type": "array"},
            "canon_rules": {"type": "array"},
            "graph_edges": {"type": "array"},
            "retrieval_units": {"type": "array"},
            "warnings": {"type": "array"},
            "empty_reason": {"type": ["string", "null"]},
        },
    }


def expected_fixtures() -> dict[str, Any]:
    base = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": "fixture-batch",
        "item_id": "fixture-positive",
        "persona_id": "horus",
        "input_hashes": {
            "source_text_sha256": "0" * 64,
            "source_metadata_sha256": "1" * 64,
            "persona_card_sha256": None,
        },
        "source_chunk": {
            "source_chunk_id": "horus_lore_chunks/fixture",
            "source_collection": "horus_lore_chunks",
            "persona_id": "horus",
            "source_doc_id": "horus_lore_docs/fixture",
            "source_label": "fixture",
            "canon_status": "canonical",
            "span": {"start_sec": None, "end_sec": None, "line_start": None, "line_end": None},
        },
        "evidence": [
            {
                "local_id": "ev_001",
                "source_chunk_id": "horus_lore_chunks/fixture",
                "support": "explicit_canon",
                "short_quote": "Horus stood before the Emperor",
                "quote_word_count": 5,
                "quote_is_contiguous": True,
                "rationale": "The quote names Horus and the Emperor.",
            }
        ],
        "entities": [
            {"local_id": "ent_horus", "canonical_name": "Horus", "entity_type": "character", "aliases": ["Horus"], "evidence_refs": ["ev_001"]},
            {"local_id": "ent_emperor", "canonical_name": "The Emperor", "entity_type": "character", "aliases": ["Emperor"], "evidence_refs": ["ev_001"]},
        ],
        "lore_facts": [
            {
                "local_id": "fact_001",
                "subject_ref": "ent_horus",
                "predicate": "stood_before",
                "object_ref": "ent_emperor",
                "claim": "Horus stood before the Emperor.",
                "support": "explicit_canon",
                "confidence": 0.9,
                "canon_status": "canonical",
                "time_scope": {"start_event_ref": None, "end_event_ref": None, "source_temporal_label": None},
                "evidence_refs": ["ev_001"],
                "generation_use": {"safe_for_runtime_persona_packet": True, "safe_for_visual_prompt": False, "safe_for_dialogue_voice": False},
            }
        ],
        "tom_states": [],
        "style_examples": [],
        "canon_rules": [],
        "graph_edges": [
            {"local_id": "edge_001", "edge_type": "has_subject", "from_ref": "fact_001", "to_ref": "ent_horus", "evidence_refs": ["ev_001"]}
        ],
        "retrieval_units": [
            {
                "local_id": "ru_001",
                "record_local_ref": "fact_001",
                "record_type": "lore_fact",
                "title": "Horus before the Emperor",
                "text": "Horus stood before the Emperor.",
                "text_source_refs": ["fact_001"],
                "entity_refs": ["ent_horus", "ent_emperor"],
                "tags": ["Horus", "Emperor"],
                "generation_use": {"safe_for_runtime_persona_packet": True, "safe_for_visual_prompt": False, "safe_for_dialogue_voice": False},
            }
        ],
        "warnings": [],
        "empty_reason": None,
    }
    empty = dict(base)
    empty.update(
        {
            "item_id": "fixture-empty",
            "evidence": [],
            "entities": [],
            "lore_facts": [],
            "tom_states": [],
            "style_examples": [],
            "canon_rules": [],
            "graph_edges": [],
            "retrieval_units": [],
            "warnings": ["no persona-relevant source claims"],
            "empty_reason": "no_persona_relevant_claims",
        }
    )
    return {
        "positive": base,
        "negative_empty": empty,
        "invalid_missing_empty_reason": {**empty, "empty_reason": None, "warnings": []},
        "invalid_long_quote": {
            **base,
            "evidence": [
                {
                    **base["evidence"][0],
                    "short_quote": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen",
                    "quote_word_count": 19,
                }
            ],
        },
    }


def local_refs(obj: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("evidence", "entities", "lore_facts", "tom_states", "style_examples", "canon_rules", "graph_edges", "retrieval_units"):
        for item in obj.get(key, []) if isinstance(obj.get(key), list) else []:
            if isinstance(item, dict) and isinstance(item.get("local_id"), str):
                refs.add(item["local_id"])
    return refs


def require_refs(errors: list[str], refs: list[Any], allowed: set[str], location: str) -> None:
    if not isinstance(refs, list):
        errors.append(f"{location} must be a list")
        return
    for ref in refs:
        if not isinstance(ref, str) or ref not in allowed:
            errors.append(f"{location} unresolved ref {ref!r}")


def validate_response(obj: Any, *, expected: dict[str, Any], source_text: str, stratum_id: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(obj, dict):
        return {"passed": False, "errors": ["response is not an object"], "warnings": warnings}

    required = schema()["required"]
    for key in required:
        if key not in obj:
            errors.append(f"missing top-level key {key}")
    extra = sorted(set(obj) - set(schema()["properties"]))
    if extra:
        errors.append(f"unexpected top-level keys: {extra}")
    if obj.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    for key in ("batch_id", "item_id", "persona_id"):
        if obj.get(key) != expected.get(key):
            errors.append(f"{key} mismatch: expected {expected.get(key)!r}, got {obj.get(key)!r}")

    hashes = obj.get("input_hashes")
    if not isinstance(hashes, dict):
        errors.append("input_hashes must be object")
    else:
        for key, value in expected.get("input_hashes", {}).items():
            if hashes.get(key) != value:
                errors.append(f"input_hashes.{key} mismatch")

    for key in ("evidence", "entities", "lore_facts", "tom_states", "style_examples", "canon_rules", "graph_edges", "retrieval_units", "warnings"):
        if key in obj and not isinstance(obj[key], list):
            errors.append(f"{key} must be array")

    refs = local_refs(obj)
    evidence_refs = {ev.get("local_id") for ev in obj.get("evidence", []) if isinstance(ev, dict)}
    for ev in obj.get("evidence", []) if isinstance(obj.get("evidence"), list) else []:
        if not isinstance(ev, dict):
            errors.append("evidence item must be object")
            continue
        quote = ev.get("short_quote")
        count = ev.get("quote_word_count")
        if not isinstance(quote, str) or not quote.strip():
            errors.append("evidence.short_quote missing")
        else:
            actual_count = len(re.findall(r"\S+", quote))
            if count != actual_count:
                errors.append(f"evidence {ev.get('local_id')} quote_word_count mismatch")
            if actual_count > 18:
                errors.append(f"evidence {ev.get('local_id')} quote exceeds 18 words")
            if quote.lower() not in source_text.lower():
                errors.append(f"evidence {ev.get('local_id')} quote not found contiguously in source")
        if ev.get("quote_is_contiguous") is not True:
            errors.append(f"evidence {ev.get('local_id')} quote_is_contiguous must be true")

    evidence_ref_locations = [
        ("entities", "evidence_refs"),
        ("lore_facts", "evidence_refs"),
        ("tom_states", "evidence_refs"),
        ("style_examples", "evidence_refs"),
        ("canon_rules", "evidence_refs"),
        ("graph_edges", "evidence_refs"),
    ]
    for section, ref_key in evidence_ref_locations:
        for item in obj.get(section, []) if isinstance(obj.get(section), list) else []:
            if isinstance(item, dict):
                require_refs(errors, item.get(ref_key, []), evidence_refs, f"{section}.{item.get('local_id')}.{ref_key}")

    for fact in obj.get("lore_facts", []) if isinstance(obj.get("lore_facts"), list) else []:
        if not isinstance(fact, dict):
            continue
        for ref_key in ("subject_ref", "object_ref"):
            ref = fact.get(ref_key)
            if ref is not None and ref not in refs:
                errors.append(f"lore_facts.{fact.get('local_id')}.{ref_key} unresolved ref {ref!r}")
        support = fact.get("support")
        confidence = fact.get("confidence")
        if support in {"weakly_implied", "inferred"} and isinstance(confidence, (int, float)) and confidence > 0.75:
            errors.append(f"lore_facts.{fact.get('local_id')} weak support has too-high confidence")

    for tom in obj.get("tom_states", []) if isinstance(obj.get("tom_states"), list) else []:
        if not isinstance(tom, dict):
            continue
        for key in ("holder_ref", "state_type", "truth_status", "knowledge_status", "time_scope", "visibility"):
            if key not in tom:
                errors.append(f"tom_states.{tom.get('local_id')} missing {key}")
        if tom.get("holder_ref") not in refs:
            errors.append(f"tom_states.{tom.get('local_id')}.holder_ref unresolved")
        require_refs(errors, tom.get("target_refs", []), refs, f"tom_states.{tom.get('local_id')}.target_refs")

    for ru in obj.get("retrieval_units", []) if isinstance(obj.get("retrieval_units"), list) else []:
        if not isinstance(ru, dict):
            continue
        record_ref = ru.get("record_local_ref")
        if record_ref not in refs:
            errors.append(f"retrieval_units.{ru.get('local_id')}.record_local_ref unresolved")
        require_refs(errors, ru.get("text_source_refs", []), refs, f"retrieval_units.{ru.get('local_id')}.text_source_refs")
        text = str(ru.get("text") or "")
        if "Horus was bald" in text and "bald" not in source_text.lower():
            warnings.append(f"retrieval_units.{ru.get('local_id')} may have projected persona-card visual constraint into source extraction")

    substantive_sections = ["entities", "lore_facts", "tom_states", "style_examples", "canon_rules", "graph_edges", "retrieval_units"]
    substantive_count = sum(len(obj.get(key, [])) for key in substantive_sections if isinstance(obj.get(key), list))
    if substantive_count == 0:
        if not obj.get("empty_reason") or not obj.get("warnings"):
            errors.append("empty output requires empty_reason and warnings")
    elif obj.get("empty_reason") is not None:
        errors.append("non-empty output must set empty_reason null")

    if stratum_id == "S8" and substantive_count > 0:
        errors.append("S8 negative control emitted substantive records")

    return {"passed": not errors, "errors": errors, "warnings": warnings}


def run_fixture_smoke(out_dir: Path) -> dict[str, Any]:
    fixtures = expected_fixtures()
    fixture_dir = out_dir / "fixtures"
    results: dict[str, Any] = {}
    source = "Horus stood before the Emperor."
    for name, payload in fixtures.items():
        write_json(fixture_dir / f"{name}.json", payload)
        result = validate_response(
            payload,
            expected={
                "batch_id": payload.get("batch_id"),
                "item_id": payload.get("item_id"),
                "persona_id": payload.get("persona_id"),
                "input_hashes": payload.get("input_hashes"),
            },
            source_text=source,
        )
        results[name] = result
    expected = {
        "positive": True,
        "negative_empty": True,
        "invalid_missing_empty_reason": False,
        "invalid_long_quote": False,
    }
    passed = all(results[name]["passed"] == want for name, want in expected.items())
    report = {"passed": passed, "expected": expected, "results": results}
    write_json(out_dir / "fixture_validator_report.json", report)
    return report


def render_prompt(batch_id: str, item_id: str, chunk: dict[str, Any], persona_card: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    source_text = chunk_text(chunk)
    source_metadata = {
        key: chunk.get(key)
        for key in ("_id", "_key", "doc_id", "parent_book_id", "chunk_index", "source", "source_meta", "entities", "is_chapter")
    }
    persona_card_text = json.dumps(persona_card, sort_keys=True) if persona_card else ""
    input_hashes = {
        "source_text_sha256": sha256_text(source_text),
        "source_metadata_sha256": sha256_text(json.dumps(source_metadata, sort_keys=True)),
        "persona_card_sha256": sha256_text(persona_card_text) if persona_card else None,
    }
    response_skeleton = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "item_id": item_id,
        "persona_id": "horus",
        "input_hashes": input_hashes,
        "source_chunk": {
            "source_chunk_id": source_metadata.get("_id"),
            "source_collection": "horus_lore_chunks",
            "persona_id": "horus",
            "source_doc_id": f"horus_lore_docs/{source_metadata.get('doc_id')}" if source_metadata.get("doc_id") else None,
            "source_label": "Use source/source_meta fields to summarize provenance",
            "canon_status": "canonical",
            "span": {"start_sec": None, "end_sec": None, "line_start": None, "line_end": None},
        },
        "evidence": [
            {
                "local_id": "ev_001",
                "source_chunk_id": source_metadata.get("_id"),
                "support": "explicit_canon",
                "short_quote": "contiguous quote from source text",
                "quote_word_count": 5,
                "quote_is_contiguous": True,
                "rationale": "Why this evidence supports only the referenced record.",
            }
        ],
        "entities": [
            {
                "local_id": "ent_001",
                "canonical_name": "Entity name from source",
                "entity_type": "character|faction|place|event|concept|object",
                "aliases": ["source aliases only"],
                "evidence_refs": ["ev_001"],
            }
        ],
        "lore_facts": [
            {
                "local_id": "fact_001",
                "subject_ref": "ent_001",
                "predicate": "atomic_predicate",
                "object_ref": None,
                "claim": "One neutral objective claim supported by evidence.",
                "support": "explicit_canon",
                "confidence": 0.9,
                "canon_status": "canonical",
                "time_scope": {"start_event_ref": None, "end_event_ref": None, "source_temporal_label": None},
                "evidence_refs": ["ev_001"],
                "generation_use": {
                    "safe_for_runtime_persona_packet": True,
                    "safe_for_visual_prompt": False,
                    "safe_for_dialogue_voice": False,
                },
            }
        ],
        "tom_states": [],
        "style_examples": [],
        "canon_rules": [],
        "graph_edges": [
            {
                "local_id": "edge_001",
                "edge_type": "has_subject",
                "from_ref": "fact_001",
                "to_ref": "ent_001",
                "evidence_refs": ["ev_001"],
            }
        ],
        "retrieval_units": [
            {
                "local_id": "ru_001",
                "record_local_ref": "fact_001",
                "record_type": "lore_fact",
                "title": "Short title",
                "text": "Search-facing rendering of fact_001 only.",
                "text_source_refs": ["fact_001"],
                "entity_refs": ["ent_001"],
                "tags": ["source-backed"],
                "generation_use": {
                    "safe_for_runtime_persona_packet": True,
                    "safe_for_visual_prompt": False,
                    "safe_for_dialogue_voice": False,
                },
            }
        ],
        "warnings": [],
        "empty_reason": None,
    }
    empty_skeleton = {
        **response_skeleton,
        "evidence": [],
        "entities": [],
        "lore_facts": [],
        "tom_states": [],
        "style_examples": [],
        "canon_rules": [],
        "graph_edges": [],
        "retrieval_units": [],
        "warnings": ["No persona-relevant source-backed claims found."],
        "empty_reason": "no_persona_relevant_claims",
    }
    instructions = f"""
You extract source-backed persona lore records for persona-dream.
Return exactly one JSON object. No Markdown. No prose outside JSON.

Hard contract:
- schema_version must be "{SCHEMA_VERSION}".
- batch_id must be "{batch_id}".
- item_id must be "{item_id}".
- persona_id must be "horus".
- input_hashes must equal the supplied hashes exactly.
- Use only source text and the optional project persona card.
- Do not use general Warhammer/Horus knowledge unless directly present in the source text or project persona card.
- Keep evidence quotes contiguous, copied from source text, and 18 words or fewer.
- If no persona-relevant claim is supported, emit empty arrays, warnings, and empty_reason = "no_persona_relevant_claims".
- Do not put subjective beliefs, fears, desires, guilt, secrets, or intentions in lore_facts; use tom_states.
- Persona-card visual rules may produce canon_rules only with canon_status "project_canonical"; do not label them external canonical lore.
- retrieval_units must not introduce new information and must cite text_source_refs.

Required top-level keys:
schema_version, batch_id, item_id, persona_id, input_hashes, source_chunk, evidence,
entities, lore_facts, tom_states, style_examples, canon_rules, graph_edges,
retrieval_units, warnings, empty_reason.

Reference rules:
- Every evidence item must be an object with a string local_id like "ev_001"; never use bare numbers.
- evidence_refs must be arrays of local_id strings like ["ev_001"]; never use [0] or [1].
- subject_ref, object_ref, holder_ref, target_refs, from_ref, to_ref, record_local_ref, text_source_refs, and entity_refs must use local_id strings emitted in this same object.
- Every record in entities, lore_facts, tom_states, style_examples, canon_rules, graph_edges, and retrieval_units must have a local_id.
- If you emit no substantive records, use the empty response skeleton exactly.

JSON SCHEMA:
{json.dumps(schema(), indent=2, sort_keys=True)}

VALID RESPONSE SKELETON:
{json.dumps(response_skeleton, indent=2, sort_keys=True)}

VALID EMPTY RESPONSE SKELETON:
{json.dumps(empty_skeleton, indent=2, sort_keys=True)}
"""
    user_payload = {
        "batch_id": batch_id,
        "item_id": item_id,
        "persona_id": "horus",
        "input_hashes": input_hashes,
        "source_chunk_metadata": source_metadata,
        "project_persona_card": persona_card,
        "source_text": source_text[:5000],
    }
    return input_hashes, instructions.strip() + "\n\nSOURCE BUNDLE JSON:\n" + json.dumps(user_payload, indent=2, sort_keys=True)


def parse_model_json(text: str) -> tuple[Any | None, str | None]:
    stripped = text.strip()
    if not stripped:
        return None, "empty response"
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(stripped[start : end + 1]), None
            except json.JSONDecodeError:
                pass
        return None, str(exc)


def run_stream_call(request_path: Path, out_dir: Path, timeout_s: int) -> dict[str, Any]:
    args = [
        "python3",
        str(SCILLM_STREAM_SCRIPT),
        "--request",
        str(request_path),
        "--out-dir",
        str(out_dir),
        "--caller",
        "persona-dream",
    ]
    started = time.time()
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s + 90, check=False)
    return {
        "args": args,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a no-write Horus lore extraction canary.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--batch-id", default="persona-dream-horus-canary-v1")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-calls", type=int, default=3, help="Live DeepSeek calls to run from the 16 sampled chunks. Use 16 for full canary.")
    parser.add_argument("--timeout-s", type=int, default=600)
    parser.add_argument("--no-execute", action="store_true", help="Only sample and write prompts; do not call scillm.")
    args = parser.parse_args()

    run_id = args.run_id or f"lore-canary-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    out_dir = args.output_dir or Path("/tmp/persona-dream") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    db = get_db()
    evidence = {
        "created_at": now_iso(),
        "run_id": run_id,
        "mode": "no_write_horus_lore_canary",
        "collections": {
            "personas": collection_count(db, "personas"),
            "horus_lore_docs": collection_count(db, "horus_lore_docs"),
            "horus_lore_chunks": collection_count(db, "horus_lore_chunks"),
            "retrieval_units": collection_count(db, "retrieval_units"),
            "tom_states": collection_count(db, "tom_states"),
            "lore_facts": collection_count(db, "lore_facts"),
            "style_examples": collection_count(db, "style_examples"),
        },
        "writes_enabled": False,
    }
    write_json(out_dir / "source_probe.json", evidence)
    write_json(out_dir / "schema" / "persona_lore_extract.v1.schema.json", schema())
    fixture_report = run_fixture_smoke(out_dir)

    persona_card = fetch_horus_persona(db)
    if persona_card is not None:
        write_json(out_dir / "horus_persona_card.json", persona_card)

    chunks = fetch_candidate_chunks(db)
    selected = sample_chunks(chunks)
    sample_receipt = {
        "sample_plan_id": SAMPLE_PLAN_ID,
        "seed": SEED,
        "algorithm": "sha256_sort(seed|stratum_id|chunk_id)",
        "total": len(selected),
        "selected": [
            {
                "stratum_id": item["stratum_id"],
                "stratum_label": item["stratum_label"],
                "_id": item.get("_id"),
                "_key": item.get("_key"),
                "doc_id": item.get("doc_id"),
                "parent_book_id": item.get("parent_book_id"),
                "chunk_index": item.get("chunk_index"),
                "source": item.get("source"),
                "source_meta": item.get("source_meta"),
                "entities": item.get("entities"),
                "is_chapter": item.get("is_chapter"),
                "text_sha256": item["text_sha256"],
                "selection_hash": item["selection_hash"],
                "text_chars": len(chunk_text(item)),
            }
            for item in selected
        ],
    }
    write_json(out_dir / "sample_receipt.json", sample_receipt)

    call_limit = max(0, min(args.max_calls, len(selected)))
    call_results: list[dict[str, Any]] = []
    for idx, chunk in enumerate(selected[:call_limit], 1):
        item_id = f"{chunk['stratum_id']}-{idx:04d}"
        call_dir = out_dir / "calls" / item_id
        call_dir.mkdir(parents=True, exist_ok=True)
        input_hashes, prompt = render_prompt(args.batch_id, item_id, chunk, persona_card)
        request = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a strict JSON extraction engine. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 2200,
            "metadata": {"batch_id": args.batch_id, "item_id": item_id, "stratum_id": chunk["stratum_id"]},
            "timeout": args.timeout_s,
        }
        write_json(call_dir / "request.json", request)
        write_json(call_dir / "expected_identity.json", {
            "batch_id": args.batch_id,
            "item_id": item_id,
            "persona_id": "horus",
            "input_hashes": input_hashes,
        })
        (call_dir / "source_text.txt").write_text(chunk_text(chunk), encoding="utf-8")
        write_json(call_dir / "source_chunk.json", chunk)
        if args.no_execute:
            call_results.append({"item_id": item_id, "status": "not_run", "reason": "no_execute"})
            continue
        stream_dir = call_dir / "stream"
        run_result = run_stream_call(call_dir / "request.json", stream_dir, args.timeout_s)
        write_json(call_dir / "stream_run.json", run_result)
        content_path = stream_dir / "content.txt"
        content = content_path.read_text(encoding="utf-8") if content_path.exists() else ""
        (call_dir / "raw_response.txt").write_text(content, encoding="utf-8")
        parsed, parse_error = parse_model_json(content)
        if parsed is not None:
            write_json(call_dir / "parsed_response.json", parsed)
        validation = (
            validate_response(parsed, expected=read_json(call_dir / "expected_identity.json"), source_text=chunk_text(chunk), stratum_id=chunk["stratum_id"])
            if parsed is not None
            else {"passed": False, "errors": [f"json_parse_failed: {parse_error}"], "warnings": []}
        )
        write_json(call_dir / "validation.json", validation)
        call_results.append({
            "item_id": item_id,
            "stratum_id": chunk["stratum_id"],
            "status": "passed" if validation["passed"] else "failed",
            "stream_returncode": run_result["returncode"],
            "content_chars": len(content),
            "validation": validation,
            "artifact_dir": str(call_dir),
        })

    passed_calls = sum(1 for item in call_results if item.get("status") == "passed")
    failed_calls = sum(1 for item in call_results if item.get("status") == "failed")
    report = {
        "schema": "persona_dream.lore_canary_report.v1",
        "created_at": now_iso(),
        "run_id": run_id,
        "output_dir": str(out_dir),
        "status": "passed" if fixture_report["passed"] and call_results and failed_calls == 0 and passed_calls == call_limit else "pending_or_failed",
        "writes_enabled": False,
        "model": args.model,
        "batch_id": args.batch_id,
        "sample_total": len(selected),
        "live_call_limit": call_limit,
        "live_calls_passed": passed_calls,
        "live_calls_failed": failed_calls,
        "fixture_validator_passed": fixture_report["passed"],
        "source_probe": str(out_dir / "source_probe.json"),
        "schema_path": str(out_dir / "schema" / "persona_lore_extract.v1.schema.json"),
        "sample_receipt": str(out_dir / "sample_receipt.json"),
        "call_results": call_results,
        "next_step": (
            "Run with --max-calls 16 after fixing failed call outputs."
            if failed_calls
            else "Inspect call artifacts, then increase --max-calls toward 16 before any Arango upsert."
        ),
    }
    write_json(out_dir / "validation_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
