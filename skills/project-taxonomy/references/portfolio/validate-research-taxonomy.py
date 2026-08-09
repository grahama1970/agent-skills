#!/usr/bin/env python3
"""Validate the high-level invariants in research-taxonomy.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "research-taxonomy.json")
data = json.loads(path.read_text(encoding="utf-8"))

area_ids = {item["id"] for item in data["areas"]}
family_ids = {item["id"] for item in data["families"]}
errors = []

for project in data["projects"]:
    repo = project["repository"]
    primary = project.get("primary_area")
    secondary = project.get("secondary_area")
    family = project.get("program_family")
    count = project["counting_status"].startswith("count")

    if primary is not None and primary not in area_ids:
        errors.append(f"{repo}: unknown primary_area {primary!r}")
    if secondary is not None and secondary not in area_ids:
        errors.append(f"{repo}: unknown secondary_area {secondary!r}")
    if primary and secondary and primary == secondary:
        errors.append(f"{repo}: primary and secondary areas must differ")
    if family is not None and family not in family_ids:
        errors.append(f"{repo}: unknown program_family {family!r}")
    if count and not primary:
        errors.append(f"{repo}: counted research line requires primary_area")
    if count and not family:
        errors.append(f"{repo}: counted research line requires program_family")
    if len(project.get("methods", [])) > 8:
        errors.append(f"{repo}: more than 8 methods")
    if len(project.get("boundary_to_preserve", "").strip()) < 20:
        errors.append(f"{repo}: missing substantive boundary_to_preserve")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)

print(
    f"PASS: {len(data['projects'])} projects, "
    f"{len(area_ids)} areas, {len(family_ids)} families"
)
