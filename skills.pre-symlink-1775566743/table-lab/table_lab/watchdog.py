"""Quality watchdog for batch table tuning.

Implements Pause-Assess-Diagnose-Resume pattern from batch-quality doctrine.
Monitors fragmentation rate and consecutive failures with configurable thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class WatchdogState:
    """Tracks batch tuning quality metrics for watchdog assessment."""

    pdfs_processed: int = 0
    pdfs_with_tables: int = 0
    pdfs_with_fragmentation: int = 0
    total_tables: int = 0
    total_cells: int = 0
    total_fragmentation: int = 0
    consecutive_failures: int = 0
    warnings: list[str] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def fragmentation_rate(self) -> float:
        """Fraction of PDFs with fragmentation > 0."""
        if self.pdfs_processed == 0:
            return 0.0
        return self.pdfs_with_fragmentation / self.pdfs_processed

    @property
    def table_detection_rate(self) -> float:
        """Fraction of PDFs where tables were found."""
        if self.pdfs_processed == 0:
            return 0.0
        return self.pdfs_with_tables / self.pdfs_processed

    def to_dict(self) -> dict:
        """Serialize for checkpoint/logging."""
        return {
            "pdfs_processed": self.pdfs_processed,
            "pdfs_with_tables": self.pdfs_with_tables,
            "pdfs_with_fragmentation": self.pdfs_with_fragmentation,
            "total_tables": self.total_tables,
            "total_cells": self.total_cells,
            "total_fragmentation": self.total_fragmentation,
            "consecutive_failures": self.consecutive_failures,
            "fragmentation_rate": round(self.fragmentation_rate, 3),
            "table_detection_rate": round(self.table_detection_rate, 3),
            "warnings_count": len(self.warnings),
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "started_at": self.started_at,
        }


def assess(
    state: WatchdogState,
    warn_frag_rate: float = 0.65,
    stop_frag_rate: float = 0.55,
    circuit_breaker_max: int = 5,
) -> str:
    """Assess watchdog state and return verdict.

    Returns:
        "ok" | "warn" | "stop"

    Thresholds (from batch-quality doctrine, adapted for table extraction):
        STOP if: consecutive_failures >= circuit_breaker_max, or frag_rate > stop_frag_rate
        WARN if: frag_rate > warn_frag_rate
    """
    if state.stopped:
        return "stop"

    # Circuit breaker: consecutive failures
    if state.consecutive_failures >= circuit_breaker_max:
        state.stopped = True
        state.stop_reason = (
            f"Circuit breaker: {state.consecutive_failures} consecutive failures "
            f"(max {circuit_breaker_max})"
        )
        return "stop"

    # Need minimum 3 PDFs before rate-based assessment
    if state.pdfs_processed >= 3:
        if state.fragmentation_rate > stop_frag_rate:
            state.stopped = True
            state.stop_reason = (
                f"Fragmentation rate {state.fragmentation_rate:.1%} exceeds stop threshold "
                f"{stop_frag_rate:.1%} ({state.pdfs_with_fragmentation}/{state.pdfs_processed} PDFs)"
            )
            return "stop"

        if state.fragmentation_rate > warn_frag_rate:
            msg = (
                f"Fragmentation rate {state.fragmentation_rate:.1%} exceeds warn threshold "
                f"{warn_frag_rate:.1%} ({state.pdfs_with_fragmentation}/{state.pdfs_processed} PDFs)"
            )
            if not state.warnings or state.warnings[-1] != msg:
                state.warnings.append(msg)
            return "warn"

    return "ok"


def record_result(
    state: WatchdogState,
    pdf_name: str,
    has_tables: bool,
    table_count: int,
    cell_count: int,
    fragmentation: int,
    error: str | None = None,
) -> str:
    """Record one PDF result and return watchdog verdict.

    Args:
        state: Mutable watchdog state.
        pdf_name: Name of the PDF processed.
        has_tables: Whether tables were found.
        table_count: Number of tables extracted.
        cell_count: Total cells across all tables.
        fragmentation: Fragmentation score.
        error: Error message if extraction failed.

    Returns:
        Watchdog verdict: "ok" | "warn" | "stop"
    """
    state.pdfs_processed += 1

    if error:
        state.consecutive_failures += 1
    elif has_tables:
        state.pdfs_with_tables += 1
        state.consecutive_failures = 0  # reset on success
        state.total_tables += table_count
        state.total_cells += cell_count
        if fragmentation > 0:
            state.pdfs_with_fragmentation += 1
            state.total_fragmentation += fragmentation
    else:
        # No tables found, no error — not a failure, just empty
        state.consecutive_failures = 0

    return assess(state)
