"""Tier 6: Model health probes for /assistant pipeline.

P21 model-registry       — Validate model_registry.json exists and is valid
P22 shadow-freshness     — Check shadow.jsonl has recent entries
P23 training-data-health — Check training data directories have non-empty labels
P24 model-files          — Check promoted model files exist on disk

Inputs: filesystem paths from ModelFactoryConfig defaults.
Outputs: ProbeResult per probe.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe

# --- Paths (matching model_factory defaults) ---

SKILLS_DIR = config.SKILLS_DIR
ASSISTANT_SKILL_DIR = SKILLS_DIR / "assistant"
ASSISTANT_METRICS_DIR = Path.home() / ".pi" / "assistant"
REGISTRY_PATH = ASSISTANT_SKILL_DIR / "model_registry.json"
SHADOW_FILE = ASSISTANT_METRICS_DIR / "shadow.jsonl"
TRAINING_DATA_DIR = ASSISTANT_METRICS_DIR / "training_data"


# ── P21: model-registry ─────────────────────────────────────────────────────


@register_probe("P21", "model-registry", tier=6)
def probe_model_registry(autofix: bool = False) -> ProbeResult:
    """Validate model_registry.json exists and has valid structure."""
    if not REGISTRY_PATH.exists():
        return ProbeResult(
            probe_id="P21", name="model-registry", tier=6,
            status=ProbeStatus.WARN,
            message=f"model_registry.json not found (bootstrap state — no models trained yet)",
            details={"path": str(REGISTRY_PATH)},
        )

    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P21", name="model-registry", tier=6,
            status=ProbeStatus.FAIL,
            message=f"model_registry.json invalid: {e}",
            details={"error": str(e), "path": str(REGISTRY_PATH)},
        )

    if not isinstance(data, dict):
        return ProbeResult(
            probe_id="P21", name="model-registry", tier=6,
            status=ProbeStatus.FAIL,
            message="model_registry.json root must be a dict",
            details={"type": type(data).__name__},
        )

    # Validate each task entry
    issues = []
    tasks = data.get("tasks", data)  # support both {tasks: {...}} and flat dict
    for task_name, info in tasks.items():
        if not isinstance(info, dict):
            issues.append(f"{task_name}: value is not a dict")
            continue
        # Check confidence thresholds are 0-1 if present
        for key in ("confidence", "agreement", "threshold"):
            val = info.get(key)
            if val is not None and (not isinstance(val, (int, float)) or val < 0 or val > 1):
                issues.append(f"{task_name}.{key}={val} not in [0,1]")

    status = ProbeStatus.PASS if not issues else ProbeStatus.WARN
    return ProbeResult(
        probe_id="P21", name="model-registry", tier=6,
        status=status,
        message=f"Registry has {len(tasks)} task(s), {len(issues)} issue(s)",
        details={"task_count": len(tasks), "issues": issues[:10]},
    )


# ── P22: shadow-freshness ───────────────────────────────────────────────────


@register_probe("P22", "shadow-freshness", tier=6)
def probe_shadow_freshness(autofix: bool = False) -> ProbeResult:
    """Check shadow.jsonl has recent entries (within 48h)."""
    if not SHADOW_FILE.exists():
        return ProbeResult(
            probe_id="P22", name="shadow-freshness", tier=6,
            status=ProbeStatus.WARN,
            message="shadow.jsonl not found",
            details={"path": str(SHADOW_FILE)},
        )

    try:
        stat = SHADOW_FILE.stat()
    except OSError as e:
        return ProbeResult(
            probe_id="P22", name="shadow-freshness", tier=6,
            status=ProbeStatus.FAIL,
            message=f"Cannot stat shadow.jsonl: {e}",
            details={"error": str(e)},
        )

    # Count lines
    try:
        line_count = sum(1 for _ in SHADOW_FILE.open())
    except OSError:
        line_count = 0

    # Check file age
    age_hours = (time.time() - stat.st_mtime) / 3600
    threshold_hours = 48

    # Check last entry timestamp if available
    last_ts = None
    try:
        # Read last line efficiently
        with SHADOW_FILE.open("rb") as f:
            f.seek(0, 2)  # end
            size = f.tell()
            if size > 0:
                # Read last 2KB to find last line
                f.seek(max(0, size - 2048))
                lines = f.read().decode("utf-8", errors="replace").strip().split("\n")
                if lines:
                    last_entry = json.loads(lines[-1])
                    last_ts = last_entry.get("ts") or last_entry.get("timestamp")
    except (json.JSONDecodeError, OSError, KeyError):
        pass

    if last_ts:
        try:
            dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            # Ensure dt is timezone-aware (if parsed without timezone, assume UTC)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        except (ValueError, AttributeError, TypeError):
            pass

    if line_count == 0:
        status = ProbeStatus.WARN
        msg = "shadow.jsonl is empty"
    elif age_hours > threshold_hours:
        status = ProbeStatus.WARN
        msg = f"{line_count} entries, last update {age_hours:.1f}h ago (stale)"
    else:
        status = ProbeStatus.PASS
        msg = f"{line_count} entries, last update {age_hours:.1f}h ago"

    return ProbeResult(
        probe_id="P22", name="shadow-freshness", tier=6,
        status=status,
        message=msg,
        details={
            "line_count": line_count,
            "age_hours": round(age_hours, 1),
            "last_ts": last_ts,
            "file_size_kb": round(stat.st_size / 1024, 1),
        },
    )


# ── P23: training-data-health ────────────────────────────────────────────────


@register_probe("P23", "training-data-health", tier=6)
def probe_training_data(autofix: bool = False) -> ProbeResult:
    """Check training data directories have non-empty harvested labels."""
    if not TRAINING_DATA_DIR.exists():
        return ProbeResult(
            probe_id="P23", name="training-data-health", tier=6,
            status=ProbeStatus.WARN,
            message="training_data directory not found",
            details={"path": str(TRAINING_DATA_DIR)},
        )

    task_dirs = [d for d in TRAINING_DATA_DIR.iterdir() if d.is_dir()]
    if not task_dirs:
        return ProbeResult(
            probe_id="P23", name="training-data-health", tier=6,
            status=ProbeStatus.WARN,
            message="No task directories in training_data",
            details={"path": str(TRAINING_DATA_DIR)},
        )

    healthy = []
    empty = []
    for td in sorted(task_dirs):
        label_files = list(td.glob("labels_*.jsonl"))
        if not label_files:
            empty.append(td.name)
            continue

        # Check if any label file has real data (non-empty input/output)
        has_real_data = False
        total_lines = 0
        for lf in label_files:
            try:
                for line in lf.open():
                    total_lines += 1
                    entry = json.loads(line)
                    inp = entry.get("input", {})
                    out = entry.get("output", {})
                    if inp and out:
                        has_real_data = True
                        break
            except (json.JSONDecodeError, OSError):
                continue
            if has_real_data:
                break

        if has_real_data:
            healthy.append({"task": td.name, "files": len(label_files), "lines": total_lines})
        else:
            empty.append(td.name)

    status = ProbeStatus.PASS if healthy else ProbeStatus.WARN
    return ProbeResult(
        probe_id="P23", name="training-data-health", tier=6,
        status=status,
        message=f"{len(healthy)} task(s) with real data, {len(empty)} empty/placeholder",
        details={
            "healthy": healthy,
            "empty": empty,
            "total_tasks": len(task_dirs),
        },
    )


# ── P24: model-files ────────────────────────────────────────────────────────


@register_probe("P24", "model-files", tier=6)
def probe_model_files(autofix: bool = False) -> ProbeResult:
    """Check promoted model files exist on disk (from registry)."""
    if not REGISTRY_PATH.exists():
        return ProbeResult(
            probe_id="P24", name="model-files", tier=6,
            status=ProbeStatus.SKIP,
            message="No model_registry.json — no models to check",
            details={},
        )

    try:
        data = json.loads(REGISTRY_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P24", name="model-files", tier=6,
            status=ProbeStatus.FAIL,
            message=f"Cannot read model_registry.json: {e}",
            details={"error": str(e)},
        )

    tasks = data.get("tasks", data)
    missing = []
    present = []

    for task_name, info in tasks.items():
        if not isinstance(info, dict):
            continue
        model_path = info.get("model_path") or info.get("path")
        if not model_path:
            continue

        p = Path(model_path)
        if p.exists():
            present.append(task_name)
        else:
            missing.append({"task": task_name, "path": str(p)})

    if not present and not missing:
        return ProbeResult(
            probe_id="P24", name="model-files", tier=6,
            status=ProbeStatus.SKIP,
            message="No model paths registered",
            details={},
        )

    status = ProbeStatus.PASS if not missing else ProbeStatus.FAIL
    return ProbeResult(
        probe_id="P24", name="model-files", tier=6,
        status=status,
        message=f"{len(present)} model(s) present, {len(missing)} missing",
        details={"present": present, "missing": missing[:10]},
    )
