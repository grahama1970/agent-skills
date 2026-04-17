#!/usr/bin/env python3
"""Apply approved corrections to skill misuse_guard.py files.

Reads from misuse_corrections collection (status=approved),
updates the skill's COLLECTION_CORRECTIONS dict, marks as applied.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import httpx

from skill_registry import get_skill_guard, SKILL_GUARDS


MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"


def get_memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)


def fetch_approved_corrections(client: httpx.Client, skill: str | None = None) -> list[dict]:
    """Fetch approved corrections ready to apply."""
    resp = client.post("/list", json={
        "collection": "misuse_corrections",
        "limit": 100,
        "filters": {"status": "approved"} if not skill else {"status": "approved", "skill": skill},
    })

    if resp.status_code != 200:
        print(f"Failed to fetch corrections: {resp.status_code}")
        return []

    return resp.json().get("documents", [])


def parse_corrections_dict(content: str, var_name: str = "COLLECTION_CORRECTIONS") -> tuple[int, int, dict]:
    """Parse the corrections dict from a misuse_guard.py file.

    Returns (start_line, end_line, current_corrections).
    """
    lines = content.split("\n")
    in_dict = False
    start_line = -1
    brace_depth = 0
    dict_lines = []

    for i, line in enumerate(lines):
        if f"{var_name} = {{" in line or f"{var_name} = {{\n" in line.rstrip():
            in_dict = True
            start_line = i
            brace_depth = line.count("{") - line.count("}")
            dict_lines.append(line)
            if brace_depth == 0:
                # Single-line dict
                break
            continue

        if in_dict:
            brace_depth += line.count("{") - line.count("}")
            dict_lines.append(line)
            if brace_depth <= 0:
                break

    if start_line == -1:
        return -1, -1, {}

    end_line = start_line + len(dict_lines) - 1

    # Parse the dict content
    dict_str = "\n".join(dict_lines)
    # Extract just the dict part
    match = re.search(r"\{([^}]*)\}", dict_str, re.DOTALL)
    if not match:
        return start_line, end_line, {}

    # Parse key-value pairs
    corrections = {}
    for line in match.group(1).split("\n"):
        # Match: "key": "value",
        m = re.match(r'\s*["\']([^"\']+)["\']\s*:\s*["\']([^"\']+)["\']', line)
        if m:
            corrections[m.group(1)] = m.group(2)

    return start_line, end_line, corrections


def generate_corrections_dict(corrections: dict, var_name: str = "COLLECTION_CORRECTIONS") -> str:
    """Generate the Python code for a corrections dict."""
    lines = [f"{var_name} = {{"]

    # Group by correction type for readability
    grouped: dict[str, list[tuple[str, str]]] = {}
    for wrong, correct in sorted(corrections.items()):
        # Infer group from pattern
        if wrong.endswith("s") and not correct.endswith("s"):
            group = "Plural → singular"
        elif not wrong.endswith("s") and correct.endswith("s"):
            group = "Singular → plural"
        elif "lesson" in wrong.lower():
            group = "Lessons"
        else:
            group = "Typos/other"

        if group not in grouped:
            grouped[group] = []
        grouped[group].append((wrong, correct))

    for group, pairs in grouped.items():
        lines.append(f"    # {group}")
        for wrong, correct in pairs:
            lines.append(f'    "{wrong}": "{correct}",')

    lines.append("}")
    return "\n".join(lines)


def apply_correction_to_file(
    guard_path: Path,
    new_corrections: dict[str, str],
    var_name: str = "COLLECTION_CORRECTIONS",
) -> bool:
    """Add new corrections to a misuse_guard.py file."""
    if not guard_path.exists():
        print(f"  Guard file not found: {guard_path}")
        return False

    content = guard_path.read_text()
    start_line, end_line, existing = parse_corrections_dict(content, var_name)

    if start_line == -1:
        print(f"  Could not find {var_name} in {guard_path}")
        return False

    # Merge corrections
    merged = {**existing, **new_corrections}

    if merged == existing:
        print(f"  No new corrections to add")
        return True

    # Generate new dict
    new_dict = generate_corrections_dict(merged, var_name)

    # Replace in file
    lines = content.split("\n")
    new_content = "\n".join(lines[:start_line]) + "\n" + new_dict + "\n" + "\n".join(lines[end_line + 1:])

    guard_path.write_text(new_content)
    print(f"  Updated {guard_path}")
    print(f"  Added {len(new_corrections)} new corrections ({len(existing)} → {len(merged)})")

    return True


def mark_as_applied(client: httpx.Client, keys: list[str]) -> None:
    """Mark corrections as applied in the database."""
    for key in keys:
        resp = client.post("/store", json={
            "document": {
                "_key": key,
                "status": "applied",
                "applied_at": int(time.time()),
            },
            "collection": "misuse_corrections",
        })
        if resp.status_code != 200:
            print(f"  Failed to mark {key} as applied")


def main():
    parser = argparse.ArgumentParser(description="Apply approved corrections")
    parser.add_argument("--skill", help="Apply only to specific skill")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied")
    args = parser.parse_args()

    client = get_memory_client()
    corrections = fetch_approved_corrections(client, args.skill)

    if not corrections:
        print("No approved corrections to apply")
        return

    # Group by skill
    by_skill: dict[str, list[dict]] = {}
    for c in corrections:
        skill = c.get("skill", "unknown")
        if skill not in by_skill:
            by_skill[skill] = []
        by_skill[skill].append(c)

    print(f"Found {len(corrections)} approved corrections across {len(by_skill)} skills\n")

    for skill, skill_corrections in by_skill.items():
        print(f"Skill: {skill} ({len(skill_corrections)} corrections)")

        guard = get_skill_guard(skill)
        if not guard:
            print(f"  No registered guard for skill '{skill}' - skipping")
            print(f"  Add to skill_registry.py to enable auto-apply")
            continue

        # Build corrections dict
        new_corrections = {}
        keys = []
        for c in skill_corrections:
            sent = c.get("sent_value", "")
            proposed = c.get("proposed_correction", "")
            if sent and proposed:
                new_corrections[sent] = proposed
                keys.append(c["_key"])
                print(f"  {sent} → {proposed}")

        if args.dry_run:
            print(f"  [DRY RUN] Would apply {len(new_corrections)} corrections")
            continue

        # Apply to file
        if apply_correction_to_file(guard.guard_path, new_corrections, guard.corrections_var):
            mark_as_applied(client, keys)
        print()


if __name__ == "__main__":
    main()
