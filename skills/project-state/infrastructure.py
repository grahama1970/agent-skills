"""Phase 1: Infrastructure collectors.

Checks project infrastructure, counts tests, inspects Embry cascade state when
applicable, enumerates skills compliance, frontend components, deployment
artifacts, and daemon-cascade wiring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

from constants import (
    CLASSIFIERS_DIR,
    DAEMON_SOCKETS,
    EMBRY_OS,
    PI_SKILLS,
    PROJECT_ROOT,
    REGISTRY_PATH,
    SHADOW_JSONL,
    TRAINING_DIR,
    is_embry_project,
)

load_dotenv()


NON_SKILL_DIR_NAMES = {
    "_shared",
    "common",
    "consume_common",
    "sanity",
    "create-claude",
    "subagent-service",
    "webgpt-engagement",
}


def collect_daemons() -> dict[str, Any]:
    """Check daemon health via Unix sockets."""
    if not is_embry_project():
        return {
            "applicable": False,
            "reason": "target root is not an Embry-style project",
            "daemons": {},
            "up": 0,
            "total": 0,
        }

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
        except Exception as exc:
            logger.error("daemon health check failed for {}: {}", name, exc)
            results[name] = {"status": "error", "detail": str(exc)[:100]}

    up = sum(1 for v in results.values() if v["status"] in ("ok", "healthy"))
    return {"daemons": results, "up": up, "total": len(DAEMON_SOCKETS)}


def collect_tests() -> dict[str, Any]:
    """Count tests via pytest --collect-only."""
    candidates = [
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "services" / "tests",
        PROJECT_ROOT / "test",
    ]
    tests_dir = next((path for path in candidates if path.exists()), None)
    if tests_dir is None:
        return {
            "total": 0,
            "collected": False,
            "error": "tests dir missing",
            "checked_paths": [str(path) for path in candidates],
        }
    try:
        if (PROJECT_ROOT / "pyproject.toml").exists():
            # `python -m pytest` uses the project env without dev groups, so a
            # project whose pytest is a dev dependency reports 0 tests. Let uv
            # resolve the tool (with an ephemeral fallback) instead.
            cmd = [
                "uv", "run", "--project", str(PROJECT_ROOT), "--with", "pytest",
                "pytest", str(tests_dir), "--collect-only", "-q",
            ]
        else:
            cmd = ["python", "-m", "pytest", str(tests_dir), "--collect-only", "-q"]
        # A cross-project subprocess must not inherit THIS skill's venv:
        # uv then warns/ignores and collection returns 0 for a target that has
        # tests (observed 2026-08-13: pitchdeck reported 0 of its 131 tests).
        child_env = {k: v for k, v in os.environ.items()
                     if k not in {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}}
        child_env["PYTHONPATH"] = f"{PROJECT_ROOT / 'services'}:{os.environ.get('PYTHONPATH', '')}"
        out = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=120,
            env=child_env,
            cwd=str(PROJECT_ROOT),
        )
        for stream in (out.stdout, out.stderr):
            match = re.search(r"(\d+)\s+tests?\s+collected", stream)
            if match:
                return {
                    "total": int(match.group(1)),
                    "collected": out.returncode == 0,
                    "path": str(tests_dir),
                }
        # pytest -q --collect-only emits either "N tests collected" or, in
        # newer versions, one "path/to/test_x.py: N" line per file with NO
        # summary — parsing only "::" lines under-reported real suites as 0.
        per_file = re.findall(r"^\S+\.py:\s*(\d+)\s*$", out.stdout, re.M)
        count = (sum(int(n) for n in per_file) if per_file
                 else sum(1 for ln in out.stdout.splitlines() if "::" in ln))
        return {
            "total": count,
            "collected": out.returncode == 0,
            "path": str(tests_dir),
            "error": (out.stderr or out.stdout)[:200] if out.returncode != 0 else None,
        }
    except Exception as exc:
        logger.error("pytest collection failed for {}: {}", PROJECT_ROOT, exc)
        return {"total": 0, "collected": False, "error": str(exc)[:100], "path": str(tests_dir)}


def collect_cascade() -> dict[str, Any]:
    """Cascade status: registry, shadow entries, classifiers on disk."""
    result: dict[str, Any] = {}
    if not is_embry_project():
        return {
            "applicable": False,
            "reason": "target root is not an Embry-style project",
            "registry": {"validators": 0, "classifiers": 0, "regressors": 0, "gpts": 0},
            "shadow": {"total": 0, "usable": 0},
            "training_data": {},
            "classifiers_on_disk": [],
            "tier_status": {
                "tier_2_teacher": "NOT_APPLICABLE",
                "tier_1_5_gpt": "NOT_APPLICABLE",
                "tier_0_5_classifier": "NOT_APPLICABLE",
            },
        }

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
    # Only roots the TARGET owns. Falling back to the global skills tree
    # reported 386 unrelated skills as a single skill's state (2026-08-13) —
    # a silent scope error is worse than an honest not-applicable.
    candidate_roots = [
        PROJECT_ROOT / ".skills" / "skills",
        PROJECT_ROOT / "skills",
    ]
    if is_embry_project() and PI_SKILLS.exists():
        candidate_roots.append(PI_SKILLS)
    if PROJECT_ROOT.resolve() == PI_SKILLS.resolve().parent or PROJECT_ROOT.resolve() == PI_SKILLS.resolve():
        candidate_roots.append(PI_SKILLS)
    skills_root = next((_normalize_skills_root(path) for path in candidate_roots if path.exists()), None)
    if skills_root is None:
        return {"total": 0, "applicable": False,
                "reason": "target root owns no skills/ tree (not a skills workspace)",
                "path": None, "missing_skill_md": [], "missing_sanity": []}
    if not skills_root.exists():
        return {"total": 0, "path": str(skills_root), "missing_skill_md": [], "missing_sanity": []}
    dirs = sorted(
        [
            d for d in skills_root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in NON_SKILL_DIR_NAMES
        ]
    )
    missing_skill_md = [d.name for d in dirs if not (d / "SKILL.md").exists()]
    missing_sanity = [d.name for d in dirs if not (d / "sanity.sh").exists() and (d / "SKILL.md").exists()]
    return {
        "total": len(dirs),
        "path": str(skills_root),
        "missing_skill_md": missing_skill_md[:10],
        "missing_skill_md_count": len(missing_skill_md),
        "missing_sanity": missing_sanity[:10],
        "missing_sanity_count": len(missing_sanity),
    }


def _normalize_skills_root(path: Path) -> Path:
    """Return the concrete directory that contains skill folders."""

    nested = path / "skills"
    if not nested.is_dir():
        return path

    root_skill_count = _count_skill_dirs(path)
    nested_skill_count = _count_skill_dirs(nested)
    return nested if nested_skill_count > root_skill_count else path


def _count_skill_dirs(path: Path) -> int:
    """Count child directories that contain skill metadata."""

    try:
        return sum(
            1
            for child in path.iterdir()
            if child.is_dir() and not child.name.startswith(".") and (child / "SKILL.md").is_file()
        )
    except OSError as exc:
        logger.error("failed to inspect skills root {}: {}", path, exc)
        return 0


def collect_frontend() -> dict[str, Any]:
    """Frontend component counts."""
    ui_dir = next(
        (
            path for path in (
                PROJECT_ROOT / "frontend",
                PROJECT_ROOT / "apps" / "embry-ui",
                PROJECT_ROOT / "prototypes" / "tabbed" / "html",
            )
            if path.exists()
        ),
        PROJECT_ROOT / "frontend",
    )
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
    systemd_dir = PROJECT_ROOT / "services" / "systemd"
    units = list(systemd_dir.iterdir()) if systemd_dir.exists() else []
    return {
        "systemd_units": len(units),
        "containerfile": (PROJECT_ROOT / "Containerfile").exists(),
        "docker_compose": (PROJECT_ROOT / "docker-compose.yml").exists()
        or (PROJECT_ROOT / "compose.yml").exists(),
    }


def collect_daemon_cascade_wiring() -> dict[str, Any]:
    """Check which daemons have cascade integration."""
    if not is_embry_project():
        return {
            "applicable": False,
            "reason": "target root is not an Embry-style project",
            "wired": {},
        }
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
