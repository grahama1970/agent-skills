"""
D3.js Visualization Catalog Types — enums, dataclasses, and the global registry dict.

Defines the core type system for the D3 visualization catalog:
- DataShape: what shape of data a viz needs
- VizFamily: high-level grouping
- RenderBackend: which backend renders the type
- VizType: a single visualization type entry
- D3_VIZ_CATALOG: the global dict that entries register into

Separated from catalog entries and lookup helpers to keep files under 800 lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class DataShape(Enum):
    """What shape of data does this viz need?"""
    CATEGORICAL = "categorical"          # {label: value}
    TIME_SERIES = "time_series"          # [{x: date, y: value}]
    BIVARIATE = "bivariate"              # [{x, y}]
    MULTIVARIATE = "multivariate"        # [{dim1, dim2, ..., dimN}]
    HIERARCHICAL = "hierarchical"        # {name, children: [...]}
    NETWORK = "network"                  # {nodes: [...], edges: [...]}
    FLOW = "flow"                        # [{source, target, value}]
    MATRIX = "matrix"                    # [[row_values]] or {row: {col: val}}
    DISTRIBUTION = "distribution"        # [values] or [{group, values}]
    GEOGRAPHIC = "geographic"            # GeoJSON or [{lat, lon, value}]
    TABULAR = "tabular"                  # [{col1, col2, ...}]
    TEXT = "text"                        # plain text / markdown


class VizFamily(Enum):
    """High-level family for grouping."""
    BAR = "bar"
    LINE = "line"
    AREA = "area"
    DOT = "dot"
    PIE = "pie"
    RADIAL = "radial"
    HIERARCHY = "hierarchy"
    NETWORK = "network"
    MAP = "map"
    DISTRIBUTION = "distribution"
    FLOW = "flow"
    TABLE = "table"
    ANNOTATION = "annotation"
    SPECIALTY = "specialty"


class RenderBackend(Enum):
    """Which backend renders this type?"""
    D3_INLINE = "d3_inline"       # D3ResponsiveChart.tsx (fast, in-React)
    MATPLOTLIB = "matplotlib"     # /create-figure matplotlib_backend.py -> canvas HTML
    PLOTLY = "plotly"              # /create-figure plotly_backend.py -> canvas HTML
    GRAPHVIZ = "graphviz"         # /create-figure graphviz_backend.py
    MERMAID = "mermaid"           # /create-figure mermaid_backend.py
    NETWORKX = "networkx"         # /create-figure networkx_backend.py
    NOT_YET = "not_yet"           # cataloged but not implemented


@dataclass
class VizType:
    """A single visualization type in the catalog."""
    name: str                             # machine name (used in routing)
    label: str                            # human label
    family: VizFamily
    data_shapes: List[DataShape]          # compatible input shapes
    min_data_points: int = 2              # minimum rows/items needed
    max_data_points: Optional[int] = None # recommended max (None = unlimited)
    min_dimensions: int = 1               # minimum columns/dimensions
    max_dimensions: Optional[int] = None
    description: str = ""                 # when to use this
    keywords: List[str] = field(default_factory=list)  # NL trigger words
    backend: RenderBackend = RenderBackend.NOT_YET
    create_figure_cmd: Optional[str] = None  # /create-figure subcommand if available
    d3_module: Optional[str] = None       # D3 module (d3-shape, d3-hierarchy, etc.)
    interactive: bool = False             # benefits from hover/zoom
    supports_canvas: bool = True          # can render in 5ft canvas mode


# The global catalog dict — entries register into this from d3_catalog_entries.py
D3_VIZ_CATALOG: Dict[str, VizType] = {}
