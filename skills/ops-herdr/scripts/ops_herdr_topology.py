#!/usr/bin/env python3
"""Grid planning and materialization for Herdr spaces.

Inputs: a requested rectangle (rows x columns) or an agent count.
Outputs: a deterministic split plan, and — when executed — a live Herdr tab whose
leaf panes map one-to-one onto grid cells.

The planner is pure and separately testable; nothing here talks to Herdr until
`materialize_grid` is called. Splits are planned by recursive balanced
partitioning rather than by repeatedly splitting the most recent pane, which
degenerates into ever-narrower slivers and makes cell order impossible to reason
about.
"""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path
from typing import Any

from loguru import logger

from ops_herdr_core import (
    HerdrContractError,
    TabTopology,
    layout_pane_ids,
    pane_layout,
    split_pane,
)

GRID_RE = re.compile(r"^(\d+)x(\d+)$")

# A cell that renders at zero size is not a useful success state, so the planner
# refuses rectangles no operator could read.
MAX_ROWS = 8
MAX_COLUMNS = 8


@dataclasses.dataclass(frozen=True, slots=True)
class SplitOp:
    """One planned split: divide the region anchored at `source_cell`."""

    source_cell: tuple[int, int]
    direction: str
    ratio: float
    new_cell: tuple[int, int]


@dataclasses.dataclass(frozen=True, slots=True)
class GridPlan:
    """A deterministic plan for one rows x columns grid."""

    rows: int
    columns: int
    splits: tuple[SplitOp, ...]
    cells: tuple[tuple[int, int], ...]

    @property
    def cell_count(self) -> int:
        """Return how many leaf panes this plan produces."""
        return self.rows * self.columns

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the plan."""
        return {
            "rows": self.rows,
            "columns": self.columns,
            "cell_count": self.cell_count,
            "cells": [list(cell) for cell in self.cells],
            "splits": [
                {
                    "source_cell": list(op.source_cell),
                    "direction": op.direction,
                    "ratio": op.ratio,
                    "new_cell": list(op.new_cell),
                }
                for op in self.splits
            ],
        }


def parse_grid(value: str) -> tuple[int, int]:
    """Parse a ROWSxCOLS string into a validated rectangle."""
    match = GRID_RE.match(value.strip().lower())
    if not match:
        raise ValueError(f"grid must look like ROWSxCOLS, got {value!r}")
    return validate_dimensions(int(match.group(1)), int(match.group(2)))


def validate_dimensions(rows: int, columns: int) -> tuple[int, int]:
    """Reject zero, negative, and unreadable rectangles."""
    if rows < 1 or columns < 1:
        raise ValueError(f"grid dimensions must be >= 1, got {rows}x{columns}")
    if rows > MAX_ROWS or columns > MAX_COLUMNS:
        raise ValueError(
            f"grid {rows}x{columns} exceeds the {MAX_ROWS}x{MAX_COLUMNS} cap; "
            "panes that small are not readable"
        )
    return rows, columns


def grid_for_count(count: int) -> tuple[int, int]:
    """Choose the most balanced rectangle that holds `count` agents.

    Deliberately returns 1x3 for three rather than a 2x2 with a dead cell: a
    silently wasted pane is a worse default than an honest row of three.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    rows = int(math.isqrt(count))
    columns = math.ceil(count / rows) if rows else count
    return validate_dimensions(rows, columns)


def plan_grid(rows: int, columns: int) -> GridPlan:
    """Plan a balanced split tree for a rows x columns grid."""
    rows, columns = validate_dimensions(rows, columns)
    splits: list[SplitOp] = []

    def partition(r0: int, c0: int, r1: int, c1: int) -> None:
        """Recursively halve a cell region along its longer dimension."""
        height, width = r1 - r0, c1 - c0
        if height * width <= 1:
            return
        if width >= height:
            mid = c0 + width // 2
            splits.append(SplitOp((r0, c0), "right", round((mid - c0) / width, 6), (r0, mid)))
            partition(r0, c0, r1, mid)
            partition(r0, mid, r1, c1)
        else:
            mid = r0 + height // 2
            splits.append(SplitOp((r0, c0), "down", round((mid - r0) / height, 6), (mid, c0)))
            partition(r0, c0, mid, c1)
            partition(mid, c0, r1, c1)

    partition(0, 0, rows, columns)
    cells = tuple((r, c) for r in range(rows) for c in range(columns))
    plan = GridPlan(rows=rows, columns=columns, splits=tuple(splits), cells=cells)
    if len(plan.splits) != plan.cell_count - 1:
        raise ValueError(
            f"planner produced {len(plan.splits)} splits for {plan.cell_count} cells; "
            "a binary partition must produce exactly cells - 1"
        )
    return plan


def materialize_grid(
    *,
    tab: TabTopology,
    plan: GridPlan,
    cwd: Path,
    cell_env: dict[tuple[int, int], list[str]] | None = None,
    session: str | None = None,
    herdr_bin: str = "herdr",
) -> dict[tuple[int, int], str]:
    """Execute a grid plan against a live Herdr tab and verify the result.

    Returns the cell-to-pane mapping. Raises if Herdr's own layout readback does
    not contain exactly the panes this function created — a successful exit code
    from `pane split` is not evidence that the grid exists.
    """
    panes: dict[tuple[int, int], str] = {(0, 0): tab.root_pane_id}
    for op in plan.splits:
        source = panes.get(op.source_cell)
        if not source:
            raise HerdrContractError(f"grid plan referenced unbuilt cell {op.source_cell}")
        panes[op.new_cell] = split_pane(
            pane_id=source,
            direction=op.direction,
            ratio=op.ratio,
            cwd=cwd,
            env_values=(cell_env or {}).get(op.new_cell, []),
            session=session,
            herdr_bin=herdr_bin,
        )

    if len(panes) != plan.cell_count:
        raise HerdrContractError(f"expected {plan.cell_count} panes, built {len(panes)}")

    observed = set(layout_pane_ids(pane_layout(pane_id=tab.root_pane_id, session=session, herdr_bin=herdr_bin)))
    if observed != set(panes.values()):
        raise HerdrContractError(
            f"layout readback disagrees with the plan; "
            f"built {sorted(panes.values())}, Herdr reports {sorted(observed)}"
        )
    logger.debug("materialized {}x{} grid: {}", plan.rows, plan.columns, panes)
    return panes


def cells_row_major(plan: GridPlan) -> list[tuple[int, int]]:
    """Return grid cells in row-major order, the order agents are assigned in."""
    return list(plan.cells)
