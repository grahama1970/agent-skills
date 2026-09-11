"""Deterministic pronunciation normalization for Chatterbox render text.

Chatterbox (and similar on-device neural TTS: Piper, Kokoro, XTTS) has no SSML,
no say-as, and no lexicon feature. The production fix used by Chatterbox's own
maintainers (resemble-ai/chatterbox#400) is exactly this: preprocess the text
before synthesis — space out acronyms so they are read as letters, and spell out
alphanumeric identifiers. This module is that preprocessing pass.

It is rule-based and deterministic (same input -> same spoken form), so it is
safe to run per render with zero latency and no model call. Only genuinely
irregular acronyms (said as a word, or expanded) need the small JSON lexicon;
the rules cover everything else.

Run `python3 pronounce.py` for the self-check.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_DIGIT = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Bracket tags like [sigh], [happy] must never be touched.
_TAG = re.compile(r"\[[^\]]*\]")
# Control-id shapes: a letter cluster adjacent to a digit (SC-7, AC-2(3), CM6),
# or a digit cluster hyphen-joined to a letter (111-A).
_ID = re.compile(r"\b[A-Za-z]{1,4}-?\d[\dA-Za-z()\-]*|\b\d+-[A-Za-z]\b")
# Bare uppercase acronym/initialism (AI, HTML, CUI). IDs are handled first.
_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")


def spell_id(token: str) -> str:
    """Spell an alphanumeric identifier digit-by-digit, letters spaced.

    "SC-7" -> "S C seven"; "111-A" -> "one one one A"; "AC-2(3)" -> "A C two three".
    """
    out: list[str] = []
    for run in re.findall(r"[A-Za-z]+|\d+|[^A-Za-z\d]+", token):
        if run.isdigit():
            out.extend(_DIGIT[d] for d in run)
        elif run.isalpha():
            out.extend(run.upper())  # each letter separate; TTS names them
        # separators (-, (, ), etc.) become word boundaries -> dropped
    return " ".join(out)


def load_lexicon(path: str | Path | None) -> dict[str, str]:
    """Load {UPPER_TERM: spoken_form}. Missing file -> empty (rules still apply)."""
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text())
    terms = data.get("terms", data) if isinstance(data, dict) else {}
    return {str(k).upper(): str(v) for k, v in terms.items()}


def normalize_pronunciation(text: str, lexicon: dict[str, str] | None = None) -> str:
    """Rewrite acronyms and control ids into speakable form. Deterministic.

    Order: protect [tags] -> lexicon overrides (longest first) -> spell ids ->
    space remaining acronyms -> restore tags.
    """
    lexicon = lexicon or {}
    # 1. protect bracket tags
    tags: list[str] = []
    def _stash(m: re.Match) -> str:
        tags.append(m.group(0))
        return f"\x00{len(tags) - 1}\x00"
    protected = _TAG.sub(_stash, text)

    # 2. lexicon overrides, longest term first so 'F-36' beats 'F'
    for term in sorted(lexicon, key=len, reverse=True):
        protected = re.sub(rf"\b{re.escape(term)}\b", lexicon[term],
                           protected, flags=re.IGNORECASE)

    # 3. spell control ids
    protected = _ID.sub(lambda m: spell_id(m.group(0)), protected)

    # 4. space out remaining bare acronyms (AI -> A I)
    protected = _ACRONYM.sub(lambda m: " ".join(m.group(0)), protected)

    # 5. restore tags
    return re.sub(r"\x00(\d+)\x00", lambda m: tags[int(m.group(1))], protected)


def demo() -> None:
    assert spell_id("SC-7") == "S C seven", spell_id("SC-7")
    assert spell_id("111-A") == "one one one A", spell_id("111-A")
    assert spell_id("AC-2(3)") == "A C two three", spell_id("AC-2(3)")
    assert spell_id("CM6") == "C M six", spell_id("CM6")

    lex = {"CUI": "C U I", "NIST": "nist", "OK": "okay"}
    assert "S C seven" in normalize_pronunciation("Apply SC-7 now.")
    assert "one one one A" in normalize_pronunciation("Control 111-A applies.")
    assert normalize_pronunciation("Handle CUI carefully.", lex) == "Handle C U I carefully."
    assert normalize_pronunciation("The NIST rule.", lex) == "The nist rule."
    # bare acronym with no lexicon entry -> spaced letters (chatterbox#400 fix)
    assert normalize_pronunciation("Use AI and HTML.") == "Use A I and H T M L."
    # native tags untouched
    assert normalize_pronunciation("Nice. [sigh] Good AI.") == "Nice. [sigh] Good A I."
    # prose numbers/years are NOT id-shaped -> left for the engine
    assert normalize_pronunciation("In 2026 we shipped 3 things.") == "In 2026 we shipped 3 things."
    print("pronounce.py self-check: PASS")


if __name__ == "__main__":
    demo()
