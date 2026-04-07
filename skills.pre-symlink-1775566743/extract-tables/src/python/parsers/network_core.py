"""Text alignment network core -- helper functions and alignment classes.

Extracted from network.py to keep both modules under 800 lines.
Used by NetworkParser for text-based table detection.

All coordinates use top-left origin: (x0, y0_top, x1, y1_bottom) where y=0
is the top of the page.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from ..pdf_bridge import TextElement


# Maximum number of columns over which a header can spread
MAX_COL_SPREAD_IN_HEADER = 3

# Minimum number of textlines in a table
MINIMUM_TEXTLINES_IN_TABLE = 6

# Alignment names
HORIZONTAL_ALIGNMENTS = ["left", "right", "middle"]
VERTICAL_ALIGNMENTS = ["top", "bottom", "center"]
ALL_ALIGNMENTS = HORIZONTAL_ALIGNMENTS + VERTICAL_ALIGNMENTS


def _get_textline_coords(tl: TextElement) -> dict[str, float]:
    """Calculate alignment coordinates for a text element."""
    return {
        "left": tl.x0,
        "right": tl.x1,
        "middle": (tl.x0 + tl.x1) / 2.0,
        "top": tl.y0,       # top-left origin: y0 is top
        "bottom": tl.y1,    # y1 is bottom
        "center": (tl.y0 + tl.y1) / 2.0,
    }


def _get_index_closest_point(
    point: float,
    sorted_list: list,
    fn=lambda x: x,
) -> Optional[int]:
    """Find index of closest point in a sorted list using binary search."""
    n = len(sorted_list)
    if n == 0:
        return None
    if point <= fn(sorted_list[0]):
        return 0
    if point >= fn(sorted_list[-1]):
        return n - 1

    left, right = 0, n - 1
    while left < right:
        mid = (left + right) // 2
        if fn(sorted_list[mid]) < point:
            left = mid + 1
        else:
            right = mid

    if left == 0:
        return 0
    if left == n:
        return n - 1

    before = fn(sorted_list[left - 1])
    after = fn(sorted_list[left])
    if abs(point - before) <= abs(point - after):
        return left - 1
    return left


def _bbox_from_textlines(textlines: list[TextElement]) -> Optional[tuple[float, float, float, float]]:
    """Return smallest bbox containing all text elements (top-left origin)."""
    if not textlines:
        return None
    x0 = min(t.x0 for t in textlines)
    y0 = min(t.y0 for t in textlines)  # smallest y0 = topmost
    x1 = max(t.x1 for t in textlines)
    y1 = max(t.y1 for t in textlines)  # largest y1 = bottommost
    return (x0, y0, x1, y1)


def _text_in_bbox(bbox: list | tuple, text: list[TextElement]) -> list[TextElement]:
    """Return text elements whose center lies within bbox (top-left origin).

    bbox: (x0, y0_top, x1, y1_bottom)
    """
    x0, y0, x1, y1 = bbox
    return [
        t for t in text
        if x0 - 2 <= (t.x0 + t.x1) / 2.0 <= x1 + 2
        and y0 - 2 <= (t.y0 + t.y1) / 2.0 <= y1 + 2
    ]


def _textlines_overlapping_bbox(
    bbox: list | tuple, textlines: list[TextElement]
) -> list[TextElement]:
    """Return all text elements that overlap with a bbox (top-left origin)."""
    x0, y0, x1, y1 = bbox
    return [
        t for t in textlines
        if t.x1 >= x0 and t.x0 <= x1 and t.y1 >= y0 and t.y0 <= y1
    ]


def _find_columns_boundaries(tls: list[TextElement], min_gap: float = 1.0) -> list[list[float]]:
    """Find disjoint column boundaries from text elements."""
    cols_bounds: list[list[float]] = []
    sorted_tls = sorted(tls, key=lambda tl: tl.x0)
    for tl in sorted_tls:
        if not cols_bounds or cols_bounds[-1][1] + min_gap < tl.x0:
            cols_bounds.append([tl.x0, tl.x1])
        else:
            cols_bounds[-1][1] = max(cols_bounds[-1][1], tl.x1)
    return cols_bounds


def _boundaries_to_split_lines(boundaries: list[list[float]]) -> list[float]:
    """Find split lines given column/row boundaries.

    Returns anchor points: left of first, midpoints between boundaries, right of last.
    """
    if not boundaries:
        return []
    anchors = [
        (boundaries[i - 1][1] + boundaries[i][0]) / 2.0
        for i in range(1, len(boundaries))
    ]
    anchors.insert(0, boundaries[0][0])
    anchors.append(boundaries[-1][1])
    return anchors


def _column_spread(left: float, right: float, col_anchors: list[float]) -> int:
    """Get the number of columns crossed by a segment [left, right]."""
    index_left = 0
    while index_left < len(col_anchors) and col_anchors[index_left] < left:
        index_left += 1
    index_right = index_left
    while index_right < len(col_anchors) and col_anchors[index_right] < right:
        index_right += 1
    return index_right - index_left


def _find_closest_tls(
    bbox: list[float], tls: list[TextElement]
) -> dict[str, Optional[TextElement]]:
    """Find closest text elements outside the bbox in all 4 directions.

    In top-left origin:
    - bbox = [x0, y0_top, x1, y1_bottom]
    - "top" means y < y0_top (above)
    - "bottom" means y > y1_bottom (below)
    """
    left_tl: Optional[TextElement] = None
    right_tl: Optional[TextElement] = None
    top_tl: Optional[TextElement] = None
    bottom_tl: Optional[TextElement] = None

    bbox_left, bbox_top, bbox_right, bbox_bottom = bbox

    for tl in tls:
        if tl.x1 < bbox_left:
            # Left: must overlap vertically
            if tl.y0 > bbox_bottom or tl.y1 < bbox_top:
                continue
            if left_tl is None or left_tl.x1 < tl.x1:
                left_tl = tl
        elif bbox_right < tl.x0:
            # Right: must overlap vertically
            if tl.y0 > bbox_bottom or tl.y1 < bbox_top:
                continue
            if right_tl is None or right_tl.x0 > tl.x0:
                right_tl = tl
        else:
            # Must overlap horizontally
            if tl.x0 > bbox_right or tl.x1 < bbox_left:
                continue
            if tl.y1 < bbox_top:
                # Above (top) in top-left origin: y1 < bbox_top
                if top_tl is None or top_tl.y1 < tl.y1:
                    top_tl = tl
            elif bbox_bottom < tl.y0:
                # Below (bottom) in top-left origin: y0 > bbox_bottom
                if bottom_tl is None or bottom_tl.y0 > tl.y0:
                    bottom_tl = tl

    return {
        "left": left_tl,
        "right": right_tl,
        "top": top_tl,
        "bottom": bottom_tl,
    }


def _extract_zones(
    all_above: list[TextElement], max_v_gap: float, top: float
) -> tuple[list[list[float]], float]:
    """Extract zones from textlines above the body bbox.

    In top-left origin, "above" means lower y values.
    'top' here refers to the top boundary y (smallest y of the current table).
    """
    tls_in_new_row = []
    pushed_up = True

    while pushed_up:
        pushed_up = False
        for tl in all_above.copy():
            if tl.y1 > top:
                # The bottom of this element extends below our boundary
                tls_in_new_row.append(tl)
                all_above.remove(tl)
                if tl.y0 < top:
                    # Extends above our current boundary
                    top = tl.y0
                    pushed_up = True

    return [[tl.x0, tl.x1] for tl in tls_in_new_row], top


def _merge_zones(zones: list[list[float]]) -> list[list[float]]:
    """Merge overlapping zones into consolidated zones."""
    zones.sort(key=lambda z: z[0])
    merged: list[list[float]] = []
    for zone in zones:
        if not merged or merged[-1][1] < zone[0]:
            merged.append(zone)
        else:
            merged[-1][1] = max(merged[-1][1], zone[1])
    return merged


def _search_header_from_body_bbox(
    body_bbox: tuple[float, float, float, float],
    textlines: list[TextElement],
    col_anchors: list[float],
    max_v_gap: float,
) -> tuple[float, float, float, float]:
    """Expand bbox upward by looking for plausible headers.

    In top-left origin, "up" means decreasing y values.
    body_bbox: (x0, y0_top, x1, y1_bottom)
    """
    new_bbox = body_bbox
    left, top, right, bottom = body_bbox

    keep_searching = True
    while keep_searching:
        keep_searching = False
        # Find text elements above the bbox (y0 < top, center within horizontal bounds)
        all_above = [
            tl for tl in textlines
            if tl.y1 < top and left < (tl.x0 + tl.x1) / 2.0 < right
        ]

        if not all_above:
            break

        closest_above = max(all_above, key=lambda tl: tl.y1)

        if closest_above and top - closest_above.y1 < max_v_gap:
            zones, new_top = _extract_zones(all_above, max_v_gap, closest_above.y0)
            merged_zones = _merge_zones(zones)

            if not merged_zones:
                break

            max_spread = max(
                _column_spread(zone[0], zone[1], col_anchors) for zone in merged_zones
            )

            if max_spread <= min(
                MAX_COL_SPREAD_IN_HEADER, math.ceil(len(col_anchors) / 2)
            ):
                top = new_top
                new_bbox = (left, top, right, bottom)
                keep_searching = True

    return new_bbox


# ---------------------------------------------------------------------------
# TextAlignment classes (ported from camelot.core)
# ---------------------------------------------------------------------------

class TextAlignment:
    """A list of textlines sharing an alignment on a coordinate."""

    def __init__(self, coord: float, textline: TextElement, align: str):
        self.coord = coord
        self.textlines: list[TextElement] = [textline]
        self.align = align

    def register_aligned_textline(self, textline: TextElement, coord: float):
        """Add a textline to this alignment, updating the running average."""
        self.coord = (self.coord * len(self.textlines) + coord) / float(
            len(self.textlines) + 1
        )
        self.textlines.append(textline)


class TextAlignments:
    """Dict of text alignments across reference alignment dimensions."""

    def __init__(self, alignment_names: list[str]):
        self._text_alignments: dict[str, list[TextAlignment]] = {
            name: [] for name in alignment_names
        }

    def _update_alignment(self, alignment: TextAlignment, coord: float, textline: TextElement):
        """Update alignment with new textline. Override in subclasses."""
        pass

    def _register_textline(self, textline: TextElement):
        """Register a textline across all alignment dimensions."""
        coords = _get_textline_coords(textline)
        for alignment_id, alignment_array in self._text_alignments.items():
            coord = coords[alignment_id]

            idx_closest = _get_index_closest_point(
                coord, alignment_array, fn=lambda x: x.coord
            )

            idx_insert = None
            if idx_closest is None:
                idx_insert = 0
            else:
                coord_closest = alignment_array[idx_closest].coord
                if coord - 0.5 < coord_closest < coord + 0.5:
                    self._update_alignment(
                        alignment_array[idx_closest], coord, textline
                    )
                elif coord_closest < coord:
                    idx_insert = idx_closest + 1
                else:
                    idx_insert = idx_closest

            if idx_insert is not None:
                new_alignment = TextAlignment(coord, textline, alignment_id)
                alignment_array.insert(idx_insert, new_alignment)


class AlignmentCounter:
    """For a given textline, tracks all other textlines aligned with it."""

    def __init__(self):
        self.alignment_to_occurrences: dict[str, list[TextElement]] = {
            a: [] for a in ALL_ALIGNMENTS
        }

    def __getitem__(self, key: str) -> list[TextElement]:
        return self.alignment_to_occurrences[key]

    def __setitem__(self, key: str, value: list[TextElement]):
        self.alignment_to_occurrences[key] = value

    def max_alignments(self, alignment_ids=None):
        """Get alignment dimension with the max number of textlines."""
        alignment_ids = alignment_ids or self.alignment_to_occurrences.keys()
        alignment_items = [
            (aid, self.alignment_to_occurrences[aid]) for aid in alignment_ids
        ]
        return max(alignment_items, key=lambda item: len(item[1]))

    def max_v(self):
        """Tuple (alignment_id, textlines) of largest vertical column."""
        return self.max_alignments(HORIZONTAL_ALIGNMENTS)

    def max_h(self):
        """Tuple (alignment_id, textlines) of largest horizontal row."""
        return self.max_alignments(VERTICAL_ALIGNMENTS)

    def max_v_count(self) -> int:
        return len(self.max_v()[1])

    def max_h_count(self) -> int:
        return len(self.max_h()[1])

    def alignment_score(self) -> int:
        """Product of (v_count - 1) * (h_count - 1)."""
        return (self.max_v_count() - 1) * (self.max_h_count() - 1)


class _IdentityDict:
    """Dict that uses object identity (id()) as keys instead of __hash__."""

    def __init__(self):
        self._data: dict[int, Any] = {}
        self._keys: dict[int, Any] = {}  # id -> actual key object

    def get(self, key, default=None):
        return self._data.get(id(key), default)

    def __setitem__(self, key, value):
        kid = id(key)
        self._data[kid] = value
        self._keys[kid] = key

    def __getitem__(self, key):
        return self._data[id(key)]

    def __contains__(self, key):
        return id(key) in self._data

    def keys(self):
        return self._keys.values()

    def values(self):
        return self._data.values()

    def items(self):
        for kid, val in self._data.items():
            yield self._keys[kid], val

    def __len__(self):
        return len(self._data)

    def __bool__(self):
        return bool(self._data)


class TextNetworks(TextAlignments):
    """Text elements connected by vertical AND horizontal alignments."""

    def __init__(self):
        super().__init__(ALL_ALIGNMENTS)
        self._textline_to_alignments = _IdentityDict()

    def _update_alignment(self, alignment: TextAlignment, coord: float, textline: TextElement):
        alignment.register_aligned_textline(textline, coord)

    def _register_all_text_lines(self, textlines: list[TextElement]):
        for tl in textlines:
            if tl.text.strip():
                self._register_textline(tl)

    def _compute_alignment_counts(self):
        """Build textline -> AlignmentCounter mapping."""
        for align_id, textedges in self._text_alignments.items():
            for textedge in textedges:
                for tl in textedge.textlines:
                    ac = self._textline_to_alignments.get(tl)
                    if ac is None:
                        ac = AlignmentCounter()
                        self._textline_to_alignments[tl] = ac
                    ac[align_id] = textedge.textlines

    def remove_unconnected_edges(self):
        """Remove elements only connected on one dimension."""
        removed = True
        while removed:
            removed = False
            for text_alignments in self._text_alignments.values():
                for ta in text_alignments:
                    to_remove = []
                    for i, tl in enumerate(ta.textlines):
                        ac = self._textline_to_alignments.get(tl)
                        if ac is None:
                            to_remove.append(i)
                            continue
                        if ac.max_h_count() <= 1 or ac.max_v_count() <= 1:
                            to_remove.append(i)
                    for idx in reversed(to_remove):
                        del ta.textlines[idx]
                        removed = True
            self._textline_to_alignments = _IdentityDict()
            self._compute_alignment_counts()

    def most_connected_textline(self) -> Optional[TextElement]:
        """Retrieve the most connected textline.

        In top-left origin, prefer textlines further down (larger y0).
        """
        if not self._textline_to_alignments:
            return None
        return max(
            self._textline_to_alignments.keys(),
            key=lambda tl: (
                self._textline_to_alignments[tl].alignment_score(),
                tl.y0,   # prefer further down (larger y in top-left)
                tl.x0,
            ),
            default=None,
        )

    def compute_plausible_gaps(self) -> Optional[tuple[float, float]]:
        """Evaluate plausible gaps between cells (h_gap, v_gap)."""
        most_aligned_tl = self.most_connected_textline()
        if most_aligned_tl is None:
            return None

        best_alignment = self._textline_to_alignments.get(most_aligned_tl)
        if best_alignment is None:
            return None

        __, ref_h_textlines = best_alignment.max_h()
        __, ref_v_textlines = best_alignment.max_v()

        if len(ref_v_textlines) <= 1 or len(ref_h_textlines) <= 1:
            return None

        h_textlines = sorted(ref_h_textlines, key=lambda tl: tl.x0)
        v_textlines = sorted(ref_v_textlines, key=lambda tl: tl.y0)

        h_gaps = [
            h_textlines[i].x0 - h_textlines[i - 1].x0
            for i in range(1, len(h_textlines))
        ]
        v_gaps = [
            v_textlines[i].y0 - v_textlines[i - 1].y0
            for i in range(1, len(v_textlines))
        ]

        if not h_gaps or not v_gaps:
            return None

        # 75th percentile
        h_gaps_sorted = sorted(h_gaps)
        v_gaps_sorted = sorted(v_gaps)
        h_p75 = h_gaps_sorted[int(len(h_gaps_sorted) * 0.75)]
        v_p75 = v_gaps_sorted[int(len(v_gaps_sorted) * 0.75)]

        return (2.0 * h_p75, 2.0 * v_p75)

    def can_expand_bbox(
        self,
        cand_bbox: list[float],
        textline: TextElement,
        gaps_hv: tuple[float, float],
        direction: str,
    ) -> bool:
        """Check if bbox can be expanded in direction toward textline.

        cand_bbox: [x0, y0_top, x1, y1_bottom] (top-left origin)
        """
        if direction == "left":
            return cand_bbox[0] - textline.x1 <= gaps_hv[0]
        elif direction == "right":
            return textline.x0 - cand_bbox[2] <= gaps_hv[0]
        elif direction == "top":
            # textline is above: cand_bbox[1] - textline.y1 is the gap
            return cand_bbox[1] - textline.y1 <= gaps_hv[1]
        elif direction == "bottom":
            # textline is below: textline.y0 - cand_bbox[3] is the gap
            return textline.y0 - cand_bbox[3] <= gaps_hv[1]
        return False

    def get_expanded_bbox(
        self,
        cand_bbox: list[float],
        textline: TextElement,
        direction: str,
    ) -> list[float]:
        """Get expanded bbox in the given direction."""
        expanded = cand_bbox.copy()
        if direction == "left":
            expanded[0] = textline.x0
        elif direction == "right":
            expanded[2] = textline.x1
        elif direction == "top":
            expanded[1] = textline.y0
        elif direction == "bottom":
            expanded[3] = textline.y1
        return expanded

    def is_valid_expansion(
        self,
        direction: str,
        tls_in_new_box: list[TextElement],
        last_cols_bounds: list,
    ) -> bool:
        """Check if expansion is valid (doesn't reduce column count for vertical expansion)."""
        cols_bounds = _find_columns_boundaries(tls_in_new_box)
        return not (
            direction in ["bottom", "top"] and len(cols_bounds) < len(last_cols_bounds)
        )

    def expand_bbox(
        self,
        bbox: list[float],
        closest_tls: dict[str, Optional[TextElement]],
        tls_search_space: list[TextElement],
        gaps_hv: tuple[float, float],
        last_cols_bounds: list,
        tls_in_bbox: list[TextElement],
    ) -> tuple[list[float], list, list[TextElement], list[TextElement]]:
        """Expand the bbox based on closest textlines."""
        cand_bbox = bbox.copy()

        for direction, textline in closest_tls.items():
            if textline is None or not self.can_expand_bbox(
                cand_bbox, textline, gaps_hv, direction
            ):
                continue

            expanded_cand_bbox = self.get_expanded_bbox(cand_bbox, textline, direction)
            new_tls = _text_in_bbox(expanded_cand_bbox, tls_search_space)
            tls_in_new_box = new_tls + tls_in_bbox

            if not self.is_valid_expansion(direction, tls_in_new_box, last_cols_bounds):
                continue

            all_tls = tls_in_bbox + new_tls
            new_bounds = _bbox_from_textlines(all_tls)
            if new_bounds:
                bbox = cand_bbox = list(new_bounds)
            last_cols_bounds = _find_columns_boundaries(all_tls)
            tls_in_bbox.extend(new_tls)
            # Remove from search space
            new_set = set(id(t) for t in new_tls)
            tls_search_space[:] = [t for t in tls_search_space if id(t) not in new_set]

        return bbox, last_cols_bounds, tls_in_bbox, tls_search_space

    def search_table_body(
        self,
        gaps_hv: tuple[float, float],
    ) -> Optional[list[float]]:
        """Build a candidate bbox for the table body.

        Returns [x0, y0_top, x1, y1_bottom] or None.
        """
        most_aligned_tl = self.most_connected_textline()
        if most_aligned_tl is None:
            return None

        bbox = [
            most_aligned_tl.x0,
            most_aligned_tl.y0,
            most_aligned_tl.x1,
            most_aligned_tl.y1,
        ]

        tls_search_space = list(self._textline_to_alignments.keys())
        tls_search_space = [t for t in tls_search_space if t is not most_aligned_tl]
        tls_in_bbox = [most_aligned_tl]
        last_bbox = None
        last_cols_bounds = [(most_aligned_tl.x0, most_aligned_tl.x1)]

        while last_bbox != bbox:
            last_bbox = bbox
            closest_tls = _find_closest_tls(bbox, tls_search_space)
            bbox, last_cols_bounds, tls_in_bbox, tls_search_space = self.expand_bbox(
                bbox,
                closest_tls,
                tls_search_space,
                gaps_hv,
                last_cols_bounds,
                tls_in_bbox,
            )

        if len(tls_in_bbox) >= MINIMUM_TEXTLINES_IN_TABLE:
            return bbox
        return None

    def generate(self, textlines: list[TextElement]):
        """Generate the text alignment network from textlines."""
        self._register_all_text_lines(textlines)
        self._compute_alignment_counts()
