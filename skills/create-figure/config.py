#!/usr/bin/env python3
"""
Configuration constants for fixture-graph skill.

Contains:
- IEEE publication settings
- Figure size presets
- Colorblind-safe colormaps
- Domain groups for visualization discovery
- Data type recommendations
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

# --- Paths ---
SKILLS_DIR = Path(__file__).parent.parent
LEAN4_PROVE_SCRIPT = SKILLS_DIR / "lean4-prove" / "run.sh"

# --- IEEE Publication Settings ---

IEEE_RC_PARAMS = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,  # TrueType fonts for Illustrator compatibility
    "ps.fonttype": 42,
    "axes.linewidth": 0.5,
    "lines.linewidth": 1.0,
    "lines.markersize": 4,
    "grid.linewidth": 0.3,
}

# IEEE column widths (inches)
IEEE_SINGLE_COLUMN = 3.5
IEEE_DOUBLE_COLUMN = 7.16

# IEEE figure size presets (width, height) in inches
IEEE_FIGURE_SIZES = {
    "single": (3.5, 2.5),      # Single column, standard height
    "single_tall": (3.5, 4.0), # Single column, tall (for multi-panel)
    "double": (7.16, 3.0),     # Double column, standard height
    "double_tall": (7.16, 5.0),# Double column, tall
    "square": (3.5, 3.5),      # Square, single column width
}

# --- Colormap Settings ---

# Colorblind-safe colormaps (recommended for accessibility)
COLORBLIND_SAFE_CMAPS = [
    "viridis",    # Default, perceptually uniform, colorblind-safe
    "plasma",     # Perceptually uniform
    "cividis",    # Specifically designed for colorblind accessibility
    "gray",       # Grayscale, universally accessible
    "Blues",      # Sequential, single hue
    "Oranges",    # Sequential, single hue
]

# Colormaps to avoid for accessibility
PROBLEMATIC_CMAPS = ["jet", "rainbow", "hsv", "spectral"]

# --- Domain Groups ---
# Helps project agents choose the right visualization

DOMAIN_GROUPS: Dict[str, Dict[str, any]] = {
    "core": {
        "description": "Universal visualizations for any project",
        "commands": ["metrics", "table", "workflow", "architecture", "deps", "uml", "heatmap"],
        "use_when": "Basic project analysis, documentation, code structure",
    },
    "control": {
        "description": "Control systems, aerospace, flight dynamics",
        "commands": ["bode", "nyquist", "rootlocus", "pole-zero", "state-space", "filter-response"],
        "use_when": "Transfer functions, stability analysis, frequency response",
    },
    "field": {
        "description": "Field distributions, nuclear/thermal analysis, physics",
        "commands": ["contour", "vector-field", "phase-portrait", "heatmap", "polar"],
        "use_when": "Flux distributions, temperature fields, flow visualization",
    },
    "project": {
        "description": "Project management, scheduling, requirements",
        "commands": ["gantt", "pert", "radar", "sankey", "parallel-coords"],
        "use_when": "Schedules, resource allocation, multi-criteria comparison",
    },
    "math": {
        "description": "Pure mathematics, 3D visualization, complex analysis",
        "commands": ["3d-surface", "3d-contour", "complex-plane", "polar", "phase-portrait"],
        "use_when": "Mathematical functions, complex numbers, dynamical systems",
    },
    "ml": {
        "description": "Machine learning, LLM evaluation, model analysis",
        "commands": [
            "confusion-matrix", "roc-curve", "pr-curve", "training-curves",
            "attention-heatmap", "embedding-scatter", "scaling-law", "roofline",
            "throughput-latency", "feature-importance", "calibration"
        ],
        "use_when": "Model evaluation, benchmarks, training analysis, interpretability",
    },
    "bio": {
        "description": "Bioinformatics, medical research, genomics",
        "commands": ["violin", "volcano", "survival-curve", "manhattan"],
        "use_when": "Gene expression, clinical trials, GWAS studies",
    },
    "hierarchy": {
        "description": "Hierarchical data, breakdowns, fault trees",
        "commands": ["treemap", "sunburst", "force-graph", "sankey"],
        "use_when": "Component breakdowns, fault analysis, flow diagrams",
    },
}

# Data type to command recommendations
DATA_TYPE_RECOMMENDATIONS: Dict[str, List[str]] = {
    "time_series": ["training-curves", "line", "gantt"],
    "classification": ["confusion-matrix", "roc-curve", "pr-curve", "calibration"],
    "distribution": ["violin", "heatmap", "histogram"],
    "comparison": ["radar", "metrics", "parallel-coords"],
    "flow": ["sankey", "workflow", "force-graph"],
    "hierarchy": ["treemap", "sunburst", "architecture"],
    "correlation": ["heatmap", "embedding-scatter"],
    "frequency": ["bode", "nyquist", "spectrogram"],
    "spatial": ["contour", "vector-field", "heatmap"],
    "complex": ["complex-plane", "polar", "phase-portrait"],
    "dependencies": ["deps", "architecture", "force-graph"],
    "schedule": ["gantt", "pert", "workflow"],
    "performance": ["roofline", "throughput-latency", "scaling-law"],
    "genomics": ["manhattan", "volcano", "violin"],
    "survival": ["survival-curve"],
    "transfer_function": ["bode", "nyquist", "rootlocus", "pole-zero"],
}


# --- Data Classes ---

@dataclass
class FigureConfig:
    """Configuration for figure generation."""
    title: str
    width: float = IEEE_SINGLE_COLUMN
    height: float = 2.5
    dpi: int = 600
    format: str = "pdf"
    style: str = "ieee"  # ieee, acm, arxiv


@dataclass
class DependencyNode:
    """A node in a dependency graph."""
    name: str
    module_type: str = "module"  # module, package, external
    loc: int = 0
    imports: List[str] = field(default_factory=list)
    imported_by: List[str] = field(default_factory=list)


def get_ieee_figsize(preset: str = "single") -> Tuple[float, float]:
    """Get IEEE figure size preset.

    Args:
        preset: One of 'single', 'single_tall', 'double', 'double_tall', 'square'

    Returns:
        (width, height) tuple in inches
    """
    return IEEE_FIGURE_SIZES.get(preset, IEEE_FIGURE_SIZES["single"])
