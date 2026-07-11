"""Assemble exact profile-sized runtime atlas PNG."""

from __future__ import annotations

from PIL import Image

from sprite_atlas.contracts import Profile
from sprite_atlas.normalize_frames import NormalizedFrame


def assemble_atlas(profile: Profile, frames: list[NormalizedFrame]) -> Image.Image:
    atlas = Image.new(
        "RGBA",
        (profile.atlas.width, profile.atlas.height),
        (0, 0, 0, 0),
    )
    fw = profile.atlas.frame_width
    fh = profile.atlas.frame_height
    for frame in frames:
        x = frame.target_column * fw
        y = frame.target_row * fh
        atlas.alpha_composite(frame.image, (x, y))
    return atlas
