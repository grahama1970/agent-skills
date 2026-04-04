"""Grammarly-like sentence markup with NVIS confidence colors.

Decomposes question text into annotated fragments. Each entity gets a
confidence level (GREEN/AMBER/RED/YELLOW) based on grounding evidence
from /extract-entities.

Thin CLI wrapper — all logic lives in graph_memory.entity_extraction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console
from rich.text import Text

app = typer.Typer(
    name="create-sentence-markup",
    help="NVIS-colored sentence annotation from entity grounding evidence.",
    no_args_is_help=True,
)
console = Console()

# NVIS colors (MIL-STD-3009)
NVIS = {
    "GREEN": {"rgb": (0, 255, 136), "hex": "#00FF88", "rich": "green"},
    "AMBER": {"rgb": (255, 170, 0), "hex": "#FFAA00", "rich": "yellow"},
    "RED": {"rgb": (255, 68, 68), "hex": "#FF4444", "rich": "red"},
    "YELLOW": {"rgb": (255, 230, 0), "hex": "#FFE600", "rich": "bright_yellow"},
}


def _render_json(text: str, annotations: list[dict[str, Any]]) -> str:
    """Machine-readable JSON output."""
    summary = {"total_annotations": len(annotations)}
    for level in ("RED", "AMBER", "YELLOW", "GREEN"):
        summary[level.lower()] = sum(1 for a in annotations if a.get("level") == level)
    summary["needs_clarify"] = sum(1 for a in annotations if a.get("action") == "clarify")
    summary["needs_reject"] = sum(1 for a in annotations if a.get("action") == "reject")

    return json.dumps({
        "text": text,
        "annotations": annotations,
        "summary": summary,
    }, indent=2, default=str)


def _render_markdown(text: str, annotations: list[dict[str, Any]]) -> str:
    """Markdown output with inline annotations."""
    level_emoji = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴", "YELLOW": "🟡"}

    # Apply longest-first to avoid partial matches
    replacements: list[tuple[str, str]] = []
    for ann in sorted(annotations, key=lambda a: -len(a.get("term", ""))):
        term = ann["term"]
        level = ann.get("level", "YELLOW")
        label = ann.get("label", "")
        emoji = level_emoji.get(level, "⚪")

        if level == "RED":
            replacements.append((term, f"**{term}** {emoji}*({label})*"))
        elif level == "AMBER":
            replacements.append((term, f"*{term}* {emoji}*({label})*"))
        elif level == "YELLOW":
            replacements.append((term, f"*{term}* {emoji}*({label})*"))
        else:  # GREEN
            replacements.append((term, f"**{term}** {emoji}"))

    result = text
    for original, replacement in replacements:
        result = result.replace(original, replacement, 1)

    return result


def _render_html(text: str, annotations: list[dict[str, Any]]) -> str:
    """HTML output with NVIS-colored spans."""
    replacements: list[tuple[str, str]] = []

    for ann in sorted(annotations, key=lambda a: -len(a.get("term", ""))):
        term = ann["term"]
        level = ann.get("level", "YELLOW")
        label = ann.get("label", "")
        color = NVIS.get(level, NVIS["YELLOW"])["hex"]

        if level == "RED":
            style = f"color:{color};font-weight:bold"
        elif level == "AMBER":
            style = f"color:{color};text-decoration:underline wavy"
        elif level == "YELLOW":
            style = f"color:{color};font-style:italic"
        else:
            style = f"color:{color};font-weight:bold"

        html = (
            f'<span style="{style}">{term}</span>'
            f' <span style="color:{color};font-size:0.85em">({label})</span>'
        )
        replacements.append((term, html))

    result = text
    for original, replacement in replacements:
        result = result.replace(original, replacement, 1)

    return result


@app.command()
def annotate(
    text: str = typer.Argument(..., help="Question text to annotate"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, markdown, html"),
    entities_json: Path | None = typer.Option(None, "--entities-json", "-e", help="Pre-computed entities JSON (skip extraction)"),
) -> None:
    """Annotate question text with NVIS-colored grounding evidence."""
    from graph_memory.entity_extraction import extract_entities, get_annotations

    if entities_json and entities_json.exists():
        # Use pre-computed entities from /extract-entities
        data = json.loads(entities_json.read_text())
        from graph_memory.entity_extraction import EntityExtractionResult
        result = EntityExtractionResult()
        result.misspellings = data.get("misspellings", [])
        result.unresolved_terms = data.get("unresolved_terms", [])
        result.not_in_corpus = data.get("not_in_corpus", [])
        result.resolution_map = data.get("resolution_map", {})
    else:
        # Run /extract-entities
        result = extract_entities(text)

    annotations = get_annotations(result)

    if format == "json":
        print(_render_json(text, annotations))
    elif format == "markdown":
        print(_render_markdown(text, annotations))
    elif format == "html":
        print(_render_html(text, annotations))
    else:
        console.print(f"[red]Unknown format: {format}. Use json, markdown, or html.[/]")
        raise typer.Exit(1)


@app.command()
def clarify(
    text: str = typer.Argument(..., help="Question text with potential misspellings"),
) -> None:
    """Detect misspellings and present "Did you mean?" via /interview.

    Composes /extract-entities for detection and /interview for human confirmation.
    Returns corrected text after human review.
    """
    from graph_memory.entity_extraction import extract_entities, get_annotations

    result = extract_entities(text)
    annotations = get_annotations(result)
    clarify_items = [a for a in annotations if a.get("action") == "clarify"]

    if not clarify_items:
        console.print("[green]No misspellings or ambiguous terms detected.[/]")
        print(json.dumps({"text": text, "corrected": text, "changes": []}, indent=2))
        return

    # Show what was found (stderr — keep stdout clean for JSON piping)
    err = Console(stderr=True)
    err.print(f"[bold]Found {len(clarify_items)} term(s) needing clarification:[/]")
    for item in clarify_items:
        level_color = NVIS.get(item.get("level", "AMBER"), NVIS["AMBER"])["rich"]
        err.print(f"  [{level_color}]{item['term']}[/] → {item.get('label', '?')}")

    # Output structured data for /interview to consume
    interview_questions = []
    for item in clarify_items:
        suggestion = item.get("suggestion", "")
        interview_questions.append({
            "id": f"clarify_{item['term']}",
            "header": item["term"][:12],
            "text": f"Did you mean '{suggestion}' instead of '{item['term']}'?",
            "options": [
                {"label": f"Yes — use {suggestion}", "description": f"Replace '{item['term']}' with '{suggestion}'"},
                {"label": f"No — keep {item['term']}", "description": "The original term is correct"},
            ],
            "multi_select": False,
        })

    print(json.dumps({
        "text": text,
        "clarify_items": clarify_items,
        "interview_questions": interview_questions,
    }, indent=2, default=str))


if __name__ == "__main__":
    app()
