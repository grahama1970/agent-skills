from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

from dogpile.search_stages import normalize_source_filter


def test_normalize_source_filter_accepts_skill_aliases() -> None:
    assert normalize_source_filter(["brave-search", "arxiv", "github-search", "youtube"]) == {
        "brave",
        "arxiv",
        "github",
        "youtube",
    }


def test_normalize_source_filter_allows_unfiltered_default() -> None:
    assert normalize_source_filter(None) is None
    assert normalize_source_filter([]) is None


def test_normalize_source_filter_rejects_unknown_sources() -> None:
    with pytest.raises(ValueError, match="unknown Dogpile source filter"):
        normalize_source_filter(["brave-search", "made-up"])
