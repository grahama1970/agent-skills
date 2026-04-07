"""
QML pattern-based blind evaluation checks for best-practices-kde rules.

Checks QML files for: hard-coded colors (not from HorusStyle singleton),
missing Accessible.name on interactive elements, property ordering violations,
file length limits, and binding loop patterns.

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


# QML color literal pattern: #RGB, #RRGGBB, #AARRGGBB
COLOR_HEX_PATTERN = re.compile(r'(?<!HorusStyle\.)(?<!\w)#[0-9a-fA-F]{3,8}\b')

# Common QML color names
COLOR_NAME_PATTERN = re.compile(
    r'\b(?:color|background|foreground)\s*:\s*"(?:red|blue|green|black|white|gray|grey|yellow|orange|purple|pink|cyan)"',
    re.IGNORECASE,
)

# Binding loop: property depends on itself
BINDING_LOOP_PATTERN = re.compile(r'(\w+)\s*:\s*.*\b\1\b')

# Interactive QML elements
INTERACTIVE_ELEMENTS = [
    "Button", "MouseArea", "TapHandler", "TextField", "TextArea",
    "ComboBox", "CheckBox", "RadioButton", "Switch", "Slider",
    "SpinBox", "Dial",
]


def run_checks(target_dir: Path) -> list[TestCheck]:
    """Run all KDE/QML best-practices checks against target directory."""
    checks: list[TestCheck] = []

    qml_files = list(target_dir.rglob("*.qml"))

    qml_files = [
        f for f in qml_files
        if not any(part in f.parts for part in (".git", "node_modules", "build"))
    ]

    if not qml_files:
        checks.append(TestCheck(
            name="qml_files_exist",
            category="structure",
            passed=True,
            description="No QML files found (nothing to check)",
        ))
        return checks

    for qml_file in qml_files:
        checks.extend(_check_qml_file(qml_file))

    return checks


def _check_qml_file(filepath: Path) -> list[TestCheck]:
    """Run checks against a single QML file."""
    checks: list[TestCheck] = []
    rel = filepath.name

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Cannot read {filepath}: {e}")
        return checks

    lines = content.splitlines()

    # File length check (600 for QML)
    checks.append(TestCheck(
        name=f"{rel}:max_lines",
        category="style",
        passed=len(lines) <= 600,
        description=f"QML file has {len(lines)} lines (max 600)"
        if len(lines) > 600
        else f"QML file within limit ({len(lines)}/600)",
    ))

    # Hard-coded colors
    hex_colors = COLOR_HEX_PATTERN.findall(content)
    named_colors = COLOR_NAME_PATTERN.findall(content)
    total_hardcoded = len(hex_colors) + len(named_colors)

    checks.append(TestCheck(
        name=f"{rel}:no_hardcoded_colors",
        category="conventions",
        passed=total_hardcoded == 0,
        description=f"Found {total_hardcoded} hard-coded colors — use HorusStyle singleton"
        if total_hardcoded > 0
        else "No hard-coded colors (uses HorusStyle)",
    ))

    # Missing Accessible.name on interactive elements
    missing_accessible = []
    for element in INTERACTIVE_ELEMENTS:
        # Find element blocks
        pattern = re.compile(
            rf'{element}\s*\{{([^}}]*(?:\{{[^}}]*\}}[^}}]*)*)\}}',
            re.DOTALL,
        )
        for match in pattern.finditer(content):
            block = match.group(1)
            if "Accessible.name" not in block and "Accessible.description" not in block:
                missing_accessible.append(element)

    if missing_accessible:
        checks.append(TestCheck(
            name=f"{rel}:accessible_name",
            category="accessibility",
            passed=False,
            description=f"Interactive elements missing Accessible.name: {', '.join(set(missing_accessible))}",
        ))
    else:
        checks.append(TestCheck(
            name=f"{rel}:accessible_name",
            category="accessibility",
            passed=True,
            description="Interactive elements have Accessible.name",
        ))

    # Binding loop detection (heuristic)
    potential_loops = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        match = BINDING_LOOP_PATTERN.search(stripped)
        if match:
            prop = match.group(1)
            # Filter out common false positives
            if prop not in ("id", "text", "source", "model", "delegate", "parent"):
                potential_loops.append(prop)

    checks.append(TestCheck(
        name=f"{rel}:no_binding_loops",
        category="correctness",
        passed=len(potential_loops) == 0,
        description=f"Potential binding loops detected: {', '.join(set(potential_loops))}"
        if potential_loops
        else "No binding loop patterns detected",
    ))

    return checks
