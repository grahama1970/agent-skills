"""Deterministic text corruption transforms for PDF extraction testing.

Each function takes clean text + a Random instance and returns corrupted text.
Apply via create_text(..., corrupt="ligature") or corrupt="all".
"""
from __future__ import annotations

import random
import re
import unicodedata


# --- 1. Ligatures ---
_LIGATURES = {"fi": "\ufb01", "fl": "\ufb02", "ff": "\ufb00", "ffi": "\ufb03", "ffl": "\ufb04"}

def corrupt_ligature(text: str, rng: random.Random, rate: float = 0.7) -> str:
    for src, lig in sorted(_LIGATURES.items(), key=lambda x: -len(x[0])):
        text = _replace_random(text, src, lig, rng, rate)
    return text


# --- 2. Hyphens ---
_HYPHENS = ["\u2013", "\u2014", "\u2010", "\u2011", "\u2212"]  # en, em, hyphen, nb-hyphen, minus

def corrupt_hyphen(text: str, rng: random.Random, rate: float = 0.5) -> str:
    return _replace_random(text, "-", lambda: rng.choice(_HYPHENS), rng, rate)


# --- 3. Homoglyphs (Latin → Cyrillic/math) ---
_HOMOGLYPHS = {"a": "\u0430", "e": "\u0435", "o": "\u043e", "p": "\u0440", "c": "\u0441",
               "x": "\u0445", "O": "\u041e", "I": "\u0406", "S": "\u0405", "l": "\u2113"}

def corrupt_homoglyph(text: str, rng: random.Random, rate: float = 0.3) -> str:
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch in _HOMOGLYPHS and rng.random() < rate:
            chars[i] = _HOMOGLYPHS[ch]
    return "".join(chars)


# --- 4. Invisible characters ---
_INVISIBLES = ["\u200b", "\u00ad", "\u200d", "\u200c", "\ufeff", "\u2060"]

def corrupt_invisible(text: str, rng: random.Random, count: int = 5) -> str:
    chars = list(text)
    for _ in range(count):
        pos = rng.randint(0, len(chars))
        chars.insert(pos, rng.choice(_INVISIBLES))
    return "".join(chars)


# --- 5. Windows-1252 encoding artifacts ---
_WIN1252 = {'"': "\u201c", "'": "\u2018", "-": "\u2013", "...": "\u2026",
            "(c)": "\u00a9", "(R)": "\u00ae", "(TM)": "\u2122", " ": "\u00a0"}

def corrupt_encoding(text: str, rng: random.Random, rate: float = 0.5) -> str:
    for src, repl in _WIN1252.items():
        text = _replace_random(text, src, repl, rng, rate)
    return text


# --- 6. OCR confusion ---
_OCR = {"rn": "m", "cl": "d", "1": "l", "0": "O", "I": "l", "vv": "w", ")": "}", "S": "5", "B": "8"}

def corrupt_ocr(text: str, rng: random.Random, rate: float = 0.3) -> str:
    for src, repl in sorted(_OCR.items(), key=lambda x: -len(x[0])):
        text = _replace_random(text, src, repl, rng, rate)
    return text


# --- 7. Whitespace ---
_SPACES = ["\u00a0", "\u2009", "\u200a", "\u2007"]

def corrupt_whitespace(text: str, rng: random.Random, rate: float = 0.4) -> str:
    words = text.split(" ")
    result = []
    for w in words:
        result.append(w)
        r = rng.random()
        if r < rate * 0.3:
            result.append("")  # missing space (jam words)
        elif r < rate * 0.6:
            result.append(rng.choice(_SPACES))  # weird space
        elif r < rate * 0.8:
            result.append("  ")  # double space
        else:
            result.append(" ")
    return "".join(result)


# --- 8. Unicode normalization (NFC→NFD) ---
def corrupt_unicode_normalization(text: str, rng: random.Random, rate: float = 0.7) -> str:
    chars = list(text)
    for i, ch in enumerate(chars):
        nfd = unicodedata.normalize("NFD", ch)
        if len(nfd) > 1 and rng.random() < rate:
            chars[i] = nfd
    return "".join(chars)


# --- 9. Number forms ---
_NUMBER_FORMS = {"\u00bd": "1/2", "\u00bc": "1/4", "\u00be": "3/4", "\u00b2": "^2",
                 "\u00b3": "^3", "\u2122": "(TM)", "\u00a9": "(c)", "\u00b0": "deg",
                 "\u00b5": "u", "\u03a9": "Ohm"}

def corrupt_number_form(text: str, rng: random.Random, rate: float = 0.6) -> str:
    # Inject number form characters, then some get "flattened"
    injections = [("\u00b2", "m\u00b2"), ("CO\u2082", "CO2"), ("10\u2076", "106"),
                  ("\u00bd", "1/2"), ("\u00bc", "1/4")]
    inj = rng.choice(injections)
    text = text + f" [{inj[0]} → {inj[1]}]" if rng.random() < rate else text
    return text


