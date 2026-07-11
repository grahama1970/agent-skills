"""Propose and apply frame mappings."""

from __future__ import annotations

from sprite_atlas.contracts import FrameMapping, MappingDocument, Profile, RowMapping
from sprite_atlas.detect_layout import DetectedRow


def propose_mapping(profile: Profile, detected_rows: list[DetectedRow], *, source_sha256: str) -> MappingDocument:
    rows: list[RowMapping] = []
    for animation in profile.animations:
        detected = next((row for row in detected_rows if row.row_index == animation.row), None)
        frames: list[FrameMapping] = []
        if detected:
            for column_index in range(min(animation.frames, len(detected.frames))):
                frames.append(
                    FrameMapping(
                        target_column=column_index,
                        source_bbox=detected.frames[column_index].bbox,
                    )
                )
        rows.append(RowMapping(target_row=animation.row, animation=animation.name, frames=frames))
    return MappingDocument(schema="sprite_atlas.mapping.v1", source_sha256=source_sha256, rows=rows)


def missing_frame_cells(profile: Profile, mapping: MappingDocument) -> list[dict[str, object]]:
    """List each required grid cell that has no mapped source art."""
    missing: list[dict[str, object]] = []
    for animation in profile.animations:
        row = next((item for item in mapping.rows if item.target_row == animation.row), None)
        present = {frame.target_column for frame in row.frames} if row else set()
        for column in range(animation.frames):
            if column not in present:
                missing.append(
                    {
                        "animation": animation.name,
                        "row": animation.row,
                        "column": column,
                        "frame_name": f"{{sprite}}_{animation.name}_{column}".replace("{sprite}", ""),
                    }
                )
    return missing


def mapping_gaps(profile: Profile, mapping: MappingDocument) -> list[dict[str, object]]:
    missing: list[dict[str, object]] = []
    for animation in profile.animations:
        row = next((item for item in mapping.rows if item.target_row == animation.row), None)
        found = len(row.frames) if row else 0
        if found < animation.frames:
            missing.append(
                {
                    "animation": animation.name,
                    "row": animation.row,
                    "expected": animation.frames,
                    "detected": found,
                    "missing_columns": list(range(found, animation.frames)),
                }
            )
    return missing


def detected_counts(profile: Profile, detected_rows: list[DetectedRow]) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    for animation in profile.animations:
        detected = next((row for row in detected_rows if row.row_index == animation.row), None)
        found = len(detected.frames) if detected else 0
        if found != animation.frames:
            gaps.append(
                {
                    "animation": animation.name,
                    "row": animation.row,
                    "expected": animation.frames,
                    "detected": found,
                    "missing_columns": list(range(min(found, animation.frames), animation.frames)),
                }
            )
    return gaps
