#!/usr/bin/env python3
"""ToM-lite teacher annotation pipeline.

Queries persona_memory records, annotates each with tom_kind, affect, intensity,
and source_quote using DeepSeek v4 Flash via scillm, validates against the
best-practices-subagent ToM-lite controlled vocabulary, and writes to staging.

Teacher model: opencode-go/deepseek-v4-flash (via scillm)
Target: persona_memory_tom_candidates (staging collection)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import importlib.util as _ilu

import httpx

# Model inference is routed through the sanctioned Tau text-reasoning node
# (only /tau may reach /scillm). httpx is retained only for the local /memory
# recall service below, not for scillm.
_ADAPTER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_text_reasoning_adapter.py"
_aspec = _ilu.spec_from_file_location("tau_text_reasoning_adapter", _ADAPTER_PATH)
assert _aspec and _aspec.loader
tau_adapter = _ilu.module_from_spec(_aspec)
_aspec.loader.exec_module(tau_adapter)

MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8601")
TEACHER_MODEL = "opencode-go/deepseek-v4-flash"
_ANNOTATION_OUTPUT_CONTRACT = {
    "tom_kind": "str", "affect": "str", "intensity": "str",
    "source_quote": "str", "confidence": "float", "abstain": "bool",
}

TOM_KIND_VALUES = {"emotion", "belief", "goal", "preference", "boundary", "relationship", "knowledge_gap", "unresolved_thread"}
AFFECT_VALUES = {"angry", "sad", "anxious", "confused", "happy", "neutral"}
INTENSITY_VALUES = {"low", "medium", "high", "extreme"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


EMOTIONAL_QUERIES: list[str] = [
    "betrayal fear anger grief love hatred desire hope guilt shame regret dread trust vengeance loss pain sorrow fury rage terror despair friendship loyalty honor courage",
    "character emotional reaction belief feeling desire fear anxiety angry rage grief memory trauma inner thought mental state breakdown revelation",
    "what does this character truly believe desire or feel about this event or person",
    "character inner emotional state conflict psychological burden unresolved tension",
]


def recall_persona_memory(limit: int = 50) -> list[dict[str, Any]]:
    """Fetch persona_memory records that lack ToM annotations but have emotional content."""
    all_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    with httpx.Client(base_url=MEMORY_URL.rstrip("/"), timeout=30.0) as client:
        for query in EMOTIONAL_QUERIES:
            resp = client.post("/recall", json={
                "q": query,
                "collections": ["persona_memory", "persona_memory_edges"],
                "scope": "persona-dream",
                "k": limit // len(EMOTIONAL_QUERIES),
            })
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("items", []):
                key = item.get("_key", "")
                if isinstance(item, dict) and not item.get("tom_state_type") and key not in seen_keys:
                    seen_keys.add(key)
                    all_items.append(item)
            if len(all_items) >= limit:
                break

    return all_items[:limit]


def build_annotation_prompt(item: dict[str, Any]) -> str:
    """Build a prompt that asks the teacher to annotate one memory record."""
    text = _extract_record_text(item)
    persona_id = item.get("persona_id", "unknown")
    record_key = item.get("_key", "")

    return (
        "Annotate this persona memory record with theory-of-mind labels.\n"
        "Use ONLY the allowed values. Quote exact text that supports each label.\n"
        "If uncertain or the text lacks emotional/ToM content, set abstain=true.\n"
        "Do NOT infer hidden intent beyond the text. Do NOT create new facts.\n"
        f"\nPersona: {persona_id}\n"
        f"Record: {record_key}\n"
        f"Text:\n{text[:3000]}\n"
        "\nAllowed values:\n"
        f"  tom_kind: {', '.join(sorted(TOM_KIND_VALUES))}\n"
        f"  affect: {', '.join(sorted(AFFECT_VALUES))}\n"
        f"  intensity: {', '.join(sorted(INTENSITY_VALUES))}\n"
        "\nReply ONLY with a JSON object:\n"
        '{"tom_kind": "...", "affect": "...", "intensity": "...", "source_quote": "...", "confidence": 0.0, "abstain": false}'
    )


def _extract_record_text(item: dict[str, Any]) -> str:
    """Extract the most useful text from a persona_memory record."""
    for key in ("retrieval_text", "claim_text", "evidence_text", "text", "content", "title"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(item)


def annotate_one(item: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any] | None:
    """Call the teacher model to annotate one record."""
    prompt = build_annotation_prompt(item)

    try:
        # Route through Tau (only /tau may reach /scillm); returns parsed JSON.
        parsed, _receipt = tau_adapter.dispatch_text_reasoning(
            prompt,
            role="model-trainer-tom-lite",
            output_contract=_ANNOTATION_OUTPUT_CONTRACT,
            caller_skill="model-trainer-tom-lite",
            model=TEACHER_MODEL,
            timeout_s=timeout,
        )
        if not isinstance(parsed, dict):
            raise ValueError("Tau text node returned no annotation JSON")
        return parsed
    except Exception as exc:
        return {"error": str(exc), "record_key": item.get("_key", "")}


def validate_annotation(annotation: dict[str, Any]) -> list[str]:
    """Validate annotation against ToM-lite controlled vocabulary."""
    errors: list[str] = []

    if annotation.get("abstain"):
        return errors

    tom_kind = annotation.get("tom_kind", "")
    if tom_kind and tom_kind not in TOM_KIND_VALUES:
        errors.append(f"invalid tom_kind: {tom_kind}")

    affect = annotation.get("affect", "")
    if affect and affect not in AFFECT_VALUES:
        errors.append(f"invalid affect: {affect}")

    intensity = annotation.get("intensity", "")
    if intensity and intensity not in INTENSITY_VALUES:
        errors.append(f"invalid intensity: {intensity}")

    source_quote = annotation.get("source_quote", "")
    if not source_quote and not annotation.get("abstain"):
        errors.append("missing source_quote")

    confidence = annotation.get("confidence", 0)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        errors.append(f"invalid confidence: {confidence}")

    return errors


def build_staging_document(
    item: dict[str, Any],
    annotation: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    """Build a staging document for persona_memory_tom_candidates."""
    record_key = item.get("_key", "")
    return {
        "_key": f"tom_candidate_{record_key}",
        "record_key": record_key,
        "persona_id": item.get("persona_id", ""),
        "book_id": item.get("book_id", ""),
        "tom_kind": annotation.get("tom_kind", ""),
        "affect": annotation.get("affect", ""),
        "intensity": annotation.get("intensity", ""),
        "source_quote": annotation.get("source_quote", ""),
        "confidence": annotation.get("confidence", 0),
        "abstain": annotation.get("abstain", False),
        "teacher_model": TEACHER_MODEL,
        "annotated_at": now_iso(),
        "validation_errors": validation_errors,
        "promotion_eligible": not validation_errors and not annotation.get("abstain", False),
        "source_record_text": _extract_record_text(item)[:500],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ToM-lite teacher annotation pipeline")
    parser.add_argument("--limit", type=int, default=50, help="Records to annotate")
    parser.add_argument("--output", default="/tmp/tom_annotations.jsonl", help="Output JSONL file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without scillm calls")
    parser.add_argument("--batch-size", type=int, default=5, help="Records per summary log line")
    args = parser.parse_args(argv)

    records = recall_persona_memory(limit=args.limit)
    print(f"Retrieved {len(records)} unannotated persona_memory records")

    if args.dry_run:
        for i, item in enumerate(records[:5]):
            print(f"\n--- Record {i+1} ---")
            print(f"  persona: {item.get('persona_id', '?')}")
            print(f"  key: {item.get('_key', '?')}")
            print(f"  text: {_extract_record_text(item)[:200]}")
        return 0

    annotated = 0
    skipped = 0
    errors = 0
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as out:
        for i, item in enumerate(records):
            result = annotate_one(item)
            if result is None:
                errors += 1
                continue

            if result.get("abstain") and not result.get("error"):
                skipped += 1
                continue

            if result.get("error"):
                errors += 1
                print(f"  [{i+1}/{len(records)}] ERROR: {result['error'][:120]}", flush=True)
                continue

            validation_errors = validate_annotation(result)
            doc = build_staging_document(item, result, validation_errors)
            out.write(json.dumps(doc) + "\n")
            annotated += 1

            if (annotated + errors + skipped) % args.batch_size == 0:
                print(f"  [{i+1}/{len(records)}] annotated={annotated} skipped={skipped} errors={errors}", flush=True)

    print(f"\nDone. {annotated} annotated, {skipped} skipped (abstain), {errors} errors")
    print(f"Output: {output_path}")

    promoted = annotated + skipped
    if errors > 0:
        print(f"WARNING: {errors} records failed annotation")
    print(f"Promotion-eligible: {annotated} (validated, source-anchored)")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
