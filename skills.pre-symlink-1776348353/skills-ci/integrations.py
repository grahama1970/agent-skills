"""External service integrations for skills-ci.

Handles task-monitor registration, memory learning, analytics, figure
generation, agent-inbox notifications, and lint/sanity/test execution.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from loguru import logger

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Report, Violation
from reporting import ARTIFACTS_DIR
from scanners import list_skill_dirs

# Heavy artifacts live on 12TB -- never on NVMe boot drive
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))


# ---------------------------------------------------------------------------
# Task monitor
# ---------------------------------------------------------------------------

def _run(cmd: Sequence[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


def resolve_task_monitor_root(skills_root: Path) -> Path:
    candidates = [
        skills_root,
        Path(__file__).resolve().parents[1],
    ]
    for candidate in candidates:
        monitor_py = candidate / "task-monitor" / "monitor.py"
        run_sh = candidate / "task-monitor" / "run.sh"
        if monitor_py.exists() and run_sh.exists():
            return candidate
    raise FileNotFoundError("task-monitor skill not found under skills root.")


def resolve_task_monitor_run(skills_root: Path) -> Path:
    monitor_root = resolve_task_monitor_root(skills_root)
    run_sh = monitor_root / "task-monitor" / "run.sh"
    if not run_sh.exists():
        raise FileNotFoundError("task-monitor run.sh not found.")
    return run_sh


def write_task_state(
    state_file: Path,
    completed: int,
    total: int,
    current_item: str,
    stats: Optional[Dict[str, int]] = None,
) -> None:
    payload = {
        "completed": completed,
        "total": total,
        "current_item": current_item,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "stats": stats or {},
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def default_state_file(report_json: Optional[Path], name: str) -> Path:
    if report_json:
        base = report_json.parent
    else:
        base = ARTIFACTS_DIR
    return base / f"{name}.state.json"


class TaskMonitorIntegration:
    def __init__(
        self,
        skills_root: Path,
        name: str,
        project: str,
        state_file: Path,
        total: int,
        description: str,
    ) -> None:
        self.run_sh = resolve_task_monitor_run(skills_root)
        self.name = name
        self.project = project
        self.state_file = state_file
        self.total = total
        self.description = description

    def _run(self, args: Sequence[str]) -> None:
        subprocess.run([str(self.run_sh), *args], check=True, text=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

    def start(self) -> None:
        self._run([
            "register",
            "--name",
            self.name,
            "--state",
            str(self.state_file),
            "--total",
            str(self.total),
            "--desc",
            self.description,
            "--project",
            self.project,
        ])
        write_task_state(self.state_file, completed=0, total=self.total, current_item="", stats={})

    def update(self, completed: int, current_item: str) -> None:
        write_task_state(self.state_file, completed=completed, total=self.total, current_item=current_item)

    def finish(self, summary: Dict[str, int]) -> None:
        stats = {
            "errors": summary.get("error", 0),
            "warnings": summary.get("warn", 0),
            "total": summary.get("total", 0),
        }
        write_task_state(self.state_file, completed=self.total, total=self.total, current_item="", stats=stats)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def find_git_root(start: Path) -> Path:
    try:
        result = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
        return Path(result.stdout.strip())
    except Exception as exc:
        raise RuntimeError(f"Unable to locate git root from {start}") from exc


# ---------------------------------------------------------------------------
# Best-practices discovery
# ---------------------------------------------------------------------------

def discover_best_practices(root: Path, override: Optional[str]) -> List[str]:
    if override:
        return [p.strip() for p in override.split(",") if p.strip()]
    found = []
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.startswith("best-practices-"):
            found.append(entry.name)
    return sorted(found)


# ---------------------------------------------------------------------------
# Agent inbox
# ---------------------------------------------------------------------------

def resolve_agent_inbox_binary(skills_root: Path) -> Path:
    candidates = [
        skills_root / "agent-inbox" / "agent-inbox",
        Path(".agents/skills/agent-inbox/agent-inbox"),
        Path("agent-inbox"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("agent-inbox executable not found in skills root or PATH.")


def send_agent_inbox_message(
    skills_root: Path,
    project: str,
    message: str,
    context_file: Optional[Path] = None,
) -> None:
    inbox_bin = resolve_agent_inbox_binary(skills_root)
    cmd = [str(inbox_bin), "send", "--to", project, "--type", "info"]
    if context_file:
        cmd.extend(["--context-file", str(context_file)])
    cmd.append(message)
    subprocess.run(cmd, check=True, text=True,
    env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )


# ---------------------------------------------------------------------------
# Sanity, tests, lint
# ---------------------------------------------------------------------------

def run_sanity_and_tests(skills_root: Path, changed_skills: List[str]) -> None:
    pytest_cmd = ["pytest", "-q"]
    if shutil.which("uv"):
        pytest_cmd = ["uv", "run", "pytest", "-q"]

    for skill in sorted(set(changed_skills)):
        skill_dir = skills_root / skill
        sanity = skill_dir / "sanity.sh"
        if sanity.exists():
            subprocess.run(["bash", str(sanity)], cwd=skill_dir, check=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )

        tests_dir = skill_dir / "tests"
        has_tests = tests_dir.exists() or any(skill_dir.glob("test_*.py"))
        if has_tests:
            subprocess.run(pytest_cmd, cwd=skill_dir, check=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )


def run_lint(skills_root: Path, skills: List[str]) -> None:
    for skill in sorted(set(skills)):
        skill_dir = skills_root / skill
        lint = skill_dir / "lint.sh"
        if lint.exists():
            subprocess.run(["bash", str(lint)], cwd=skill_dir, check=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )


# ---------------------------------------------------------------------------
# Post-scan integrations (memory, analytics, figures)
# ---------------------------------------------------------------------------

def learn_report(skills_root: Path, report: Report) -> None:
    """Store scan summary in /memory via Unix socket for drift/regression detection."""
    summary = report.summary()
    # Build per-rule breakdown
    rule_counts: Dict[str, int] = {}
    for v in report.violations:
        rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
    top_rules = ", ".join(f"{r}={c}" for r, c in sorted(rule_counts.items(), key=lambda x: -x[1])[:8])
    problem = (
        f"skills-ci scan at {report.timestamp}: "
        f"{summary['error']} errors, {summary['warn']} warnings across {len(set(v.skill for v in report.violations))} skills. "
        f"Top rules: {top_rules}"
    )
    solution = (
        f"Total violations: {summary['total']}. "
        f"Rule breakdown: {json.dumps(rule_counts)}. "
        f"Best practices checked: {', '.join(report.best_practices)}."
    )
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            client.post("/learn", json={
                "problem": problem,
                "solution": solution,
                "tags": ["skills-ci", "scan", "drift-detection"],
            })
    except Exception as e:
        logger.debug("memory learn failed: {}", e)


def sync_skill_actions(skills_root: Path) -> int:
    """Register every skill's triggers as app_actions docs in /memory.

    This makes skills discoverable via voice and natural language through
    the /memory intent pipeline. Each skill becomes one app_actions doc
    with its trigger phrases as the searchable problem field.

    Returns the number of skills successfully registered.
    """
    from scanners import parse_frontmatter

    registered = 0
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        client = httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)
    except Exception as e:
        logger.warning("Cannot connect to memory daemon for app_actions sync: {}", e)
        return 0

    try:
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                text = skill_md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            fm = parse_frontmatter(text)
            if fm is None:
                continue

            # Skip internal skills — not voice-invocable
            if fm.get("internal"):
                continue

            triggers = fm.get("triggers", [])
            if not triggers or not isinstance(triggers, list):
                continue

            skill_name = skill_dir.name
            description = fm.get("description", "")
            if isinstance(description, str):
                description = description.strip()[:200]
            composes = fm.get("composes", [])
            provides = fm.get("provides", [])

            # Build the app_actions document
            problem = " | ".join(str(t) for t in triggers)
            solution = json.dumps({
                "ui_action": "RUN_SKILL",
                "skill": skill_name,
                "composes": composes if isinstance(composes, list) else [],
                "provides": provides if isinstance(provides, list) else [],
            })

            doc = {
                "problem": problem,
                "solution": solution,
                "scope": "embry-os",
                "tags": [
                    "queryspec-action",
                    "embry-os",
                    "action:RUN_SKILL",
                    f"skill:{skill_name}",
                    "skill-action",
                ],
            }

            try:
                resp = client.post("/learn", json=doc)
                if resp.status_code < 300:
                    registered += 1
                else:
                    logger.debug("app_actions upsert failed for {}: {}", skill_name, resp.status_code)
            except Exception as e:
                logger.debug("app_actions upsert failed for {}: {}", skill_name, e)

        logger.info("Synced {} skill actions to app_actions", registered)
    finally:
        client.close()

    return registered


def run_analytics(skills_root: Path, report_json_path: Path) -> None:
    """Run /analytics on the violations data for trend analysis."""
    analytics_run = skills_root / "analytics" / "run.sh"
    if not analytics_run.exists():
        return
    try:
        subprocess.run(
            [str(analytics_run), str(report_json_path),
             "--query", "violations by rule and severity, top 10 skills by violation count, trend over time"],
            capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except Exception as e:
        logger.debug("value lookup failed: {}", e)


def generate_figures(skills_root: Path, report: Report) -> None:
    """Generate coverage/violation figures via /create-figure."""
    figure_run = skills_root / "create-figure" / "run.sh"
    if not figure_run.exists():
        return
    summary = report.summary()
    # Build data for figure generation
    rule_counts: Dict[str, int] = {}
    for v in report.violations:
        rule_counts[v.rule] = rule_counts.get(v.rule, 0) + 1
    data_str = json.dumps({"rules": rule_counts, "summary": summary})
    output_dir = ARTIFACTS_DIR
    try:
        subprocess.run(
            [str(figure_run), "--type", "bar",
             "--title", f"Skills CI Violations ({report.timestamp[:10]})",
             "--data", data_str,
             "--output", str(output_dir / "violations_chart.png")],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except Exception as e:
        logger.debug("value lookup failed: {}", e)


# ---------------------------------------------------------------------------
# Systemd hardening scan
# ---------------------------------------------------------------------------

SYSTEMD_HARDENING_DIRECTIVES = {
    "ProtectSystem": "strict",
    "PrivateTmp": "yes",
    "NoNewPrivileges": "true",
    "ProtectHome": "read-only",
    "RestrictSUIDSGID": "yes",
}


def scan_systemd_hardening(project_root: Path) -> List[Violation]:
    """Scan .pi/systemd/*.service files for missing hardening directives."""
    systemd_dir = project_root / ".pi" / "systemd"
    if not systemd_dir.is_dir():
        return []

    violations: List[Violation] = []
    for service_file in sorted(systemd_dir.glob("*.service")):
        content = service_file.read_text(encoding="utf-8")
        lines = {
            line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
            for line in content.splitlines()
            if "=" in line and not line.strip().startswith("#")
        }
        for directive, expected in SYSTEMD_HARDENING_DIRECTIVES.items():
            if directive not in lines:
                violations.append(Violation(
                    rule="systemd-hardening",
                    severity="warn",
                    skill=service_file.stem,
                    path=str(service_file),
                    message=f"Missing hardening directive: {directive}={expected}",
                ))
            elif lines[directive] != expected:
                violations.append(Violation(
                    rule="systemd-hardening",
                    severity="warn",
                    skill=service_file.stem,
                    path=str(service_file),
                    message=f"Hardening directive {directive}={lines[directive]}, expected {expected}",
                ))
    return violations
