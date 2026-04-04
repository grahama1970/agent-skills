"""Score and compare Camelot extraction results."""
from __future__ import annotations

from .probe import ProbeResult


def quality_grade(result: ProbeResult) -> str:
    """Return a human-readable quality grade.

    Returns:
        "excellent" | "good" | "poor" | "failed"
    """
    if result.error or result.table_count == 0:
        return "failed"
    if result.fragmentation == 0 and result.cell_count >= 10:
        return "excellent"
    if result.fragmentation == 0:
        return "good"
    return "poor"


def score_result(result: ProbeResult) -> float:
    """Compute composite quality score for a probe result.

    Higher is better. Rewards cell count, penalizes fragmentation.
    Returns -1.0 for failed extractions.

    Lattice mode gets a small preference bonus because it produces
    structurally cleaner tables for most PDFs (especially standards docs).
    """
    if result.error or result.table_count == 0:
        return -1.0

    # Base score: cell count minus fragmentation penalty (3x, not 10x —
    # many "fragmented" cells are just multi-line content with internal newlines)
    score = float(result.cell_count) - (result.fragmentation * 3.0)

    # Lattice preference: +10% bonus. Lattice tables have real grid structure,
    # stream mode often hallucinates table boundaries in running text.
    if result.flavor == "lattice":
        score *= 1.1

    # Don't let valid extractions score below 0.1
    return max(0.1, score) if result.table_count > 0 else score


def compare_results(a: ProbeResult, b: ProbeResult) -> dict:
    """Compare two probe results and explain which is better.

    Returns dict with 'winner' ('a' or 'b'), 'reason', and metrics.
    """
    sa = score_result(a)
    sb = score_result(b)

    a_label = _label(a)
    b_label = _label(b)

    if sa < 0 and sb < 0:
        return {
            "winner": "neither",
            "reason": "Both extractions failed or found no tables",
            "a": {"label": a_label, "score": sa},
            "b": {"label": b_label, "score": sb},
        }

    if sa > sb:
        winner, loser, wl, ll = a, b, a_label, b_label
        winner_key = "a"
    else:
        winner, loser, wl, ll = b, a, b_label, a_label
        winner_key = "b"

    reasons = []
    if winner.fragmentation < loser.fragmentation:
        reasons.append(f"lower fragmentation ({winner.fragmentation} vs {loser.fragmentation})")
    if winner.cell_count > loser.cell_count:
        reasons.append(f"more cells ({winner.cell_count} vs {loser.cell_count})")
    if winner.table_count > loser.table_count:
        reasons.append(f"more tables ({winner.table_count} vs {loser.table_count})")
    if winner.duration_ms < loser.duration_ms:
        reasons.append(f"faster ({winner.duration_ms}ms vs {loser.duration_ms}ms)")

    reason = f"{wl} wins: " + (", ".join(reasons) if reasons else f"higher score ({max(sa,sb):.0f} vs {min(sa,sb):.0f})")

    return {
        "winner": winner_key,
        "reason": reason,
        "a": {
            "label": a_label,
            "score": sa,
            "tables": a.table_count,
            "cells": a.cell_count,
            "fragmentation": a.fragmentation,
            "duration_ms": a.duration_ms,
        },
        "b": {
            "label": b_label,
            "score": sb,
            "tables": b.table_count,
            "cells": b.cell_count,
            "fragmentation": b.fragmentation,
            "duration_ms": b.duration_ms,
        },
    }


def is_good_enough(
    result: ProbeResult,
    min_cells: int = 4,
    max_fragmentation: int = 0,
) -> bool:
    """Check if a result is good enough to stop tuning.

    Args:
        result: Probe result to evaluate.
        min_cells: Minimum cell count (default 4 = at least a 2x2 table).
        max_fragmentation: Maximum allowed fragmentation (default 0).

    Returns:
        True if result meets quality thresholds.
    """
    return (
        result.table_count > 0
        and result.fragmentation <= max_fragmentation
        and result.cell_count >= min_cells
        and result.error is None
    )


def _label(r: ProbeResult) -> str:
    """Human-readable label for a probe result."""
    if r.flavor == "lattice":
        return f"lattice(ls={r.line_scale})"
    else:
        return f"stream(et={r.edge_tol})"
