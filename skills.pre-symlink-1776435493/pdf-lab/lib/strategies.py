"""Pre-defined extraction parameter strategies for the deterministic convergence loop.

Ordered cheapest-first: baseline -> ratio sweeps -> body-size sweeps -> grid.
"""

from __future__ import annotations

from loguru import logger

_RATIOS = [1.05, 1.1, 1.15, 1.2, 1.3, 1.5, 2.0]
_SIZES = [8.0, 9.0, 10.0, 11.0, 12.0]


def _strat(name: str, body: float | None, ratio: float | None, desc: str) -> dict:
    return {
        "name": name,
        "body_font_size_override": body,
        "header_ratio_override": ratio,
        "description": desc,
    }


def generate_strategies(baseline_median: float | None = None) -> list[dict]:
    """Return ordered strategy list (cheapest first) for the convergence loop."""
    strategies = [_strat("baseline", None, None, "Default pdf_oxide behavior")]

    for r in _RATIOS:
        strategies.append(_strat(f"ratio_{r}", None, r, f"Header ratio override {r}"))

    if baseline_median is not None:
        sizes = [round(baseline_median + d, 1) for d in [-2, -1, 0, 1, 2]]
        logger.info("Body sizes centered on median {}: {}", baseline_median, sizes)
    else:
        sizes = list(_SIZES)

    for s in sizes:
        strategies.append(_strat(f"body_{s}", s, None, f"Body font size override {s}"))

    logger.debug("Generated {} strategies", len(strategies))
    return strategies


def strategy_grid(ratios: list[float], sizes: list[float]) -> list[dict]:
    """Grid search: all ratio x size combinations."""
    grid = []
    for r in ratios:
        for s in sizes:
            grid.append(_strat(f"grid_{r}_{s}", s, r, f"Grid ratio={r} body={s}"))
    logger.debug("Generated {} grid strategies", len(grid))
    return grid
