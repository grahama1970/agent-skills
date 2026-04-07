"""Compatibility layer for the extractor pipeline.

Converts ExtractionResult to the format expected by s05_table_extractor.py.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ExtractionResult, Table


# Strategy parameter mappings
STRATEGY_PARAMS = {
    "lattice_default": {
        "strategy": "lattice",
        "line_scale": 15,
        "process_background": False,
        "line_tol": 2,
        "joint_tol": 2,
    },
    "lattice_strong": {
        "strategy": "lattice",
        "line_scale": 40,
        "process_background": True,
        "line_tol": 2,
        "joint_tol": 2,
    },
    "stream_default": {
        "strategy": "stream",
        "edge_tol": 50,
        "row_tol": 2,
        "column_tol": 0,
    },
    "stream_tight": {
        "strategy": "stream",
        "edge_tol": 30,
        "row_tol": 1,
        "column_tol": 0,
    },
    "network_default": {
        "strategy": "network",
    },
    "hybrid_default": {
        "strategy": "hybrid",
    },
}

# Base strategies (no variant suffix)
_BASE_STRATEGIES = {"lattice", "stream", "network", "hybrid"}


def to_extractor_format(result) -> list[dict]:
    """Convert ExtractionResult to extractor pipeline format.

    Each table becomes a dict with:
    - page_number: int (1-indexed)
    - page_index: int (0-indexed)
    - bbox: tuple (x0, y0, x1, y1) — top-left origin
    - pandas_df: dict (from table.df.to_pandas().to_dict('records'))
    - strategy: str
    - accuracy: float
    - whitespace: float
    - title: str or None
    - ai_title: str or None
    - ai_description: str or None
    - ai_headers: list or None
    - components: list or None (for merged tables)
    """
    output = []
    for table in result:
        try:
            df = table.df
            if df is not None and len(df) > 0:
                pandas_df = df.to_pandas().to_dict('records')
            else:
                pandas_df = []
        except Exception:
            pandas_df = []

        output.append({
            "page_number": table.page_number,
            "page_index": table.page_index,
            "bbox": table.bbox,
            "pandas_df": pandas_df,
            "strategy": table.strategy,
            "accuracy": table.accuracy,
            "whitespace": table.whitespace,
            "title": table.title,
            "ai_title": table.ai_title,
            "ai_description": table.ai_description,
            "ai_headers": table.ai_headers,
            "components": table.components,
        })

    return output


def from_extractor_strategy(strategy_name: str) -> dict:
    """Map extractor strategy names to native parser params.

    Args:
        strategy_name: One of "lattice_default", "lattice_strong",
                       "stream_default", "stream_tight", "network_default",
                       "hybrid_default", or a bare strategy name like "lattice".

    Returns:
        Dict of parser parameters.
    """
    # Exact match first
    if strategy_name in STRATEGY_PARAMS:
        return dict(STRATEGY_PARAMS[strategy_name])

    # Bare strategy name (e.g. "stream", "lattice")
    if strategy_name in _BASE_STRATEGIES:
        return {"strategy": strategy_name}

    # Try to parse "<parser>_<variant>" pattern
    parts = strategy_name.rsplit("_", 1)
    if len(parts) == 2 and parts[0] in _BASE_STRATEGIES:
        return {"strategy": parts[0]}

    # Default fallback
    return {"strategy": "auto"}
