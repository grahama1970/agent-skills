#!/usr/bin/env python3
"""Record human reviewer decisions from a filled adjudication worksheet.

Parses the ```decision blocks written by build_adjudication_worksheet.py,
validates them fail-closed against the source batch, and emits
f36.sparta_equivalence_reviewed_decisions.v1.

This artifact records reviewer relations only. It never grants compliance
credit and never sets generation_eligible.

Self-contained: the canonical/hash helpers below are copied verbatim from the
pi-mono pipeline (build_sparta_profile_denominator_delta.py) so artifact
hashing stays byte-compatible.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(record_adjudication_decisions.cpython-312.pyc) after the .py source was lost
(never tracked in git, no disk copy survived). Faithful to the 3.12
disassembly. Now TRACKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BATCH = Path("/tmp/f36-sparta-equivalence-adjudication-batch.v1.json")
DEFAULT_WORKSHEET = Path("/tmp/f36-sparta-equivalence-adjudication-worksheet.v1.md")
DEFAULT_OUTPUT = Path("/tmp/f36-sparta-equivalence-reviewed-decisions.v1.json")
MATCH_RELATIONS = {
    "equivalent",
    "exact_duplicate",
    "existing_broader",
    "existing_narrower",
    "complementary_partial",
}
DECISION_FIELDS = ("review_item_id", "reviewer_identity", "relation", "matched_f36_requirement_id", "rationale")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_artifact_hash(artifact: dict[str, Any]) -> str:
    stable = json.loads(canonical(artifact))
    stable["generated_at"] = "<volatile>"
    stable["validation"]["artifact_hash"] = None
    return sha256_text(canonical(stable))


def load_batch(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text())
    if doc.get("schema") != "f36.sparta_equivalence_adjudication_batch.v1":
        raise ValueError(f"unexpected batch schema: {doc.get('schema')}")
    return doc


def parse_decision_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    in_block = False
    current: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "```decision":
            in_block = True
            current = {}
            continue
        if in_block and stripped == "```":
            in_block = False
            blocks.append(current)
            continue
        if not in_block:
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        if key not in DECISION_FIELDS:
            continue
        current[key] = value.strip()
    if in_block:
        raise ValueError("unterminated ```decision block in worksheet")
    return blocks


def validate_decisions(blocks: list[dict[str, str]], batch: dict[str, Any]):
    items_by_id = {item.get("review_item_id"): item for item in (batch.get("batch_items") or [])}
    decided: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        item_id = block.get("review_item_id", "")
        item = items_by_id.get(item_id)
        if item is None:
            errors.append(f"unknown review_item_id: {item_id or '<missing>'}")
            continue
        if item_id in seen:
            errors.append(f"duplicate decision block for {item_id}")
            continue
        seen.add(item_id)
        relation = block.get("relation", "")
        if not relation:
            skipped.append({"review_item_id": item_id})
            continue
        allowed = item.get("allowed_relation_options") or []
        if relation not in allowed:
            errors.append(f"{item_id}: relation '{relation}' not in allowed options")
            continue
        matched = block.get("matched_f36_requirement_id", "")
        candidate_ids = item.get("candidate_f36_requirement_ids") or []
        if relation in MATCH_RELATIONS:
            if not matched:
                errors.append(f"{item_id}: relation '{relation}' requires matched_f36_requirement_id")
                continue
            if matched not in candidate_ids:
                errors.append(f"{item_id}: matched id '{matched}' is not a nominated candidate")
                continue
        elif matched:
            errors.append(f"{item_id}: matched_f36_requirement_id must be blank for relation '{relation}'")
            continue
        if not block.get("reviewer_identity"):
            errors.append(f"{item_id}: reviewer_identity is required for a decided item")
            continue
        if not block.get("rationale"):
            errors.append(f"{item_id}: rationale is required for a decided item")
            continue
        decided.append({
            "review_item_id": item_id,
            "sparta_requirement_id": item.get("sparta_requirement_id"),
            "disposition_entering_review": item.get("current_final_disposition"),
            "reviewer_identity": block.get("reviewer_identity"),
            "relation": relation,
            "matched_f36_requirement_id": matched or None,
            "rationale": block.get("rationale"),
        })
    return (decided, skipped, errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    batch = load_batch(args.batch)
    blocks = parse_decision_blocks(args.worksheet.read_text())
    decided, skipped, errors = validate_decisions(blocks, batch)
    relation_counts: dict[str, int] = {}
    for decision in decided:
        relation_counts[decision["relation"]] = relation_counts.get(decision["relation"], 0) + 1
    validation = batch.get("validation") or {}
    items = batch.get("batch_items") or []
    doc = {
        "schema": "f36.sparta_equivalence_reviewed_decisions.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_hashes": {
            "batch_artifact_hash": validation.get("artifact_hash"),
            "batch_file_sha256": sha256_file(args.batch),
            "worksheet_file_sha256": sha256_file(args.worksheet),
        },
        "decisions": sorted(decided, key=lambda d: d["review_item_id"]),
        "summary": {
            "batch_items": len(items),
            "decided_items": len(decided),
            "skipped_items": len(skipped),
            "relation_counts": dict(sorted(relation_counts.items())),
            "compliance_credit": 0,
            "generation_eligible_items": 0,
        },
        "validation": {
            "status": "pass" if not errors else "fail",
            "errors": errors,
            "warnings": [
                "reviewed decisions are relation records only, not compliance credit",
                "generation eligibility requires a separate accepted-decision pipeline step",
            ],
        },
    }
    doc["validation"]["artifact_hash"] = stable_artifact_hash(doc)
    args.output.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "decided_items": len(decided),
        "skipped_items": len(skipped),
        "errors": errors,
        "validation_status": doc["validation"]["status"],
    }, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
