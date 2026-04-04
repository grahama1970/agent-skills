"""
Parser for Kindle's My Clippings.txt format.

Format:
    Book Title (Author Name)
    - Your Highlight on page 42 | Location 612-615 | Added on Monday, January 15, 2024 12:30:00 AM

    The highlighted text goes here.
    ==========
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


SEPARATOR = "=========="

# Match: "- Your Highlight on page 42 | Location 612-615 | Added on ..."
# Or:    "- Your Note on page 42 | Location 612 | Added on ..."
# Or:    "- Your Bookmark on Location 612 | Added on ..."
_META_RE = re.compile(
    r"- Your (?P<type>Highlight|Note|Bookmark)"
    r"(?:\s+on\s+page\s+(?P<page>\d+))?"
    r"(?:\s*\|\s*Location\s+(?P<loc_start>\d+)(?:-(?P<loc_end>\d+))?)?"
    r"(?:\s*\|\s*Added on\s+(?P<date>.+))?",
    re.IGNORECASE,
)

# Match: "Book Title (Author Name)"
_TITLE_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<author>[^)]+)\)\s*$")


@dataclass
class Clipping:
    title: str
    author: str
    clip_type: str  # highlight, note, bookmark
    content: str
    page: int | None = None
    location_start: int | None = None
    location_end: int | None = None
    added_on: str | None = None


@dataclass
class ClippingsResult:
    books: dict[str, list[Clipping]] = field(default_factory=dict)
    total: int = 0
    errors: int = 0


def parse_clippings(path: Path) -> ClippingsResult:
    """Parse a My Clippings.txt file into structured clippings."""
    text = path.read_text(encoding="utf-8-sig")  # Handle BOM
    blocks = text.split(SEPARATOR)
    result = ClippingsResult()

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 2:
            result.errors += 1
            continue

        # Line 0: Title (Author)
        title_match = _TITLE_RE.match(lines[0].strip())
        if title_match:
            title = title_match.group("title").strip()
            author = title_match.group("author").strip()
        else:
            title = lines[0].strip()
            author = "Unknown"

        # Line 1: Metadata
        meta_match = _META_RE.match(lines[1].strip())
        if not meta_match:
            result.errors += 1
            continue

        clip_type = meta_match.group("type").lower()
        page = int(meta_match.group("page")) if meta_match.group("page") else None
        loc_start = int(meta_match.group("loc_start")) if meta_match.group("loc_start") else None
        loc_end = int(meta_match.group("loc_end")) if meta_match.group("loc_end") else None
        added_on = meta_match.group("date").strip() if meta_match.group("date") else None

        # Lines 3+: Content (line 2 is usually blank)
        content_lines = [l for l in lines[2:] if l.strip()]
        content = "\n".join(content_lines).strip()

        clipping = Clipping(
            title=title,
            author=author,
            clip_type=clip_type,
            content=content,
            page=page,
            location_start=loc_start,
            location_end=loc_end,
            added_on=added_on,
        )

        key = f"{title} — {author}"
        if key not in result.books:
            result.books[key] = []
        result.books[key].append(clipping)
        result.total += 1

    return result


def clippings_to_json(result: ClippingsResult) -> str:
    """Convert parsed clippings to JSON."""
    output = {}
    for book_key, clips in result.books.items():
        output[book_key] = [asdict(c) for c in clips]
    return json.dumps(output, indent=2, ensure_ascii=False)


def save_highlights_for_book(
    result: ClippingsResult,
    title: str,
    output_dir: Path,
) -> Path | None:
    """Save highlights for a specific book to its library directory."""
    for book_key, clips in result.books.items():
        if title.lower() in book_key.lower():
            highlights = [asdict(c) for c in clips if c.clip_type == "highlight"]
            if not highlights:
                return None

            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / "highlights.json"
            out_path.write_text(
                json.dumps(highlights, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return out_path

    return None
