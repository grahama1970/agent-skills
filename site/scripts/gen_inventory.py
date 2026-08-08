#!/usr/bin/env python3
"""Regenerate site/inventory.json from the real repo state.

Every number and cell the site renders comes from this file, stamped with
the source commit. Run from anywhere; writes site/inventory.json. The site
must never display an inventory figure that this generator did not emit.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PREFIXES = (
    "monitor-", "create-", "best-practices-", "ops-", "review-", "ingest-",
    "consume-", "learn-", "discover-", "extract-", "train-", "tts-",
)


def main() -> None:
    skills = []
    for d in sorted((REPO / "skills").iterdir()):
        if d.is_dir() and (d / "SKILL.md").exists():
            cat = next((p.rstrip("-") for p in PREFIXES if d.name.startswith(p)), "core")
            skills.append({"n": d.name, "c": cat, "s": (d / "sanity.sh").exists()})
    if not skills:
        raise SystemExit("inventory generation failed: no skills found")
    # Exclude hidden dirs (e.g. .ask) so the public count matches visible agents,
    # the same way skills are counted above.
    agents = sum(
        1 for d in (REPO / "agents").iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()
    as_of = subprocess.check_output(
        ["git", "show", "-s", "--format=%cs", "HEAD"], cwd=REPO, text=True
    ).strip()
    inventory = {
        "commit": commit,
        "as_of": as_of,
        "generator": "site/scripts/gen_inventory.py",
        "stats": {
            "skills": len(skills),
            "sanity": sum(1 for s in skills if s["s"]),
            "agents": agents,
        },
        "skills": skills,
    }
    out = REPO / "site" / "inventory.json"
    out.write_text(json.dumps(inventory, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(inventory["stats"]), commit, as_of)


if __name__ == "__main__":
    main()
