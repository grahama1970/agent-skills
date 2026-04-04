"""normalize - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

from typing import Literal

import unicodedata

NormMode = Literal["off", "basic", "nfkc"]


def normalize_text(text: str, mode: NormMode) -> str:
    if mode == "off":
        return text
    if mode == "nfkc":
        return unicodedata.normalize("NFKC", text)
    if mode == "basic":
        return unicodedata.normalize("NFC", text)
    return text
