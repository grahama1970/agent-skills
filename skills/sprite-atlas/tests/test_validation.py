from PIL import Image

from sprite_atlas.contracts import Anchor, AnimationRow, AtlasSpec, NormalizationSpec, Profile
from sprite_atlas.validate_atlas import validate_atlas_png


def test_empty_runtime_atlas_fails_required_rows():
    profile = Profile(
        schema="sprite_atlas.profile.v1",
        profile_id="validation-test",
        atlas=AtlasSpec(2, 1, 16, 16),
        output_format="png",
        output_mode="RGBA",
        background="transparent",
        scale_mode="nearest_neighbor",
        anchor=Anchor(0.5, 0.85),
        normalization=NormalizationSpec(),
        animations=(AnimationRow("idle", 0, 2, True),),
    )
    atlas = Image.new("RGBA", (profile.atlas.width, profile.atlas.height), (0, 0, 0, 0))
    checks = validate_atlas_png(atlas, profile)
    idle = next(c for c in checks if c.name == "row_idle_occupied")
    assert not idle.passed
