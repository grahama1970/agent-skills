"""Antipattern documentation scanner for skills-ci.

Checks that high-fan-in skills (composed by 3+ other skills) document
common agent mistakes with concrete WRONG/RIGHT examples.

Agents repeatedly misuse frequently-composed skills (memory, scillm,
mockup-lab, etc.) without learning. Concrete "Common Mistakes" sections
with WRONG code examples are the only effective countermeasure.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from models import Violation
from scanners import parse_frontmatter

# Section headers that indicate dedicated antipattern documentation.
# Loose markers like "Do NOT" appear everywhere — we need a dedicated section.
_SECTION_MARKERS = [
    "## Common Mistakes",
    "## Anti-pattern",
    "## Antipattern",
    "## What NOT",
    "## Do NOT",
    "## DON'T",
]
# Inline markers that count only if they appear 2+ times (indicates a pattern list)
_INLINE_MARKERS = ["WRONG:", "WRONG —", "DON'T:", "Bad example:"]

# Minimum composes-refs to trigger the check
_MIN_FAN_IN = 3

# Cache for composes-ref counting (built once per scan run)
_composes_cache: Optional[Dict[str, int]] = None


def _build_composes_cache(skills_root: Path) -> Dict[str, int]:
    """Count how many other skills list each skill in their composes: field."""
    cache: Dict[str, int] = {}
    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir():
            continue
        sm = skill_dir / "SKILL.md"
        if not sm.exists():
            continue
        try:
            fm = parse_frontmatter(sm.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if fm and isinstance(fm.get("composes"), list):
            for dep in fm["composes"]:
                dep_name = str(dep).strip()
                cache[dep_name] = cache.get(dep_name, 0) + 1
    return cache


def _count_composes_refs(skill_name: str, skills_root: Path) -> int:
    """Return how many skills compose this one."""
    global _composes_cache
    if _composes_cache is None:
        _composes_cache = _build_composes_cache(skills_root)
    return _composes_cache.get(skill_name, 0)


def scan_missing_antipatterns(
    skill_dir: Path,
    skill_name: str,
    skill_md_text: str,
) -> List[Violation]:
    """Warn if a high-fan-in skill lacks antipattern documentation."""
    violations: List[Violation] = []

    # Extract body (after frontmatter)
    body = skill_md_text.split("---", 2)[-1] if skill_md_text.count("---") >= 2 else skill_md_text

    # Check for dedicated antipattern section header
    has_section = any(marker in body for marker in _SECTION_MARKERS)
    # Or 2+ inline WRONG/DON'T markers (indicates a pattern list, not incidental usage)
    inline_count = sum(1 for marker in _INLINE_MARKERS if marker in body)
    if has_section or inline_count >= 2:
        return violations

    # Only warn for skills composed by 3+ others
    refs = _count_composes_refs(skill_name, skill_dir.parent)
    if refs >= _MIN_FAN_IN:
        violations.append(Violation(
            rule="skills.missing_antipatterns",
            severity="warn",
            skill=skill_name,
            path=str(skill_dir / "SKILL.md"),
            message=(
                f"Composed by {refs} other skills but SKILL.md has no antipattern "
                f"documentation. Add a '## Common Mistakes' section with concrete "
                f"WRONG/RIGHT examples. Agents misuse high-fan-in skills repeatedly."
            ),
        ))

    return violations
