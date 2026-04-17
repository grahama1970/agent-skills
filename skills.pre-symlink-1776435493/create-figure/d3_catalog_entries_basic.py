"""
D3.js Visualization Catalog Entries — basic chart families.

Registers VizType instances for: Bar, Line, Area, Dot, Pie, and Radial families.
These are the most common chart types used in data visualization.

Part 1 of 2. See d3_catalog_entries_advanced.py for Hierarchy, Network, Flow,
Distribution, Matrix/Heatmap, Map, Table, Specialty, and Text families.
"""

from __future__ import annotations

from d3_catalog_types import (
    D3_VIZ_CATALOG,
    DataShape,
    RenderBackend,
    VizFamily,
    VizType,
)


def _register(v: VizType) -> VizType:
    """Register a VizType into the global catalog dict."""
    D3_VIZ_CATALOG[v.name] = v
    return v


# ---------------------------------------------------------------------------
# BAR family
# ---------------------------------------------------------------------------
_register(VizType(
    name="bar",
    label="Bar Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=2, max_data_points=30,
    min_dimensions=1, max_dimensions=2,
    description="Compare discrete categories. Best for <30 items.",
    keywords=["count", "compare", "how many", "breakdown", "distribution", "bar"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="metrics --type bar",
    d3_module="d3-scale",
))

_register(VizType(
    name="hbar",
    label="Horizontal Bar Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=2, max_data_points=50,
    min_dimensions=1, max_dimensions=2,
    description="Compare categories with long labels. Better than bar for >10 items.",
    keywords=["ranking", "rank", "top", "bottom", "sorted", "leaderboard"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="metrics --type hbar",
    d3_module="d3-scale",
))

_register(VizType(
    name="stacked_bar",
    label="Stacked Bar Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL, DataShape.MULTIVARIATE],
    min_data_points=2, max_data_points=20,
    min_dimensions=2, max_dimensions=10,
    description="Show composition within categories. Each bar is subdivided.",
    keywords=["stacked", "composition", "breakdown by", "grouped"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="grouped_bar",
    label="Grouped Bar Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL, DataShape.MULTIVARIATE],
    min_data_points=2, max_data_points=15,
    min_dimensions=2, max_dimensions=6,
    description="Side-by-side bars per category for direct comparison.",
    keywords=["grouped", "side by side", "compare across", "versus"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="diverging_bar",
    label="Diverging Bar Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=3, max_data_points=30,
    min_dimensions=1,
    description="Show positive/negative deviation from a baseline.",
    keywords=["diverging", "positive negative", "above below", "change", "delta", "gain loss"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="waterfall",
    label="Waterfall Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=3, max_data_points=20,
    min_dimensions=1,
    description="Show cumulative effect of sequential positive/negative values.",
    keywords=["waterfall", "cumulative", "running total", "bridge", "incremental"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="marimekko",
    label="Marimekko / Mosaic Chart",
    family=VizFamily.BAR,
    data_shapes=[DataShape.MATRIX, DataShape.MULTIVARIATE],
    min_data_points=4,
    min_dimensions=2,
    description="Variable-width stacked bars showing two-dimensional composition.",
    keywords=["marimekko", "mosaic", "market share", "two-way"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

# ---------------------------------------------------------------------------
# LINE family
# ---------------------------------------------------------------------------
_register(VizType(
    name="line",
    label="Line Chart",
    family=VizFamily.LINE,
    data_shapes=[DataShape.TIME_SERIES, DataShape.BIVARIATE],
    min_data_points=3,
    min_dimensions=2,
    description="Show trend over time or continuous variable. Best for temporal data.",
    keywords=["trend", "over time", "progress", "history", "trajectory", "convergence", "timeline"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="training-curves",
    d3_module="d3-shape",
))

_register(VizType(
    name="multi_line",
    label="Multi-Line Chart",
    family=VizFamily.LINE,
    data_shapes=[DataShape.TIME_SERIES, DataShape.MULTIVARIATE],
    min_data_points=3,
    min_dimensions=3,
    description="Compare multiple series over the same x-axis.",
    keywords=["compare trends", "multiple series", "overlay", "multi-line"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="slope",
    label="Slope Chart",
    family=VizFamily.LINE,
    data_shapes=[DataShape.CATEGORICAL, DataShape.BIVARIATE],
    min_data_points=2, max_data_points=15,
    min_dimensions=2,
    description="Show change between exactly two time points or conditions.",
    keywords=["before after", "change", "slope", "shift", "improvement"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="candlestick",
    label="Candlestick Chart",
    family=VizFamily.LINE,
    data_shapes=[DataShape.TIME_SERIES],
    min_data_points=5,
    min_dimensions=5,  # date, open, high, low, close
    description="Financial OHLC data with open/high/low/close per period.",
    keywords=["candlestick", "ohlc", "stock", "financial", "trading"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="sparkline",
    label="Sparkline",
    family=VizFamily.LINE,
    data_shapes=[DataShape.TIME_SERIES],
    min_data_points=5,
    min_dimensions=1,
    description="Tiny inline trend indicator, no axes. For dashboards/tables.",
    keywords=["sparkline", "inline", "mini chart", "trend indicator"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

# ---------------------------------------------------------------------------
# AREA family
# ---------------------------------------------------------------------------
_register(VizType(
    name="area",
    label="Area Chart",
    family=VizFamily.AREA,
    data_shapes=[DataShape.TIME_SERIES],
    min_data_points=3,
    min_dimensions=2,
    description="Like line chart but filled below. Emphasizes volume/magnitude.",
    keywords=["area", "filled", "volume", "magnitude"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="stacked_area",
    label="Stacked Area Chart",
    family=VizFamily.AREA,
    data_shapes=[DataShape.TIME_SERIES, DataShape.MULTIVARIATE],
    min_data_points=3,
    min_dimensions=3,
    description="Show how composition changes over time. Parts sum to whole.",
    keywords=["stacked area", "composition over time", "cumulative"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="streamgraph",
    label="Streamgraph",
    family=VizFamily.AREA,
    data_shapes=[DataShape.TIME_SERIES, DataShape.MULTIVARIATE],
    min_data_points=10,
    min_dimensions=3,
    description="Organic flowing stacked area, centered. Good for genre/topic evolution.",
    keywords=["streamgraph", "stream", "flow over time", "evolution"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
    interactive=True,
))

_register(VizType(
    name="ridgeline",
    label="Ridgeline / Joy Plot",
    family=VizFamily.AREA,
    data_shapes=[DataShape.DISTRIBUTION, DataShape.MULTIVARIATE],
    min_data_points=10,
    min_dimensions=2,
    description="Overlapping density plots for comparing distributions across groups.",
    keywords=["ridgeline", "joy plot", "distribution comparison", "density"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="horizon",
    label="Horizon Chart",
    family=VizFamily.AREA,
    data_shapes=[DataShape.TIME_SERIES],
    min_data_points=20,
    min_dimensions=2,
    description="Compact area chart using color bands. Shows many series in small space.",
    keywords=["horizon", "compact", "many series", "dense time series"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

# ---------------------------------------------------------------------------
# DOT family (scatter, bubble, etc.)
# ---------------------------------------------------------------------------
_register(VizType(
    name="scatter",
    label="Scatter Plot",
    family=VizFamily.DOT,
    data_shapes=[DataShape.BIVARIATE, DataShape.MULTIVARIATE],
    min_data_points=5,
    min_dimensions=2, max_dimensions=4,  # x, y, optional size, color
    description="Show relationship between two continuous variables.",
    keywords=["scatter", "correlation", "relationship", "xy", "versus", "plot"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="bubble",
    label="Bubble Chart",
    family=VizFamily.DOT,
    data_shapes=[DataShape.MULTIVARIATE],
    min_data_points=5,
    min_dimensions=3,  # x, y, size
    description="Scatter with size encoding. Three dimensions in 2D space.",
    keywords=["bubble", "three variables", "size", "magnitude"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="beeswarm",
    label="Beeswarm Plot",
    family=VizFamily.DOT,
    data_shapes=[DataShape.DISTRIBUTION, DataShape.CATEGORICAL],
    min_data_points=10,
    min_dimensions=1,
    description="Non-overlapping dots showing individual values within categories.",
    keywords=["beeswarm", "swarm", "individual points", "jitter"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-force",
))

_register(VizType(
    name="dot_plot",
    label="Dot Plot",
    family=VizFamily.DOT,
    data_shapes=[DataShape.CATEGORICAL, DataShape.BIVARIATE],
    min_data_points=3,
    min_dimensions=1,
    description="Dots on a common scale. Cleaner than bar for many categories.",
    keywords=["dot plot", "cleveland"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="lollipop",
    label="Lollipop Chart",
    family=VizFamily.DOT,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=3, max_data_points=30,
    min_dimensions=1,
    description="Horizontal stems with dots. Cleaner than bar for ranked data.",
    keywords=["lollipop", "stem", "ranked", "horizontal dots"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="scatter_matrix",
    label="Scatterplot Matrix (SPLOM)",
    family=VizFamily.DOT,
    data_shapes=[DataShape.MULTIVARIATE],
    min_data_points=10,
    min_dimensions=3, max_dimensions=8,
    description="All pairwise scatter plots in a grid. For exploring correlations.",
    keywords=["scatter matrix", "splom", "pairwise", "pairs plot"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
    interactive=True,
))

# ---------------------------------------------------------------------------
# PIE / RADIAL family
# ---------------------------------------------------------------------------
_register(VizType(
    name="pie",
    label="Pie Chart",
    family=VizFamily.PIE,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=2, max_data_points=8,
    min_dimensions=1,
    description="Show parts of a whole. Best with <8 slices.",
    keywords=["pie", "proportion", "share", "percentage", "split", "composition"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="metrics --type pie",
    d3_module="d3-shape",
))

_register(VizType(
    name="donut",
    label="Donut Chart",
    family=VizFamily.PIE,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=2, max_data_points=8,
    min_dimensions=1,
    description="Pie with center hole. Can show total or label in center.",
    keywords=["donut", "ring", "doughnut"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="radar",
    label="Radar / Spider Chart",
    family=VizFamily.RADIAL,
    data_shapes=[DataShape.MULTIVARIATE],
    min_data_points=1, max_data_points=5,  # 1-5 series
    min_dimensions=3, max_dimensions=12,
    description="Compare multiple dimensions for 1-5 items. Good for profiles/scoring.",
    keywords=["radar", "spider", "profile", "dimensions", "multi-attribute", "persona", "scoring"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="radar",
    d3_module="d3-shape",
))

_register(VizType(
    name="radial_bar",
    label="Radial Stacked Bar",
    family=VizFamily.RADIAL,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=3, max_data_points=20,
    min_dimensions=1,
    description="Bar chart wrapped in a circle. Aesthetic but harder to read.",
    keywords=["radial bar", "circular bar", "clock"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))
