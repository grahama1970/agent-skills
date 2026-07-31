"""Phase 4: Best-practices anti-pattern scanner.

Scans the codebase for common anti-patterns across Python services, React
frontend code, and skill SKILL.md compliance (frontmatter, provides field).
"""

from __future__ import annotations

import re
from typing import Any

from constants import BEST_PRACTICE_SKILLS, EMBRY_OS, PI_SKILLS


def collect_best_practices() -> dict[str, Any]:
    """Scan for common anti-patterns across the codebase."""
    findings = []

    # Python anti-patterns in services/
    services_dir = EMBRY_OS / "services"
    if services_dir.exists():
        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file) or ".venv" in str(py_file):
                continue
            try:
                content = py_file.read_text()
            except Exception:
                continue

            rel = str(py_file.relative_to(EMBRY_OS))

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

    # React anti-patterns in frontend
    ui_src = EMBRY_OS / "apps" / "embry-ui" / "src"
    if ui_src.exists():
        for tsx_file in ui_src.rglob("*.tsx"):
            try:
                content = tsx_file.read_text()
            except Exception:
                continue
            rel = str(tsx_file.relative_to(EMBRY_OS))

            # console.log in production code
            if "console.log" in content:
                findings.append({"file": rel, "issue": "console_log", "severity": "low"})

            # any type usage
            if re.search(r':\s*any\b', content):
                findings.append({"file": rel, "issue": "typescript_any", "severity": "low"})

    # Skills best practices
    if PI_SKILLS.exists():
        for skill_dir in PI_SKILLS.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # Missing frontmatter
                if not content.startswith("---"):
                    findings.append({
                        "file": f"skills/{skill_dir.name}/SKILL.md",
                        "issue": "missing_frontmatter",
                        "severity": "medium",
                    })
                # Missing provides field
                elif "provides:" not in content:
                    findings.append({
                        "file": f"skills/{skill_dir.name}/SKILL.md",
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
