"""Security, structure, theme, and deterministic-build validation for SVG artifacts.

The validator treats SVG as untrusted input. It uses defusedxml, rejects active content and
external resources, parses CSS with tinycss2, verifies references and accessibility, and
returns a typed receipt. Expected invalid-input exceptions are logged visibly.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import tinycss2
from defusedxml import ElementTree as SafeElementTree
from loguru import logger

from . import __version__
from .browser import verify_readme_image
from .io import load_scene, load_theme
from .models import BrowserEvidence, Finding, Theme, ValidationReceipt
from .render import render_scene

HEX_COLOR_GRAMMAR = re.compile(r"#[0-9A-Fa-f]{6}\b")
FORBIDDEN_TAGS = {"script", "foreignObject", "iframe", "object", "embed"}
REFERENCE_ATTRIBUTES = {"fill", "stroke", "filter", "clip-path", "mask", "marker-start", "marker-mid", "marker-end"}
HREF_ATTRIBUTES = {"href", "{http://www.w3.org/1999/xlink}href"}


def sha256_bytes(content: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(content).hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fragment_reference(value: str) -> str | None:
    stripped = value.strip()
    if stripped.startswith("url(#") and stripped.endswith(")"):
        return stripped[5:-1]
    return None


def _css_external_urls(style_text: str) -> list[str]:
    external: list[str] = []
    rules = tinycss2.parse_stylesheet(style_text, skip_comments=True, skip_whitespace=True)

    def walk(tokens: list[object]) -> None:
        for token in tokens:
            token_type = getattr(token, "type", "")
            if token_type == "url":
                value = str(getattr(token, "value", ""))
                if not value.startswith("#") and not value.startswith("data:"):
                    external.append(value)
            content = getattr(token, "content", None)
            if isinstance(content, list):
                walk(content)
            arguments = getattr(token, "arguments", None)
            if isinstance(arguments, list):
                walk(arguments)

    for rule in rules:
        if getattr(rule, "type", "") == "error":
            external.append("CSS_PARSE_ERROR")
        if getattr(rule, "at_keyword", "").lower() == "import":
            external.append("@import")
        content = getattr(rule, "content", None)
        if isinstance(content, list):
            walk(content)
        prelude = getattr(rule, "prelude", None)
        if isinstance(prelude, list):
            walk(prelude)
    return external


def _theme_findings(svg_text: str, root: ElementTree.Element, theme: Theme) -> list[Finding]:
    findings: list[Finding] = []
    allowed_colors = {
        theme.canvas.background.lower(),
        *(value.lower() for value in theme.palette.model_dump().values()),
    }
    discovered = {match.group(0).lower() for match in HEX_COLOR_GRAMMAR.finditer(svg_text)}
    unexpected = sorted(discovered - allowed_colors)
    if unexpected:
        findings.append(
            Finding(
                code="THEME_COLOR",
                severity="error",
                message=f"unexpected strict-theme colors: {', '.join(unexpected)}",
            )
        )

    allowed_strokes = {
        float(theme.strokes.thin),
        float(theme.strokes.normal),
        float(theme.strokes.emphasis),
        float(theme.strokes.icon),
    }
    unexpected_widths: set[float] = set()
    for element in root.iter():
        value = element.attrib.get("stroke-width")
        if value is None:
            continue
        try:
            width = float(value)
        except ValueError:
            findings.append(
                Finding(code="THEME_STROKE", severity="error", message=f"non-numeric stroke-width: {value}")
            )
            continue
        if width not in allowed_strokes:
            unexpected_widths.add(width)
    if unexpected_widths:
        rendered = ", ".join(f"{value:g}" for value in sorted(unexpected_widths))
        findings.append(
            Finding(
                code="THEME_STROKE",
                severity="error",
                message=f"unexpected strict-theme stroke widths: {rendered}",
            )
        )
    return findings


def validate_svg_text(
    svg_text: str,
    source_path: str,
    *,
    theme: Theme | None = None,
    strict_theme: bool = False,
    browser_evidence: BrowserEvidence | None = None,
) -> ValidationReceipt:
    """Validate SVG text and return a complete typed receipt."""

    findings: list[Finding] = []
    if "<!DOCTYPE" in svg_text.upper() or "<!ENTITY" in svg_text.upper():
        findings.append(Finding(code="XML_DTD", severity="error", message="DTD or entity declaration is forbidden"))

    try:
        root = SafeElementTree.fromstring(svg_text)
    except Exception as exc:
        logger.error("safe SVG parsing failed for {}: {}", source_path, exc)
        findings.append(Finding(code="XML_PARSE", severity="error", message=str(exc)))
        return ValidationReceipt(
            status="FAIL",
            tool_version=__version__,
            source_path=source_path,
            source_sha256=sha256_bytes(svg_text.encode("utf-8")),
            theme=theme.name if theme else None,
            findings=tuple(findings),
            browser=browser_evidence
            or BrowserEvidence(status="NOT_RUN", loaded=False, details="browser verification not requested"),
            proof_scope="safe parse attempt and active-content screening",
            does_not_prove="layout, animation, or README compatibility because XML parsing failed",
            seam_validation={"kind": "svg-to-receipt", "status": "FAIL"},
        )

    if _local_name(root.tag) != "svg":
        findings.append(Finding(code="SVG_ROOT", severity="error", message="root element must be svg"))
    if root.attrib.get("role") != "img":
        findings.append(Finding(code="A11Y_ROLE", severity="error", message="SVG must declare role=img"))
    if "viewBox" not in root.attrib:
        findings.append(Finding(code="SVG_VIEWBOX", severity="error", message="SVG must declare viewBox"))

    ids: set[str] = set()
    references: set[str] = set()
    style_texts: list[str] = []
    title_count = 0
    desc_count = 0

    for element in root.iter():
        name = _local_name(element.tag)
        if name == "title":
            title_count += 1
        if name == "desc":
            desc_count += 1
        if name == "style":
            style_texts.append(element.text or "")
        if name in FORBIDDEN_TAGS:
            findings.append(Finding(code="ACTIVE_TAG", severity="error", message=f"forbidden SVG element: {name}"))
        element_id = element.attrib.get("id")
        if element_id:
            if element_id in ids:
                findings.append(Finding(code="DUPLICATE_ID", severity="error", message=f"duplicate id: {element_id}"))
            ids.add(element_id)
        for attribute, value in element.attrib.items():
            local_attribute = _local_name(attribute)
            if local_attribute.lower().startswith("on"):
                findings.append(
                    Finding(code="EVENT_HANDLER", severity="error", message=f"event handler is forbidden: {local_attribute}")
                )
            if attribute in HREF_ATTRIBUTES or local_attribute == "href":
                if value.startswith("#"):
                    references.add(value[1:])
                elif not value.startswith("data:"):
                    findings.append(
                        Finding(code="EXTERNAL_HREF", severity="error", message=f"external href is forbidden: {value}")
                    )
            if local_attribute in REFERENCE_ATTRIBUTES:
                reference = _fragment_reference(value)
                if reference:
                    references.add(reference)
                elif "url(" in value:
                    findings.append(
                        Finding(code="EXTERNAL_URL", severity="error", message=f"external or malformed url reference: {value}")
                    )

    if title_count != 1:
        findings.append(Finding(code="A11Y_TITLE", severity="error", message="SVG must contain exactly one title"))
    if desc_count != 1:
        findings.append(Finding(code="A11Y_DESC", severity="error", message="SVG must contain exactly one desc"))

    unresolved = sorted(references - ids)
    if unresolved:
        findings.append(
            Finding(code="UNRESOLVED_REF", severity="error", message=f"unresolved fragment references: {', '.join(unresolved)}")
        )

    combined_style = "\n".join(style_texts)
    for url in _css_external_urls(combined_style):
        findings.append(Finding(code="CSS_EXTERNAL", severity="error", message=f"forbidden CSS resource: {url}"))
    animation_index = combined_style.find("animation:")
    media_index = combined_style.find("@media (prefers-reduced-motion: no-preference)")
    if animation_index >= 0 and (media_index < 0 or animation_index < media_index):
        findings.append(
            Finding(
                code="REDUCED_MOTION",
                severity="error",
                message="CSS animation must be isolated behind reduced-motion no-preference",
            )
        )

    if strict_theme and theme is not None:
        findings.extend(_theme_findings(svg_text, root, theme))

    browser = browser_evidence or BrowserEvidence(
        status="NOT_RUN",
        loaded=False,
        details="browser verification not requested",
    )
    if browser.status == "FAIL":
        findings.append(Finding(code="BROWSER", severity="error", message=browser.details))
    status = "FAIL" if any(finding.severity == "error" for finding in findings) else "PASS"
    return ValidationReceipt(
        status=status,
        tool_version=__version__,
        source_path=source_path,
        source_sha256=sha256_bytes(svg_text.encode("utf-8")),
        theme=theme.name if theme else None,
        findings=tuple(findings),
        browser=browser,
        proof_scope="XML safety, active-content rejection, references, accessibility, reduced motion, optional strict theme and Chromium img-mode motion",
        does_not_prove="pixel-perfect rendering on every browser, remote font availability, or future GitHub proxy behavior",
        seam_validation={"kind": "svg-to-receipt", "status": status},
    )


def validate_svg_file(
    svg_path: Path,
    *,
    theme: Theme | None = None,
    strict_theme: bool = False,
    browser: bool = False,
) -> ValidationReceipt:
    """Validate one SVG file, optionally through real Chromium."""

    text = svg_path.read_text(encoding="utf-8")
    evidence = verify_readme_image(svg_path) if browser else None
    return validate_svg_text(
        text,
        str(svg_path),
        theme=theme,
        strict_theme=strict_theme,
        browser_evidence=evidence,
    )


def verify_scene_file(
    scene_path: Path,
    output_path: Path,
    *,
    browser: bool,
) -> ValidationReceipt:
    """Render twice, prove deterministic bytes, write output, and validate it."""

    scene = load_scene(scene_path)
    theme = load_theme(scene.theme, scene_path.parent)
    first = render_scene(scene, theme)
    second = render_scene(scene, theme)
    deterministic = first.encode("utf-8") == second.encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(first, encoding="utf-8")
    receipt = validate_svg_file(output_path, theme=theme, strict_theme=True, browser=browser)
    findings = list(receipt.findings)
    if not deterministic:
        findings.append(
            Finding(code="DETERMINISM", severity="error", message="two compiler passes emitted different bytes")
        )
    status = "FAIL" if any(finding.severity == "error" for finding in findings) else "PASS"
    return receipt.model_copy(
        update={
            "status": status,
            "deterministic_rebuild": deterministic,
            "findings": tuple(findings),
            "seam_validation": {"kind": "scene-to-svg", "status": status},
        }
    )
