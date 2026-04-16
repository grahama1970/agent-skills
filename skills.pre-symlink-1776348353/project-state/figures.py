"""Figure generation from report data.

Creates visualizations (pie charts, bar charts, hbar charts) from the
project state report by invoking the /create-figure skill with JSON data.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from constants import CREATE_FIGURE_SKILL


def generate_figures(report: dict, output_dir: str) -> list[str]:
    """Generate visualizations from report data via /create-figure.

    Creates targeted figures from report data:
    - Gap severity pie chart
    - Cascade health metrics bar chart
    - Component project status radar
    - Training data heatmap (if enough tasks)
    """
    if not CREATE_FIGURE_SKILL.exists():
        logger.warning("/create-figure skill not found, skipping figures")
        return []

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    generated = []

    # 1. Gap severity breakdown (pie)
    phase6 = report.get("phase_6_gaps", {})
    gaps = phase6.get("gaps", []) if isinstance(phase6, dict) else phase6
    if gaps:
        sev_counts = {}
        for g in gaps:
            sev = g.get("severity", "unknown")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
        _run_figure("metrics", sev_counts, out_path / "gap_severity.png",
                     chart_type="pie", title="Gap Severity Distribution")
        generated.append(str(out_path / "gap_severity.png"))

    # 2. Cascade health (bar: validators, classifiers, regressors, shadow usable)
    cascade = report.get("phase_1_infrastructure", {}).get("cascade", {})
    if cascade:
        reg = cascade.get("registry", {})
        shadow = cascade.get("shadow", {})
        cascade_metrics = {
            "Validators": reg.get("validators", 0),
            "Classifiers": reg.get("classifiers", 0),
            "Regressors": reg.get("regressors", 0),
            "Classifiers on disk": len(cascade.get("classifiers_on_disk", [])),
            "Shadow usable": shadow.get("usable", 0),
        }
        _run_figure("metrics", cascade_metrics, out_path / "cascade_health.png",
                     chart_type="bar", title="3-Tier Cascade Health")
        generated.append(str(out_path / "cascade_health.png"))

    # 3. Training data by task (hbar -- shows relative label counts)
    training = cascade.get("training_data", {})
    if training and len(training) >= 3:
        # Sort by count descending, take top 12
        sorted_tasks = dict(sorted(training.items(), key=lambda x: -x[1])[:12])
        _run_figure("metrics", sorted_tasks, out_path / "training_labels.png",
                     chart_type="hbar", title="Training Labels by Task")
        generated.append(str(out_path / "training_labels.png"))

    # 4. Daemon status (simple metrics -- all should be 1 for "up")
    daemons = report.get("phase_1_infrastructure", {}).get("daemons", {})
    daemon_map = daemons.get("daemons", {})
    if daemon_map:
        daemon_scores = {
            name: 1 if info.get("status") in ("ok", "healthy") else 0
            for name, info in daemon_map.items()
        }
        _run_figure("metrics", daemon_scores, out_path / "daemon_status.png",
                     chart_type="bar", title="Daemon Health (1=UP, 0=DOWN)")
        generated.append(str(out_path / "daemon_status.png"))

    return generated


def _run_figure(command: str, data: dict, output: Path,
                chart_type: str = "bar", title: str = "") -> bool:
    """Invoke /create-figure with JSON data."""
    data_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, data_file)
    data_file.close()

    cmd = ["bash", str(CREATE_FIGURE_SKILL), command,
           "--input", data_file.name, "--output", str(output),
           "--type", chart_type]
    if title:
        cmd.extend(["--title", title])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        os.unlink(data_file.name)
        if result.returncode == 0 and output.exists():
            return True
        if result.returncode != 0 and result.stderr:
            logger.warning("Figure warning ({}): {}", output.name, result.stderr[:100])
        return False
    except Exception as e:
        os.unlink(data_file.name)
        logger.warning("Figure error ({}): {}", output.name, e)
        return False
