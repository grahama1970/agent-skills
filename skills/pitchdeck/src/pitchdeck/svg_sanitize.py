"""Strict-allowlist SVG safety boundary (#1268).

One gate for every inline SVG entering the canonical document (and any
future uploaded-SVG / Mermaid-snapshot path): parse, then REJECT anything
outside a closed grammar — script/foreignObject/image, event-handler
attributes, external or javascript: references, CSS url()/@import, DOCTYPE
and processing instructions. Fail-closed: `assert_safe` raises SvgRejected
with the exact violation; nothing is silently stripped (a sanitizer that
mutates hides intent — authors fix their SVG instead). Inputs are
size-capped before parsing to blunt entity/expansion abuse.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

MAX_SVG_BYTES = 200_000

ALLOWED_TAGS = {
    "svg", "g", "defs", "marker", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "title", "desc", "clipPath",
    "linearGradient", "radialGradient", "stop", "symbol",
}
_EVENT_ATTR = re.compile(r"^on", re.IGNORECASE)
_URL_FUNC = re.compile(r"url\s*\(", re.IGNORECASE)
_SCHEME = re.compile(r"^\s*(javascript|data|http|https|file|ftp)\s*:", re.IGNORECASE)


class SvgRejected(ValueError):
    """Raised when inline SVG violates the safety grammar."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def assert_safe(svg: str) -> str:
    """Validate inline SVG against the allowlist; return it unchanged on pass."""
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise SvgRejected(f"svg exceeds {MAX_SVG_BYTES} bytes")
    lowered = svg.lower()
    for needle, why in (
        ("<!doctype", "DOCTYPE declarations"),
        ("<!entity", "entity declarations"),
        ("<?", "processing instructions"),
        ("<script", "script elements"),
        ("@import", "CSS imports"),
        ("<foreignobject", "foreignObject elements"),
    ):
        if needle in lowered:
            raise SvgRejected(f"svg contains {why}")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise SvgRejected(f"svg does not parse: {exc}") from exc
    if _local(root.tag) != "svg":
        raise SvgRejected(f"root element is '{_local(root.tag)}', not svg")
    for el in root.iter():
        tag = _local(el.tag)
        if tag not in ALLOWED_TAGS:
            raise SvgRejected(f"element '{tag}' is not in the SVG allowlist")
        for name, value in el.attrib.items():
            attr = _local(name)
            if _EVENT_ATTR.match(attr):
                raise SvgRejected(f"event-handler attribute '{attr}' on <{tag}>")
            if attr in {"href", "xlink:href"} or name.endswith("}href"):
                if not value.startswith("#"):
                    raise SvgRejected(f"non-local href '{value[:40]}' on <{tag}>")
            if _SCHEME.match(value):
                raise SvgRejected(f"external/scheme reference in '{attr}' on <{tag}>")
            if attr == "style" and _URL_FUNC.search(value):
                raise SvgRejected(f"css url() in style attribute on <{tag}>")
    return svg
