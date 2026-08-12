#!/usr/bin/env python3
"""Merge interview response and scan metadata into canonical-intent.json.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(update_canonical_intent.cpython-312.pyc) after the .py source was lost (never
tracked in git, no disk copy survived). Faithful to the 3.12 disassembly. Now
TRACKED.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

import typer


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        pass
    starts = [m.start() for m in re.finditer(r"\{", text)]
    ends = [m.end() for m in re.finditer(r"\}", text)]
    for start in starts:
        for end in reversed(ends):
            if end <= start:
                continue
            try:
                return json.loads(text[start:end])
            except Exception:
                continue
    return {}


def read_json(path: pathlib.Path, default: Any) -> Any:
    if not path or not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_interview(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {"responses": {}}
    return extract_json(path.read_text(encoding="utf-8", errors="replace")) or {"responses": {}}


def read_text(path: pathlib.Path) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def response_value(responses: dict[str, Any], key: str) -> Any:
    item = responses.get(key)
    if item is None:
        return None
    if isinstance(item, dict):
        if item.get("other_text"):
            return item.get("other_text")
        return item.get("value")
    return item


def ensure_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    canonical: pathlib.Path = typer.Option(..., help="canonical-intent.json path"),
    review_map: pathlib.Path = typer.Option(..., help="review-map.json path"),
    interview_response: pathlib.Path = typer.Option(..., help="Interview response JSON path"),
    change_note: pathlib.Path = typer.Option(..., help="change-note.md path"),
    iteration: str = typer.Option(..., help="Current iteration ID"),
    out: pathlib.Path = typer.Option(..., help="Output path for updated canonical-intent.json"),
):
    canon = read_json(canonical, {})
    rmap = read_json(review_map, {})
    interview = read_interview(interview_response)
    responses = interview.get("responses", {}) if isinstance(interview, dict) else {}
    cnote = read_text(change_note)
    page = rmap.get("page", {})
    sections = rmap.get("sections", [])
    deep_sections = [
        s for s in sections
        if s.get("layer_guess") == "deep_dive"
        or s.get("role_guess") in frozenset({"appendix_or_deep_dive", "errata"})
    ]
    now = datetime.now(timezone.utc).isoformat()
    canon.setdefault("schema_version", "0.1.0")
    canon.setdefault("created_at", now)
    canon["updated_at"] = now
    canon["last_iteration"] = iteration
    canon.setdefault("history", [])
    canon["page"] = {
        "url": page.get("url"),
        "title": page.get("title"),
        "page_type_guess": page.get("page_type_guess"),
        "section_count": page.get("section_count"),
        "image_count": page.get("image_count"),
        "cta_count": page.get("cta_count"),
    }
    mappings = {
        "primary_goal": "primary_goal",
        "primary_reader": "primary_reader",
        "review_scope": "review_scope",
        "deep_dive_role": "deep_dive_role",
        "complexity_policy": "complexity_policy",
    }
    for response_key, canonical_key in mappings.items():
        value = response_value(responses, response_key)
        if value:
            canon[canonical_key] = value
    list_mappings = {
        "section_priorities": "section_priorities",
        "image_review_focus": "image_review_focus",
        "review_dimensions": "review_dimensions",
        "detected_warnings": "prioritized_warnings",
        "change_intent": "last_change_intent",
    }
    for response_key, canonical_key in list_mappings.items():
        value = response_value(responses, response_key)
        if value:
            canon[canonical_key] = ensure_list(value)
    if "primary_goal" not in canon:
        inferred_goal = (
            "Explain how something works"
            if page.get("page_type_guess") in frozenset({"technical_explainer", "documentation", "tutorial"})
            else "Clarify the page's primary message and user path"
        )
        canon["primary_goal"] = inferred_goal
    if "primary_reader" not in canon:
        canon["primary_reader"] = "Mixed audience"
    if "review_scope" not in canon:
        canon["review_scope"] = "Primary flow plus boundary to optional detail" if deep_sections else "Entire page"
    if "deep_dive_role" not in canon and deep_sections:
        canon["deep_dive_role"] = "Optional technical appendix"
    if "complexity_policy" not in canon:
        canon["complexity_policy"] = "Use progressive disclosure"
    if "review_dimensions" not in canon:
        canon["review_dimensions"] = [
            "First-impression clarity",
            "Narrative flow",
            "Visual hierarchy",
            "Image usefulness",
            "CTA clarity",
            "Accessibility and semantics",
        ]
    if cnote:
        canon.setdefault("change_notes", []).append({
            "iteration": iteration,
            "note": cnote,
            "recorded_at": now,
        })
    canon["intended_layers"] = []
    canon["intended_layers"].append({
        "name": "primary_flow",
        "purpose": "Primary explanation/user journey of the page.",
        "required_for_understanding": True,
    })
    if deep_sections:
        canon["intended_layers"].append({
            "name": "deep_dive_or_appendix",
            "purpose": canon.get("deep_dive_role", "Optional deeper detail."),
            "required_for_understanding": canon.get("deep_dive_role") == "Required part of the explanation",
        })
    canon["persistent_review_questions"] = [
        "Can the primary reader understand the page's main purpose quickly?",
        "Does the section order create a clear flow?",
        "Do images clarify the message rather than distract from it?",
        "Are CTAs or next steps obvious at the right moments?",
        "Are headings, landmarks, alt text, link labels, and dense sections accessible and scannable?",
    ]
    if deep_sections:
        canon["persistent_review_questions"].append(
            "If a deep-dive/appendix exists, is it clearly optional or clearly integrated "
            "according to the human-confirmed role?"
        )
    canon["history"].append({
        "iteration": iteration,
        "updated_at": now,
        "interview_completed": bool(interview.get("completed")) if isinstance(interview, dict) else False,
        "responses_present": sorted(list(responses.keys())),
        "change_note_present": bool(cnote),
    })
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(canon, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    app()
