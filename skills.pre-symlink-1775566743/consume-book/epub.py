"""EPUB helpers for consume-book."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from ebooklib import epub, ITEM_DOCUMENT


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self._parts)


def extract_title(epub_path: Path) -> Optional[str]:
    """Extract title metadata from an EPUB file."""
    book = epub.read_epub(str(epub_path))
    titles = book.get_metadata("DC", "title")
    if not titles:
        return None
    title = titles[0][0]
    return title if title else None


def extract_text(epub_path: Path) -> str:
    """Extract plain text from an EPUB file."""
    book = epub.read_epub(str(epub_path))
    parts: list[str] = []

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        content = item.get_content()
        html = content.decode("utf-8", errors="ignore")
        parser = _TextExtractor()
        parser.feed(html)
        text = parser.get_text()
        if text:
            parts.append(text)

    return "\n\n".join(parts)
