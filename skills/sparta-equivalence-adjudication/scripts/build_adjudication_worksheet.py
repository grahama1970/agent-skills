#!/usr/bin/env python3
"""Render the SPARTA/F36 equivalence adjudication batch as a reviewer worksheet.

The worksheet is a markdown document a human/domain reviewer edits in place:
each item carries a fenced ```decision block whose fields the reviewer fills.
Filled worksheets are parsed by record_adjudication_decisions.py.
Rendering is read-only over the batch; it grants no compliance credit.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(build_adjudication_worksheet.cpython-312.pyc) after the .py source was lost
(never tracked in git, no disk copy survived). Faithful to the 3.12
disassembly. Now TRACKED.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_BATCH = Path("/tmp/f36-sparta-equivalence-adjudication-batch.v1.json")
DEFAULT_OUTPUT = Path("/tmp/f36-sparta-equivalence-adjudication-worksheet.v1.md")
GROUP_ORDER = [
    ("candidate_new_intent", "Candidate new intent (no plausible existing F36 candidate was nominated)"),
    ("blocked_incomplete_sparta_path", "Blocked: incomplete SPARTA path"),
    ("blocked_ambiguous_equivalence", "Blocked: ambiguous equivalence"),
]


def load_batch(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text())
    if doc.get("schema") != "f36.sparta_equivalence_adjudication_batch.v1":
        raise ValueError(f"unexpected batch schema: {doc.get('schema')}")
    return doc


def render_candidate(candidate: dict[str, Any]) -> list[str]:
    basis = candidate.get("nomination_basis") or {}
    tokens = ", ".join(basis.get("overlap_tokens") or [])
    return [
        f"- **{candidate.get('requirement_id')}** — {candidate.get('title')} "
        f"({candidate.get('requirement_type')}, {candidate.get('component_family_id')}, "
        f"review_state: {candidate.get('review_state')})",
        f"  - excerpt: {candidate.get('statement_excerpt')}",
        f"  - nomination: score {basis.get('score')}, overlap [{tokens}]",
        f"  - approved SPARTA edges: {candidate.get('approved_sparta_edge_count')}, "
        f"accepted evidence cases: {candidate.get('accepted_evidence_case_count')}",
    ]


def render_item(index: int, item: dict[str, Any]) -> list[str]:
    intent = item.get("expected_normalized_intent") or {}
    paths = (item.get("shared_obligation") or {}).get("sample_path_ids") or []
    tactics = sorted({p.get("tactic_id") for p in paths if p.get("tactic_id")})
    countermeasures = sorted({p.get("countermeasure_id") for p in paths if p.get("countermeasure_id")})
    lines = [
        f"### Item {index:03d} — `{item.get('review_item_id')}`",
        "",
        f"- disposition entering review: `{item.get('current_final_disposition')}`",
        f"- SPARTA requirement: `{item.get('sparta_requirement_id')}`",
        f"- intent excerpt: {intent.get('text_excerpt')}",
        f"- path completeness: `{item.get('path_completeness_state')}`, "
        f"profiles affected: {item.get('profile_count')}",
        f"- SPARTA path sample: tactics [{', '.join(tactics)}], "
        f"countermeasures [{', '.join(countermeasures)}]",
        f"- selection reasons: {', '.join(item.get('selection_reasons') or [])}",
        "",
    ]
    candidates = item.get("candidate_f36_requirements") or []
    if candidates:
        lines.append("Candidate existing F36 requirements:")
        lines.append("")
        for candidate in candidates:
            lines.extend(render_candidate(candidate))
        lines.append("")
    else:
        lines.append("Candidate existing F36 requirements: none nominated.")
        lines.append("")
    options = " | ".join(item.get("allowed_relation_options") or [])
    lines.extend([
        f"Allowed relations: `{options}`",
        "",
        "```decision",
        f"review_item_id: {item.get('review_item_id')}",
        "reviewer_identity: ",
        "relation: ",
        "matched_f36_requirement_id: ",
        "rationale: ",
        "```",
        "",
        "---",
        "",
    ])
    return lines


def build_worksheet(batch: dict[str, Any]) -> str:
    items = batch.get("batch_items") or []
    grouped: dict[str, list] = {key: [] for key, _ in GROUP_ORDER}
    for item in items:
        grouped.setdefault(item.get("current_final_disposition"), []).append(item)
    for group in grouped.values():
        group.sort(key=lambda i: str(i.get("review_item_id")))
    validation = batch.get("validation") or {}
    lines = [
        "# SPARTA/F36 Equivalence Adjudication Worksheet",
        "",
        f"Source batch artifact hash: `{validation.get('artifact_hash')}`",
        f"Batch items: {len(items)}. Decisions here record reviewer relations only; "
        "compliance credit stays 0 and generation stays blocked until accepted decisions exist.",
        "",
        "How to fill a decision block:",
        "",
        "- `reviewer_identity`: your name or handle (required for any decided item).",
        "- `relation`: exactly one of the item's allowed relations. Leave blank to skip the item.",
        "- `matched_f36_requirement_id`: required for exact_duplicate / equivalent / "
        "existing_narrower / existing_broader / complementary_partial; must be one of the "
        "item's nominated candidate IDs. Leave blank otherwise.",
        "- `rationale`: one or two sentences (required for any decided item).",
        "",
        "Reviewer guidance from the batch:",
        "",
    ]
    for key, text in sorted((batch.get("review_instructions") or {}).items()):
        lines.append(f"- **{key}**: {text}")
    lines.append("")
    index = 0
    for key, title in GROUP_ORDER:
        group = grouped.get(key) or []
        if not group:
            continue
        lines.extend([f"## {title} ({len(group)} items)", ""])
        for item in group:
            index += 1
            lines.extend(render_item(index, item))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    batch = load_batch(args.batch)
    worksheet = build_worksheet(batch)
    args.output.write_text(worksheet)
    items = batch.get("batch_items") or []
    validation = batch.get("validation") or {}
    print(json.dumps({
        "batch": str(args.batch),
        "output": str(args.output),
        "batch_items": len(items),
        "source_artifact_hash": validation.get("artifact_hash"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
