"""Parameter search space and trial selection for pdf-lab convergence.

Maps detected patterns to tunable parameter ranges and selects next
trial parameters based on previous iteration results.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class TrialParams:
    """A single set of parameters to try during convergence."""

    # Tier 1: Environment variable defaults
    env: Dict[str, str] = field(default_factory=dict)

    # Tier 2: Heuristic thresholds
    font_threshold: float = 11.0
    short_section_merge_threshold: int = 150
    min_table_lines: int = 4

    # Tier 3: Pattern rules
    new_citation_pattern: str = ""

    # Tier 4: Preset updates
    preset: str = ""
    preset_update: Dict[str, Any] = field(default_factory=dict)

    # Extraction-time overrides (used for immediate re-extraction)
    extraction_overrides: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TrialParams:
        return cls(
            env=data.get("env", {}),
            font_threshold=data.get("font_threshold", 11.0),
            short_section_merge_threshold=data.get("short_section_merge_threshold", 150),
            min_table_lines=data.get("min_table_lines", 4),
            new_citation_pattern=data.get("new_citation_pattern", ""),
            preset=data.get("preset", ""),
            preset_update=data.get("preset_update", {}),
            extraction_overrides=data.get("extraction_overrides", {}),
        )


# Pattern-specific parameter ranges
PATTERN_PARAM_RANGES: Dict[str, Dict[str, Any]] = {
    "section_undersegmentation": {
        "font_threshold": [8.0, 9.0, 9.5, 10.0, 10.5],
        "short_section_merge_threshold": [80, 100, 120, 200, 250],
    },
    "section_oversegmentation": {
        "font_threshold": [11.5, 12.0, 13.0, 14.0],
        "short_section_merge_threshold": [100, 150, 200, 300],
    },
    "missed_tables": {
        "CAMELOT_LINE_SCALE_DEFAULT": [5, 10, 20, 30, 40, 60, 80],
        "TABLE_VERTICAL_PADDING_RATIO": [0.15, 0.20, 0.25, 0.30, 0.40],
        "TABLE_HORIZONTAL_PADDING_RATIO": [0.05, 0.07, 0.10, 0.15],
    },
    "false_positive_tables": {
        "CAMELOT_LINE_SCALE_DEFAULT": [15, 20, 30, 40],
        "min_table_lines": [3, 4, 5, 6, 8],
    },
    "multi_column": {
        "font_threshold": [9.0, 9.5, 10.0, 10.5, 11.0],
        "CAMELOT_LINE_SCALE_DEFAULT": [20, 30, 40, 60],
    },
    "split_tables": {
        "CAMELOT_LINE_SCALE_DEFAULT": [30, 40, 60, 80],
        "TABLE_VERTICAL_PADDING_RATIO": [0.20, 0.30, 0.40, 0.50],
    },
    "scanned_no_ocr": {
        "TABLE_EXTRACTION_DPI": [150, 200, 300],
        "font_threshold": [9.0, 10.0, 11.0],
    },
}

# Default baseline parameters (current pipeline defaults)
BASELINE_PARAMS = TrialParams(
    env={
        "CAMELOT_LINE_SCALE_DEFAULT": "15",
        "TABLE_VERTICAL_PADDING_RATIO": "0.30",
        "TABLE_HORIZONTAL_PADDING_RATIO": "0.07",
        "TABLE_EXTRACTION_DPI": "200",
    },
    font_threshold=11.0,
    short_section_merge_threshold=150,
    min_table_lines=4,
)


class ParamSpace:
    """Manages the search space and selects next trial parameters.

    Uses a simple strategy: start from baseline, then explore pattern-specific
    ranges one dimension at a time, guided by correction context from failed
    iterations.
    """

    def __init__(self, patterns: List[str], delta_before: float):
        self.patterns = patterns
        self.delta_before = delta_before
        self._tried: List[Dict[str, Any]] = []
        self._ranges = self._build_ranges()
        self._iteration = 0

    def _build_ranges(self) -> Dict[str, List[Any]]:
        """Merge parameter ranges from all detected patterns."""
        merged: Dict[str, List[Any]] = {}
        for pattern in self.patterns:
            ranges = PATTERN_PARAM_RANGES.get(pattern, {})
            for param, values in ranges.items():
                if param not in merged:
                    merged[param] = []
                for v in values:
                    if v not in merged[param]:
                        merged[param].append(v)
        # Sort numeric ranges
        for param in merged:
            try:
                merged[param] = sorted(merged[param])
            except TypeError:
                pass
        return merged

    def next_trial(self, correction_context: Optional[Dict[str, Any]] = None) -> TrialParams:
        """Select next trial parameters.

        Strategy:
        - Iteration 0: baseline
        - Iteration 1+: explore parameter ranges guided by correction context
        """
        self._iteration += 1

        if self._iteration == 1:
            return BASELINE_PARAMS

        params = TrialParams(
            env=copy.deepcopy(BASELINE_PARAMS.env),
            font_threshold=BASELINE_PARAMS.font_threshold,
            short_section_merge_threshold=BASELINE_PARAMS.short_section_merge_threshold,
            min_table_lines=BASELINE_PARAMS.min_table_lines,
        )

        # Apply corrections from previous iteration
        if correction_context:
            params = self._apply_corrections(params, correction_context)
        else:
            params = self._explore_random(params)

        self._tried.append(params.to_dict())
        return params

    def _apply_corrections(
        self, params: TrialParams, ctx: Dict[str, Any]
    ) -> TrialParams:
        """Adjust parameters based on what went wrong in previous trial."""
        # Section undercount → lower font threshold
        if ctx.get("section_undercount"):
            candidates = self._ranges.get("font_threshold", [9.0, 9.5, 10.0])
            current = params.font_threshold
            lower = [v for v in candidates if v < current]
            if lower:
                params.font_threshold = lower[-1]  # Next lower value

        # Section overcount → raise font threshold
        if ctx.get("section_overcount"):
            candidates = self._ranges.get("font_threshold", [12.0, 13.0])
            current = params.font_threshold
            higher = [v for v in candidates if v > current]
            if higher:
                params.font_threshold = higher[0]

        # Table undercount → adjust line_scale
        if ctx.get("table_undercount"):
            candidates = self._ranges.get("CAMELOT_LINE_SCALE_DEFAULT", [20, 30, 40, 60])
            tried_scales = [
                int(t.get("env", {}).get("CAMELOT_LINE_SCALE_DEFAULT", 0))
                for t in self._tried
            ]
            untried = [v for v in candidates if v not in tried_scales]
            if untried:
                params.env["CAMELOT_LINE_SCALE_DEFAULT"] = str(untried[0])

        # Table overcount → raise min_table_lines
        if ctx.get("table_overcount"):
            candidates = self._ranges.get("min_table_lines", [5, 6, 8])
            current = params.min_table_lines
            higher = [v for v in candidates if v > current]
            if higher:
                params.min_table_lines = higher[0]

        # Padding adjustments
        if ctx.get("table_boundary_issues"):
            candidates = self._ranges.get(
                "TABLE_VERTICAL_PADDING_RATIO", [0.20, 0.30, 0.40]
            )
            current = float(params.env.get("TABLE_VERTICAL_PADDING_RATIO", "0.30"))
            different = [v for v in candidates if abs(v - current) > 0.01]
            if different:
                params.env["TABLE_VERTICAL_PADDING_RATIO"] = str(different[0])

        return params

    def _explore_random(self, params: TrialParams) -> TrialParams:
        """When no correction context, pick a random unexplored parameter combo."""
        if not self._ranges:
            return params

        # Pick a random parameter to vary
        param_name = random.choice(list(self._ranges.keys()))
        values = self._ranges[param_name]

        if not values:
            return params

        value = random.choice(values)

        # Map parameter to the right place
        env_params = {
            "CAMELOT_LINE_SCALE_DEFAULT",
            "TABLE_VERTICAL_PADDING_RATIO",
            "TABLE_HORIZONTAL_PADDING_RATIO",
            "TABLE_EXTRACTION_DPI",
        }

        if param_name in env_params:
            params.env[param_name] = str(value)
        elif param_name == "font_threshold":
            params.font_threshold = value
        elif param_name == "short_section_merge_threshold":
            params.short_section_merge_threshold = value
        elif param_name == "min_table_lines":
            params.min_table_lines = value

        return params


def build_param_space(patterns: List[str], delta_before: float) -> ParamSpace:
    """Build a parameter search space from detected patterns and current delta."""
    return ParamSpace(patterns=patterns, delta_before=delta_before)
