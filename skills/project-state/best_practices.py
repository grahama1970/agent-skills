"""Phase 4: Best-practices anti-pattern scanner.

Scans the codebase for common anti-patterns across Python services, React
frontend code, and skill SKILL.md compliance (frontmatter, provides field).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger

from constants import BEST_PRACTICE_SKILLS, PI_SKILLS, PROJECT_ROOT, is_embry_project


_EXCLUDED_DIRS = {
    ".git",
    ".claude",
    ".skills",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "local",
    "artifacts",
}


def _is_excluded(path: Path) -> bool:
    """Return true for generated, vendored, or local artifact paths."""
    return any(part in _EXCLUDED_DIRS for part in path.parts)


def _skill_roots() -> list[Path]:
    """Return skill roots relevant to the target checkout."""
    roots = [
        PROJECT_ROOT / ".skills" / "skills",
        PROJECT_ROOT / "skills",
    ]
    if is_embry_project():
        roots.append(PI_SKILLS)
    seen: set[Path] = set()
    unique = []
    for root in roots:
        if root.exists() and root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def collect_best_practices() -> dict[str, Any]:
    """Scan for common anti-patterns across the codebase."""
    findings = []

    # Python anti-patterns in the target checkout.
    if PROJECT_ROOT.exists():
        for py_file in PROJECT_ROOT.rglob("*.py"):
            if _is_excluded(py_file.relative_to(PROJECT_ROOT)):
                continue
            try:
                content = py_file.read_text()
            except Exception as exc:
                logger.error("failed to read python file {}: {}", py_file, exc)
                continue

            rel = str(py_file.relative_to(PROJECT_ROOT))

            # Hardcoded secrets
            if re.search(r'(password|secret|token|api_key)\s*=\s*["\'][^"\']{8,}', content, re.IGNORECASE):
                findings.append({"file": rel, "issue": "hardcoded_secret", "severity": "critical"})

            # Bare except
            if re.search(r'\bexcept\s*:', content):
                findings.append({"file": rel, "issue": "bare_except", "severity": "medium"})

            # Hardcoded /home/graham paths (should use Path.home() or env)
            if "/home/graham" in content and "test" not in rel.lower():
                findings.append({"file": rel, "issue": "hardcoded_home_path", "severity": "low"})

            # print() instead of logger in daemon code
            if "daemon" in rel and re.search(r'\bprint\s*\(', content):
                # Allow if loguru is imported
                if "from loguru" not in content and "import loguru" not in content:
                    findings.append({"file": rel, "issue": "print_instead_of_logger", "severity": "low"})

    # React anti-patterns in target frontend code.
    if PROJECT_ROOT.exists():
        for tsx_file in PROJECT_ROOT.rglob("*.tsx"):
            if _is_excluded(tsx_file.relative_to(PROJECT_ROOT)):
                continue
            try:
                content = tsx_file.read_text()
            except Exception as exc:
                logger.error("failed to read tsx file {}: {}", tsx_file, exc)
                continue
            rel = str(tsx_file.relative_to(PROJECT_ROOT))

            # console.log in production code
            if "console.log" in content:
                findings.append({"file": rel, "issue": "console_log", "severity": "low"})

            # any type usage
            if re.search(r':\s*any\b', content):
                findings.append({"file": rel, "issue": "typescript_any", "severity": "low"})

    # Skills best practices for skill roots inside the target checkout.
    for skills_root in _skill_roots():
        for skill_dir in skills_root.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # Missing frontmatter
                if not content.startswith("---"):
                    findings.append({
                        "file": str(skill_md.relative_to(PROJECT_ROOT))
                        if skill_md.is_relative_to(PROJECT_ROOT)
                        else f"skills/{skill_dir.name}/SKILL.md",
                        "issue": "missing_frontmatter",
                        "severity": "medium",
                    })
                # Missing provides field
                elif "provides:" not in content:
                    findings.append({
                        "file": str(skill_md.relative_to(PROJECT_ROOT))
                        if skill_md.is_relative_to(PROJECT_ROOT)
                        else f"skills/{skill_dir.name}/SKILL.md",
                        "issue": "missing_provides",
                        "severity": "low",
                    })

    # Group by severity
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    return {
        "findings": findings[:30],  # cap for readability
        "total_findings": len(findings),
        "by_severity": by_severity,
        "best_practice_skills_available": [
            bp for bp in BEST_PRACTICE_SKILLS
            if (PI_SKILLS / bp / "SKILL.md").exists()
        ],
    }
