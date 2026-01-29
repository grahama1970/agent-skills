#!/usr/bin/env python3
"""Text and section processing for distill skill.

Provides:
- Section detection using patterns from extractor project
- Sentence splitting with abbreviation handling
- Code block extraction with language detection
- Treesitter integration for symbol extraction
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Tuple

from .config import (
    ABBREVIATIONS,
    RE_ALPHA,
    RE_CAPTION,
    RE_DATE,
    RE_DECIMAL,
    RE_LABELED,
    RE_MD_HEADER,
    RE_REQUIREMENT,
    RE_ROMAN,
    TREESITTER_LANG_MAP,
)
from .utils import log


# =============================================================================
# Section Detection
# =============================================================================


def is_likely_section_header(line: str) -> Tuple[bool, str]:
    """Check if line looks like a section header using extractor patterns.

    Args:
        line: Line of text to check

    Returns:
        Tuple of (is_header, title)
    """
    line = line.strip()
    if not line or len(line) < 3:
        return False, ""

    # Negative patterns - reject these
    if RE_CAPTION.match(line):
        return False, ""
    if RE_REQUIREMENT.match(line):
        return False, ""
    if RE_DATE.match(line):
        return False, ""
    # Short label ending with colon (e.g., "Note:", "Warning:")
    if len(line) <= 40 and line.endswith(":"):
        return False, ""
    # Sentences (end with . or ; unless clearly numbered)
    if (line.endswith(".") or line.endswith(";")) and not re.match(r'^\d+\.', line):
        # Allow numbered sections ending with period
        if not RE_DECIMAL.match(line):
            return False, ""

    # Positive patterns
    m = RE_DECIMAL.match(line)
    if m:
        return True, m.group(2).strip()

    m = RE_ROMAN.match(line)
    if m:
        return True, m.group(2).strip()

    m = RE_ALPHA.match(line)
    if m:
        return True, m.group(2).strip()

    m = RE_LABELED.match(line)
    if m:
        return True, m.group(3).strip()

    return False, ""


def _remove_code_blocks(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Remove code blocks and return positions for adjustment.

    Args:
        text: Text containing code blocks

    Returns:
        Tuple of (cleaned_text, list of (start, end) ranges)
    """
    # Match fenced code blocks (``` or ~~~)
    code_block_re = re.compile(r'```[\s\S]*?```|~~~[\s\S]*?~~~', re.MULTILINE)
    ranges = [(m.start(), m.end()) for m in code_block_re.finditer(text)]
    cleaned = code_block_re.sub('', text)
    return cleaned, ranges


def split_by_sections(text: str) -> List[Tuple[str, str]]:
    """Split text by structural sections (headers, numbered sections).

    Uses patterns from extractor project for robust section detection.

    Args:
        text: Text to split into sections

    Returns:
        List of (section_title, section_content) tuples.
        Falls back to single section if no structure detected.
    """
    sections: List[Tuple[str, str]] = []

    # Remove code blocks before detecting headers (to avoid # comments)
    cleaned_text, _ = _remove_code_blocks(text)

    # Try markdown headers first (only in non-code text)
    md_matches = list(RE_MD_HEADER.finditer(cleaned_text))
    if len(md_matches) >= 2:  # Need at least 2 headers to split
        # Find header positions in original text
        for i, match in enumerate(md_matches):
            title = match.group(2).strip()
            # Find this header in original text
            header_text = match.group(0)
            orig_pos = text.find(header_text)
            if orig_pos == -1:
                continue
            start = orig_pos + len(header_text)
            # Find next header in original
            if i + 1 < len(md_matches):
                next_header = md_matches[i + 1].group(0)
                end = text.find(next_header, start)
                if end == -1:
                    end = len(text)
            else:
                end = len(text)
            content = text[start:end].strip()
            if content and len(content) > 20:  # Skip trivially small sections
                sections.append((title, content))
        if sections:
            return sections

    # Try numbered/labeled sections using extractor patterns
    # Scan line by line for section headers
    lines = cleaned_text.split('\n')
    header_positions: List[Tuple[int, str, str]] = []  # (line_idx, full_line, title)

    for idx, line in enumerate(lines):
        is_header, title = is_likely_section_header(line)
        if is_header and title:
            header_positions.append((idx, line.strip(), title))

    if len(header_positions) >= 2:
        # Build sections from header positions
        text_lines = text.split('\n')
        for i, (line_idx, full_line, title) in enumerate(header_positions):
            # Content starts after header line
            start_line = line_idx + 1
            # Content ends at next header (or end of text)
            if i + 1 < len(header_positions):
                end_line = header_positions[i + 1][0]
            else:
                end_line = len(text_lines)

            content_lines = text_lines[start_line:end_line]
            content = '\n'.join(content_lines).strip()

            if content and len(content) > 20:
                sections.append((full_line, content))

        if sections:
            return sections

    # No structure found - return as single section
    return [("", text)]


