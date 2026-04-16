#!/usr/bin/env python3
"""Sweep all SKILL.md files to add task-monitor to composes.

Run:
    python .pi/skills/common/sweep_task_monitor.py --dry-run
    python .pi/skills/common/sweep_task_monitor.py
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parent.parent  # .pi/skills/

# Directories to skip (not real skills)
SKIP_DIRS = {"common", "consume_common", "__pycache__", "sanity", ".git"}


def add_task_monitor_to_skill(skill_md: Path, dry_run: bool) -> str:
    """Add task-monitor to composes in a SKILL.md file.

    Returns: 'added', 'already', 'no_frontmatter', 'added_composes'
    """
    text = skill_md.read_text()

    # Check for YAML frontmatter
    if not text.startswith("---"):
        return "no_frontmatter"

    # Split frontmatter from body
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "no_frontmatter"

    frontmatter = parts[1]
    body = parts[2]

    # Check if task-monitor already in composes
    if re.search(r"composes:.*task-monitor", frontmatter, re.DOTALL):
        return "already"

    # Check for composes list items
    composes_match = re.search(r"^composes:\s*$", frontmatter, re.MULTILINE)
    composes_inline = re.search(r"^composes:\s*\[", frontmatter, re.MULTILINE)

    if composes_match:
        # Multi-line composes — find the list and add task-monitor
        # Find position after "composes:" line and its list items
        lines = frontmatter.split("\n")
        new_lines = []
        in_composes = False
        added = False

        for line in lines:
            new_lines.append(line)
            if re.match(r"^composes:\s*$", line):
                in_composes = True
                continue
            if in_composes:
                if re.match(r"^\s+-\s+", line):
                    # Still in composes list
                    continue
                else:
                    # End of composes list — insert before this line
                    if not added:
                        new_lines.insert(-1, "  - task-monitor")
                        added = True
                    in_composes = False

        if in_composes and not added:
            # composes was at end of frontmatter
            new_lines.append("  - task-monitor")
            added = True

        if added:
            new_frontmatter = "\n".join(new_lines)
            new_text = f"---{new_frontmatter}---{body}"
            if not dry_run:
                skill_md.write_text(new_text)
            return "added"

    elif composes_inline:
        # Inline composes: [a, b, c] — add task-monitor
        def add_tm(m):
            content = m.group(0)
            # Insert before closing bracket
            return content.rstrip("]") + ", task-monitor]"

        new_frontmatter = re.sub(
            r"^(composes:\s*\[.*?)\]",
            lambda m: m.group(1) + ", task-monitor]",
            frontmatter,
            flags=re.MULTILINE,
        )
        new_text = f"---{new_frontmatter}---{body}"
        if not dry_run:
            skill_md.write_text(new_text)
        return "added"

    else:
        # No composes section — add one before the closing ---
        # Find a good place: after provides, or after metadata, or at end of frontmatter
        new_frontmatter = frontmatter.rstrip() + "\ncomposes:\n  - task-monitor\n"
        new_text = f"---{new_frontmatter}---{body}"
        if not dry_run:
            skill_md.write_text(new_text)
        return "added_composes"


def main():
    parser = argparse.ArgumentParser(description="Add task-monitor to all SKILL.md composes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results = {"added": 0, "already": 0, "no_frontmatter": 0, "added_composes": 0, "missing": 0}

    skill_dirs = sorted(
        d for d in SKILLS_ROOT.iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS
    )

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            results["missing"] += 1
            continue

        result = add_task_monitor_to_skill(skill_md, dry_run=args.dry_run)
        results[result] += 1

        if result in ("added", "added_composes"):
            action = "DRY" if args.dry_run else "UPDATED"
            print(f"  [{action}] {skill_dir.name}: {result}")

    print(f"\nSummary ({'DRY RUN' if args.dry_run else 'LIVE'}):")
    print(f"  Added task-monitor:    {results['added']}")
    print(f"  Added composes section: {results['added_composes']}")
    print(f"  Already had it:        {results['already']}")
    print(f"  No frontmatter:        {results['no_frontmatter']}")
    print(f"  No SKILL.md:           {results['missing']}")
    print(f"  Total dirs scanned:    {len(skill_dirs)}")


if __name__ == "__main__":
    main()
