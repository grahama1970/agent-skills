"""
Structure checks for best-practices-skills rules.

Validates skill directory structure: SKILL.md with valid frontmatter,
run.sh, sanity.sh, provides/composes fields, heavy artifact symlinks.

Inputs: target directory path (a skill directory)
Outputs: list of TestCheck results
Failure modes: non-skill directories pass trivially
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from loguru import logger

import sys
_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from test_lab import TestCheck

# Threshold for "heavy" artifacts that should be on 12TB
HEAVY_ARTIFACT_MB = 500
HEAVY_EXTENSIONS = {".pt", ".pth", ".onnx", ".bin", ".safetensors", ".gguf", ".ckpt"}


def run_checks(target_dir: Path) -> list[TestCheck]:
    """Run all skill structure checks against target directory."""
    checks: list[TestCheck] = []

    # Check if this looks like a skill directory
    skill_md = target_dir / "SKILL.md"
    run_sh = target_dir / "run.sh"
    sanity_sh = target_dir / "sanity.sh"

    # SKILL.md existence and validity
    checks.append(TestCheck(
        name="skill_md_exists",
        category="structure",
        passed=skill_md.exists(),
        description="Missing SKILL.md — required for all skills"
        if not skill_md.exists()
        else "SKILL.md present",
    ))

    if skill_md.exists():
        checks.extend(_check_skill_md(skill_md))

    # run.sh
    checks.append(TestCheck(
        name="run_sh_exists",
        category="structure",
        passed=run_sh.exists(),
        description="Missing run.sh — required entry point for skills"
        if not run_sh.exists()
        else "run.sh present",
    ))

    if run_sh.exists():
        checks.append(TestCheck(
            name="run_sh_executable",
            category="structure",
            passed=os.access(run_sh, os.X_OK),
            description="run.sh is not executable"
            if not os.access(run_sh, os.X_OK)
            else "run.sh is executable",
        ))

    # sanity.sh
    checks.append(TestCheck(
        name="sanity_sh_exists",
        category="testing",
        passed=sanity_sh.exists(),
        description="Missing sanity.sh — required for real-world validation"
        if not sanity_sh.exists()
        else "sanity.sh present",
    ))

    # Heavy artifact check
    checks.extend(_check_heavy_artifacts(target_dir))

    return checks


def _check_skill_md(skill_md: Path) -> list[TestCheck]:
    """Validate SKILL.md frontmatter."""
    checks: list[TestCheck] = []

    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception as e:
        checks.append(TestCheck(
            name="skill_md_readable",
            category="structure",
            passed=False,
            description=f"Cannot read SKILL.md: {e}",
        ))
        return checks

    # Check YAML frontmatter exists
    has_frontmatter = content.startswith("---")
    checks.append(TestCheck(
        name="skill_md_frontmatter",
        category="structure",
        passed=has_frontmatter,
        description="SKILL.md missing YAML frontmatter (must start with ---)"
        if not has_frontmatter
        else "SKILL.md has YAML frontmatter",
    ))

    if not has_frontmatter:
        return checks

    # Extract frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        checks.append(TestCheck(
            name="skill_md_frontmatter_closed",
            category="structure",
            passed=False,
            description="SKILL.md frontmatter not properly closed (missing closing ---)",
        ))
        return checks

    frontmatter = fm_match.group(1)

    # Check required fields
    has_name = re.search(r'^name:\s*\S', frontmatter, re.MULTILINE) is not None
    checks.append(TestCheck(
        name="skill_md_name",
        category="structure",
        passed=has_name,
        description="SKILL.md frontmatter missing 'name' field"
        if not has_name
        else "SKILL.md has 'name' field",
    ))

    has_description = re.search(r'^description:', frontmatter, re.MULTILINE) is not None
    checks.append(TestCheck(
        name="skill_md_description",
        category="structure",
        passed=has_description,
        description="SKILL.md frontmatter missing 'description' field"
        if not has_description
        else "SKILL.md has 'description' field",
    ))

    has_provides = re.search(r'^provides:', frontmatter, re.MULTILINE) is not None
    checks.append(TestCheck(
        name="skill_md_provides",
        category="structure",
        passed=has_provides,
        description="SKILL.md frontmatter missing 'provides' field"
        if not has_provides
        else "SKILL.md has 'provides' field",
    ))

    has_composes = re.search(r'^composes:', frontmatter, re.MULTILINE) is not None
    checks.append(TestCheck(
        name="skill_md_composes",
        category="structure",
        passed=has_composes,
        description="SKILL.md frontmatter missing 'composes' field"
        if not has_composes
        else "SKILL.md has 'composes' field",
    ))

    return checks


def _check_heavy_artifacts(target_dir: Path) -> list[TestCheck]:
    """Check that heavy artifacts are symlinked to 12TB storage."""
    checks: list[TestCheck] = []
    heavy_files = []

    for ext in HEAVY_EXTENSIONS:
        heavy_files.extend(target_dir.rglob(f"*{ext}"))

    if not heavy_files:
        return checks  # No heavy files, nothing to check

    for heavy_file in heavy_files:
        size_mb = heavy_file.stat().st_size / (1024 * 1024) if heavy_file.exists() else 0
        is_symlink = heavy_file.is_symlink()

        if size_mb > HEAVY_ARTIFACT_MB and not is_symlink:
            checks.append(TestCheck(
                name=f"{heavy_file.name}:symlink_to_12tb",
                category="storage",
                passed=False,
                description=f"Heavy artifact ({size_mb:.0f}MB) not symlinked to 12TB storage",
            ))
        elif is_symlink:
            link_target = str(heavy_file.resolve())
            on_12tb = "/mnt/storage12tb" in link_target
            checks.append(TestCheck(
                name=f"{heavy_file.name}:symlink_target",
                category="storage",
                passed=on_12tb,
                description=f"Symlink points to {link_target} (not on 12TB)"
                if not on_12tb
                else "Heavy artifact correctly symlinked to 12TB",
            ))

    return checks
