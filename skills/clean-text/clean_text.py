#!/usr/bin/env python3
"""
Text normalization tool for handling PDF encoding issues and security evasion.

Comprehensive Unicode normalization based on patterns from text_toolz.
Handles:
- Windows-1252 characters (common in old PDFs)
- Unicode whitespace variants
- Hyphen/dash variants
- Quote variants
- Ligatures
- Directional formatting
- Control characters
- Line-break hyphenation

Security extensions (used by services/common/validation.py):
- Cyrillic→Latin homoglyph translation
- Mixed-script detection (homoglyph attack indicator)
- Invisible content detection (>50% invisible chars)
- URL double-decoding (defeats %25-encoded evasion)
- Letter-spacing collapse (defeats "F O R" evasion)
- BOM prefix stripping
"""

import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import typer


def normalize_text(text: str) -> str:
    """Normalize text to handle encoding issues and invisible characters.

    PDFs often have 15+ different encodings for hyphens, various Unicode
    whitespace, ligatures, and other characters. This normalizes them for
    consistent pattern matching.
    """
    if not text:
        return ""

    # Step 1: Convert Windows-1252 characters FIRST (before control char removal)
    windows_1252_map = {
        "\x91": "'",   # Left single quote
        "\x92": "'",   # Right single quote
        "\x93": '"',   # Left double quote
        "\x94": '"',   # Right double quote
        "\x95": "-",   # Bullet
        "\x96": "-",   # En dash
        "\x97": "-",   # Em dash
        "\x85": "...", # Horizontal ellipsis
        "\x99": "(TM)", # Trademark
        "\xa9": "(C)", # Copyright
        "\xae": "(R)", # Registered
    }
    for old, new in windows_1252_map.items():
        text = text.replace(old, new)

    # Step 2: NFKC Unicode Normalization (foundational)
    text = unicodedata.normalize("NFKC", text)

    # Step 3: Remove directional formatting characters
    directional_pattern = "[\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069]"
    text = re.sub(directional_pattern, "", text)

    # Step 4: Remove control characters (C0/C1) but preserve newlines/tabs
    control_pattern = "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]"
    text = re.sub(control_pattern, "", text)

    # Step 5: Whitespace variants -> ASCII space
    whitespace_map = {
        "\u00a0": " ",  # Non-breaking space
        "\u2002": " ",  # En space
        "\u2003": " ",  # Em space
        "\u2009": " ",  # Thin space
        "\u200a": " ",  # Hair space
        "\u202f": " ",  # Narrow no-break space
        "\u205f": " ",  # Medium mathematical space
        "\u3000": " ",  # Ideographic space
        "\u200b": "",   # Zero-width space
        "\u200c": "",   # Zero-width non-joiner
        "\u200d": "",   # Zero-width joiner
        "\ufeff": "",   # BOM
        "\u2060": "",   # Word joiner
    }
    for old, new in whitespace_map.items():
        text = text.replace(old, new)

    # Step 6: Hyphen/Dash variants -> ASCII hyphen
    hyphen_chars = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u058a\u05be\u1400\u1806\u2e17\u2e1a\u30a0\ufe58\ufe63\uff0d"
    for hc in hyphen_chars:
        text = text.replace(hc, "-")
    text = text.replace("\u00ad", "")  # Soft hyphen (remove)

    # Step 7: Quote variants -> ASCII quotes
    single_quotes = "\u2018\u2019\u201a\u201b\u2032\u2035"
    double_quotes = "\u201c\u201d\u201e\u201f\u2033\u2036\u00ab\u00bb"
    for qc in single_quotes:
        text = text.replace(qc, "'")
    for qc in double_quotes:
        text = text.replace(qc, '"')

    # Step 8: Period/Dot variants
    text = text.replace("\u2024", ".")  # One dot leader
    text = text.replace("\u2027", ".")  # Hyphenation point
    text = text.replace("\u30fb", ".")  # Katakana middle dot
    text = text.replace("\u2026", "...")  # Horizontal ellipsis

    # Step 9: Bullet points -> hyphen
    bullet_chars = "\u2022\u25cf\u25e6\u25cb\u25aa\u25ab\u25a0\u25a1\u2023\u2043"
    for bc in bullet_chars:
        text = text.replace(bc, "-")

    # Step 10: Ligatures (expand)
    ligatures = {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
    }
    for old, new in ligatures.items():
        text = text.replace(old, new)

    # Step 11: Fix hyphenated words at line breaks
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)

    # Step 12: Collapse multiple whitespace to single space
    text = " ".join(text.split())
    return text.strip()


# ── Security-focused text sanitization ────────────────────────────────────────
# Used by services/common/validation.py (Tier 0 validators) and any service
# that needs to normalize text before injection detection.

# Cyrillic→Latin homoglyph map for confusable detection.
# Covers the most common Cyrillic characters that visually match Latin.
HOMOGLYPH_MAP = str.maketrans({
    "\u0410": "A", "\u0412": "B", "\u0421": "C", "\u0415": "E",
    "\u041d": "H", "\u041a": "K", "\u041c": "M", "\u041e": "O",
    "\u0420": "P", "\u0422": "T", "\u0425": "X", "\u0430": "a",
    "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c",
    "\u0443": "y", "\u0456": "i", "\u0445": "x",
})

# Zero-width and invisible characters regex
# (NFKC handles fullwidth; this catches directional + zero-width + BOM + tags)
INVISIBLE_CHARS_RE = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
    r"\u2060\u2061\u2062\u2063\u2064\u2066\u2067\u2068\u2069"
    r"\ufeff\ufff9\ufffa\ufffb\U000e0001-\U000e007f]"
)

# Directional override detection uses the same INVISIBLE_CHARS_RE regex
# plus unicodedata.bidirectional() for Bidi category checks.


