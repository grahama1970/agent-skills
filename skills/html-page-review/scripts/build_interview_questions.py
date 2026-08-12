#!/usr/bin/env python3
"""Build interview-skill questions from a detected page map.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(build_interview_questions.cpython-312.pyc) after the .py source was lost (never
tracked in git, no disk copy survived). Faithful to the 3.12 disassembly. Now
TRACKED.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import typer


def read_json(path: pathlib.Path | None, default: Any) -> Any:
    if not path or not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_text(path: pathlib.Path) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def option(label: str, description: str) -> dict[str, str]:
    return {"label": label, "description": description}


def short(value: str, limit: int = 140) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit - 1] + "…"


def section_options(sections: list[dict[str, Any]], max_items: int = 16) -> list[dict[str, str]]:
    opts = []
    for section in sections[:max_items]:
        idx = section.get("index")
        heading = section.get("heading") or f"Section {idx}"
        role = section.get("role_guess") or "unclear"
        layer = section.get("layer_guess") or "unknown"
        desc = (
            f"Detected as {role}; layer={layer}; "
            f"images={section.get('image_count', 0)}; CTAs={section.get('cta_count', 0)}."
        )
        preview = section.get("text_preview") or ""
        if preview:
            desc += f" Preview: {short(preview, 120)}"
        opts.append(option(f"{idx}. {heading}", desc))
    if len(sections) > max_items:
        opts.append(option(
            "Other sections not listed",
            f"The scanner detected {len(sections)} sections; only the first {max_items} are listed here.",
        ))
    return opts


def preview_images(manifest: dict[str, Any], max_images: int = 6) -> list[str]:
    images = []
    for item in manifest.get("screenshots", []):
        files = item.get("files") or []
        if files:
            images.append(files[0])
        if len(images) >= max_images:
            return images
    return images


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    review_map: pathlib.Path = typer.Option(..., help="review-map.json from the page scan"),
    section_screenshots: pathlib.Path = typer.Option(..., help="section-screenshots.json manifest"),
    section_diff: pathlib.Path = typer.Option(..., help="section-diff.json for delta reviews"),
    canonical: pathlib.Path = typer.Option(..., help="canonical-intent.json path"),
    change_note: pathlib.Path = typer.Option(..., help="change-note.md text file"),
    out: pathlib.Path = typer.Option(..., help="Output JSON file for interview payload"),
):
    rmap = read_json(review_map, {})
    screenshot_manifest = read_json(section_screenshots, {})
    sdiff = read_json(section_diff, {})
    canon = read_json(canonical, {})
    cnote = read_text(change_note)

    page = rmap.get("page", {})
    sections = rmap.get("sections", [])
    warnings = rmap.get("warnings", [])
    deep_sections = [
        s for s in sections
        if s.get("layer_guess") == "deep_dive"
        or s.get("role_guess") in frozenset({"appendix_or_deep_dive", "errata"})
    ]
    image_heavy = page.get("image_count", 0) >= max(8, max(1, page.get("section_count", 1)) * 1.5)
    has_previous_intent = bool(canon)
    is_delta = bool(cnote) or sdiff.get("status") != "first_iteration"

    title = "HTML Page Review Setup"
    context_bits = [
        f"I scanned the rendered page '{page.get('title') or page.get('url') or 'untitled'}'.",
        f"Detected page type: {page.get('page_type_guess', 'unknown')}. "
        f"Detected sections: {page.get('section_count', len(sections))}. "
        f"Images: {page.get('image_count', 0)}. CTAs: {page.get('cta_count', 0)}.",
    ]
    if deep_sections:
        context_bits.append(
            "I detected a likely appendix/errata/deep-dive layer. Please confirm whether it is "
            "optional or required reading."
        )
    if image_heavy:
        context_bits.append(
            "The page appears image-heavy, so the review should consider image roles, captions, "
            "alt text, and copy-image alignment."
        )
    if has_previous_intent:
        context_bits.append(
            "A previous canonical intent exists and will be reused unless you override it here."
        )
    if cnote:
        context_bits.append(f"Human-reported changes: {cnote}")

    questions = []
    if is_delta:
        questions.append({
            "id": "change_intent",
            "header": "Changes",
            "text": "What should the re-review focus on for this iteration?",
            "recommendation": "Review the human-reported changes, detected structural diffs, and any affected surrounding flow.",
            "reason": "Re-reviews should not repeat the whole first-pass review unless the intent or structure changed substantially.",
            "options": [
                option("Validate the changed sections only", "Focus on the sections that changed and their immediate neighbors."),
                option("Validate changed sections plus overall flow", "Check whether the changes improved the page-level story and scan path."),
                option("Re-run a full page review", "Use when the page has been substantially redesigned."),
                option("Focus on previous high-severity issues", "Check whether earlier major issues were resolved."),
            ],
            "multi_select": True,
        })

    questions.append({
        "id": "primary_goal",
        "header": "Goal",
        "text": "What is the primary goal of this page?",
        "recommendation": "Confirm the page goal before reviewing clarity and design.",
        "reason": "A page can be clear for one goal and confusing for another; the review should judge the intended job.",
        "options": [
            option("Explain how something works", "Prioritize sequence, conceptual clarity, and section-to-section flow."),
            option("Convince visitors to take action", "Prioritize first-impression clarity, persuasion, trust, and CTA prominence."),
            option("Document a technical system", "Prioritize completeness, accuracy, anchors, examples, and implementation detail."),
            option("Showcase examples or visual work", "Prioritize image hierarchy, captions, scanning, and proof."),
            option("Train or onboard users", "Prioritize guided learning, progressive disclosure, and clear step outcomes."),
        ],
        "multi_select": False,
    })

    questions.append({
        "id": "primary_reader",
        "header": "Reader",
        "text": "Who is the primary reader?",
        "recommendation": canon.get("primary_reader") if canon.get("primary_reader") else "Choose the audience whose confusion would matter most.",
        "reason": "Design and technical depth should be reviewed against the intended reader, not a generic visitor.",
        "options": [
            option("Nontechnical first-time user", "Needs simple language, strong visual hierarchy, and minimal jargon."),
            option("Technical evaluator", "Can handle schemas/APIs but still needs a clean conceptual path."),
            option("Internal developer", "Needs implementation detail, edge cases, and debugging value."),
            option("Client or stakeholder", "Needs confidence, business value, proof, and a clear next step."),
            option("Mixed audience", "Needs progressive disclosure: simple main flow plus optional detail."),
        ],
        "multi_select": False,
    })

    questions.append({
        "id": "review_scope",
        "header": "Scope",
        "text": "What should receive the deepest review?",
        "recommendation": "Primary flow plus boundary to optional detail" if deep_sections else "Entire page",
        "reason": "Long pages benefit from scoped review so the feedback is actionable rather than generic.",
        "images": preview_images(screenshot_manifest, 4),
        "options": [
            option("Entire page", "Review all detected sections and page-level flow."),
            option("Primary flow only", "Focus on the main user journey and leave dense detail alone."),
            option("Primary flow plus boundary to optional detail", "Test whether simple and complex layers are separated correctly."),
            option("Appendix / errata / deep-dive only", "Focus on findability, organization, examples, and technical usefulness."),
            option("Changed sections only", "Use for a narrow re-review after targeted edits."),
        ],
        "multi_select": False,
    })

    if sections:
        questions.append({
            "id": "section_priorities",
            "header": "Sections",
            "text": "Which detected sections are most important to review?",
            "recommendation": "Select the sections that determine whether the page succeeds.",
            "reason": "The scanner found a section map; confirming priorities prevents the review from over-focusing on incidental sections.",
            "options": section_options(sections),
            "multi_select": True,
        })

    if deep_sections:
        questions.append({
            "id": "deep_dive_role",
            "header": "Deep Dive",
            "text": "How should the appendix/errata/deep-dive material be treated?",
            "recommendation": "Optional technical appendix unless required for understanding.",
            "reason": "The review should not penalize intentional complexity, but it should verify that complexity is correctly isolated and searchable.",
            "options": [
                option("Optional technical appendix", "The main page should be understandable without reading this section."),
                option("Required part of the explanation", "The review should treat it as part of the main learning path."),
                option("Correction log / errata", "The section should clearly distinguish corrections from core explanation."),
                option("Reference manual", "Prioritize anchors, subheadings, examples, and lookup value."),
                option("Implementation proof", "Prioritize trust, evidence, and technical credibility."),
            ],
            "multi_select": False,
        })

    questions.append({
        "id": "complexity_policy",
        "header": "Density",
        "text": "How should the reviewer handle dense or technical content?",
        "recommendation": "Use progressive disclosure: simplify the main flow, preserve detail in clearly labeled optional sections.",
        "reason": "Some complexity may be intentional and valuable; the review should distinguish necessary depth from avoidable confusion.",
        "options": [
            option("Simplify aggressively", "Flag jargon, dense blocks, and technical implementation details that slow first-time readers."),
            option("Use progressive disclosure", "Keep the main path simple while preserving optional detail for engaged readers."),
            option("Preserve technical density", "Only flag organization/findability issues, not complexity itself."),
            option("Review both separately", "Score main-flow clarity and deep-dive usefulness as separate layers."),
        ],
        "multi_select": False,
    })

    if image_heavy:
        questions.append({
            "id": "image_review_focus",
            "header": "Images",
            "text": "What should the image review emphasize?",
            "recommendation": "Check whether each major image clarifies the section's message and is labeled by role.",
            "reason": "Image-heavy pages often fail because visuals are impressive but their function is unclear.",
            "options": [
                option("Image usefulness", "Classify images as essential, supportive, decorative, redundant, or confusing."),
                option("Copy-image alignment", "Check whether headings/captions explain what each image means."),
                option("Alt text and accessibility", "Check meaningful alt text and decorative-image handling."),
                option("Visual rhythm and density", "Check whether images overwhelm, fragment, or improve the reading path."),
                option("Before/after or step evidence", "Check whether visual examples prove the process or outcome."),
            ],
            "multi_select": True,
        })

    questions.append({
        "id": "review_dimensions",
        "header": "Lens",
        "text": "Which review lenses matter most?",
        "recommendation": "Clarity, flow, visual hierarchy, image usefulness, CTA clarity, accessibility.",
        "reason": "This controls how the final feedback is prioritized.",
        "options": [
            option("First-impression clarity", "What a scanner understands in the first few seconds."),
            option("Narrative flow", "Whether the section order builds a coherent argument or learning path."),
            option("Visual hierarchy", "What draws attention first, second, and third."),
            option("Design polish", "Spacing, alignment, density, rhythm, and consistency."),
            option("CTA clarity", "Whether desired next actions are obvious and well timed."),
            option("Accessibility and semantics", "Headings, alt text, link labels, landmarks, and keyboard-friendly structure."),
            option("Mobile clarity", "Whether the page remains understandable on a narrow screen."),
            option("Technical accuracy / implementation clarity", "Whether technical sections are precise and connected to the main flow."),
        ],
        "multi_select": True,
    })

    if warnings:
        questions.append({
            "id": "detected_warnings",
            "header": "Warnings",
            "text": "The scanner detected possible issues. Which should be prioritized?",
            "recommendation": "Prioritize high-severity warnings and anything that affects the primary reader.",
            "reason": "Some automated warnings are intentional design choices; human confirmation prevents false positives.",
            "options": [option(w.get("code", "warning"), w.get("message", "")) for w in warnings[:10]],
            "multi_select": True,
        })

    payload = {
        "title": title,
        "context": " ".join(context_bits),
        "questions": questions,
        "metadata": {
            "generator": "html-page-review/scripts/build_interview_questions.py",
            "page_type_guess": page.get("page_type_guess"),
            "section_count": len(sections),
            "image_count": page.get("image_count", 0),
            "has_previous_intent": has_previous_intent,
            "is_delta_review": is_delta,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    app()
