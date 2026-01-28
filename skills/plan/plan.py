#!/usr/bin/env python3
"""
Plan Skill - Create orchestration-ready task files.

This skill guides human-agent collaboration to create comprehensive task files
that /orchestrate can reliably execute.

Key principles (from research):
- Planner-Executor-Verifier loop: separate planning from execution and verification
- Task graph (DAG) over flat lists: represent dependencies explicitly
- Stop when testable: decompose until each task has a concrete test
- Definition of Done per node: exact pass criteria, expected artifacts
- Budget-aware planning: stop decomposition when overhead exceeds value
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# Well-known packages that don't need sanity scripts
WELL_KNOWN_PACKAGES = {
    # Standard library
    "json", "os", "sys", "pathlib", "typing", "re", "datetime", "collections",
    "itertools", "functools", "contextlib", "dataclasses", "enum", "abc",
    "copy", "shutil", "tempfile", "subprocess", "argparse", "logging",
    "unittest", "asyncio", "concurrent", "threading", "multiprocessing",
    "hashlib", "secrets", "base64", "urllib", "http", "socket", "ssl",
    "email", "html", "xml", "csv", "sqlite3", "pickle", "shelve", "io",
    "string", "textwrap", "difflib", "struct", "codecs", "unicodedata",
    "math", "random", "statistics", "fractions", "decimal", "numbers",
    "time", "calendar", "locale", "gettext", "operator", "inspect",
    "traceback", "warnings", "gc", "weakref", "types", "builtins",

    # Well-known third-party
    "requests", "httpx", "aiohttp", "urllib3",
    "numpy", "pandas", "scipy", "matplotlib", "seaborn", "plotly",
    "pytest", "unittest", "mock", "hypothesis",
    "click", "typer", "rich", "tqdm",
    "pydantic", "attrs", "dataclasses_json",
    "sqlalchemy", "alembic", "peewee",
    "flask", "fastapi", "django", "starlette",
    "redis", "pymongo", "psycopg2", "mysql",
    "boto3", "google-cloud", "azure",
    "docker", "kubernetes",
    "yaml", "toml", "tomli", "tomllib",
    "jinja2", "mako",
    "pillow", "opencv-python",
    "beautifulsoup4", "lxml", "html5lib",
    "cryptography", "paramiko",
    "celery", "rq", "dramatiq",
    "loguru", "structlog",
}


@dataclass
class Task:
    """Represents a single task in the task file."""
    id: str
    description: str
    agent: str = "general-purpose"
    parallel_group: int = 0
    dependencies: list[str] = field(default_factory=list)
    sanity_script: str | None = None
    test_file: str | None = None
    assertion: str | None = None
    notes: str = ""

    def to_markdown(self) -> str:
        """Convert task to markdown format."""
        lines = [f"- [ ] **{self.id}**: {self.description}"]
        lines.append(f"  - Agent: {self.agent}")
        lines.append(f"  - Parallel: {self.parallel_group}")

        deps = ", ".join(self.dependencies) if self.dependencies else "none"
        lines.append(f"  - Dependencies: {deps}")

        if self.notes:
            lines.append(f"  - Notes: {self.notes}")

        if self.sanity_script:
            lines.append(f"  - **Sanity**: `{self.sanity_script}` (must pass first)")
        else:
            lines.append("  - **Sanity**: None (standard library / well-known packages)")

        lines.append("  - **Definition of Done**:")
        if self.test_file:
            lines.append(f"    - Test: `{self.test_file}`")
            lines.append(f"    - Assertion: {self.assertion or 'TBD'}")
        else:
            lines.append("    - Test: MISSING - must be created before implementation")
            lines.append(f"    - Assertion: {self.assertion or 'TBD - define what success looks like'}")

        return "\n".join(lines)


@dataclass
class Dependency:
    """Represents a non-standard dependency that needs a sanity script."""
    name: str
    api_method: str
    sanity_script: str
    status: str = "PENDING"  # PENDING, PASS, FAIL

    def to_markdown_row(self) -> str:
        """Convert to markdown table row."""
        status_mark = "[x]" if self.status == "PASS" else "[ ]"
        return f"| {self.name} | `{self.api_method}` | `{self.sanity_script}` | {status_mark} {self.status} |"


@dataclass
class TaskFile:
    """Represents a complete task file."""
    title: str
    goal: str
    context: str
    dependencies: list[Dependency] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    notes: str = ""

    def to_markdown(self) -> str:
        """Generate the complete task file markdown."""
        lines = [
            f"# Task List: {self.title}",
            "",
            f"**Created**: {datetime.now().strftime('%Y-%m-%d')}",
            f"**Goal**: {self.goal}",
            "",
            "## Context",
            "",
            self.context,
            "",
        ]

        # Dependencies section
        lines.append("## Crucial Dependencies (Sanity Scripts)")
        lines.append("")
        if self.dependencies:
            lines.append("| Library | API/Method | Sanity Script | Status |")
            lines.append("|---------|------------|---------------|--------|")
            for dep in self.dependencies:
                lines.append(dep.to_markdown_row())
            lines.append("")
            lines.append("> All sanity scripts must PASS before proceeding to implementation.")
        else:
            lines.append("| Library | API/Method | Sanity Script | Status |")
            lines.append("|---------|------------|---------------|--------|")
            lines.append("| N/A | Standard library / well-known only | N/A | N/A |")
            lines.append("")
            lines.append("> No sanity scripts needed - all dependencies are well-known.")
        lines.append("")

        # Questions/Blockers section
        lines.append("## Questions/Blockers")
        lines.append("")
        if self.questions:
            for q in self.questions:
                lines.append(f"- {q}")
        else:
            lines.append("None - all requirements clear.")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Tasks section - group by parallel group
        lines.append("## Tasks")
        lines.append("")

        # Group tasks by parallel group
        groups: dict[int, list[Task]] = {}
        for task in self.tasks:
            if task.parallel_group not in groups:
                groups[task.parallel_group] = []
            groups[task.parallel_group].append(task)

        for group_num in sorted(groups.keys()):
            group_tasks = groups[group_num]
            if group_num == 0:
                lines.append("### P0: Setup (Sequential)")
            elif group_num == max(groups.keys()):
                lines.append(f"### P{group_num}: Validation (After All Previous)")
            else:
                lines.append(f"### P{group_num}: Implementation (Parallel)")
            lines.append("")

            for task in group_tasks:
                lines.append(task.to_markdown())
                lines.append("")

        lines.append("---")
        lines.append("")

        # Completion criteria
        lines.append("## Completion Criteria")
        lines.append("")
        if self.completion_criteria:
            for criterion in self.completion_criteria:
                lines.append(f"- [ ] {criterion}")
        else:
            lines.append("- [ ] All sanity scripts pass")
            lines.append("- [ ] All tasks marked [x]")
            lines.append("- [ ] All Definition of Done tests pass")
            lines.append("- [ ] No regressions in existing tests")
        lines.append("")

        # Notes
        if self.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(self.notes)
            lines.append("")

        return "\n".join(lines)


def identify_non_standard_imports(code_or_description: str) -> list[str]:
    """
    Identify potential non-standard imports from code or task description.

    Returns list of package names that might need sanity scripts.
    """
    # Extract potential package names from imports
    import_pattern = r'(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
    matches = re.findall(import_pattern, code_or_description)

    # Also look for package names mentioned in descriptions
    # Common patterns: "use X", "using X", "with X library"
    desc_pattern = r'(?:use|using|with)\s+([a-zA-Z_][a-zA-Z0-9_-]+)(?:\s+(?:library|package|module))?'
    desc_matches = re.findall(desc_pattern, code_or_description.lower())

    all_packages = set(matches + desc_matches)

    # Filter to non-standard packages
    non_standard = [
        pkg for pkg in all_packages
        if pkg.lower() not in WELL_KNOWN_PACKAGES
        and not pkg.startswith('_')
    ]

    return non_standard


def needs_sanity_script(package_name: str) -> bool:
    """Check if a package needs a sanity script."""
    return package_name.lower() not in WELL_KNOWN_PACKAGES


def generate_sanity_script_template(package_name: str, api_method: str = "TBD") -> str:
    """Generate a template sanity script for a package."""
    return f'''#!/usr/bin/env python3
"""
Sanity script: {package_name}
Purpose: Verify {package_name} API works in isolation
Documentation: <add Context7 or docs link>

