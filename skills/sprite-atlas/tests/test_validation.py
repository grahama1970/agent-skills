from pathlib import Path

from PIL import Image

from sprite_atlas.contracts import load_profile
from sprite_atlas.validate_atlas import validate_atlas_png


PROFILE = Path(__file__).resolve().parents[2] / "battle" / "profiles" / "pixijs-runtime-atlas-64.v1.json"


def test_empty_runtime_atlas_fails_required_rows():
    profile = load_profile(PROFILE)
    atlas = Image.new("RGBA", (profile.atlas.width, profile.atlas.height), (0, 0, 0, 0))
    checks = validate_atlas_png(atlas, profile)
    idle = next(c for c in checks if c.name == "row_idle_occupied")
    assert not idle.passed
