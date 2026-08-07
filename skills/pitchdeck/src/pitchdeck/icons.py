"""Hash-pinned icon library resolution with fail-closed editability (#1271).

Icons are LIBRARY REFERENCES: each manifest entry carries the sanitized SVG
source (web rendering), its sha256, and a NATIVE editable mapping built only
from what python-pptx supports natively — preset shapes and straight-segment
freeform vertex loops, optionally grouped. resolve_icon() is a target-profile
branch, not an opportunistic chain: when editable shapes are required and no
native mapping exists it RAISES (a degradation receipt never waives
editability); raster fallback is only returned for explicitly
degradation-permitted profiles and is reported as such.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .svg_sanitize import assert_safe

LIBRARY_DIR = Path(__file__).parent / "design" / "icons"
MANIFEST = LIBRARY_DIR / "manifest.json"


class IconResolutionError(ValueError):
    """Raised when an icon cannot satisfy the requested editability class."""


def load_manifest(manifest_path: Path = MANIFEST) -> dict[str, dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema") != "pitchdeck.icon_library.v1":
        raise IconResolutionError("icon manifest schema mismatch")
    icons = {}
    for entry in data["icons"]:
        svg_path = manifest_path.parent / entry["svg_file"]
        svg = svg_path.read_text(encoding="utf-8")
        if hashlib.sha256(svg.encode()).hexdigest() != entry["svg_sha256"]:
            raise IconResolutionError(f"icon '{entry['id']}': svg hash mismatch (library integrity)")
        assert_safe(svg)
        icons[entry["id"]] = {**entry, "svg": svg}
    return icons


def resolve_icon(
    library_id: str,
    *,
    require_editable: bool,
    profile: str = "native",
    manifest_path: Path = MANIFEST,
) -> dict:
    """Resolve one icon for a target profile; returns mapping + receipt fields."""
    icons = load_manifest(manifest_path)
    if library_id not in icons:
        raise IconResolutionError(f"icon '{library_id}' is not in the library manifest")
    entry = icons[library_id]
    candidates = ["native_mapping", "png_fallback"]
    if entry.get("native_mapping"):
        return {
            "library_id": library_id,
            "representation": "native_editable_shape_tree",
            "mapping": entry["native_mapping"],
            "svg": entry["svg"],
            "svg_sha256": entry["svg_sha256"],
            "candidates_considered": candidates[:1],
        }
    if require_editable:
        raise IconResolutionError(
            f"icon '{library_id}': no native editable mapping and editable shapes are required — failing closed"
        )
    if entry.get("png_fallback"):
        return {
            "library_id": library_id,
            "representation": "opaque_raster_picture",
            "mapping": None,
            "svg": entry["svg"],
            "svg_sha256": entry["svg_sha256"],
            "candidates_considered": candidates,
            "degradation": f"profile '{profile}' permitted raster fallback",
        }
    raise IconResolutionError(f"icon '{library_id}': no representation available for profile '{profile}'")
