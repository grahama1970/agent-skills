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


def _tracked_at_head() -> set[str]:
    """Files tracked at HEAD — so counts reflect the committed state, not a dirty
    working tree. This makes the generator deterministic: a local run and the CI
    run at the same commit produce identical counts (uncommitted/untracked files
    never inflate or deflate the numbers)."""
    out = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", "skills", "agents"],
        cwd=REPO, text=True,
    )
    return set(out.splitlines())


def main() -> None:
    tracked = _tracked_at_head()
    # top-level skills with a tracked SKILL.md; sanity = those with a tracked sanity.sh
    skill_names = sorted({
        f.split("/")[1] for f in tracked
        if f.startswith("skills/") and f.count("/") == 2 and f.endswith("/SKILL.md")
    })
    has_sanity = {
        f.split("/")[1] for f in tracked
        if f.startswith("skills/") and f.count("/") == 2 and f.endswith("/sanity.sh")
    }
    skills = []
    for name in skill_names:
        cat = next((p.rstrip("-") for p in PREFIXES if name.startswith(p)), "core")
        skills.append({"n": name, "c": cat, "s": name in has_sanity})
    if not skills:
        raise SystemExit("inventory generation failed: no skills found")
    # top-level, non-hidden agent directories tracked at HEAD.
    agents = len({
        f.split("/")[1] for f in tracked
        if f.startswith("agents/") and f.count("/") >= 2 and not f.split("/")[1].startswith(".")
    })
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
