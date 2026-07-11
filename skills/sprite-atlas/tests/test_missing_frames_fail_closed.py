from PIL import Image

from sprite_atlas.contracts import (
    Anchor,
    AnimationRow,
    AtlasSpec,
    FrameMapping,
    MappingDocument,
    NormalizationSpec,
    Profile,
    RowMapping,
    SourceBBox,
)
from sprite_atlas.normalize_frames import normalize_frames


def test_common_scale_overflow_blocks_without_fabricating_frames():
    profile = Profile(
        schema="sprite_atlas.profile.v1",
        profile_id="overflow-test",
        atlas=AtlasSpec(2, 1, 16, 16),
        output_format="png",
        output_mode="RGBA",
        background="transparent",
        scale_mode="nearest_neighbor",
        anchor=Anchor(0.5, 0.85),
        normalization=NormalizationSpec(edge_guard_px=1, allow_per_frame_scaling=False),
        animations=(AnimationRow("run", 0, 2, True),),
    )
    source = Image.new("RGBA", (80, 40), (40, 120, 20, 255))
    mapping = MappingDocument(
        schema="sprite_atlas.mapping.v1",
        source_sha256="synthetic",
        rows=[
            RowMapping(
                target_row=0,
                animation="run",
                frames=[
                    FrameMapping(0, SourceBBox(0, 0, 40, 40)),
                    FrameMapping(1, SourceBBox(40, 0, 80, 10)),
                ],
            )
        ],
    )
    normalized, overflow = normalize_frames(source, profile, mapping)
    assert normalized == []
    assert overflow
    assert {item["reason"] for item in overflow} == {"BLOCKED_FRAME_OVERFLOW"}
