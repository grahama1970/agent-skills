"""Workstation health integration for Discord publisher."""

from __future__ import annotations

from loguru import logger

import json
import subprocess
from pathlib import Path

from publisher_config import COMPONENT_TEXT_DISPLAY, FLAG_IS_COMPONENTS_V2

OPS_WORKSTATION_PATH = Path(__file__).resolve().parent.parent / "ops-workstation"


def get_workstation_health() -> dict:
    """Get workstation health from ops-workstation skill."""
    health_data = {
        "limits": None,
        "memory": None,
        "gpu": None,
        "disk": None,
    }

    # Get limits
    try:
        result = subprocess.run(
            ["bash", "scripts/limits.sh", "--json"],
            cwd=OPS_WORKSTATION_PATH,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            health_data["limits"] = json.loads(result.stdout)
    except Exception as e:
        print(f"Failed to get limits: {e}")

    # Get quick check (memory, disk)
    try:
        result = subprocess.run(
            ["bash", "scripts/check.sh"],
            cwd=OPS_WORKSTATION_PATH,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Memory usage:" in line:
                    pct = line.split(":")[-1].strip().replace("%", "")
                    health_data["memory"] = {"used_pct": int(pct)}
    except Exception as e:
        print(f"Failed to get check: {e}")

    # Get GPU (if available)
    try:
        result = subprocess.run(
            ["bash", "scripts/gpu-check.sh", "--json"],
            cwd=OPS_WORKSTATION_PATH,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            health_data["gpu"] = json.loads(result.stdout)
    except Exception as e:
        logger.debug("GPU health check failed: {}", e)

    return health_data


def build_health_dashboard() -> dict:
    """Build Discord Components V2 dashboard for workstation health."""
    health = get_workstation_health()

    components = []
    issues = []

    # Determine overall status
    limits = health.get("limits", {})
    warnings = limits.get("warnings", 0) if limits else 0
    critical = limits.get("critical", 0) if limits else 0

    mem_pct = health.get("memory", {}).get("used_pct", 0) if health.get("memory") else 0

    if critical > 0 or mem_pct >= 90:
        status_icon = "\U0001f534"
        status_text = "needs attention"
    elif warnings > 0 or mem_pct >= 75:
        status_icon = "\U0001f7e1"
        status_text = "warning"
    else:
        status_icon = "\U0001f7e2"
        status_text = "healthy"

    # Header
    header = f"## {status_icon} HORUS Workstation \u2014 {status_text}"
    components.append({
        "type": COMPONENT_TEXT_DISPLAY,
        "content": header,
    })

    # Build status lines
    status_lines = []

    # Memory
    if mem_pct > 0:
        mem_icon = "\U0001f534" if mem_pct >= 90 else "\U0001f7e1" if mem_pct >= 75 else "\U0001f7e2"
        status_lines.append(f"{mem_icon} Memory: {mem_pct}%")

    # Limits
    if limits:
        inotify = limits.get("inotify", {})
        current = inotify.get("current_instances", 0)
        max_watches = inotify.get("max_watches", 0)

        if critical > 0:
            status_lines.append(f"\U0001f534 Limits: {critical} critical")
            issues.append("inotify/file limits near exhaustion")
        elif warnings > 0:
            status_lines.append(f"\U0001f7e1 Limits: {warnings} warning(s)")
        else:
            status_lines.append(f"\U0001f7e2 Limits: OK ({current} watchers)")

    # GPU
    gpu = health.get("gpu")
    if gpu and gpu.get("available"):
        gpu_temp = gpu.get("temp_c", 0)
        gpu_mem = gpu.get("mem_used_pct", 0)
        gpu_icon = "\U0001f534" if gpu_temp >= 85 else "\U0001f7e1" if gpu_temp >= 75 else "\U0001f7e2"
        status_lines.append(f"{gpu_icon} GPU: {gpu_temp}\u00b0C, {gpu_mem}% mem")

    if status_lines:
        components.append({
            "type": COMPONENT_TEXT_DISPLAY,
            "content": "\n".join(status_lines),
        })

    # Issues section (if any)
    if issues:
        components.append({
            "type": COMPONENT_TEXT_DISPLAY,
            "content": "\n".join([f"**{i}**" for i in issues]),
        })

    return {
        "components": components,
        "flags": FLAG_IS_COMPONENTS_V2,
    }
