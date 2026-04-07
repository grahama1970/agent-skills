"""Chart-specific D3 code generators for figure-lab compositions.

Re-exports all generator functions from the split sub-modules so that
existing ``from figure_lab.chart_generators import gen_*`` imports
continue to work without changes.

Sub-modules:
  - ``chart_gen_basic``: bar (vertical, horizontal, stacked, grouped) and area charts
  - ``chart_gen_statistical``: radar, bubble, heatmap, histogram, box plot,
    waterfall, funnel, ridgeline, beeswarm, gauge
"""
from __future__ import annotations

from figure_lab.chart_gen_basic import (  # noqa: F401
    gen_area,
    gen_bar_fallback,
    gen_grouped_bar,
    gen_hbar,
    gen_stacked_area,
    gen_stacked_bar,
)
from figure_lab.chart_gen_statistical import (  # noqa: F401
    gen_beeswarm,
    gen_box_plot,
    gen_bubble,
    gen_funnel,
    gen_gauge,
    gen_heatmap,
    gen_histogram,
    gen_radar,
    gen_ridgeline,
    gen_waterfall,
)

__all__ = [
    "gen_area",
    "gen_bar_fallback",
    "gen_beeswarm",
    "gen_box_plot",
    "gen_bubble",
    "gen_funnel",
    "gen_gauge",
    "gen_grouped_bar",
    "gen_hbar",
    "gen_heatmap",
    "gen_histogram",
    "gen_radar",
    "gen_ridgeline",
    "gen_stacked_area",
    "gen_stacked_bar",
    "gen_waterfall",
]