def sanitize_for_validation(text: str) -> str:
    """Security-focused normalization to defeat encoding-based evasion.

    Builds on normalize_text() but adds URL-decoding, homoglyph translation,
    and letter-spacing collapse. Used by Tier 0 validators.

    Unlike normalize_text() which collapses all whitespace (good for PDF text),
    this preserves overall structure and only collapses whitespace between
    single letters (to defeat "F O R" → "FOR" evasion).
    """
    # Strip BOM prefix and byte order marks (UTF-8/UTF-16 BOM evasion)
    text = text.lstrip("\ufeff\ufffe\u00ff\u00fe")
    # NFKC: fullwidth FOR → FOR, compatibility decomposition
    text = unicodedata.normalize("NFKC", text)
    # Strip invisible chars (zero-width, directional, BOM, tag chars)
    text = INVISIBLE_CHARS_RE.sub("", text)
    # Translate Cyrillic/Latin homoglyphs
    text = text.translate(HOMOGLYPH_MAP)
    # URL-decode (two passes for double-encoding)
    text = unquote(unquote(text))
    # Collapse whitespace/tabs/null-bytes between single letters (defeats "F O R" and "F\tO\tR")
    text = re.sub(r"(?<=\b\w)[\s\x00]+(?=\w\b)", "", text)
    # Strip null bytes entirely (defeats FOR%00doc%00IN)
    text = text.replace("\x00", "")
    return text


def has_control_chars(text: str) -> bool:
    """Check for null bytes, DEL, and non-printable control characters.

    Returns True if text contains any C0 control characters (except \\n, \\r, \\t),
    null bytes, or DEL (0x7F).
    """
    for ch in text:
        cp = ord(ch)
        if cp == 0:  # null byte
            return True
        if cp == 0x7f:  # DEL
            return True
        if cp < 32 and ch not in ("\n", "\r", "\t"):  # other control chars
            return True
    return False


def has_mixed_scripts(text: str) -> bool:
    """Detect mixed Latin/Cyrillic scripts (homoglyph attack indicator).

    Returns True if text contains BOTH Latin and Cyrillic characters,
    which is a strong indicator of homoglyph-based evasion.
    """
    has_latin = False
    has_cyrillic = False
    for ch in text:
        name = unicodedata.name(ch, "")
        if "CYRILLIC" in name:
            has_cyrillic = True
        elif "LATIN" in name:
            has_latin = True
        if has_latin and has_cyrillic:
            return True
    return False


def has_invisible_content(text: str) -> bool:
    """Detect text that is entirely or primarily invisible characters.

    Returns True if >50% of characters are invisible/zero-width/directional.
    """
    if not text:
        return False
    invisible_count = len(INVISIBLE_CHARS_RE.findall(text))
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in ("Cf", "Mn", "Me"):  # format, nonspacing mark, enclosing mark
            invisible_count += 1
    return invisible_count > len(text) * 0.5


def has_directional_chars(text: str) -> bool:
    """Check for directional override/embedding characters (text disguise).

    Detects Unicode Bidi control characters by their Unicode category (Cf)
    and specific codepoint ranges for directional formatting.
    """
    for ch in text:
        cp = ord(ch)
        # LRM (U+200E), RLM (U+200F)
        if cp in (0x200E, 0x200F):
            return True
        # LRE, RLE, PDF, LRO, RLO (U+202A-U+202E)
        if 0x202A <= cp <= 0x202E:
            return True
        # LRI, RLI, FSI, PDI (U+2066-U+2069)
        if 0x2066 <= cp <= 0x2069:
            return True
    return False


def is_whitespace_only(text: str) -> bool:
    """Check if text is effectively empty after sanitization.

    Catches: whitespace-only, zero-width-only, BOM-only, invisible-char-only.
    """
    cleaned = INVISIBLE_CHARS_RE.sub("", text).strip()
    return not cleaned


def normalize_file(input_path: Path, output_path: Optional[Path] = None) -> str:
    """Normalize text from a file."""
    text = input_path.read_text(encoding="utf-8", errors="replace")
    normalized = normalize_text(text)

    if output_path:
        output_path.write_text(normalized, encoding="utf-8")
        return f"Normalized text written to {output_path}"

    return normalized


app = typer.Typer(help="Normalize text to handle PDF/Unicode encoding issues")


@app.command()
def main(
    input: str = typer.Argument(None, help="Input file path or text (reads from stdin if not provided)"),
    output: Path = typer.Option(None, "-o", "--output", help="Output file path (prints to stdout if not provided)"),
    text: bool = typer.Option(False, "-t", "--text", help="Treat input as text instead of file path"),
    stats: bool = typer.Option(False, "--stats", help="Show normalization statistics"),
) -> None:
    """Normalize text to handle PDF/Unicode encoding issues."""
    # Get input text
    if input:
        if text:
            raw_text = input
        else:
            raw_text = Path(input).read_text(encoding="utf-8", errors="replace")
    elif not sys.stdin.isatty():
        # Handle stdin with encoding errors gracefully (common with PDF text)
        raw_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    else:
        raise typer.Exit(1)

    # Normalize
    original_len = len(raw_text)
    normalized = normalize_text(raw_text)

    # Output
    if output:
        output.write_text(normalized, encoding="utf-8")
        print(f"Normalized text written to {output}", file=sys.stderr)
    else:
        print(normalized)

    # Stats
    if stats:
        print(f"\n--- Statistics ---", file=sys.stderr)
        print(f"Original length: {original_len} chars", file=sys.stderr)
        print(f"Normalized length: {len(normalized)} chars", file=sys.stderr)
        print(f"Reduction: {original_len - len(normalized)} chars", file=sys.stderr)


if __name__ == "__main__":
    app()
