#!/usr/bin/env python3
"""
Utility functions for fixture-graph skill.

Contains:
- Backend availability checks
- IEEE style application
- Colormap accessibility warnings
- Common helper functions
"""

import subprocess
import sys
from typing import List

import typer

from config import IEEE_RC_PARAMS, COLORBLIND_SAFE_CMAPS, PROBLEMATIC_CMAPS


# --- Backend Availability Checks ---

def check_graphviz() -> bool:
    """Check if Graphviz (dot) is available."""
    try:
        result = subprocess.run(["dot", "-V"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_mermaid() -> bool:
    """Check if mermaid-cli (mmdc) is available."""
    try:
        result = subprocess.run(["mmdc", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_matplotlib() -> bool:
    """Check if matplotlib is available."""
    try:
        import matplotlib
        return True
    except ImportError:
        return False


def check_seaborn() -> bool:
    """Check if seaborn is available."""
    try:
        import seaborn
        return True
    except ImportError:
        return False


def check_plotly() -> bool:
    """Check if plotly is available (for Sankey, sunburst, treemap)."""
    try:
        import plotly
        return True
    except ImportError:
        return False


def check_squarify() -> bool:
    """Check if squarify is available (for treemaps with matplotlib)."""
    try:
        import squarify
        return True
    except ImportError:
        return False


def check_pandas() -> bool:
    """Check if pandas is available."""
    try:
        import pandas
        return True
    except ImportError:
        return False


def check_control() -> bool:
    """Check if python-control is available (Bode, Nyquist, root locus)."""
    try:
        import control
        return True
    except ImportError:
        return False


def check_scipy() -> bool:
    """Check if scipy is available (signal processing, interpolation)."""
    try:
        import scipy
        return True
    except ImportError:
        return False


def check_networkx() -> bool:
    """Check if NetworkX is available."""
    try:
        import networkx
        return True
    except ImportError:
        return False


def check_pydeps() -> bool:
    """Check if pydeps is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pydeps", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_pyreverse() -> bool:
    """Check if pyreverse (from pylint) is available."""
    try:
        result = subprocess.run(["pyreverse", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_numpy() -> bool:
    """Check if numpy is available."""
    try:
        import numpy
        return True
    except ImportError:
        return False


# --- Style and Formatting Functions ---

def apply_ieee_style() -> None:
    """Apply IEEE publication style to matplotlib."""
    import matplotlib.pyplot as plt
    for key, value in IEEE_RC_PARAMS.items():
        try:
            plt.rcParams[key] = value
        except KeyError:
            pass  # Skip if key doesn't exist in this matplotlib version


def check_colormap_accessibility(cmap: str) -> None:
    """Warn if colormap has accessibility issues."""
    if cmap.lower() in [c.lower() for c in PROBLEMATIC_CMAPS]:
        typer.echo(
            f"[WARN] Colormap '{cmap}' is not colorblind-safe. "
            f"Consider: {', '.join(COLORBLIND_SAFE_CMAPS[:3])}",
            err=True
        )


# --- Numpy Fallback ---

def get_numpy():
    """Get numpy module or fallback implementation."""
    try:
        import numpy as np
        return np
    except ImportError:
        # Minimal fallback for when numpy isn't available
        class NumpyFallback:
            pi = 3.14159265358979323846

            @staticmethod
            def linspace(start: float, stop: float, num: int) -> List[float]:
                step = (stop - start) / (num - 1) if num > 1 else 0
                return [start + i * step for i in range(num)]

            @staticmethod
            def array(data, dtype=None):
                return list(data)

            @staticmethod
            def meshgrid(x, y):
                X = [[xi for xi in x] for _ in y]
                Y = [[yi for _ in x] for yi in y]
                return X, Y

        return NumpyFallback()
