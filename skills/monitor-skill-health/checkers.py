"""Violation checkers, file discovery, and risk scoring for monitor-skill-health.

Contains all rule-pack violation detectors (Python, KDE, React, skills structure),
the assess runner, risk scoring, and the main audit_skill orchestration function.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from config import (
    AGENTS_ROOT,
    ARTIFACT_STORAGE_ROOT,
    ASSESS_REFERENCE_PATH_PARTS,
    ASSESS_PY,
    ASSESS_RUN,
    HEAVY_ARTIFACT_DIRS,
    HEAVY_ARTIFACT_SUFFIXES,
    HIGH_RISK_MEDIUM_THRESHOLD,
    HIGH_RISK_MONOLITH_LINES,
    HIGH_RISK_SCORE_THRESHOLD,
    NOISE_PATH_PARTS,
    RISK_BASE_SCORES,
    SEVERITY_ORDER,
    SKILLS_ROOT,
    STATE_DIR,
)


@dataclass
class AuditResult:
    """Result of auditing a single skill or agent directory."""

    skill: str
    path: str
    status: str
    rule_packs: list[str]
    works_well: list[str]
    needs_fix: list[dict[str, Any]]
    aspirational_gaps: list[dict[str, Any]]
    next_steps: list[str]
    errors: list[str]
    target_type: str = "skill"
    target: str = ""
    deep_review: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------


def safe_read_lines(path: Path) -> list[str]:
    """Read file lines, returning empty list on failure."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def discover_skills() -> list[Path]:
    """Return sorted list of skill directories containing SKILL.md."""
    skills: list[Path] = []
    for child in sorted(SKILLS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if (child / "SKILL.md").exists():
            skills.append(child)
    return skills


def discover_agents() -> list[Path]:
    """Return sorted list of agent directories containing AGENTS.md."""
    agents: list[Path] = []
    if not AGENTS_ROOT.exists():
        return agents
    for child in sorted(AGENTS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in {"tests"}:
            continue
        if (child / "AGENTS.md").exists():
            agents.append(child)
    return agents


def discover_targets(include_agents: bool = True) -> list[tuple[str, Path]]:
    """Return sorted auditable targets as (target_type, directory)."""
    targets: list[tuple[str, Path]] = [("skill", path) for path in discover_skills()]
    if include_agents:
        targets.extend(("agent", path) for path in discover_agents())
    return sorted(targets, key=lambda item: (item[0], item[1].name))


def collect_source_files(skill_dir: Path) -> list[Path]:
    """Collect auditable source files from a skill directory, skipping noise."""
    exclude = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    files: list[Path] = []
    for root, dirs, names in os.walk(skill_dir):
        root_path = Path(root)
        rel_root = root_path.relative_to(skill_dir)
        dirs[:] = [
            d
            for d in dirs
            if d not in exclude and not _is_noise_relative_path(rel_root / d)
        ]
        for name in names:
            file_path = root_path / name
            rel_path = file_path.relative_to(skill_dir)
            if _is_noise_relative_path(rel_path):
                continue
            if file_path.suffix.lower() in {".py", ".qml", ".ts", ".tsx", ".js", ".jsx", ".md", ".sh"}:
                files.append(file_path)
    return files


# ---------------------------------------------------------------------------
# Noise / location filters
# ---------------------------------------------------------------------------


def _is_noise_relative_path(rel_path: Path) -> bool:
    return any(part in NOISE_PATH_PARTS for part in rel_path.parts)


def _is_noise_location(skill_dir: Path, location: str) -> bool:
    raw = (location or "").strip()
    if not raw:
        return False

    loc_path = Path(raw)
    if loc_path.is_absolute():
        try:
            rel = loc_path.relative_to(skill_dir)
            return _is_noise_relative_path(rel)
        except ValueError:
            normalized = raw.replace("\\", "/")
            return any(f"/{marker}/" in normalized for marker in NOISE_PATH_PARTS)

    return _is_noise_relative_path(Path(raw))


def _is_reference_location(location: str) -> bool:
    """Return True for documentation/review/example locations from assess."""
    raw = (location or "").strip()
    if not raw:
        return False

    path = Path(raw)
    parts = path.parts
    if path.is_absolute():
        normalized = raw.replace("\\", "/")
        return any(f"/{marker}/" in normalized for marker in ASSESS_REFERENCE_PATH_PARTS)

    return any(part in ASSESS_REFERENCE_PATH_PARTS for part in parts)


def _severity_for_assess_location(location: str) -> str:
    """Keep executable/contract findings medium; make reference prose low."""
    return "low" if _is_reference_location(location) else "medium"


# ---------------------------------------------------------------------------
# Violation checkers
# ---------------------------------------------------------------------------


def storage_policy_violations(skill_dir: Path) -> list[dict[str, Any]]:
    """Check heavy artifact directory and file storage policy."""
    violations: list[dict[str, Any]] = []

    for name in sorted(HEAVY_ARTIFACT_DIRS):
        path = skill_dir / name
        if not path.exists():
            continue

        rel = str(path.relative_to(skill_dir))
        if path.is_symlink():
            try:
                target = path.resolve(strict=False)
            except OSError:
                violations.append(
                    {
                        "rule_pack": "best-practices-skills",
                        "rule": "storage-policy-symlink-broken",
                        "severity": "medium",
                        "file": rel,
                        "message": f"Heavy artifact symlink `{rel}` is broken.",
                    }
                )
                continue

            try:
                target.relative_to(ARTIFACT_STORAGE_ROOT)
            except ValueError:
                violations.append(
                    {
                        "rule_pack": "best-practices-skills",
                        "rule": "storage-policy-symlink-target",
                        "severity": "medium",
                        "file": rel,
                        "message": (
                            f"`{rel}` points to `{target}`; expected under `{ARTIFACT_STORAGE_ROOT}`."
                        ),
                    }
                )
            continue

        if path.is_dir():
            violations.append(
                {
                    "rule_pack": "best-practices-skills",
                    "rule": "storage-policy-symlink-required",
                    "severity": "medium",
                    "file": rel,
                    "message": (
                        f"Heavy artifact dir `{rel}` should be a symlink into "
                        f"`{ARTIFACT_STORAGE_ROOT}`."
                    ),
                }
            )

    for file_path in skill_dir.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in HEAVY_ARTIFACT_SUFFIXES:
            rel = str(file_path.relative_to(skill_dir))
            violations.append(
                {
                    "rule_pack": "best-practices-skills",
                    "rule": "storage-policy-large-file",
                    "severity": "medium",
                    "file": rel,
                    "message": (
                        f"Artifact file `{rel}` should live under `{ARTIFACT_STORAGE_ROOT}` "
                        "with a symlink in the skill directory."
                    ),
                }
            )

    return violations


def _has_yaml_frontmatter(skill_md: Path) -> bool:
    lines = safe_read_lines(skill_md)
    return len(lines) >= 3 and lines[0].strip() == "---" and any(l.strip() == "---" for l in lines[1:])


def _frontmatter_keys(skill_md: Path) -> set[str]:
    lines = safe_read_lines(skill_md)
    if not lines or lines[0].strip() != "---":
        return set()

    keys: set[str] = set()
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":", 1)[0].strip()
            if key:
                keys.add(key)
    return keys


def python_violations(skill_dir: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Check Python files for convention violations."""
    violations: list[dict[str, Any]] = []

    for file_path in files:
        if file_path.suffix != ".py":
            continue
        rel = str(file_path.relative_to(skill_dir))
        lines = safe_read_lines(file_path)

        if len(lines) > 800:
            violations.append(
                {
                    "rule_pack": "best-practices-python",
                    "rule": "style-max-800-lines",
                    "severity": "medium",
                    "file": rel,
                    "message": f"Python file has {len(lines)} lines (>800).",
                }
            )

        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
            has_module_docstring = ast.get_docstring(tree) is not None
        except (OSError, SyntaxError, UnicodeDecodeError):
            has_module_docstring = False
        if lines and not has_module_docstring:
            violations.append(
                {
                    "rule_pack": "best-practices-python",
                    "rule": "style-module-docstring",
                    "severity": "low",
                    "file": rel,
                    "message": "Module appears to be missing a top-level docstring.",
                }
            )

        if _imports_module(file_path, "requests"):
            violations.append(
                {
                    "rule_pack": "best-practices-python",
                    "rule": "conventions-httpx",
                    "severity": "medium",
                    "file": rel,
                    "message": "Detected requests usage; prefer httpx by repo convention.",
                }
            )

    return violations


def _imports_module(file_path: Path, module_name: str) -> bool:
    """Return True when a Python file imports a module, ignoring strings/comments."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root == module_name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root == module_name:
                return True
    return False


def kde_violations(skill_dir: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Check QML files for KDE convention violations."""
    violations: list[dict[str, Any]] = []
    color_re = re.compile(r"#[0-9a-fA-F]{3,8}")

    for file_path in files:
        if file_path.suffix.lower() != ".qml":
            continue
        rel = str(file_path.relative_to(skill_dir))
        lines = safe_read_lines(file_path)

        if len(lines) > 600:
            violations.append(
                {
                    "rule_pack": "best-practices-kde",
                    "rule": "style-max-600-lines",
                    "severity": "medium",
                    "file": rel,
                    "message": f"QML file has {len(lines)} lines (>600).",
                }
            )

        joined = "\n".join(lines)
        if color_re.search(joined):
            violations.append(
                {
                    "rule_pack": "best-practices-kde",
                    "rule": "design-singleton-style",
                    "severity": "low",
                    "file": rel,
                    "message": "Hardcoded hex color detected; prefer singleton style tokens.",
                }
            )

    return violations


def react_violations(skill_dir: Path, files: list[Path]) -> list[dict[str, Any]]:
    """Check React/JSX files for accessibility violations."""
    violations: list[dict[str, Any]] = []
    for file_path in files:
        if file_path.suffix.lower() not in {".tsx", ".jsx"}:
            continue
        rel = str(file_path.relative_to(skill_dir))
        content = "\n".join(safe_read_lines(file_path))
        if "aria-" not in content and "<button" in content:
            violations.append(
                {
                    "rule_pack": "best-practices-react",
                    "rule": "a11y-semantic-controls",
                    "severity": "low",
                    "file": rel,
                    "message": "Button markup without obvious accessibility attributes.",
                }
            )
    return violations


def skills_violations(skill_dir: Path) -> list[dict[str, Any]]:
    """Check skill structure (SKILL.md, frontmatter, extra docs, storage)."""
    violations: list[dict[str, Any]] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        violations.append(
            {
                "rule_pack": "best-practices-skills",
                "rule": "required-structure",
                "severity": "critical",
                "file": "SKILL.md",
                "message": "Skill directory is missing SKILL.md.",
            }
        )
        return violations

    if not _has_yaml_frontmatter(skill_md):
        violations.append(
            {
                "rule_pack": "best-practices-skills",
                "rule": "frontmatter-required",
                "severity": "critical",
                "file": "SKILL.md",
                "message": "SKILL.md is missing valid YAML frontmatter.",
            }
        )
        return violations

    keys = _frontmatter_keys(skill_md)
    for required in ("name", "description", "provides", "composes"):
        if required not in keys:
            violations.append(
                {
                    "rule_pack": "best-practices-skills",
                    "rule": "composition-frontmatter",
                    "severity": "high",
                    "file": "SKILL.md",
                    "message": f"Frontmatter is missing required key: {required}.",
                }
            )

    for extra_doc in ("README.md", "CHANGELOG.md"):
        if (skill_dir / extra_doc).exists():
            violations.append(
                {
                    "rule_pack": "best-practices-skills",
                    "rule": "avoid-extra-docs",
                    "severity": "low",
                    "file": extra_doc,
                    "message": "Prefer a single SKILL.md; extra docs are discouraged.",
                }
            )

    violations.extend(storage_policy_violations(skill_dir))

    return violations


def agent_violations(agent_dir: Path) -> list[dict[str, Any]]:
    """Check agent contract structure (AGENTS.md frontmatter and required keys)."""
    violations: list[dict[str, Any]] = []
    agents_md = agent_dir / "AGENTS.md"

    if not agents_md.exists():
        return [
            {
                "rule_pack": "best-practices-agent",
                "rule": "agent-contract-required",
                "severity": "critical",
                "file": "AGENTS.md",
                "message": "Agent directory is missing AGENTS.md.",
            }
        ]

    if not _has_yaml_frontmatter(agents_md):
        return [
            {
                "rule_pack": "best-practices-agent",
                "rule": "agent-frontmatter-required",
                "severity": "critical",
                "file": "AGENTS.md",
                "message": "AGENTS.md is missing valid YAML frontmatter.",
            }
        ]

    keys = _frontmatter_keys(agents_md)
    for required in ("id", "kind", "title", "mode", "composes"):
        if required not in keys:
            violations.append(
                {
                    "rule_pack": "best-practices-agent",
                    "rule": "agent-frontmatter",
                    "severity": "high",
                    "file": "AGENTS.md",
                    "message": f"Agent frontmatter is missing required key: {required}.",
                }
            )

    if agent_dir.name != (next((line.split(":", 1)[1].strip() for line in safe_read_lines(agents_md) if line.strip().startswith("id:")), "") or agent_dir.name):
        violations.append(
            {
                "rule_pack": "best-practices-agent",
                "rule": "agent-id-directory-match",
                "severity": "medium",
                "file": "AGENTS.md",
                "message": "Agent id should match its directory name for registry routing.",
            }
        )

    return violations


# ---------------------------------------------------------------------------
# Assess runner
# ---------------------------------------------------------------------------


def run_assess(skill_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Run the assess skill on a directory and return (report, errors)."""
    errors: list[str] = []
    report_path = STATE_DIR / f"assess_{skill_dir.name}_{int(time.time() * 1000)}.json"

    primary_cmd = [str(ASSESS_RUN), "run", str(skill_dir), "--output", str(report_path)]
    proc = subprocess.run(primary_cmd, capture_output=True, text=True, check=False, timeout=300)
    if proc.returncode != 0 and ASSESS_PY.exists():
        fallback_cmd = [sys.executable, str(ASSESS_PY), "run", str(skill_dir), "--output", str(report_path)]
        proc = subprocess.run(fallback_cmd, capture_output=True, text=True, check=False, timeout=300)

    if proc.returncode != 0:
        errors.append(f"assess failed ({proc.returncode}): {proc.stderr.strip()[:240]}")
        return {}, errors

    if not report_path.exists():
        errors.append("assess produced no output file")
        return {}, errors

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return report, errors
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"failed to parse assess output: {exc}")
        return {}, errors
    finally:
        try:
            report_path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Status / scoring / risk
# ---------------------------------------------------------------------------


def status_for(violations: list[dict[str, Any]], errors: list[str]) -> str:
    """Determine overall status from violations and errors."""
    if errors:
        return "critical"
    if any(v.get("severity") == "critical" for v in violations):
        return "critical"
    if any(v.get("severity") in {"high", "medium"} for v in violations):
        return "warning"
    return "healthy"


def next_steps(needs_fix: list[dict[str, Any]], aspirational: list[dict[str, Any]]) -> list[str]:
    """Generate prioritised next-step suggestions."""
    ordered = sorted(
        needs_fix,
        key=lambda item: SEVERITY_ORDER.get(str(item.get("severity", "low")), 0),
        reverse=True,
    )
    steps: list[str] = []
    for issue in ordered[:3]:
        file_ref = issue.get("file", "unknown")
        rule = issue.get("rule", "unknown-rule")
        steps.append(f"Fix `{rule}` in `{file_ref}`.")

    if aspirational:
        steps.append("Resolve TODO/stub items or remove stale aspirational claims.")

    if not steps:
        steps.append("No immediate fixes required; keep nightly monitoring active.")

    return steps


def monolith_line_count(issue: dict[str, Any]) -> int:
    """Extract line count from a style-max-800-lines issue message."""
    if issue.get("rule") != "style-max-800-lines":
        return 0
    message = str(issue.get("message", ""))
    match = re.search(r"has\s+(\d+)\s+lines", message)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def risk_score(result: AuditResult) -> int:
    """Compute a numeric risk score for a single audit result."""
    score = 0
    for issue in result.needs_fix + result.aspirational_gaps:
        severity = str(issue.get("severity", "low"))
        score += RISK_BASE_SCORES.get(severity, 0)
        rule = str(issue.get("rule", ""))
        if rule == "brittle":
            score += 2
        if rule == "style-max-800-lines":
            lines = monolith_line_count(issue)
            if lines >= 4000:
                score += 40
            elif lines >= 2500:
                score += 25
            elif lines >= 1500:
                score += 15
            elif lines >= 1000:
                score += 8
    return score


def is_high_risk(result: AuditResult) -> bool:
    """Determine whether a result qualifies as high-risk."""
    if result.status == "critical":
        return True
    issues = result.needs_fix + result.aspirational_gaps
    if any(issue.get("severity") in {"critical", "high"} for issue in issues):
        return True
    medium_count = sum(1 for issue in issues if issue.get("severity") == "medium")
    if medium_count >= HIGH_RISK_MEDIUM_THRESHOLD:
        return True
    if any(monolith_line_count(issue) >= HIGH_RISK_MONOLITH_LINES for issue in issues):
        return True
    return risk_score(result) >= HIGH_RISK_SCORE_THRESHOLD


def rank_high_risk(results: list[AuditResult]) -> list[tuple[int, AuditResult]]:
    """Return high-risk results ranked by descending risk score."""
    ranked: list[tuple[int, AuditResult]] = []
    for result in results:
        if is_high_risk(result):
            ranked.append((risk_score(result), result))
    ranked.sort(key=lambda item: (item[0], item[1].skill), reverse=True)
    return ranked


def normalize_assess_gaps(skill_dir: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw assess aspirational entries into normalised gap findings."""
    gaps: list[dict[str, Any]] = []
    for entry in entries:
        location = str(entry.get("location", "unknown"))
        if _is_noise_location(skill_dir, location):
            continue
        gaps.append(
            {
                "rule_pack": "assess",
                "rule": "aspirational",
                "severity": _severity_for_assess_location(location),
                "file": location,
                "message": entry.get("reason") or entry.get("feature", "aspirational item"),
            }
        )
    return gaps


def rule_packs_for(files: list[Path], target_type: str = "skill") -> list[str]:
    """Determine which rule packs apply based on file extensions."""
    packs = {"best-practices-agent"} if target_type == "agent" else {"best-practices-skills"}
    if any(path.suffix == ".py" for path in files):
        packs.add("best-practices-python")
    if any(path.suffix.lower() == ".qml" for path in files):
        packs.add("best-practices-kde")
    if any(path.suffix.lower() in {".tsx", ".jsx"} for path in files):
        packs.add("best-practices-react")
    return sorted(packs)


# ---------------------------------------------------------------------------
# Main audit entry point
# ---------------------------------------------------------------------------


def audit_skill(skill_dir: Path) -> AuditResult:
    """Run all checkers against a single skill and return an AuditResult."""
    return audit_target(skill_dir, target_type="skill")


def audit_agent(agent_dir: Path) -> AuditResult:
    """Run all checkers against a single agent and return an AuditResult."""
    return audit_target(agent_dir, target_type="agent")


def audit_target(target_dir: Path, target_type: str = "skill") -> AuditResult:
    """Run all checkers against a single skill or agent and return an AuditResult."""
    files = collect_source_files(target_dir)
    assess_report, assess_errors = run_assess(target_dir)

    needs_fix: list[dict[str, Any]] = []
    if target_type == "agent":
        needs_fix.extend(agent_violations(target_dir))
    else:
        needs_fix.extend(skills_violations(target_dir))
    needs_fix.extend(python_violations(target_dir, files))
    needs_fix.extend(kde_violations(target_dir, files))
    needs_fix.extend(react_violations(target_dir, files))

    brittle = assess_report.get("categories", {}).get("brittle", []) if assess_report else []
    for entry in brittle:
        location = str(entry.get("location", "unknown"))
        if _is_noise_location(target_dir, location):
            continue
        needs_fix.append(
            {
                "rule_pack": "assess",
                "rule": "brittle",
                "severity": _severity_for_assess_location(location),
                "file": location,
                "message": entry.get("reason") or entry.get("feature", "brittle item"),
            }
        )

    aspirational_entries = assess_report.get("categories", {}).get("aspirational", []) if assess_report else []
    aspirational = normalize_assess_gaps(target_dir, aspirational_entries)

    works_well = []
    for entry in assess_report.get("categories", {}).get("working_well", []) if assess_report else []:
        feature = entry.get("feature", "feature")
        location = entry.get("location", "unknown")
        works_well.append(f"{feature} has companion coverage signal ({location}).")

    if not works_well:
        works_well.append("No strong positives detected automatically; manual review may add context.")

    errors = assess_errors
    status = status_for(needs_fix, errors)

    return AuditResult(
        skill=target_dir.name,
        path=str(target_dir),
        status=status,
        rule_packs=rule_packs_for(files, target_type=target_type),
        works_well=works_well,
        needs_fix=needs_fix,
        aspirational_gaps=aspirational,
        next_steps=next_steps(needs_fix, aspirational),
        errors=errors,
        target_type=target_type,
        target=f"{'agents' if target_type == 'agent' else 'skills'}/{target_dir.name}",
    )
