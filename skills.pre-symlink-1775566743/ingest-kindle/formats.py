"""
Ebook format handlers: .epub (ebooklib), .mobi/.azw3 (calibre ebook-convert).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from loguru import logger

EXTRACTION_MARKER = "<!-- EXTRACTION_COMPLETE -->"


def extract_epub(filepath: Path, output_dir: Path) -> Path:
    """Extract text from .epub using ebooklib."""
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(filepath), options={"ignore_ncx": True})

    # Extract metadata
    title = book.get_metadata("DC", "title")
    author = book.get_metadata("DC", "creator")
    identifier = book.get_metadata("DC", "identifier")

    metadata = {
        "title": title[0][0] if title else filepath.stem,
        "author": author[0][0] if author else "Unknown",
        "identifier": identifier[0][0] if identifier else None,
        "format": "epub",
        "source_file": filepath.name,
    }

    # Extract text from all document items
    text_parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        content = item.get_content()
        # Strip HTML tags (simple approach — good enough for QRA extraction)
        text = _strip_html(content.decode("utf-8", errors="replace"))
        text = text.strip()
        if text:
            text_parts.append(text)

    full_text = "\n\n".join(text_parts)

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    text_path = output_dir / "text.md"
    text_path.write_text(
        f"# {metadata['title']}\n\n"
        f"**Author:** {metadata['author']}\n\n"
        f"---\n\n"
        f"{full_text}\n\n"
        f"{EXTRACTION_MARKER}\n",
        encoding="utf-8",
    )

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return text_path


def extract_mobi_azw3(filepath: Path, output_dir: Path) -> Path:
    """Extract text from .mobi/.azw3 using calibre's ebook-convert CLI."""
    # Check calibre is available
    try:
        subprocess.run(
            ["ebook-convert", "--version"],
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError(
            "calibre's ebook-convert not found. Install calibre:\n"
            "  sudo apt install calibre   # Debian/Ubuntu\n"
            "  brew install calibre        # macOS\n"
            "Or convert to .epub first and use that instead."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert to txt via calibre
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run(
            ["ebook-convert", str(filepath), str(tmp_path)],
            capture_output=True,
            check=True,
            text=True,
        )
        full_text = tmp_path.read_text(encoding="utf-8", errors="replace")
    finally:
        tmp_path.unlink(missing_ok=True)

    # Extract metadata via calibre
    metadata = {
        "title": filepath.stem,
        "author": "Unknown",
        "format": filepath.suffix.lstrip("."),
        "source_file": filepath.name,
    }

    try:
        result = subprocess.run(
            ["ebook-convert", str(filepath), "/dev/null", "--read-metadata-from-opf=/dev/stdout"],
            capture_output=True,
            text=True,
        )
        # Fallback: just use filename-based metadata
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    text_path = output_dir / "text.md"
    text_path.write_text(
        f"# {metadata['title']}\n\n"
        f"**Author:** {metadata['author']}\n\n"
        f"---\n\n"
        f"{full_text}\n\n"
        f"{EXTRACTION_MARKER}\n",
        encoding="utf-8",
    )

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return text_path


def extract_book(filepath: Path, output_dir: Path) -> Path:
    """Route to the correct extractor based on file extension."""
    ext = filepath.suffix.lower()
    if ext == ".epub":
        return extract_epub(filepath, output_dir)
    elif ext in (".mobi", ".azw3", ".azw"):
        return extract_mobi_azw3(filepath, output_dir)
    else:
        raise ValueError(
            f"Unsupported format: {ext}. Supported: .epub, .mobi, .azw3"
        )


def _strip_html(html: str) -> str:
    """Simple HTML tag stripping. Not a full parser — sufficient for ebook text."""
    import re

    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div>, <li> with newlines
    html = re.sub(r"<(?:br|p|div|li)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Remove remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    html = html.replace("&amp;", "&")
    html = html.replace("&lt;", "<")
    html = html.replace("&gt;", ">")
    html = html.replace("&quot;", '"')
    html = html.replace("&nbsp;", " ")
    html = html.replace("&#39;", "'")
    # Collapse multiple blank lines
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()
