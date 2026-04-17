"""Phase 1: Infrastructure collectors.

Checks daemon health via Unix sockets, counts tests, inspects the 3-tier
cascade (registry, shadow data, classifiers), enumerates skills compliance,
frontend components, deployment artifacts, and daemon-cascade wiring.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from constants import (
    CLASSIFIERS_DIR,
    DAEMON_SOCKETS,
    EMBRY_OS,
    PI_SKILLS,
    REGISTRY_PATH,
    SHADOW_JSONL,
    TRAINING_DIR,
)


def collect_daemons() -> dict[str, Any]:
    """Check daemon health via Unix sockets."""
    results = {}
    for name, sock in DAEMON_SOCKETS.items():
        if not Path(sock).exists():
            results[name] = {"status": "socket_missing", "detail": sock}
            continue
        try:
            out = subprocess.run(
                ["curl", "-s", "--max-time", "3", "--unix-socket", sock,
                 "http://localhost/health"],
                capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                data = json.loads(out.stdout)
                results[name] = {"status": data.get("status", "unknown"), "detail": "ok"}
            else:
                results[name] = {"status": "error", "detail": out.stderr[:100]}
        except Exception as e:
            results[name] = {"status": "error", "detail": str(e)[:100]}

    up = sum(1 for v in results.values() if v["status"] in ("ok", "healthy"))
    return {"daemons": results, "up": up, "total": len(DAEMON_SOCKETS)}


def collect_tests() -> dict[str, Any]:
    """Count tests via pytest --collect-only."""
    tests_dir = EMBRY_OS / "services" / "tests"
    if not tests_dir.exists():
        return {"total": 0, "collected": False, "error": "tests dir missing"}
    try:
        out = subprocess.run(
            ["uv", "run", "python", "-m", "pytest", str(tests_dir),
             "--collect-only", "-q"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": f"{EMBRY_OS / 'services'}:{os.environ.get('PYTHONPATH', '')}"},
            cwd=str(EMBRY_OS),
        )
        for line in out.stdout.splitlines():
            if "test" in line and "selected" in line:
                count = int(line.split()[0])
                return {"total": count, "collected": True}
        count = sum(1 for ln in out.stdout.splitlines() if "::" in ln)
        return {"total": count, "collected": True}
    except Exception as e:
        return {"total": 0, "collected": False, "error": str(e)[:100]}


def collect_cascade() -> dict[str, Any]:
    """Cascade status: registry, shadow entries, classifiers on disk."""
    result: dict[str, Any] = {}

    if REGISTRY_PATH.exists():
        reg = json.loads(REGISTRY_PATH.read_text())
        result["registry"] = {
            "validators": len(reg.get("validators", {})),
            "classifiers": len(reg.get("classifiers", {})),
            "regressors": len(reg.get("regressors", {})),
            "gpts": len(reg.get("gpts", {})),
        }
    else:
        result["registry"] = {"validators": 0, "classifiers": 0, "regressors": 0, "gpts": 0}

    if SHADOW_JSONL.exists():
        lines = SHADOW_JSONL.read_text().splitlines()
        total = len(lines)
        usable = 0
        for line in lines:
            try:
                e = json.loads(line)
                if (e.get("input_data") and e.get("teacher_grade")) or (e.get("input") and e.get("output")):
                    usable += 1
            except (json.JSONDecodeError, KeyError):
                continue
        result["shadow"] = {"total": total, "usable": usable}
    else:
        result["shadow"] = {"total": 0, "usable": 0}

    training = {}
    if TRAINING_DIR.exists():
        for task_dir in sorted(TRAINING_DIR.iterdir()):
            if task_dir.is_dir():
                count = 0
                for f in task_dir.glob("labels_*.jsonl"):
                    count += sum(1 for ln in f.read_text().splitlines() if ln.strip())
                training[task_dir.name] = count
    result["training_data"] = training

    classifiers_on_disk = []
    if CLASSIFIERS_DIR.exists():
        for f in sorted(CLASSIFIERS_DIR.glob("*.joblib")):
            classifiers_on_disk.append({
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    result["classifiers_on_disk"] = classifiers_on_disk

    reg = result["registry"]
    result["tier_status"] = {
        "tier_2_teacher": "ACTIVE" if reg["validators"] > 0 else "MISSING",
        "tier_1_5_gpt": "DEPLOYED" if reg["gpts"] > 0 else "NOT_TRAINED",
        "tier_0_5_classifier": f"{len(classifiers_on_disk)} ON DISK" if classifiers_on_disk else "NONE",
    }
    return result


def collect_skills() -> dict[str, Any]:
    """Count skills and check for SKILL.md + sanity.sh compliance."""
    if not PI_SKILLS.exists():
        return {"total": 0, "path": str(PI_SKILLS), "missing_skill_md": [], "missing_sanity": []}
    dirs = sorted([d for d in PI_SKILLS.iterdir() if d.is_dir() and not d.name.startswith(".")])
    missing_skill_md = [d.name for d in dirs if not (d / "SKILL.md").exists()]
    missing_sanity = [d.name for d in dirs if not (d / "sanity.sh").exists() and (d / "SKILL.md").exists()]
    return {
        "total": len(dirs),
        "path": str(PI_SKILLS),
        "missing_skill_md": missing_skill_md[:10],
        "missing_skill_md_count": len(missing_skill_md),
        "missing_sanity": missing_sanity[:10],
        "missing_sanity_count": len(missing_sanity),
    }


def collect_frontend() -> dict[str, Any]:
    """Frontend component counts."""
    ui_dir = EMBRY_OS / "apps" / "embry-ui"
    result: dict[str, Any] = {"exists": ui_dir.exists()}
    if not ui_dir.exists():
        return result
    tsx_files = list((ui_dir / "src").rglob("*.tsx")) if (ui_dir / "src").exists() else []
    rs_files = list((ui_dir / "src-tauri" / "src").rglob("*.rs")) if (ui_dir / "src-tauri" / "src").exists() else []
    result["tsx_components"] = len(tsx_files)
    result["rust_files"] = len(rs_files)
    return result


def collect_deploy() -> dict[str, Any]:
    """Deployment artifact counts."""
    systemd_dir = EMBRY_OS / "services" / "systemd"
    units = list(systemd_dir.glob("embry-*")) if systemd_dir.exists() else []
    return {
        "systemd_units": len(units),
        "containerfile": (EMBRY_OS / "Containerfile").exists(),
    }


def collect_daemon_cascade_wiring() -> dict[str, Any]:
    """Check which daemons have cascade integration."""
    wired = {}
    for name in ("inference-daemon", "sparta-daemon", "datalake-daemon"):
        main_py = EMBRY_OS / "services" / name / "main.py"
        if main_py.exists():
            content = main_py.read_text()
            has_cascade = "InferenceRouter" in content or "_cascade_validate" in content or "cascade" in content.lower()
            wired[name] = has_cascade
        else:
            wired[name] = False
    return wired