# =============================================================================
# Sentence Splitting
# =============================================================================


def split_sentences(text: str) -> List[str]:
    """Split text into sentences. Simple regex-based, handles common abbreviations.

    Args:
        text: Text to split into sentences

    Returns:
        List of sentences
    """
    if not text or not text.strip():
        return []

    # Try NLTK if available
    try:
        from nltk.tokenize import PunktSentenceTokenizer
        tok = PunktSentenceTokenizer()
        tok._params.abbrev_types.update({a.replace(".", "") for a in ABBREVIATIONS})
        sents = [t.strip() for t in tok.tokenize(text) if t.strip()]
        if sents:
            return sents
    except Exception:
        pass

    # Fallback: regex split on sentence boundaries
    # Split on .!? followed by space and capital letter
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', text)
    sents = [s.strip() for s in sents if s.strip()]

    # Merge sentences ending with known abbreviations
    merged: List[str] = []
    abbr_pat = r"\b(" + "|".join(re.escape(a + ".") for a in ABBREVIATIONS) + r")$"
    abbr_re = re.compile(abbr_pat, re.I)
    for sent in sents:
        if merged and abbr_re.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {sent}"
        else:
            merged.append(sent)

    return merged if merged else [text]


# =============================================================================
# Section Building
# =============================================================================


def build_sections(
    text: str,
    max_section_chars: int = 5000,
) -> List[Tuple[str, str]]:
    """Build sections from text, respecting document structure.

    Args:
        text: Text to split into sections
        max_section_chars: Maximum characters per section

    Returns:
        List of (section_title, section_content) tuples.

    Strategy:
    1. Split by section delimiters (markdown headers, numbered sections)
    2. Each section is ONE unit for Q&A extraction
    3. Only chunk very large sections (>max_section_chars) as fallback
    """
    sections = split_by_sections(text)
    result: List[Tuple[str, str]] = []

    for title, content in sections:
        content = content.strip()
        if not content:
            continue

        # Section is reasonable size - keep as single unit
        if len(content) <= max_section_chars:
            result.append((title, content))
            continue

        # Section too large - split at sentence boundaries, preserving coherence
        # Find natural break points (paragraph breaks, sentence ends)
        sents = split_sentences(content)
        if not sents:
            result.append((title, content[:max_section_chars]))
            continue

        # Group sentences into chunks, breaking at natural points
        chunk_sents: List[str] = []
        chunk_chars = 0
        part_num = 1

        for sent in sents:
            # Would adding this sentence exceed limit?
            if chunk_chars + len(sent) > max_section_chars and chunk_sents:
                # Save current chunk
                chunk_title = f"{title} (part {part_num})" if title else f"Part {part_num}"
                result.append((chunk_title, " ".join(chunk_sents)))
                part_num += 1
                chunk_sents = []
                chunk_chars = 0

            chunk_sents.append(sent)
            chunk_chars += len(sent) + 1

        # Don't forget last chunk
        if chunk_sents:
            chunk_title = f"{title} (part {part_num})" if title and part_num > 1 else title
            result.append((chunk_title, " ".join(chunk_sents)))

    return result


# =============================================================================
# Code Block Extraction
# =============================================================================


def extract_code_blocks(text: str) -> List[Dict[str, Any]]:
    """Extract fenced code blocks with language annotation.

    Args:
        text: Text containing code blocks

    Returns:
        List of {"language": str, "code": str, "start": int, "end": int}
    """
    # Match ```language\ncode\n``` or ~~~language\ncode\n~~~
    pattern = re.compile(
        r'(?:```|~~~)([A-Za-z0-9_+#.+-]*)\n([\s\S]*?)(?:```|~~~)',
        re.MULTILINE
    )

    blocks = []
    for match in pattern.finditer(text):
        language = match.group(1).strip().lower() or "text"
        code = match.group(2).strip()
        if code:  # Only include non-empty blocks
            blocks.append({
                "language": language,
                "code": code,
                "start": match.start(),
                "end": match.end(),
            })

    return blocks


def parse_code_with_treesitter(code: str, language: str) -> List[Dict[str, Any]]:
    """Parse code using treesitter skill to extract symbols.

    Args:
        code: Source code to parse
        language: Programming language

    Returns:
        List of symbols with kind, name, signature, docstring.
    """
    ts_lang = TREESITTER_LANG_MAP.get(language, language)

    try:
        result = subprocess.run(
            [
                "uvx", "--from", "git+https://github.com/grahama1970/treesitter-tools.git",
                "treesitter-tools", "symbols", "/dev/stdin",
                "--language", ts_lang, "--content"
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        log(f"treesitter parsing failed: {e}", style="yellow")

    return []
