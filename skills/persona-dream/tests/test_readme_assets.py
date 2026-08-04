"""The README's images must exist, and stay cheap.

A broken image in the header is worse than no header: it is the first thing a
reader sees and it says the project does not check its own surfaces. The header
also arrived as a 1.7 MB PNG, which is 18x the size of the same picture as WebP,
so the format is pinned rather than left to whoever adds the next asset.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

#: Markdown image refs: ![alt](path)
IMAGE_REF = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

#: Pillow + WebP at quality 95 is the convention for README art in this skill.
#: Not lower: the header is dark gradients and a fine starfield, which is what
#: lossy WebP bands, so the setting is chosen with headroom rather than for the
#: smallest possible file. Not PNG either -- the source was 1.7 MB against
#: 167 KB for a visually indistinguishable WebP.
ALLOWED_SUFFIXES = {".webp"}


def _refs() -> list[str]:
    return [m.group(1).strip() for m in IMAGE_REF.finditer(README.read_text(encoding="utf-8"))]


def test_readme_has_images_at_all():
    """The interface walkthrough was once reduced to a two-line pointer."""
    assert len(_refs()) >= 10, "the README lost its interface screenshots"


def test_every_readme_image_resolves():
    missing = [ref for ref in _refs() if not (README.parent / ref).resolve().is_file()]
    assert not missing, f"README references images that do not exist: {missing}"


def test_readme_assets_are_webp():
    """Pillow + WebP, per the project convention."""
    offenders = [
        ref for ref in _refs()
        if ref.startswith("assets/readme/") and Path(ref).suffix.lower() not in ALLOWED_SUFFIXES
    ]
    assert not offenders, (
        f"README assets must be .webp (convert with Pillow): {offenders}"
    )


def test_the_header_image_is_the_research_loop():
    """The hero is the loop diagram, not a generic project card.

    A reader arriving cold should see what the project does before reading any
    claim about it.
    """
    refs = _refs()
    assert refs, "README has no images"
    assert refs[0] == "assets/readme/research-loop.webp", (
        f"the first image should be the research-loop header, got {refs[0]!r}"
    )


def test_the_header_image_stays_small_enough_to_load():
    header = (README.parent / "assets/readme/research-loop.webp").resolve()
    size = header.stat().st_size
    assert size < 400_000, (
        f"header is {size} bytes; re-encode with Pillow at WebP quality 95"
    )
