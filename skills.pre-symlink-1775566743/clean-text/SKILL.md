---
name: clean-text
description: >
  Normalize text to handle PDF/Unicode encoding issues and security evasion.
  Converts Windows-1252, curly quotes, em/en dashes, ligatures,
  directional formatting, zero-width chars, and more to clean ASCII.
  Security extensions: homoglyph translation, mixed-script detection,
  invisible content detection, URL double-decoding, letter-spacing collapse.
allowed-tools: Bash, Read
triggers:
  - clean text
  - normalize text
  - normalize unicode
  - fix encoding
  - clean pdf text
  - normalize pdf
  - text cleaning
  - sanitize input
  - homoglyph detection
metadata:
  short-description: Clean PDF/Unicode text to ASCII + security sanitization
  project-path: /home/graham/workspace/experiments/pi-mono
provides:
  - clean-text
  - sanitize-for-validation
composes: [task-monitor]

taxonomy:
  - preprocessing
  - text
  - precision
  - corruption
---

# Clean Text

Comprehensive text normalization for handling PDF and Unicode encoding issues,
plus security-focused sanitization for injection detection.

## Quick Start

```bash
# Normalize text from stdin
echo "Hello\u2019world" | .pi/skills/clean-text/run.sh

# Normalize a file
.pi/skills/clean-text/run.sh document.txt

# Normalize with output file
.pi/skills/clean-text/run.sh document.txt -o clean.txt

# Treat argument as text (not filename)
.pi/skills/clean-text/run.sh -t "Hello\u201cworld\u201d"

# Show statistics
.pi/skills/clean-text/run.sh document.txt --stats
```

## What It Normalizes

| Category | Examples | Normalized To |
|----------|----------|---------------|
| **Whitespace** | Non-breaking, em/en space, hair space | Regular space |
| **Hyphens** | En dash, em dash, minus sign, figure dash | ASCII hyphen `-` |
| **Quotes** | Curly quotes, guillemets, primes | Straight `'` and `"` |
| **Windows-1252** | `\x93`, `\x94`, `\x92` | `"`, `"`, `'` |
| **Ligatures** | fi, fl, ffi, ffl | Expanded letters |
| **Bullets** | Various bullet points | Hyphen `-` |
| **Zero-width** | ZWSP, ZWNJ, ZWJ, BOM | Removed |
| **Directional** | LTR/RTL marks | Removed |
| **Control chars** | C0/C1 (except newline/tab) | Removed |
| **Line breaks** | `intro-\nduction` | `introduction` |

## Pipeline Integration

This skill is based on the same normalization used in the extractor pipeline's
s02_marker_extractor.py. The code is kept in sync with text_toolz patterns.

### Python Usage

```python
from clean_text import normalize_text

# Clean text for pattern matching
text = "1.\u00a0Introduction"  # Non-breaking space
clean = normalize_text(text)   # "1. Introduction"
```

## Normalization Steps

1. **Windows-1252 conversion** - Handle legacy MS Office encoding
2. **NFKC normalization** - Unicode compatibility decomposition
3. **Remove directional formatting** - LTR/RTL marks
4. **Remove control characters** - C0/C1 (preserve newlines)
5. **Normalize whitespace** - All special spaces to ASCII
6. **Normalize hyphens** - All dash variants to `-`
7. **Normalize quotes** - Curly to straight
8. **Normalize dots** - Ellipsis, leader dots
9. **Normalize bullets** - All bullet types to `-`
10. **Expand ligatures** - fi/fl/ffi/ffl
11. **Fix line-break hyphens** - Join hyphenated words
12. **Collapse whitespace** - Multiple spaces to single

## Security Sanitization API

For Tier 0 validators and injection detection, import the security functions directly:

```python
from clean_text import (
    sanitize_for_validation,  # NFKC + homoglyph + URL-decode + letter-spacing
    has_control_chars,        # null, DEL, C0 control chars
    has_mixed_scripts,        # Latin+Cyrillic mixing (homoglyph attack)
    has_invisible_content,    # >50% invisible characters
    has_directional_chars,    # Unicode Bidi override characters
    is_whitespace_only,       # empty after sanitization
    HOMOGLYPH_MAP,            # Cyrillic→Latin translation table
    INVISIBLE_CHARS_RE,       # zero-width + directional + BOM regex
)
```

Used by: `services/common/validation.py` (Embry OS Tier 0 validators)

## Based On

- text_toolz library patterns
- extractor pipeline s02 normalization
- NFKC Unicode standard
