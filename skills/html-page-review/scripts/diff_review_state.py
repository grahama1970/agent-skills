#!/usr/bin/env python3
"""Diff two review-map.json files for iterative page re-review.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(diff_review_state.cpython-312.pyc) after the .py source was lost (never tracked
in git, no disk copy survived). Faithful to the 3.12 disassembly. Now TRACKED.
"""
from __future__ import annotations

import difflib
import json
import pathlib
import re
from typing import Any

import typer


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_heading(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"^\d+\.\s*", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def section_key(section: dict[str, Any]) -> str:
    heading = norm_heading(section.get("heading", ""))
    if heading:
        return heading
    return f"{section.get('index')}"


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=a, b=b).ratio()


def summarize(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": section.get("index"),
        "heading": section.get("heading"),
        "role_guess": section.get("role_guess"),
        "layer_guess": section.get("layer_guess"),
        "top": section.get("top"),
        "height": section.get("height"),
        "image_count": section.get("image_count"),
        "cta_count": section.get("cta_count"),
        "text_hash": section.get("text_hash"),
    }


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    previous: pathlib.Path = typer.Option(..., help="Previous review-map.json"),
    current: pathlib.Path = typer.Option(..., help="Current review-map.json"),
    out: pathlib.Path = typer.Option(..., help="Output diff JSON file"),
):
    prev = read_json(previous)
    cur = read_json(current)
    prev_sections = prev.get("sections", [])
    cur_sections = cur.get("sections", [])
    prev_by_key = {section_key(s): s for s in prev_sections}
    cur_by_key = {section_key(s): s for s in cur_sections}
    matched_prev = set()
    matched_cur = set()
    matches = []
    for key in sorted(set(prev_by_key) & set(cur_by_key)):
        matches.append((key, key, 1.0))
        matched_prev.add(key)
        matched_cur.add(key)
    for p_key in prev_by_key:
        if p_key in matched_prev:
            continue
        best_key = None
        best_score = 0.0
        for c_key in cur_by_key:
            if c_key in matched_cur:
                continue
            score = similarity(p_key, c_key)
            if score > best_score:
                best_score = score
                best_key = c_key
        if best_key and best_score >= 0.72:
            matches.append((p_key, best_key, best_score))
            matched_prev.add(p_key)
            matched_cur.add(best_key)
    added = [summarize(cur_by_key[k]) for k in cur_by_key if k not in matched_cur]
    removed = [summarize(prev_by_key[k]) for k in prev_by_key if k not in matched_prev]
    renamed = []
    changed = []
    moved = []
    for p_key, c_key, score in matches:
        p = prev_by_key[p_key]
        c = cur_by_key[c_key]
        if p_key != c_key:
            renamed.append({
                "from": summarize(p),
                "to": summarize(c),
                "similarity": round(score, 3),
            })
        changed_fields = []
        for field in ("text_hash", "image_count", "cta_count", "role_guess", "layer_guess", "code_block_count"):
            if p.get(field) != c.get(field):
                changed_fields.append({
                    "field": field,
                    "previous": p.get(field),
                    "current": c.get(field),
                })
        if changed_fields:
            changed.append({
                "previous": summarize(p),
                "current": summarize(c),
                "changed_fields": changed_fields,
            })
        if p.get("index") != c.get("index") or abs(float(p.get("top") or 0) - float(c.get("top") or 0)) > 300:
            moved.append({
                "previous": summarize(p),
                "current": summarize(c),
            })
    prev_page = prev.get("page", {})
    cur_page = cur.get("page", {})
    page_delta = {
        "section_count": {"previous": prev_page.get("section_count"), "current": cur_page.get("section_count")},
        "image_count": {"previous": prev_page.get("image_count"), "current": cur_page.get("image_count")},
        "cta_count": {"previous": prev_page.get("cta_count"), "current": cur_page.get("cta_count")},
        "page_height": {"previous": prev_page.get("page_height"), "current": cur_page.get("page_height")},
        "page_type_guess": {"previous": prev_page.get("page_type_guess"), "current": cur_page.get("page_type_guess")},
    }
    result = {
        "status": "compared",
        "previous_url": prev_page.get("url"),
        "current_url": cur_page.get("url"),
        "page_delta": page_delta,
        "added_sections": added,
        "removed_sections": removed,
        "renamed_sections": renamed,
        "changed_sections": changed,
        "moved_sections": moved,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "renamed": len(renamed),
            "changed": len(changed),
            "moved": len(moved),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    app()
