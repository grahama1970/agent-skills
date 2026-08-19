"""Safely inspect SVG corpora and extract reusable visual-system evidence.

The extractor does not execute SVG content. It reports measured frequencies rather than
claiming that every discovered token belongs in a final theme.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import tinycss2
from defusedxml import ElementTree as SafeElementTree
from loguru import logger

HEX_COLOR_GRAMMAR = re.compile(r"#[0-9A-Fa-f]{6}\b")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sources(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(candidate for candidate in path.rglob("*.svg") if candidate.is_file())
        elif path.suffix.lower() == ".svg":
            files.add(path)
        else:
            raise ValueError(f"inspect accepts SVG files or directories: {path}")
    if not files:
        raise ValueError("no SVG files found")
    return tuple(sorted(file.resolve() for file in files))


def _css_values(style_text: str) -> tuple[list[str], list[str], list[str]]:
    fonts: list[str] = []
    durations: list[str] = []
    keyframes: list[str] = []
    rules = tinycss2.parse_stylesheet(style_text, skip_comments=True, skip_whitespace=True)
    for rule in rules:
        if getattr(rule, "type", "") == "error":
            raise ValueError(f"CSS parse error: {rule.message}")
        if getattr(rule, "at_keyword", "").lower() == "keyframes":
            keyframes.append(tinycss2.serialize(rule.prelude).strip())
        content = getattr(rule, "content", None)
        if not isinstance(content, list):
            continue
        declarations = tinycss2.parse_declaration_list(content, skip_comments=True, skip_whitespace=True)
        for declaration in declarations:
            if getattr(declaration, "type", "") != "declaration":
                continue
            value = tinycss2.serialize(declaration.value).strip()
            if declaration.lower_name == "font-family":
                fonts.append(value)
            if declaration.lower_name in {"animation", "animation-duration"}:
                for token in declaration.value:
                    if getattr(token, "type", "") == "dimension" and getattr(token, "lower_unit", "") in {"s", "ms"}:
                        durations.append(f"{token.value:g}{token.lower_unit}")
    return fonts, durations, keyframes


def inspect_sources(paths: tuple[Path, ...]) -> dict[str, object]:
    """Return a deterministic style-inspection report for one SVG corpus."""

    view_boxes: Counter[str] = Counter()
    colors: Counter[str] = Counter()
    fonts: Counter[str] = Counter()
    strokes: Counter[str] = Counter()
    radii: Counter[str] = Counter()
    durations: Counter[str] = Counter()
    keyframes: Counter[str] = Counter()
    source_files = _sources(paths)

    for source in source_files:
        text = source.read_text(encoding="utf-8")
        try:
            root = SafeElementTree.fromstring(text)
        except Exception as exc:
            logger.error("SVG inspection parse failed for {}: {}", source, exc)
            raise
        view_box = root.attrib.get("viewBox")
        if view_box:
            view_boxes[view_box] += 1
        colors.update(match.group(0).upper() for match in HEX_COLOR_GRAMMAR.finditer(text))
        for element in root.iter():
            stroke = element.attrib.get("stroke-width")
            if stroke:
                strokes[stroke] += 1
            if _local_name(element.tag) == "rect" and element.attrib.get("rx"):
                radii[element.attrib["rx"]] += 1
            if _local_name(element.tag) == "style":
                css_fonts, css_durations, css_keyframes = _css_values(element.text or "")
                fonts.update(css_fonts)
                durations.update(css_durations)
                keyframes.update(css_keyframes)

    return {
        "schema": "readme-svg-style-inspection.v1",
        "source_files": [str(path) for path in source_files],
        "view_boxes": dict(view_boxes.most_common()),
        "colors": dict(colors.most_common()),
        "font_families": dict(fonts.most_common()),
        "stroke_widths": dict(strokes.most_common()),
        "corner_radii": dict(radii.most_common()),
        "animation_durations": dict(durations.most_common()),
        "keyframes": dict(keyframes.most_common()),
    }
