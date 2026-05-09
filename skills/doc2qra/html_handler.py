#!/usr/bin/env python3
"""HTML extraction for doc2qra.

Converts HTML documents to markdown-like text with headings preserved so
section detection can produce meaningful QRA titles instead of coarse parts.
"""

from __future__ import annotations

import html
import re
from typing import Iterable

from bs4 import BeautifulSoup, Tag


_HTML_MARKERS = re.compile(r"<\s*(?:!doctype\s+html|html|head|body|article|section|p|h[1-6])\b", re.I)
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANK_RE = re.compile(r"\n{3,}")
_SKIP_HEADING_RE = re.compile(r"^(?:references|bibliography|works cited)\b", re.I)


def looks_like_html(text: str) -> bool:
    """Return True when text appears to be an HTML document or fragment."""
    return bool(_HTML_MARKERS.search(text[:20_000]))


def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = _SPACE_RE.sub(" ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def _is_within(node: Tag, names: Iterable[str]) -> bool:
    names_set = set(names)
    parent = node.parent
    while isinstance(parent, Tag):
        if parent.name in names_set:
            return True
        parent = parent.parent
    return False


def _append_unique(parts: list[str], value: str) -> None:
    value = _clean_text(value)
    if value and (not parts or parts[-1] != value):
        parts.append(value)


def extract_html_text(raw_html: str, *, source_title: str = "") -> str:
    """Extract readable markdown-like text from HTML.

    The output intentionally keeps structural headings as markdown headers,
    because doc2qra's section splitter already understands markdown.
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    for tag in soup.select(".ltx_page_footer, .ltx_role_footnote, .ltx_bibliography, .references"):
        tag.decompose()

    root = soup.find("article") or soup.find("main") or soup.body or soup
    parts: list[str] = []

    title_node = (
        soup.select_one("h1.ltx_title_document")
        or soup.select_one("h1.title")
        or soup.find("h1")
    )
    title = source_title or (title_node.get_text(" ", strip=True) if title_node else "")
    if title:
        _append_unique(parts, f"# {title}")

    stop = False
    for node in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "figcaption", "caption"], recursive=True):
        if stop:
            break
        if not isinstance(node, Tag):
            continue
        if node.name == "h1" and title_node is not None and node is title_node:
            continue
        if node.name in {"p", "li"} and _is_within(node, {"figcaption", "caption"}):
            continue

        text = _clean_text(node.get_text(" ", strip=True))
        if not text:
            continue

        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if _SKIP_HEADING_RE.match(text):
                stop = True
                break
            level = min(int(node.name[1]), 6)
            _append_unique(parts, f"{'#' * level} {text}")
        elif node.name == "li":
            if not _is_within(node, {"li"}):
                _append_unique(parts, f"- {text}")
        else:
            _append_unique(parts, text)

    extracted = "\n\n".join(parts).strip()
    extracted = _BLANK_RE.sub("\n\n", extracted)
    return extracted or _clean_text(BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True))
