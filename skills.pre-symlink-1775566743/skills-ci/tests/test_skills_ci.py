"""test_skills_ci - tests.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from pathlib import Path
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skills_ci", ROOT / "skills_ci.py")
skills_ci = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["skills_ci"] = skills_ci
spec.loader.exec_module(skills_ci)


FIXTURES = Path(__file__).parent / "fixtures" / "skills_root"


def test_scan_reports_violations():
    report, _ = skills_ci.scan_skills(
        FIXTURES,
        best_practices=["best-practices-skills", "best-practices-python"],
        mode="scan",
        apply=False,
        max_fix_loc=400,
    )
    summary = report.summary()
    assert summary["total"] > 0
    # Expect missing docstring + requests usage in skill-a/example.py
    assert any(v.rule == "python.module_docstring" for v in report.violations)
    assert any(v.rule == "python.requests" for v in report.violations)


def test_apply_safe_fixes_docstring_and_requests(tmp_path: Path):
    sample = tmp_path / "sample.py"
    sample.write_text("import requests\n\n\n" "def call(url):\n    return requests.get(url)\n")
    violations = [
        skills_ci.Violation(
            rule="python.module_docstring",
            severity="warn",
            skill="tmp",
            path=str(sample),
            message="Missing module docstring",
            fixable=True,
        ),
        skills_ci.Violation(
            rule="python.requests",
            severity="warn",
            skill="tmp",
            path=str(sample),
            message="Uses requests",
            fixable=True,
        ),
    ]
    applied, skipped = skills_ci.apply_safe_fixes(violations, max_fix_loc=400)
    assert str(sample) in applied
    assert not skipped
    updated = sample.read_text()
    assert updated.startswith('"""')
    assert "import httpx as requests" in updated


def test_run_lint_executes_script(tmp_path: Path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    skill_dir = skill_root / "skill-lint"
    skill_dir.mkdir()
    marker = skill_dir / "lint_ran.txt"
    lint = skill_dir / "lint.sh"
    lint.write_text("#!/bin/bash\nset -e\n\necho ok > lint_ran.txt\n")
    lint.chmod(0o755)
    skills_ci.run_lint(skill_root, ["skill-lint"])
    assert marker.exists()


def test_write_per_skill_reports(tmp_path: Path):
    violations = [
        skills_ci.Violation(
            rule="skills.frontmatter_missing",
            severity="error",
            skill="skill-a",
            path="skill-a/SKILL.md",
            message="Missing frontmatter",
        ),
        skills_ci.Violation(
            rule="python.module_docstring",
            severity="warn",
            skill="skill-b",
            path="skill-b/example.py",
            message="Missing module docstring",
        ),
    ]
    report = skills_ci.Report(
        root="/tmp/skills",
        best_practices=["best-practices-skills"],
        mode="scan",
        timestamp="2026-02-04T00:00:00Z",
        violations=violations,
        applied_fixes=[],
        skipped_fixes=[],
    )
    out_dir = tmp_path / "per-skill"
    skills_ci.write_per_skill_reports(report, out_dir)
    payload = json.loads((out_dir / "skill-a" / "report.json").read_text())
    assert payload["skill"] == "skill-a"
    assert payload["summary"]["total"] == 1
