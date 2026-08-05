from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from .io import slugify

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
_HTML_IMAGE_RE = re.compile(
    r"<img\b[^>]*?src=[\"']([^\"']+)[\"'][^>]*?(?:alt=[\"']([^\"']*)[\"'])?[^>]*>",
    re.IGNORECASE,
)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_TAG_RE = re.compile(r"<[^>]+>")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(slots=True)
class MarkdownImage:
    src: str
    alt: str
    section: str
    line: int


@dataclass(slots=True)
class MarkdownSection:
    heading: str
    level: int
    line: int
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    images: list[MarkdownImage] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = self.paragraphs + self.bullets
        return " ".join(part.strip() for part in parts if part.strip())


@dataclass(slots=True)
class MarkdownDocument:
    path: Path
    title: str
    intro: list[str]
    sections: list[MarkdownSection]
    images: list[MarkdownImage]

    def find_section(self, keywords: list[str]) -> MarkdownSection | None:
        lowered = [keyword.lower() for keyword in keywords]
        for section in self.sections:
            heading = section.heading.lower()
            if any(keyword in heading for keyword in lowered):
                return section
        return None


def clean_inline(text: str) -> str:
    text = html.unescape(text)
    text = _INLINE_LINK_RE.sub(r"\1", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("`", "")
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _flush_paragraph(buffer: list[str], destination: list[str]) -> None:
    if not buffer:
        return
    text = clean_inline(" ".join(buffer))
    if text:
        destination.append(text)
    buffer.clear()


def parse_markdown(path: Path) -> MarkdownDocument:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = path.stem
    intro: list[str] = []
    sections: list[MarkdownSection] = []
    images: list[MarkdownImage] = []
    current: MarkdownSection | None = None
    paragraph_buffer: list[str] = []
    in_fence = False

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
            level = len(heading_match.group(1))
            heading = clean_inline(heading_match.group(2))
            if level == 1 and title == path.stem:
                title = heading
                continue
            current = MarkdownSection(heading=heading, level=level, line=line_no)
            sections.append(current)
            continue

        found_images: list[MarkdownImage] = []
        for match in _MD_IMAGE_RE.finditer(stripped):
            alt, src = match.group(1), match.group(2)
            found_images.append(
                MarkdownImage(
                    src=src,
                    alt=clean_inline(alt) or "README image",
                    section=current.heading if current else "Introduction",
                    line=line_no,
                )
            )
        for match in _HTML_IMAGE_RE.finditer(stripped):
            src, alt = match.group(1), match.group(2) or "README image"
            found_images.append(
                MarkdownImage(
                    src=src,
                    alt=clean_inline(alt),
                    section=current.heading if current else "Introduction",
                    line=line_no,
                )
            )
        if found_images:
            images.extend(found_images)
            if current:
                current.images.extend(found_images)
            continue

        if not stripped:
            _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
            continue

        if stripped.startswith(("- ", "* ", "+ ")):
            _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
            bullet = clean_inline(stripped[2:])
            if bullet:
                if current:
                    current.bullets.append(bullet)
                else:
                    intro.append(bullet)
            continue

        if re.match(r"^\d+[.)]\s+", stripped):
            _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
            bullet = clean_inline(re.sub(r"^\d+[.)]\s+", "", stripped))
            if bullet:
                if current:
                    current.bullets.append(bullet)
                else:
                    intro.append(bullet)
            continue

        if stripped.startswith("|"):
            # Tables are too dense for automatic slide prose. Keep a compact row summary.
            cells = [clean_inline(cell) for cell in stripped.strip("|").split("|")]
            cells = [cell for cell in cells if cell and not set(cell) <= {"-", ":"}]
            if cells:
                target = current.bullets if current else intro
                target.append(" — ".join(cells))
            continue

        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ")

        paragraph_buffer.append(stripped)

    _flush_paragraph(paragraph_buffer, current.paragraphs if current else intro)
    return MarkdownDocument(path=path, title=title, intro=intro, sections=sections, images=images)


def compact_text(text: str, max_chars: int = 360) -> str:
    text = clean_inline(text)
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1].rsplit(" ", 1)[0]
    return truncated.rstrip(" ,;:") + "…"


def candidate_sentences(document: MarkdownDocument, limit: int = 40) -> list[tuple[str, str, int]]:
    """Return conservative claim candidates as (section, text, line)."""
    candidates: list[tuple[str, str, int]] = []

    for index, paragraph in enumerate(document.intro[:3], start=1):
        text = compact_text(paragraph, 420)
        if len(text) >= 24:
            candidates.append(("Introduction", text, index))

    for section in document.sections:
        source_texts = section.paragraphs[:2] + section.bullets[:4]
        for text in source_texts:
            text = compact_text(text, 420)
            if len(text) < 24:
                continue
            candidates.append((section.heading, text, section.line))
            if len(candidates) >= limit:
                return candidates

    return candidates


def section_slug(section: str) -> str:
    return slugify(section, fallback="section")


def first_strong_phrase(path: Path) -> str | None:
    raw = path.read_text(encoding="utf-8")
    for match in _BOLD_RE.finditer(raw):
        phrase = clean_inline(match.group(1))
        if 20 <= len(phrase) <= 360:
            return phrase
    return None
