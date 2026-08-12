#!/usr/bin/env python3
"""Build a GPT/WebGPT-ready review prompt from captured page evidence.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(build_review_prompt.cpython-312.pyc) after the .py source was lost (never
tracked in git, no disk copy survived). Faithful to the 3.12 disassembly. Now
TRACKED.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import typer


def read_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_text(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_None._\n"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("\n", "<br>") for x in row) + " |")
    return "\n".join(out) + "\n"


def short(value: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit - 1] + "…"


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    session_dir: pathlib.Path = typer.Option(..., help="Root session directory"),
    iteration_dir: pathlib.Path = typer.Option(..., help="Current iteration directory"),
    out: pathlib.Path = typer.Option(..., help="Output Markdown file for review prompt"),
):
    canonical = read_json(session_dir / "canonical-intent.json", {})
    review_map = read_json(iteration_dir / "scan" / "review-map.json", {})
    section_diff = read_json(iteration_dir / "scan" / "section-diff.json", {})
    screenshot_manifest = read_json(iteration_dir / "scan" / "section-screenshots.json", {})
    interview_response = read_json(iteration_dir / "interview" / "interview-response.json", {})
    change_note = read_text(iteration_dir / "change-note.md")
    visible_text_path = iteration_dir / "scan" / "visible-text.txt"
    accessibility_path = iteration_dir / "scan" / "accessibility-tree.txt"
    raw_screenshot_path = iteration_dir / "raw" / "desktop-full.png"

    page = review_map.get("page", {})
    sections = review_map.get("sections", [])
    warnings = review_map.get("warnings", [])
    image_inventory = review_map.get("image_inventory", [])
    cta_inventory = review_map.get("cta_inventory", [])

    section_rows = []
    for s in sections:
        section_rows.append([
            s.get("index"),
            s.get("heading"),
            s.get("role_guess"),
            s.get("layer_guess"),
            s.get("image_count"),
            s.get("cta_count"),
            short(s.get("text_preview", ""), 160),
        ])

    screenshot_rows = []
    for item in screenshot_manifest.get("screenshots", []):
        files = item.get("files") or []
        screenshot_rows.append([
            item.get("section_index"),
            item.get("heading"),
            item.get("layer_guess"),
            "<br>".join(files),
        ])

    warning_rows = [[w.get("severity"), w.get("code"), w.get("message")] for w in warnings]

    diff_summary = section_diff.get("summary") or {}
    added_rows = [
        [s.get("index"), s.get("heading"), s.get("role_guess"), s.get("layer_guess")]
        for s in section_diff.get("added_sections", [])
    ]
    removed_rows = [
        [s.get("index"), s.get("heading"), s.get("role_guess"), s.get("layer_guess")]
        for s in section_diff.get("removed_sections", [])
    ]
    changed_rows = []
    for c in section_diff.get("changed_sections", [])[:20]:
        current = c.get("current", {})
        fields = ", ".join(str(f.get("field")) for f in c.get("changed_fields", []))
        changed_rows.append([current.get("index"), current.get("heading"), fields])

    image_role_counts: dict[str, int] = {}
    for img in image_inventory:
        role = img.get("role_guess") or "unknown"
        image_role_counts[role] = image_role_counts.get(role, 0) + 1
    image_role_rows = [
        [role, count]
        for role, count in sorted(image_role_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    cta_rows = []
    for cta in cta_inventory[:30]:
        cta_rows.append([
            cta.get("section_index"),
            cta.get("tag"),
            cta.get("text"),
            cta.get("href") or "",
        ])

    prompt = "".join([
        "# HTML Page Review Request\n\nYou are reviewing a rendered HTML page for clarity, flow, structure, design, "
        "visual hierarchy, image usefulness, accessibility, and iteration-to-iteration improvement.\n\n"
        "Use the saved human intent as the review contract. Do not review against generic taste alone. "
        "Distinguish between content that is accidentally confusing and content that is intentionally dense or "
        "technical.\n\n## Evidence handling\n\nThis request references local evidence files generated by the "
        "`html-page-review` skill.\n\n"
        "- If your environment can inspect local image files, inspect the section screenshots listed below in "
        "order.\n"
        "- If your environment cannot inspect local files, ask the agent/human to attach the listed screenshots, "
        "especially the section screenshots and `desktop-full.png`.\n"
        "- If you cannot see the images, clearly mark visual/design conclusions as lower confidence and rely on "
        "the structural metadata, visible text, and accessibility tree.\n\n"
        "## Page summary\n\n| Field | Value |\n|---|---|\n| URL | ",
        f"{page.get('url') or ''}",
        " |\n| Title | ",
        f"{page.get('title') or ''}",
        " |\n| Page type guess | ",
        f"{page.get('page_type_guess') or ''}",
        " |\n| Sections | ",
        f"{page.get('section_count') or len(sections)}",
        " |\n| Images | ",
        f"{page.get('image_count') or len(image_inventory)}",
        " |\n| CTAs | ",
        f"{page.get('cta_count') or len(cta_inventory)}",
        " |\n| Viewport | ",
        f"{page.get('viewport_width')}",
        " × ",
        f"{page.get('viewport_height')}",
        " |\n| Page height | ",
        f"{page.get('page_height')}",
        " |\n\n## Saved human intent / review contract\n\n```json\n",
        f"{json.dumps(canonical, indent=2, ensure_ascii=False)}",
        "\n```\n\n## Human-reported changes for this iteration\n\n",
        f"{change_note or '_No explicit change note was provided._'}",
        "\n\n## Interview response for this iteration\n\n```json\n",
        f"{json.dumps(interview_response, indent=2, ensure_ascii=False)}",
        "\n```\n\n## Iteration diff summary\n\n```json\n",
        f"{json.dumps(diff_summary, indent=2, ensure_ascii=False)}",
        "\n```\n\n### Added sections\n\n",
        f"{md_table(['Index', 'Heading', 'Role', 'Layer'], added_rows)}",
        "\n\n### Removed sections\n\n",
        f"{md_table(['Index', 'Heading', 'Role', 'Layer'], removed_rows)}",
        "\n\n### Changed sections\n\n",
        f"{md_table(['Index', 'Heading', 'Changed fields'], changed_rows)}",
        "\n\n## Detected section map\n\n",
        f"{md_table(['#', 'Heading', 'Role guess', 'Layer guess', 'Images', 'CTAs', 'Preview'], section_rows)}",
        "\n\n## Section screenshots to inspect\n\n",
        f"{md_table(['Section', 'Heading', 'Layer', 'Screenshot file(s)'], screenshot_rows)}",
        "\n\nFull-page screenshot:\n\n```text\n",
        f"{raw_screenshot_path}",
        "\n```\n\nVisible text file:\n\n```text\n",
        f"{visible_text_path}",
        "\n```\n\nAccessibility tree file:\n\n```text\n",
        f"{accessibility_path}",
        "\n```\n\n## Image role counts\n\n",
        f"{md_table(['Role guess', 'Count'], image_role_rows)}",
        "\n\n## CTA inventory\n\n",
        f"{md_table(['Section', 'Tag', 'Text', 'Href'], cta_rows)}",
        "\n\n## Automated scan warnings\n\n",
        f"{md_table(['Severity', 'Code', 'Message'], warning_rows)}",
        "\n\n# Review tasks\n\nReturn a review with the following sections:\n\n"
        "1. **One-paragraph summary** of what the page appears to explain or sell.\n"
        "2. **Fit to saved intent**: whether the page currently satisfies the human-confirmed goal, audience, "
        "scope, and complexity policy.\n"
        "3. **First-impression clarity score** from 1–10.\n"
        "4. **Narrative / flow score** from 1–10.\n"
        "5. **Visual hierarchy / design score** from 1–10. If you cannot inspect images, say so and lower "
        "confidence.\n"
        "6. **Image usefulness score** from 1–10 for image-heavy pages. Classify major images/sections as "
        "essential, supportive, decorative, redundant, or confusing.\n"
        "7. **Accessibility / semantic clarity score** from 1–10.\n"
        "8. **Iteration delta**: what improved, regressed, or became newly unclear since the previous "
        "iteration.\n"
        "9. **Top 5 high-priority issues**, with section, evidence, why it matters, and concrete fix.\n"
        "10. **Section-by-section issue table** with severity, evidence, recommendation, and example improved "
        "copy/layout where useful.\n"
        "11. **Recommended revised structure**, especially if the page should separate primary flow from "
        "appendix/deep-dive material.\n"
        "12. **Action checklist**: the smallest set of changes likely to improve the next review round.\n\n"
        "## Special review rules\n\n"
        "- A dense appendix, errata, or technical deep-dive should not be penalized merely for being complex. "
        "Judge whether it is clearly labeled, optional/required as intended, searchable, and connected back to "
        "the main flow.\n"
        "- For long pages, prioritize the first screen, section transitions, anchors/TOC, repeated CTAs, and "
        "whether each section has a clear role.\n"
        "- For image-heavy pages, verify that images have understandable roles and that headings/captions "
        "explain what users should learn from each visual.\n"
        "- For re-reviews, explicitly compare against the diff and the human-reported changes rather than "
        "starting from scratch.\n",
    ])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")


if __name__ == "__main__":
    app()
