"""
Table quality scoring functions.

Evaluates extracted tables based on:
- Cell parsing accuracy
- Column/row alignment
- Header detection
- Content integrity
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from loguru import logger


@dataclass
class QualityMetrics:
    """Comprehensive quality metrics for extracted table."""
    cell_accuracy: float  # 0-1, how well cells are parsed
    structure_score: float  # 0-1, column/row alignment
    header_score: float  # 0-1, header detection quality
    completeness: float  # 0-1, content not truncated
    overall: float  # Weighted combination


def compute_cell_accuracy(df: pd.DataFrame) -> float:
    """
    Score cell parsing accuracy.

    Checks for:
    - Empty cells that shouldn't be empty
    - Merged cells parsed incorrectly
    - Whitespace issues
    """
    if df.empty:
        return 0.0

    total_cells = df.size
    problematic = 0

    for col in df.columns:
        for val in df[col]:
            val_str = str(val).strip()

            # Empty cell (may be valid, so partial penalty)
            if not val_str or val_str == "nan":
                problematic += 0.3

            # Excessive whitespace (parsing issue)
            elif "  " in val_str:
                problematic += 0.2

            # Truncation indicators
            elif val_str.endswith("...") or val_str.endswith("…"):
                problematic += 0.5

    accuracy = max(0.0, 1.0 - (problematic / total_cells))
    return accuracy


def compute_structure_score(df: pd.DataFrame) -> float:
    """
    Score table structure quality.

    Checks for:
    - Consistent column counts
    - Proper alignment
    - No merged row issues
    """
    if df.empty:
        return 0.0

    score = 1.0

    # Check for ragged columns (inconsistent data types)
    for col in df.columns:
        # If column has mixed types, deduct
        types = df[col].apply(type).unique()
        if len(types) > 2:  # Allow str + NaN
            score -= 0.1

    # Check column names
    if all(str(c).startswith("Unnamed") for c in df.columns):
        score -= 0.2  # No proper headers detected

    # Check for mostly empty columns
    for col in df.columns:
        empty_ratio = df[col].isna().sum() / len(df)
        if empty_ratio > 0.8:
            score -= 0.1

    return max(0.0, score)


def compute_header_score(df: pd.DataFrame, expected_headers: Optional[list] = None) -> float:
    """
    Score header detection quality.

    Args:
        df: Extracted dataframe
        expected_headers: Optional list of expected header names
    """
    if df.empty:
        return 0.0

    score = 1.0

    # Check if headers are generic
    generic_count = sum(
        1 for c in df.columns
        if str(c).startswith("Unnamed") or str(c).startswith("Column")
    )
    generic_ratio = generic_count / len(df.columns)
    score -= 0.3 * generic_ratio

    # Check if first row looks like data, not headers
    if len(df) > 0:
        first_row = df.iloc[0]
        # If all values in first row are numeric, headers might be wrong
        try:
            numeric_count = sum(
                1 for v in first_row
                if pd.to_numeric(str(v).strip(), errors="coerce") is not pd.NA
            )
            if numeric_count == len(first_row):
                score -= 0.2  # First row is all numbers, probably data
        except Exception as e:
            logger.debug("scoring failed: {}", e)

    # Compare with expected headers if provided
    if expected_headers:
        actual = set(str(c).lower() for c in df.columns)
        expected = set(h.lower() for h in expected_headers)
        overlap = len(actual & expected) / max(len(expected), 1)
        score = (score + overlap) / 2

    return max(0.0, score)


def compute_completeness(
    df: pd.DataFrame,
    expected_rows: Optional[int] = None,
    expected_cols: Optional[int] = None,
) -> float:
    """
    Score table completeness.

    Args:
        df: Extracted dataframe
        expected_rows: Optional expected row count
        expected_cols: Optional expected column count
    """
    if df.empty:
        return 0.0

    score = 1.0

    # Check against expectations
    if expected_rows and len(df) < expected_rows:
        score *= len(df) / expected_rows

    if expected_cols and len(df.columns) < expected_cols:
        score *= len(df.columns) / expected_cols

    # Check for truncation indicators in last row/column
    if len(df) > 0:
        last_row = df.iloc[-1]
        for val in last_row:
            if "..." in str(val) or "continued" in str(val).lower():
                score -= 0.2
                break

    return max(0.0, score)


def compute_quality_reward(
    df: pd.DataFrame,
    expected_headers: Optional[list] = None,
    expected_rows: Optional[int] = None,
    expected_cols: Optional[int] = None,
) -> QualityMetrics:
    """
    Compute comprehensive quality metrics for extracted table.

    Returns:
        QualityMetrics with individual scores and overall score.
    """
    cell_accuracy = compute_cell_accuracy(df)
    structure_score = compute_structure_score(df)
    header_score = compute_header_score(df, expected_headers)
    completeness = compute_completeness(df, expected_rows, expected_cols)

    # Weighted overall score
    overall = (
        0.35 * cell_accuracy +
        0.25 * structure_score +
        0.20 * header_score +
        0.20 * completeness
    )

    return QualityMetrics(
        cell_accuracy=cell_accuracy,
        structure_score=structure_score,
        header_score=header_score,
        completeness=completeness,
        overall=overall,
    )


def quality_to_reward(metrics: QualityMetrics) -> float:
    """Convert quality metrics to GRPO reward."""
    return metrics.overall
