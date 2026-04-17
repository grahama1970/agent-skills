"""
D3.js Visualization Catalog Entries — aggregator module.

Imports both entry sub-modules to register all VizType instances into
D3_VIZ_CATALOG. Split into two files to keep each under 800 lines:

- d3_catalog_entries_basic.py: Bar, Line, Area, Dot, Pie, Radial
- d3_catalog_entries_advanced.py: Hierarchy, Network, Flow, Distribution,
  Matrix/Heatmap, Map, Table, Specialty/ML, Text
"""

import d3_catalog_entries_basic  # noqa: F401
import d3_catalog_entries_advanced  # noqa: F401
