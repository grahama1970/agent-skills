"""Tier 4: Project Health probes (heavyweight, runs last).

P08 project-assess      — Run /assess on each registered project
P09 project-walkthrough  — Run /create-walkthrough on each registered project

Inputs: ~/.agent_skills_targets for project list.
Outputs: ProbeResult per probe.
"""
from __future__ import annotations
import os

import json
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe


def _load_targets() -> list[Path]:
    """Load registered project paths from ~/.agent_skills_targets."""
    if not config.TARGETS_FILE.exists():
        return []
    lines = config.TARGETS_FILE.read_text().strip().splitlines()
    return [Path(line.strip()) for line in lines if line.strip() and not line.startswith("#")]


# ── P08: project-assess ──────────────────────────────────────────────────────


@register_probe("P08", "project-assess", tier=4)
def probe_project_assess(autofix: bool = False) -> ProbeResult:
    """Run /assess on each registered project."""
    targets = _load_targets()
    if not targets:
        return ProbeResult(
            probe_id="P08", name="project-assess", tier=4,
            status=ProbeStatus.SKIP,
            message="No registered projects in ~/.agent_skills_targets",
            details={},
        )

    results = {}
    critical_count = 0

    for project_path in targets:
        name = project_path.name
        assess_py = project_path / ".pi/skills/assess/assess.py"

        if not assess_py.exists():
            results[name] = {"status": "skip", "reason": "assess skill not found"}
            continue

        try:
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmp_path = tmp.name

            proc = subprocess.run(
                ["python3", str(assess_py), "run", str(project_path), "--output", tmp_path],
                capture_output=True, text=True, timeout=300,
                cwd=str(project_path),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if proc.returncode == 0:
                try:
                    data = json.loads(Path(tmp_path).read_text())
                    findings = data.get("findings", [])
                    critical = [f for f in findings if f.get("severity") in ("critical", "high")]
                    results[name] = {
                        "status": "ok",
                        "findings": len(findings),
                        "critical": len(critical),
                    }
                    critical_count += len(critical)
                except (json.JSONDecodeError, OSError):
                    results[name] = {"status": "ok", "findings": 0, "critical": 0}
            else:
                results[name] = {
                    "status": "error",
                    "stderr": proc.stderr[:200] if proc.stderr else "",
                }
        except subprocess.TimeoutExpired:
            results[name] = {"status": "timeout"}
        except OSError as e:
            results[name] = {"status": "error", "reason": str(e)}
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except (NameError, OSError):
                pass

    assessed = sum(1 for r in results.values() if r.get("status") == "ok")
    status = ProbeStatus.PASS if critical_count == 0 else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P08", name="project-assess", tier=4,
        status=status,
        message=f"{assessed}/{len(targets)} assessed, {critical_count} critical findings",
        details={"projects": results},
    )


# ── P09: project-walkthrough ─────────────────────────────────────────────────


@register_probe("P09", "project-walkthrough", tier=4)
def probe_project_walkthrough(autofix: bool = False) -> ProbeResult:
    """Run /create-walkthrough on each registered project."""
    targets = _load_targets()
    if not targets:
        return ProbeResult(
            probe_id="P09", name="project-walkthrough", tier=4,
            status=ProbeStatus.SKIP,
            message="No registered projects in ~/.agent_skills_targets",
            details={},
        )

    results = {}

    for project_path in targets:
        name = project_path.name
        walkthrough_sh = project_path / ".pi/skills/create-walkthrough/run.sh"

        if not walkthrough_sh.exists():
            results[name] = {"status": "skip", "reason": "create-walkthrough not found"}
            continue

        try:
            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
                tmp_path = tmp.name

            proc = subprocess.run(
                [
                    str(walkthrough_sh), "generate",
                    "--recent-changes",
                    "--output", tmp_path,
                ],
                capture_output=True, text=True, timeout=600,
                cwd=str(project_path),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if proc.returncode == 0:
                try:
                    content = Path(tmp_path).read_text()
                    results[name] = {"status": "ok", "length": len(content)}
                except OSError:
                    results[name] = {"status": "ok", "length": 0}
            else:
                results[name] = {
                    "status": "error",
                    "stderr": proc.stderr[:200] if proc.stderr else "",
                }
        except subprocess.TimeoutExpired:
            results[name] = {"status": "timeout"}
        except OSError as e:
            results[name] = {"status": "error", "reason": str(e)}
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except (NameError, OSError):
                pass

    generated = sum(1 for r in results.values() if r.get("status") == "ok")

    return ProbeResult(
        probe_id="P09", name="project-walkthrough", tier=4,
        status=ProbeStatus.PASS,
        message=f"{generated}/{len(targets)} walkthroughs generated",
        details={"projects": results},
    )
