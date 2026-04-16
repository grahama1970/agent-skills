"""
Pattern-based blind evaluation checks for best-practices-react rules.

Checks React/Next.js/TSX files for common anti-patterns: barrel file
re-exports, missing aria attributes, sequential fetches without Promise.all,
missing key props in lists, and inline styles.

Inputs: target directory path
Outputs: list of TestCheck results
Failure modes: unreadable files (skipped)
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

import sys
_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from test_lab import TestCheck


def run_checks(target_dir: Path) -> list[TestCheck]:
    """Run all React best-practices checks against target directory."""
    checks: list[TestCheck] = []

    tsx_files = list(target_dir.rglob("*.tsx")) + list(target_dir.rglob("*.jsx"))
    ts_files = list(target_dir.rglob("*.ts"))
    all_files = tsx_files + ts_files

    # Skip node_modules, .next, dist
    all_files = [
        f for f in all_files
        if not any(
            part in f.parts
            for part in ("node_modules", ".next", "dist", "build", ".git")
        )
    ]

    if not all_files:
        checks.append(TestCheck(
            name="react_files_exist",
            category="structure",
            passed=True,
            description="No React/TS files found (nothing to check)",
        ))
        return checks

    # Check for barrel files (index.ts that only re-exports)
    checks.extend(_check_barrel_files(all_files))

    for f in tsx_files:
        checks.extend(_check_tsx_file(f))

    return checks


def _check_barrel_files(all_files: list[Path]) -> list[TestCheck]:
    """Detect barrel file re-exports (bad for bundle size)."""
    checks: list[TestCheck] = []

    index_files = [f for f in all_files if f.name in ("index.ts", "index.tsx")]
    for idx_file in index_files:
        try:
            content = idx_file.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("//")]
        if not lines:
            continue

        # If all non-empty lines are exports, it's a barrel file
        export_lines = [l for l in lines if l.startswith("export")]
        is_barrel = len(export_lines) == len(lines) and len(lines) > 1

        if is_barrel:
            checks.append(TestCheck(
                name=f"{idx_file.name}:barrel_export",
                category="performance",
                passed=False,
                description="Barrel file re-exports hurt bundle size — use direct imports",
            ))

    return checks


def _check_tsx_file(filepath: Path) -> list[TestCheck]:
    """Run checks against a single TSX/JSX file."""
    checks: list[TestCheck] = []
    rel = filepath.name

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Cannot read {filepath}: {e}")
        return checks

    # Missing aria-* on interactive elements
    interactive_patterns = [
        (r'<button\b(?![^>]*aria-)', "button"),
        (r'<a\b(?![^>]*aria-label)(?![^>]*aria-describedby)', "anchor"),
        (r'<input\b(?![^>]*aria-label)(?![^>]*aria-labelledby)', "input"),
        (r'onClick=\{[^}]+\}(?![^>]*role=)', "clickable element"),
    ]

    a11y_violations = []
    for pattern, element in interactive_patterns:
        if re.search(pattern, content):
            a11y_violations.append(element)

    if a11y_violations:
        checks.append(TestCheck(
            name=f"{rel}:accessibility",
            category="accessibility",
            passed=False,
            description=f"Interactive elements missing aria attributes: {', '.join(set(a11y_violations))}",
        ))
    else:
        checks.append(TestCheck(
            name=f"{rel}:accessibility",
            category="accessibility",
            passed=True,
            description="Interactive elements have aria attributes",
        ))

    # Missing key prop in .map() lists
    map_without_key = re.search(
        r'\.map\([^)]*\)\s*=>\s*(?:\(?\s*<\w+(?![^>]*\bkey\b))',
        content,
    )
    checks.append(TestCheck(
        name=f"{rel}:list_key_prop",
        category="correctness",
        passed=map_without_key is None,
        description="List items from .map() missing key prop"
        if map_without_key
        else "List items have key props",
    ))

    # Inline styles instead of design tokens
    inline_style_count = len(re.findall(r'style=\{\{', content))
    checks.append(TestCheck(
        name=f"{rel}:no_inline_styles",
        category="style",
        passed=inline_style_count <= 2,  # Allow a couple for dynamic styles
        description=f"Found {inline_style_count} inline style objects — prefer design tokens/CSS"
        if inline_style_count > 2
        else "Minimal inline styles",
    ))

    # Sequential fetches (multiple await fetch without Promise.all)
    await_fetch_count = len(re.findall(r'await\s+fetch\(', content))
    has_promise_all = "Promise.all" in content or "Promise.allSettled" in content
    checks.append(TestCheck(
        name=f"{rel}:parallel_fetches",
        category="performance",
        passed=await_fetch_count <= 1 or has_promise_all,
        description=f"Found {await_fetch_count} sequential awaited fetches — use Promise.all"
        if await_fetch_count > 1 and not has_promise_all
        else "Fetches are parallel or single",
    ))

    return checks
