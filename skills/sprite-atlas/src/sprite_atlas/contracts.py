"""Profile and work-order contracts for sprite-atlas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AtlasSpec:
    columns: int
    rows: int
    frame_width: int
    frame_height: int
    margin: int = 0
    spacing: int = 0

    @property
    def width(self) -> int:
        return self.columns * self.frame_width + (self.columns - 1) * self.spacing + 2 * self.margin

    @property
    def height(self) -> int:
        return self.rows * self.frame_height + (self.rows - 1) * self.spacing + 2 * self.margin


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float


@dataclass(frozen=True)
class NormalizationSpec:
    edge_guard_px: int = 1
    baseline_tolerance_px: int = 2
    body_scale_tolerance_ratio: float = 0.08
    allow_per_frame_scaling: bool = False


@dataclass(frozen=True)
class AnimationRow:
    name: str
    row: int
    frames: int
    loop: bool = False


@dataclass(frozen=True)
class Profile:
    schema: str
    profile_id: str
    atlas: AtlasSpec
    output_format: str
    output_mode: str
    background: str
    scale_mode: str
    anchor: Anchor
    normalization: NormalizationSpec
    animations: tuple[AnimationRow, ...]

    def animation_for_row(self, row: int) -> AnimationRow | None:
        for animation in self.animations:
            if animation.row == row:
                return animation
        return None

    def required_occupied_counts(self) -> dict[str, int]:
        return {a.name: a.frames for a in self.animations}


def load_profile(path: Path) -> Profile:
    data = json.loads(path.read_text(encoding="utf-8"))
    atlas = data["atlas"]
    output = data.get("output", {})
    norm = data.get("normalization", {})
    animations = tuple(
        AnimationRow(
            name=item["name"],
            row=int(item["row"]),
            frames=int(item["frames"]),
            loop=bool(item.get("loop", False)),
        )
        for item in data["animations"]
    )
    return Profile(
        schema=data.get("schema", "sprite_atlas.profile.v1"),
        profile_id=data["profile_id"],
        atlas=AtlasSpec(
            columns=int(atlas["columns"]),
            rows=int(atlas["rows"]),
            frame_width=int(atlas["frame_width"]),
            frame_height=int(atlas["frame_height"]),
            margin=int(atlas.get("margin", 0)),
            spacing=int(atlas.get("spacing", 0)),
        ),
        output_format=output.get("format", "png"),
        output_mode=output.get("mode", "RGBA"),
        background=output.get("background", "transparent"),
        scale_mode=output.get("scale_mode", "nearest_neighbor"),
        anchor=Anchor(float(data["anchor"]["x"]), float(data["anchor"]["y"])),
        normalization=NormalizationSpec(
            edge_guard_px=int(norm.get("edge_guard_px", 1)),
            baseline_tolerance_px=int(norm.get("baseline_tolerance_px", 2)),
            body_scale_tolerance_ratio=float(norm.get("body_scale_tolerance_ratio", 0.08)),
            allow_per_frame_scaling=bool(norm.get("allow_per_frame_scaling", False)),
        ),
        animations=animations,
    )


@dataclass(frozen=True)
class SourceBBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def as_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class FrameMapping:
    target_column: int
    source_bbox: SourceBBox


@dataclass
class RowMapping:
    target_row: int
    animation: str
    frames: list[FrameMapping]


@dataclass
class MappingDocument:
    schema: str
    source_sha256: str
    rows: list[RowMapping]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_sha256": self.source_sha256,
            "rows": [
                {
                    "target_row": row.target_row,
                    "animation": row.animation,
                    "frames": [
                        {
                            "target_column": frame.target_column,
                            "source_bbox": frame.source_bbox.as_list(),
                        }
                        for frame in row.frames
                    ],
                }
                for row in self.rows
            ],
        }


def load_mapping(path: Path, *, source_sha256: str) -> MappingDocument:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[RowMapping] = []
    for row in data["rows"]:
        frames = [
            FrameMapping(
                target_column=int(frame["target_column"]),
                source_bbox=SourceBBox(*[int(v) for v in frame["source_bbox"]]),
            )
            for frame in row["frames"]
        ]
        rows.append(
            RowMapping(
                target_row=int(row["target_row"]),
                animation=str(row["animation"]),
                frames=frames,
            )
        )
    return MappingDocument(
        schema=data.get("schema", "sprite_atlas.mapping.v1"),
        source_sha256=data.get("source_sha256", source_sha256),
        rows=rows,
    )
