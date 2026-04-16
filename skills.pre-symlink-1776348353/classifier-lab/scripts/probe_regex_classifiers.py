#!/usr/bin/env python3
"""Probe: Find regex doing classification work across the codebase.

Scans .pi/skills/ and .pi/extensions/ for patterns where regex/string
matching is doing what a trained classifier could do better.

Outputs JSON list of candidates with severity and suggested task.

Usage:
    python probe_regex_classifiers.py [--min-branches 5] [--json]
"""
import json
import re
import sys
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SCRIPT_DIR = Path(__file__).resolve().parent  # .pi/skills/classifier-lab/scripts/
SKILLS_DIR = SCRIPT_DIR.parent.parent         # .pi/skills/
PI_MONO = SKILLS_DIR.parent.parent            # pi-mono/
EXTENSIONS_DIR = PI_MONO / ".pi" / "extensions"


def count_trigger_lines(skill_md: Path) -> int:
    """Count trigger entries in a SKILL.md file."""
    text = skill_md.read_text()
    in_triggers = False
    count = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("triggers:"):
            in_triggers = True
            continue
        if in_triggers:
            if stripped.startswith("- "):
                count += 1
            elif stripped and not stripped.startswith("#"):
                break
    return count


def scan_for_regex_classification(file_path: Path) -> dict | None:
    """Check if a file uses regex/string matching for classification-like routing."""
    try:
        text = file_path.read_text(errors="ignore")
    except Exception:
        return None

    indicators = {
        "re_match": len(re.findall(r"re\.(match|search|findall|compile)", text)),
        "if_in_text": len(re.findall(r"if\s+.*\bin\b.*text|if\s+.*\.includes\(|if\s+.*\.startswith\(", text)),
        "elif_chains": len(re.findall(r"elif|else\s+if", text)),
        "pattern_match": len(re.findall(r"pattern|regex|match.*case|switch\s*\(", text)),
        "string_compare": len(re.findall(r'===?\s*["\']|\.lower\(\)\s*==|\.trim\(\)\s*===', text)),
    }

    total_indicators = sum(indicators.values())
    if total_indicators < 3:
        return None

    return {
        "file": str(file_path.relative_to(PI_MONO)),
        "indicators": indicators,
        "total_indicators": total_indicators,
    }


@app.command()
def scan(
    min_branches: int = typer.Option(5, help="Minimum regex/branch indicators to flag"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Scan for regex doing classification work."""
    candidates: list[dict] = []

    # ── Scan SKILL.md trigger lists ──────────────────────────
    logger.info("Scanning SKILL.md trigger lists...")
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        triggers = count_trigger_lines(skill_md)
        if triggers >= 5:
            candidates.append({
                "file": str(skill_md.relative_to(PI_MONO)),
                "type": "trigger-routing",
                "trigger_count": triggers,
                "severity": "high" if triggers >= 10 else "medium",
                "description": f"{skill_dir.name}: {triggers} trigger phrases — regex string matching for skill routing",
                "suggested_task": f"multi-label classifier for {skill_dir.name} skill invocation",
            })

    # ── Scan extension files ─────────────────────────────────
    logger.info("Scanning extensions...")
    if EXTENSIONS_DIR.exists():
        for ext_file in EXTENSIONS_DIR.glob("*.ts"):
            result = scan_for_regex_classification(ext_file)
            if result and result["total_indicators"] >= min_branches:
                candidates.append({
                    **result,
                    "type": "extension-routing",
                    "severity": "high" if result["total_indicators"] >= 10 else "medium",
                    "description": f"{ext_file.name}: {result['total_indicators']} routing indicators — pattern matching for classification",
                    "suggested_task": f"classifier to replace regex routing in {ext_file.name}",
                })

    # ── Scan Python files for if/elif classification chains ──
    logger.info("Scanning Python files for classification patterns...")
    skip_patterns = {"__pycache__", ".venv", "node_modules", "unsloth_compiled_cache", ".worktrees", "dist", "build", ".data", ".artifacts", "tmp"}
    for py_file in SKILLS_DIR.rglob("*.py"):
        path_str = str(py_file)
        if any(s in path_str for s in skip_patterns):
            continue
        # Skip files > 500 lines (likely libraries, not routing logic)
        try:
            line_count = len(py_file.read_text(errors="ignore").split("\n"))
            if line_count > 500:
                continue
        except Exception:
            continue
        result = scan_for_regex_classification(py_file)
        if result and result["total_indicators"] >= min_branches:
            candidates.append({
                **result,
                "type": "python-classification",
                "severity": "high" if result["total_indicators"] >= 15 else "medium",
                "description": f"{py_file.name}: {result['total_indicators']} classification indicators",
                "suggested_task": f"classifier for routing logic in {py_file.name}",
            })

    # Filter: only show trigger-routing and extension-routing by default
    # Python file hits are too noisy — regex in code != classification routing
    actionable = [c for c in candidates if c["type"] in ("trigger-routing", "extension-routing")]
    python_hits = [c for c in candidates if c["type"] == "python-classification"]

    # Sort by severity and indicator count
    actionable.sort(key=lambda c: (-1 if c["severity"] == "high" else 0, -c.get("total_indicators", c.get("trigger_count", 0))))
    candidates = actionable  # only show actionable by default

    logger.info(f"\nFound {len(candidates)} candidates")

    if output_json:
        print(json.dumps(candidates, indent=2))
    else:
        for c in candidates:
            sev = "🔴" if c["severity"] == "high" else "🟡"
            print(f"{sev} {c['description']}")
            print(f"   File: {c['file']}")
            print(f"   Suggested: {c['suggested_task']}")
            print()

    return candidates


if __name__ == "__main__":
    app()
