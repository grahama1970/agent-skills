"""Phase 1b: Component project health checks.

Parses registered component projects from embry.yaml when present and checks
each for git status, dirty files, and test counts via pytest --collect-only.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from constants import EMBRY_YAML, HAS_YAML

try:
    import yaml
except ImportError:
    pass


def _parse_components_config() -> dict[str, dict[str, str]]:
    """Read component projects from embry.yaml."""
    if not EMBRY_YAML.exists():
        return {}
    if HAS_YAML:
        with open(EMBRY_YAML) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("components", {})
    # Fallback: simple regex parse -- only within the components: section
    text = EMBRY_YAML.read_text()
    components: dict[str, dict[str, str]] = {}
    in_components = False
    current = None
    for line in text.splitlines():
        # Detect top-level keys (no indentation)
        if line and not line[0].isspace() and ":" in line:
            if line.strip() == "components:":
                in_components = True
            else:
                in_components = False
            current = None
            continue
        if not in_components:
            continue
        # 2-space indent = component name
        if re.match(r"^  [a-zA-Z]", line) and ":" in line:
            key = line.strip().rstrip(":")
            current = key
            components[current] = {}
        elif current and line.strip().startswith("path:"):
            components[current]["path"] = line.split(":", 1)[1].strip()
        elif current and line.strip().startswith("role:"):
            components[current]["role"] = line.split(":", 1)[1].strip()
        elif current and line.strip().startswith("test_cmd:"):
            components[current]["test_cmd"] = line.split(":", 1)[1].strip().strip('"').strip("'")
    return components


def collect_components() -> dict[str, Any]:
    """Check health of registered component projects."""
    config = _parse_components_config()
    if not config:
        return {"registered": 0, "projects": {}, "note": "No component registry found"}

    projects: dict[str, dict[str, Any]] = {}
    for name, info in config.items():
        raw_path = info.get("path", "")
        proj_path = Path(raw_path).expanduser()
        entry: dict[str, Any] = {
            "role": info.get("role", ""),
            "path": str(proj_path),
        }

        if not proj_path.exists():
            entry["status"] = "MISSING"
            projects[name] = entry
            continue

        # Git status: last commit + dirty check
        try:
            log_out = subprocess.run(
                ["git", "log", "-1", "--format=%h %ar %s"],
                capture_output=True, text=True, timeout=5, cwd=str(proj_path),
            )
            if log_out.returncode == 0:
                entry["last_commit"] = log_out.stdout.strip()
        except Exception as exc:
            logger.error("git log check failed for {}: {}", proj_path, exc)

        try:
            dirty_out = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=5, cwd=str(proj_path),
            )
            if dirty_out.returncode == 0:
                changed = len([ln for ln in dirty_out.stdout.splitlines() if ln.strip()])
                entry["dirty"] = changed > 0
                entry["changed_files"] = changed
        except Exception as exc:
            logger.error("git status check failed for {}: {}", proj_path, exc)

        # Test count via pytest --collect-only (fast, doesn't run tests)
        test_cmd = info.get("test_cmd", "")
        if test_cmd and "pytest" in test_cmd:
            tests_dir = proj_path / "tests"
            if not tests_dir.exists():
                # Try common alternatives
                for alt in ("test", "services/tests"):
                    if (proj_path / alt).exists():
                        tests_dir = proj_path / alt
                        break

            if tests_dir.exists():
                try:
                    out = subprocess.run(
                        ["uv", "run", "--project", str(proj_path),
                         "python", "-m", "pytest", str(tests_dir),
                         "--collect-only", "-q"],
                        capture_output=True, text=True, timeout=30,
                        cwd=str(proj_path),
                    )
                    # Parse "N tests collected" from stdout or stderr
                    collected = 0
                    for text in (out.stdout, out.stderr):
                        for line in text.splitlines():
                            m = re.search(r"(\d+) tests? collected", line)
                            if m:
                                collected = int(m.group(1))
                                break
                        if collected > 0:
                            break
                    if collected > 0:
                        entry["tests"] = collected
                        entry["test_status"] = "COLLECTED"
                    else:
                        entry["tests"] = 0
                        entry["test_status"] = "ERROR"
                        entry["test_error"] = out.stderr[:100] if out.stderr else out.stdout[:100]
                except subprocess.TimeoutExpired:
                    entry["test_status"] = "TIMEOUT"
                except Exception as e:
                    entry["test_status"] = "ERROR"
                    entry["test_error"] = str(e)[:100]
            else:
                entry["test_status"] = "NO_TESTS_DIR"
        else:
            entry["test_status"] = "SKIPPED"

        entry["status"] = "OK"
        projects[name] = entry

    return {
        "registered": len(config),
        "ok": sum(1 for p in projects.values() if p.get("status") == "OK"),
        "projects": projects,
    }