# --- 10. Linebreak corruption ---
def corrupt_linebreak(text: str, rng: random.Random, rate: float = 0.3) -> str:
    words = text.split()
    result = []
    for w in words:
        if len(w) > 6 and rng.random() < rate:
            mid = rng.randint(2, len(w) - 2)
            if rng.random() < 0.5:
                result.append(w[:mid] + "-\n" + w[mid:])  # hyphenated break
            else:
                result.append(w[:mid] + "\n" + w[mid:])  # raw break
        else:
            result.append(w)
    return " ".join(result)


# --- 11. Superscript flattening ---
_SUPER = {"\u00b2": "2", "\u00b3": "3", "\u2070": "0", "\u00b9": "1",
          "\u2074": "4", "\u2075": "5", "\u2076": "6", "\u2077": "7",
          "\u2078": "8", "\u2079": "9"}
_SUB = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4"}

def corrupt_superscript(text: str, rng: random.Random, rate: float = 0.8) -> str:
    for src, repl in {**_SUPER, **_SUB}.items():
        text = text.replace(src, repl)
    return text


# --- 12. Bullet mixing ---
_BULLETS = ["\u2022", "\u00b7", "\u25aa", "\u25ba", "\u25e6", "-", "*", "\u25cf", "\u2023", "\uf0b7"]

def corrupt_bullet(text: str, rng: random.Random, rate: float = 0.6) -> str:
    for b in _BULLETS:
        text = _replace_random(text, b, lambda: rng.choice(_BULLETS), rng, rate)
    return text


# --- 13. Table leak ---
def corrupt_table_leak(text: str, rng: random.Random, rate: float = 0.3) -> str:
    words = text.split()
    result = []
    for i, w in enumerate(words):
        result.append(w)
        if rng.random() < rate * 0.1:
            result.append(rng.choice(["\t", "|", "\t\t"]))
    return " ".join(result)


# --- 14. Header bleed ---
_HEADERS = ["PAGE {n}", "NIST SP 800-171 Rev 3", "DRAFT", "UNCLASSIFIED",
            "MIL-STD-882E", "FOR OFFICIAL USE ONLY", "Rev. A"]

def corrupt_header_bleed(text: str, rng: random.Random, count: int = 1) -> str:
    words = text.split()
    for _ in range(count):
        if len(words) > 4:
            pos = rng.randint(2, len(words) - 2)
            header = rng.choice(_HEADERS).format(n=rng.randint(1, 200))
            words.insert(pos, header)
    return " ".join(words)


# --- 15. Column merge ---
def corrupt_column_merge(text: str, rng: random.Random, count: int = 2) -> str:
    _MARGIN_NOISE = ["Left margin: 1\"", "Right margin: 1\"", "Figure 3.2",
                     "Table continued", "See Section 4.1", "(Rev. B)"]
    words = text.split()
    for _ in range(count):
        if len(words) > 6:
            pos = rng.randint(2, len(words) - 2)
            words.insert(pos, rng.choice(_MARGIN_NOISE))
    return " ".join(words)


# --- Registry ---
CORRUPTIONS: dict[str, callable] = {
    "ligature": corrupt_ligature,
    "hyphen": corrupt_hyphen,
    "homoglyph": corrupt_homoglyph,
    "invisible": corrupt_invisible,
    "encoding": corrupt_encoding,
    "ocr": corrupt_ocr,
    "whitespace": corrupt_whitespace,
    "unicode_normalization": corrupt_unicode_normalization,
    "number_form": corrupt_number_form,
    "linebreak": corrupt_linebreak,
    "superscript": corrupt_superscript,
    "bullet": corrupt_bullet,
    "table_leak": corrupt_table_leak,
    "header_bleed": corrupt_header_bleed,
    "column_merge": corrupt_column_merge,
}


def apply_corruption(text: str, corruption: str, seed: int = 42) -> str:
    """Apply one or all corruption transforms to text."""
    rng = random.Random(seed)
    if corruption == "all":
        for fn in CORRUPTIONS.values():
            text = fn(text, rng)
        return text
    if corruption in CORRUPTIONS:
        return CORRUPTIONS[corruption](text, rng)
    raise ValueError(f"Unknown corruption: {corruption}. Available: {list(CORRUPTIONS.keys())}")


# --- Helpers ---
def _replace_random(text: str, src, repl, rng: random.Random, rate: float) -> str:
    """Replace occurrences of src with repl at given rate."""
    if callable(repl):
        parts = text.split(src) if isinstance(src, str) else [text]
        if len(parts) == 1:
            return text
        result = [parts[0]]
        for p in parts[1:]:
            result.append(repl() if rng.random() < rate else src)
            result.append(p)
        return "".join(result)
    else:
        parts = text.split(src)
        if len(parts) == 1:
            return text
        result = [parts[0]]
        for p in parts[1:]:
            result.append(repl if rng.random() < rate else src)
            result.append(p)
        return "".join(result)
