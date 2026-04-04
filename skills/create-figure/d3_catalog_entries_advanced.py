"""
D3.js Visualization Catalog Entries — advanced and specialized chart families.

Registers VizType instances for: Hierarchy, Network, Flow, Distribution,
Matrix/Heatmap, Map, Table, Specialty/ML, and Text families.

Part 2 of 2. See d3_catalog_entries_basic.py for Bar, Line, Area, Dot,
Pie, and Radial families.
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
# HIERARCHY family
# ---------------------------------------------------------------------------
_register(VizType(
    name="treemap",
    label="Treemap",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL, DataShape.CATEGORICAL],
    min_data_points=3,
    min_dimensions=1,
    description="Nested rectangles showing hierarchical size data.",
    keywords=["treemap", "space filling", "hierarchy", "nested", "size breakdown"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="treemap",
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="sunburst",
    label="Sunburst Chart",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=3,
    min_dimensions=1,
    description="Concentric rings showing hierarchical breakdown. Interactive drill-down.",
    keywords=["sunburst", "radial tree", "drill down", "nested rings"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="sunburst",
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="circle_packing",
    label="Circle Packing",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=3,
    min_dimensions=1,
    description="Nested circles for hierarchy. Alternative to treemap.",
    keywords=["circle packing", "packed circles", "bubble hierarchy"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="icicle",
    label="Icicle / Partition Chart",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=3,
    min_dimensions=1,
    description="Rectangular partition of hierarchy. Like horizontal sunburst.",
    keywords=["icicle", "partition", "flame chart", "flamegraph"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="tidy_tree",
    label="Tidy Tree / Dendrogram",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=3,
    min_dimensions=1,
    description="Classic tree layout with parent-child relationships.",
    keywords=["tree", "dendrogram", "hierarchy", "org chart", "taxonomy", "family tree"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="radial_tree",
    label="Radial Tree / Dendrogram",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=5,
    min_dimensions=1,
    description="Tree laid out in polar coordinates. Compact for large hierarchies.",
    keywords=["radial tree", "radial dendrogram", "circular tree"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
    interactive=True,
))

_register(VizType(
    name="indented_tree",
    label="Indented Tree",
    family=VizFamily.HIERARCHY,
    data_shapes=[DataShape.HIERARCHICAL],
    min_data_points=3,
    min_dimensions=1,
    description="File-explorer style indented list. Familiar, scannable.",
    keywords=["indented", "file tree", "outline", "nested list"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
))

# ---------------------------------------------------------------------------
# NETWORK family
# ---------------------------------------------------------------------------
_register(VizType(
    name="force_graph",
    label="Force-Directed Graph",
    family=VizFamily.NETWORK,
    data_shapes=[DataShape.NETWORK],
    min_data_points=3,
    min_dimensions=1,
    description="Physics simulation for node-link diagrams. Good for topology.",
    keywords=["network", "graph", "nodes", "edges", "connections", "topology", "relationships"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="force-graph",
    d3_module="d3-force",
    interactive=True,
))

_register(VizType(
    name="arc_diagram",
    label="Arc Diagram",
    family=VizFamily.NETWORK,
    data_shapes=[DataShape.NETWORK],
    min_data_points=3,
    min_dimensions=1,
    description="Nodes on a line, arcs show connections. Good for sequential data.",
    keywords=["arc diagram", "connections", "sequential links"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

_register(VizType(
    name="chord",
    label="Chord Diagram",
    family=VizFamily.NETWORK,
    data_shapes=[DataShape.MATRIX, DataShape.FLOW],
    min_data_points=3,
    min_dimensions=2,
    description="Show inter-relationships between groups arranged in a circle.",
    keywords=["chord", "inter-relationships", "mutual", "bilateral", "connections"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-chord",
    interactive=True,
))

_register(VizType(
    name="edge_bundling",
    label="Hierarchical Edge Bundling",
    family=VizFamily.NETWORK,
    data_shapes=[DataShape.NETWORK, DataShape.HIERARCHICAL],
    min_data_points=10,
    min_dimensions=1,
    description="Curved edges grouped by hierarchy. Beautiful for dependency viz.",
    keywords=["edge bundling", "bundled", "dependency", "import graph"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hierarchy",
    interactive=True,
))

# ---------------------------------------------------------------------------
# FLOW family
# ---------------------------------------------------------------------------
_register(VizType(
    name="sankey",
    label="Sankey Diagram",
    family=VizFamily.FLOW,
    data_shapes=[DataShape.FLOW],
    min_data_points=2,
    min_dimensions=3,  # source, target, value
    description="Show flow/transfer between stages. Width = magnitude.",
    keywords=["sankey", "flow", "pipeline", "transfer", "from to", "stage"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="sankey",
    d3_module="d3-sankey",
    interactive=True,
))

_register(VizType(
    name="funnel",
    label="Funnel Chart",
    family=VizFamily.FLOW,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=3, max_data_points=10,
    min_dimensions=1,
    description="Show progressive reduction through stages (conversion funnel).",
    keywords=["funnel", "conversion", "pipeline stages", "drop off", "attrition"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="alluvial",
    label="Alluvial Diagram",
    family=VizFamily.FLOW,
    data_shapes=[DataShape.FLOW, DataShape.MULTIVARIATE],
    min_data_points=3,
    min_dimensions=3,
    description="Like Sankey but shows categorical transitions between stages.",
    keywords=["alluvial", "transitions", "categorical flow", "parallel sets"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-sankey",
    interactive=True,
))

# ---------------------------------------------------------------------------
# DISTRIBUTION family
# ---------------------------------------------------------------------------
_register(VizType(
    name="histogram",
    label="Histogram",
    family=VizFamily.DISTRIBUTION,
    data_shapes=[DataShape.DISTRIBUTION],
    min_data_points=10,
    min_dimensions=1,
    description="Show frequency distribution of continuous values.",
    keywords=["histogram", "distribution", "frequency", "bins", "counts"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-array",
))

_register(VizType(
    name="box_plot",
    label="Box Plot",
    family=VizFamily.DISTRIBUTION,
    data_shapes=[DataShape.DISTRIBUTION, DataShape.CATEGORICAL],
    min_data_points=5,
    min_dimensions=1,
    description="Show median, quartiles, and outliers. Compare distributions.",
    keywords=["box plot", "boxplot", "quartiles", "median", "outliers", "whiskers"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="violin",
    label="Violin Plot",
    family=VizFamily.DISTRIBUTION,
    data_shapes=[DataShape.DISTRIBUTION, DataShape.CATEGORICAL],
    min_data_points=10,
    min_dimensions=1,
    description="Rotated density plots showing distribution shape per group.",
    keywords=["violin", "density", "distribution shape", "kde"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

_register(VizType(
    name="density_contour",
    label="Density Contour / 2D KDE",
    family=VizFamily.DISTRIBUTION,
    data_shapes=[DataShape.BIVARIATE],
    min_data_points=20,
    min_dimensions=2,
    description="Contour lines showing 2D point density. For large scatter data.",
    keywords=["density contour", "kde", "density", "contour"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-contour",
))

_register(VizType(
    name="qq_plot",
    label="Q-Q Plot",
    family=VizFamily.DISTRIBUTION,
    data_shapes=[DataShape.DISTRIBUTION],
    min_data_points=10,
    min_dimensions=1,
    description="Compare distribution to theoretical (normal). Points on diagonal = match.",
    keywords=["qq", "quantile", "normal", "normality test"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-scale",
))

# ---------------------------------------------------------------------------
# MATRIX / HEATMAP family
# ---------------------------------------------------------------------------
_register(VizType(
    name="heatmap",
    label="Heatmap",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.MATRIX, DataShape.MULTIVARIATE],
    min_data_points=4,
    min_dimensions=2,
    description="Color-coded matrix. Correlation, confusion, schedule, etc.",
    keywords=["heatmap", "heat map", "correlation", "matrix", "grid", "intensity"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="heatmap",
    d3_module="d3-scale",
))

_register(VizType(
    name="hexbin",
    label="Hexbin Map",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.BIVARIATE],
    min_data_points=50,
    min_dimensions=2,
    description="Hexagonal binning of scatter data. For dense point clouds.",
    keywords=["hexbin", "hex", "binned scatter", "density scatter"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-hexbin",
))

_register(VizType(
    name="calendar",
    label="Calendar Heatmap",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.TIME_SERIES],
    min_data_points=30,
    min_dimensions=2,
    description="GitHub-style contribution calendar. Value per day.",
    keywords=["calendar", "daily", "heatmap calendar", "contribution", "activity"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-time",
))

# ---------------------------------------------------------------------------
# MAP family (geographic)
# ---------------------------------------------------------------------------
_register(VizType(
    name="choropleth",
    label="Choropleth Map",
    family=VizFamily.MAP,
    data_shapes=[DataShape.GEOGRAPHIC],
    min_data_points=2,
    min_dimensions=2,
    description="Color-coded geographic regions by value. States, countries, etc.",
    keywords=["map", "choropleth", "geographic", "by state", "by country", "regional"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-geo",
    interactive=True,
))

_register(VizType(
    name="bubble_map",
    label="Bubble Map",
    family=VizFamily.MAP,
    data_shapes=[DataShape.GEOGRAPHIC],
    min_data_points=2,
    min_dimensions=3,  # lat, lon, value
    description="Sized circles on a map. Location + magnitude.",
    keywords=["bubble map", "point map", "locations", "geo bubbles"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-geo",
    interactive=True,
))

_register(VizType(
    name="spike_map",
    label="Spike Map",
    family=VizFamily.MAP,
    data_shapes=[DataShape.GEOGRAPHIC],
    min_data_points=2,
    min_dimensions=3,
    description="Vertical spikes on a map showing magnitude at locations.",
    keywords=["spike map", "spike", "vertical map"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-geo",
))

# ---------------------------------------------------------------------------
# TABLE family
# ---------------------------------------------------------------------------
_register(VizType(
    name="table",
    label="Data Table",
    family=VizFamily.TABLE,
    data_shapes=[DataShape.TABULAR, DataShape.CATEGORICAL],
    min_data_points=1,
    min_dimensions=1,
    description="Tabular display of structured data. Always valid.",
    keywords=["table", "list", "detail", "all data", "raw", "show me the data", "records"],
    backend=RenderBackend.D3_INLINE,
    d3_module=None,
))

# ---------------------------------------------------------------------------
# SPECIALTY / ML family
# ---------------------------------------------------------------------------
_register(VizType(
    name="confusion_matrix",
    label="Confusion Matrix",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.MATRIX],
    min_data_points=4,
    min_dimensions=2,
    description="Classification performance matrix. Predicted vs actual.",
    keywords=["confusion matrix", "classification", "predicted actual", "true positive"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="confusion-matrix",
    d3_module="d3-scale",
))

_register(VizType(
    name="roc_curve",
    label="ROC Curve",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.BIVARIATE],
    min_data_points=10,
    min_dimensions=2,
    description="Receiver Operating Characteristic. FPR vs TPR for classifiers.",
    keywords=["roc", "auc", "receiver operating", "classifier performance"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="roc-curve",
    d3_module="d3-shape",
))

_register(VizType(
    name="parallel_coords",
    label="Parallel Coordinates",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.MULTIVARIATE],
    min_data_points=5,
    min_dimensions=3, max_dimensions=15,
    description="Each dimension is a vertical axis. Lines connect values per row.",
    keywords=["parallel coordinates", "multivariate", "multi-dimensional", "design space"],
    backend=RenderBackend.D3_INLINE,
    create_figure_cmd="parallel-coords",
    d3_module="d3-scale",
    interactive=True,
))

_register(VizType(
    name="voronoi",
    label="Voronoi Diagram",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.BIVARIATE],
    min_data_points=3,
    min_dimensions=2,
    description="Partition space by nearest point. Useful for spatial analysis.",
    keywords=["voronoi", "tessellation", "nearest neighbor", "spatial partition"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-delaunay",
))

_register(VizType(
    name="contour",
    label="Contour Plot",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.MATRIX, DataShape.BIVARIATE],
    min_data_points=9,
    min_dimensions=3,
    description="Iso-lines of a 2D scalar field. Topographic style.",
    keywords=["contour", "iso-lines", "topographic", "elevation", "field"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-contour",
))

_register(VizType(
    name="word_cloud",
    label="Word Cloud",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=5,
    min_dimensions=1,
    description="Words sized by frequency/importance. Informal but popular.",
    keywords=["word cloud", "tag cloud", "words", "frequency", "terms"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-cloud",
))

_register(VizType(
    name="gauge",
    label="Gauge / KPI",
    family=VizFamily.SPECIALTY,
    data_shapes=[DataShape.CATEGORICAL],
    min_data_points=1, max_data_points=1,
    min_dimensions=1,
    description="Single value indicator with min/max range. Dashboard KPI.",
    keywords=["gauge", "kpi", "score", "metric", "single value", "current value"],
    backend=RenderBackend.D3_INLINE,
    d3_module="d3-shape",
))

# ---------------------------------------------------------------------------
# TEXT family (not a visualization but a valid response)
# ---------------------------------------------------------------------------
_register(VizType(
    name="text",
    label="Text Response",
    family=VizFamily.ANNOTATION,
    data_shapes=[DataShape.TEXT],
    min_data_points=0,
    min_dimensions=0,
    description="Plain text or markdown response. No visualization needed.",
    keywords=["explain", "what is", "why", "describe", "tell me", "how does", "define"],
    backend=RenderBackend.D3_INLINE,
    d3_module=None,
))
