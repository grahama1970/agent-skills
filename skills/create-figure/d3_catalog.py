#!/usr/bin/env python3
"""
D3.js Visualization Catalog — complete type registry for Stage 2 classifier.

Every visualization type D3.js can produce, with metadata for the /assistant
viz-type-selector to choose the optimal chart for a given dataset.

Used by:
- agent_endpoint.py Stage 2 classifier (data shape -> viz type)
- /analytics skill (data profiling -> viz recommendation)
- /create-figure (rendering dispatch)

Categories mirror the D3 Observable Gallery:
https://observablehq.com/@d3/gallery

This module is a facade that re-exports from:
- d3_catalog_types: enums, dataclasses, D3_VIZ_CATALOG dict
- d3_catalog_entries: all registered VizType instances
Lookup helpers and the recommend_viz heuristic live here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger

# Re-export types so consumers can still do: from d3_catalog import ...
from d3_catalog_types import (  # noqa: F401
    D3_VIZ_CATALOG,
    DataShape,
    RenderBackend,
    VizFamily,
    VizType,
)

# Importing entries triggers registration into D3_VIZ_CATALOG
import d3_catalog_entries  # noqa: F401

logger.debug(
    "D3 catalog loaded: {} viz types registered", len(D3_VIZ_CATALOG)
)


# =============================================================================
# Lookup helpers for the classifier
# =============================================================================

def get_viz_types_for_shape(shape: DataShape) -> List[VizType]:
    """Return all viz types compatible with a given data shape."""
    return [v for v in D3_VIZ_CATALOG.values() if shape in v.data_shapes]


def get_viz_types_for_family(family: VizFamily) -> List[VizType]:
    """Return all viz types in a family."""
    return [v for v in D3_VIZ_CATALOG.values() if v.family == family]


def get_implemented_viz_types() -> List[VizType]:
    """Return only viz types that have a working backend."""
    return [v for v in D3_VIZ_CATALOG.values()
            if v.backend != RenderBackend.NOT_YET]


def get_viz_type(name: str) -> Optional[VizType]:
    """Lookup a viz type by name."""
    return D3_VIZ_CATALOG.get(name)


def match_keywords(query: str) -> List[tuple[str, float]]:
    """Score all viz types against a natural language query.

    Returns list of (viz_name, score) sorted by score descending.
    Used as Tier 0 heuristic in the Stage 2 classifier.
    """
    query_lower = query.lower()
    scores: list[tuple[str, float]] = []

    for name, viz in D3_VIZ_CATALOG.items():
        score = 0.0
        for kw in viz.keywords:
            if kw in query_lower:
                # Longer keyword matches are more specific
                score += len(kw.split()) * 0.2
        if score > 0:
            scores.append((name, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def recommend_viz(
    n_rows: int,
    n_cols: int,
    col_types: Optional[Dict[str, str]] = None,
    has_time: bool = False,
    has_hierarchy: bool = False,
    has_geo: bool = False,
    has_network: bool = False,
    query: Optional[str] = None,
) -> List[tuple[str, float, str]]:
    """Recommend visualization types based on data profile.

    This is the Stage 2 heuristic that /analytics feeds into.

    Args:
        n_rows: Number of data rows
        n_cols: Number of columns
        col_types: Dict of {col_name: "numeric"|"categorical"|"datetime"|"text"}
        has_time: Whether a datetime column exists
        has_hierarchy: Whether data has parent-child structure
        has_geo: Whether geographic coordinates exist
        has_network: Whether nodes/edges structure exists
        query: Optional NL query for keyword boosting

    Returns:
        List of (viz_name, confidence, reason) sorted by confidence desc.
    """
    col_types = col_types or {}
    n_numeric = sum(1 for t in col_types.values() if t == "numeric")
    n_categorical = sum(1 for t in col_types.values() if t == "categorical")
    recommendations: list[tuple[str, float, str]] = []

    for name, viz in D3_VIZ_CATALOG.items():
        # Skip unimplemented types for now
        if viz.backend == RenderBackend.NOT_YET:
            continue

        score = 0.0
        reason_parts: list[str] = []

        # Data point range check
        if n_rows < viz.min_data_points:
            continue
        if viz.max_data_points and n_rows > viz.max_data_points * 3:
            score -= 0.3
            reason_parts.append(f"too many rows ({n_rows})")

        # Dimension check
        if n_cols < viz.min_dimensions:
            continue
        if viz.max_dimensions and n_cols > viz.max_dimensions * 2:
            score -= 0.2

        # Shape-specific scoring
        if has_time and DataShape.TIME_SERIES in viz.data_shapes:
            score += 0.4
            reason_parts.append("time series data")
        if has_hierarchy and DataShape.HIERARCHICAL in viz.data_shapes:
            score += 0.5
            reason_parts.append("hierarchical structure")
        if has_geo and DataShape.GEOGRAPHIC in viz.data_shapes:
            score += 0.5
            reason_parts.append("geographic data")
        if has_network and DataShape.NETWORK in viz.data_shapes:
            score += 0.5
            reason_parts.append("network/graph data")

        # Column type matching
        if n_numeric >= 2 and DataShape.BIVARIATE in viz.data_shapes:
            score += 0.3
            reason_parts.append(f"{n_numeric} numeric columns")
        if n_categorical >= 1 and DataShape.CATEGORICAL in viz.data_shapes:
            score += 0.2
            reason_parts.append("has categories")
        if n_numeric >= 3 and DataShape.MULTIVARIATE in viz.data_shapes:
            score += 0.3
            reason_parts.append("multivariate")

        # Row count sweet spot
        if viz.min_data_points <= n_rows <= (viz.max_data_points or 1000):
            score += 0.2
            reason_parts.append("good row count")

        # Keyword boost from query
        if query:
            kw_scores = match_keywords(query)
            for kw_name, kw_score in kw_scores:
                if kw_name == name:
                    score += kw_score
                    reason_parts.append("keyword match")
                    break

        if score > 0:
            reason = "; ".join(reason_parts) if reason_parts else "general fit"
            recommendations.append((name, round(score, 2), reason))

    recommendations.sort(key=lambda x: x[1], reverse=True)
    return recommendations[:10]  # top 10


def profile_data(
    data: list[dict],
    query: Optional[str] = None,
) -> List[tuple[str, float, str]]:
    """Profile raw data and recommend viz types.

    This is the bridge function that /analytics and any caller can use.
    Takes a list of dicts (rows), auto-detects column types and data shape,
    then delegates to recommend_viz().

    Args:
        data: List of dicts (rows of data)
        query: Optional NL description for keyword boosting

    Returns:
        List of (viz_name, confidence, reason) from recommend_viz()
    """
    if not data:
        return [("table", 0.5, "empty data")]

    # Profile columns from first 100 rows
    sample = data[:100]
    cols = {}
    for row in sample:
        for k, v in row.items():
            if k not in cols:
                cols[k] = []
            cols[k].append(v)

    col_types: Dict[str, str] = {}
    has_time = False
    has_geo = False
    has_hierarchy = False
    has_network = False

    geo_hints = {"lat", "lon", "lng", "latitude", "longitude", "geo", "country", "state"}
    hierarchy_hints = {"parent", "children", "depth", "level", "path"}
    network_hints = {"source", "target", "from", "to", "node", "edge"}
    time_hints = {"date", "time", "timestamp", "created", "updated", "year", "month", "day"}

    for col_name, values in cols.items():
        name_lower = col_name.lower()
        non_none = [v for v in values if v is not None]
        if not non_none:
            col_types[col_name] = "text"
            continue

        # Check numeric
        numeric_count = sum(1 for v in non_none if isinstance(v, (int, float)))
        if numeric_count > len(non_none) * 0.8:
            col_types[col_name] = "numeric"
        else:
            # Check datetime strings
            str_vals = [str(v) for v in non_none[:10]]
            import re
            date_pattern = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}")
            date_count = sum(1 for s in str_vals if date_pattern.search(s))
            if date_count > len(str_vals) * 0.5:
                col_types[col_name] = "datetime"
                has_time = True
            else:
                # Categorical if low cardinality
                unique = len(set(str(v) for v in non_none))
                if unique <= min(20, len(non_none) * 0.5):
                    col_types[col_name] = "categorical"
                else:
                    col_types[col_name] = "text"

        # Detect special shapes from column names
        if name_lower in time_hints or col_types.get(col_name) == "datetime":
            has_time = True
        if name_lower in geo_hints:
            has_geo = True
        if name_lower in hierarchy_hints:
            has_hierarchy = True
        if name_lower in network_hints:
            has_network = True

    n_rows = len(data)
    n_cols = len(col_types)

    logger.debug(
        "profile_data: {} rows, {} cols, types={}, time={}, geo={}, hierarchy={}, network={}",
        n_rows, n_cols, col_types, has_time, has_geo, has_hierarchy, has_network,
    )

    return recommend_viz(
        n_rows=n_rows,
        n_cols=n_cols,
        col_types=col_types,
        has_time=has_time,
        has_hierarchy=has_hierarchy,
        has_geo=has_geo,
        has_network=has_network,
        query=query,
    )


# =============================================================================
# CLI entry point for testing
# =============================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        implemented = get_implemented_viz_types()
        not_yet = [v for v in D3_VIZ_CATALOG.values() if v.backend == RenderBackend.NOT_YET]
        print(f"=== D3 Visualization Catalog: {len(D3_VIZ_CATALOG)} types ===\n")
        print(f"Implemented ({len(implemented)}):")
        for v in implemented:
            cmd = f" -> {v.create_figure_cmd}" if v.create_figure_cmd else ""
            print(f"  {v.name:20s} {v.backend.value:12s} {v.label}{cmd}")
        print(f"\nNot yet implemented ({len(not_yet)}):")
        for v in not_yet:
            print(f"  {v.name:20s} {v.label}")
    elif len(sys.argv) > 2 and sys.argv[1] == "recommend":
        query = " ".join(sys.argv[2:])
        print(f"Query: {query}")
        kw_matches = match_keywords(query)
        print(f"\nKeyword matches:")
        for name, score in kw_matches[:5]:
            print(f"  {name:20s} score={score:.1f}")
    else:
        print(f"D3 Visualization Catalog: {len(D3_VIZ_CATALOG)} types")
        print(f"  Implemented: {len(get_implemented_viz_types())}")
        print(f"  Families: {len(set(v.family for v in D3_VIZ_CATALOG.values()))}")
        print(f"\nUsage: python d3_catalog.py list")
        print(f"       python d3_catalog.py recommend 'show me convergence over time'")