Exit codes:
  0 = PASS (dependency works)
  1 = FAIL (dependency broken)
  42 = CLARIFY (needs human input)
"""
import sys
from pathlib import Path

# Check import
try:
    import {package_name}
except ImportError:
    print(f"FAIL: {package_name} not installed. Run: pip install {package_name}")
    sys.exit(1)

# Test basic functionality
try:
    # TODO: Add actual test of {api_method}
    # Example:
    # result = {package_name}.{api_method}(...)
    # assert condition, "Expected behavior description"

    print(f"PASS: {package_name} imported successfully")
    print("TODO: Add actual API test")
    sys.exit(42)  # CLARIFY - needs actual test implementation

except Exception as e:
    print(f"FAIL: {{e}}")
    sys.exit(1)
'''


def validate_task_file(filepath: Path) -> dict[str, Any]:
    """
    Validate an existing task file for orchestration readiness.

    Returns a dict with:
    - valid: bool
    - issues: list of issues found
    - warnings: list of warnings
    """
    issues: list[str] = []
    warnings: list[str] = []

    if not filepath.exists():
        return {"valid": False, "issues": [f"File not found: {filepath}"], "warnings": []}

    content = filepath.read_text()

    # Check for Questions/Blockers
    if "## Questions/Blockers" in content:
        # Find the section content
        section_match = re.search(
            r'## Questions/Blockers\s*\n(.*?)(?=\n##|\n---|\Z)',
            content,
            re.DOTALL
        )
        if section_match:
            section = section_match.group(1).strip()
            # Check if section starts with "None" or similar (resolved)
            resolved_patterns = ["none", "n/a", "resolved", "all requirements clear", "all questions resolved"]
            is_resolved = any(section.lower().startswith(p) for p in resolved_patterns)

            if not is_resolved:
                # Check for actual bullet points (lines starting with "- ")
                has_bullets = any(line.strip().startswith("- ") for line in section.split('\n'))
                if has_bullets:
                    issues.append("Questions/Blockers section has unresolved items")
    else:
        warnings.append("No Questions/Blockers section found")

    # Check for Definition of Done
    tasks_without_dod = []
    task_pattern = r'\*\*Task\s+(\d+(?:\.\d+)?)\*\*[^\n]*'
    dod_pattern = r'\*\*Definition of Done\*\*:'

    for match in re.finditer(task_pattern, content):
        task_id = match.group(1)
        # Find the task block
        task_start = match.start()
        next_task = re.search(r'\n- \[ \] \*\*Task', content[task_start + 1:])
        task_end = task_start + next_task.start() + 1 if next_task else len(content)
        task_block = content[task_start:task_end]

        if "**Definition of Done**:" not in task_block:
            tasks_without_dod.append(f"Task {task_id}")
        elif "Test: MISSING" in task_block:
            warnings.append(f"Task {task_id} has MISSING test definition")

    if tasks_without_dod:
        issues.append(f"Tasks without Definition of Done: {', '.join(tasks_without_dod)}")

    # Check for sanity scripts if dependencies declared
    if "## Crucial Dependencies" in content:
        dep_section = re.search(
            r'\| Library \| API/Method \| Sanity Script \| Status \|\s*\n\|[-|]+\|\s*\n(.*?)(?=\n\n|\n>|\Z)',
            content,
            re.DOTALL
        )
        if dep_section:
            for line in dep_section.group(1).strip().split('\n'):
                if '| N/A |' not in line and '[ ] PENDING' in line:
                    warnings.append("Sanity scripts marked PENDING - run them before orchestration")
                    break

    # Check unchecked tasks count
    unchecked = len(re.findall(r'- \[ \] \*\*Task', content))
    checked = len(re.findall(r'- \[x\] \*\*Task', content))

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "stats": {
            "total_tasks": unchecked + checked,
            "completed_tasks": checked,
            "pending_tasks": unchecked,
        }
    }


def print_validation_report(result: dict[str, Any], filepath: Path) -> None:
    """Print a formatted validation report."""
    print(f"\n{'='*60}")
    print(f"Task File Validation: {filepath}")
    print('='*60)

    stats = result.get("stats", {})
    print(f"\nTasks: {stats.get('completed_tasks', 0)}/{stats.get('total_tasks', 0)} completed")

    if result["valid"]:
        print("\n[PASS] Task file is ready for orchestration")
    else:
        print("\n[FAIL] Task file has blocking issues:")
        for issue in result["issues"]:
            print(f"  - {issue}")

    if result["warnings"]:
        print("\nWarnings (non-blocking):")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create orchestration-ready task files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive planning session
  plan.py "Add PDF table extraction"

  # Validate existing task file
  plan.py --validate 01_TASKS.md

  # Analyze dependencies in a description
  plan.py --analyze-deps "Use camelot and pdfplumber to extract tables"
"""
    )

    parser.add_argument(
        "goal",
        nargs="?",
        help="High-level goal to plan"
    )

    parser.add_argument(
        "--validate",
        metavar="FILE",
        help="Validate an existing task file"
    )

    parser.add_argument(
        "--analyze-deps",
        metavar="TEXT",
        help="Analyze text for non-standard dependencies"
    )

    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output file (default: stdout)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of markdown"
    )

    args = parser.parse_args()

    # Validation mode
    if args.validate:
        filepath = Path(args.validate)
        result = validate_task_file(filepath)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_validation_report(result, filepath)

        return 0 if result["valid"] else 1

    # Dependency analysis mode
    if args.analyze_deps:
        non_standard = identify_non_standard_imports(args.analyze_deps)

        if args.json:
            result = {
                "non_standard_packages": non_standard,
                "needs_sanity_scripts": len(non_standard) > 0
            }
            print(json.dumps(result, indent=2))
        else:
            if non_standard:
                print("Non-standard packages found (may need sanity scripts):")
                for pkg in non_standard:
                    print(f"  - {pkg}")
            else:
                print("No non-standard packages found. All dependencies are well-known.")

        return 0

    # Planning mode - requires a goal
    if not args.goal:
        parser.print_help()
        return 1

    # For now, print a template that the agent would fill in
    # In practice, this would be called by the agent with structured data
    print(f"Planning goal: {args.goal}")
    print("\nThis script is meant to be used by the agent.")
    print("For interactive planning, use the /plan skill trigger.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
