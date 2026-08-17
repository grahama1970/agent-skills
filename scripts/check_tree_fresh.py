"""Fail when the working tree is a stale snapshot of committed code.

The recurring failure this catches: a lane writes old file versions over the
checkout, so the working tree silently DELETES files that exist in HEAD and
reverts others to a days-old state. Everything built on top of that tree is
built on code that is not `main`, and every "live proof" run against it proves
nothing. Observed 2026-08-05 (48 paths, Aug 3 baseline over Aug 4 commits) and
again 2026-08-17 (73 paths, 24 files deleted from skills/monitor-opportunities,
including github_repo_intelligence.py, tau_semantic_prepare.py, and
report_acceptance.py).

The signature is cheap to detect and expensive to miss:

  * a tracked file present in HEAD but absent from the working tree, and
  * a large one-sided deletion in a skill directory.

Run before working in a skill, or at session start over the whole repo:

    python3 scripts/check_tree_fresh.py
    python3 scripts/check_tree_fresh.py --path skills/monitor-opportunities

Exit 1 on missing files, exit 0 otherwise (large deletions warn but do not
fail, because a deliberate deletion commit-in-progress looks the same).
"""

from __future__ import annotations

import argparse
import collections
import subprocess
import sys

DELETION_WARN_LINES = 400


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.stdout


def branch_state() -> str:
    branch = git("branch", "--show-current").strip() or "(detached)"
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    if not upstream:
        return f"branch {branch} (no upstream)"
    ahead = git("rev-list", "--count", f"{upstream}..HEAD").strip() or "?"
    behind = git("rev-list", "--count", f"HEAD..{upstream}").strip() or "?"
    return f"branch {branch}, {ahead} ahead / {behind} behind {upstream}"


def group(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if parts[0] == "skills" and len(parts) > 2 else parts[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=None, help="limit the check to one path")
    args = parser.parse_args()

    scope = ["--", args.path] if args.path else []
    name_status = git("diff", "--name-status", "HEAD", *scope).strip()
    numstat = git("diff", "--numstat", "HEAD", *scope).strip()

    missing: list[str] = []
    for line in name_status.split("\n"):
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        if status.startswith("D"):
            missing.append(path.strip())

    removed_by_group: dict[str, int] = collections.defaultdict(int)
    for line in numstat.split("\n"):
        if not line.strip():
            continue
        added, removed, path = (line.split("\t") + ["", "", ""])[:3]
        if removed.isdigit():
            removed_by_group[group(path)] += int(removed)

    print(f"tree freshness: {branch_state()}")

    if missing:
        by_group: dict[str, list[str]] = collections.defaultdict(list)
        for path in missing:
            by_group[group(path)].append(path)
        print(
            f"STALE TREE: {len(missing)} tracked file(s) exist in HEAD but are missing "
            "from the working tree. Code here is NOT what is committed; do not build, "
            "test, or claim proof against it."
        )
        for name, paths in sorted(by_group.items()):
            print(f"  {name}: {len(paths)} missing")
            for path in sorted(paths)[:10]:
                print(f"    - {path}")
            if len(paths) > 10:
                print(f"    ... and {len(paths) - 10} more")
        print("Recover with: git diff HEAD -- <path> > backup.patch && git checkout HEAD -- <path>")
        return 1

    heavy = {name: n for name, n in removed_by_group.items() if n >= DELETION_WARN_LINES}
    for name, n in sorted(heavy.items(), key=lambda kv: -kv[1]):
        print(f"WARNING: {name} removes {n} committed lines in the working tree; confirm this is intentional")

    if not name_status:
        print("OK: working tree matches HEAD for the checked path")
    elif not heavy:
        print("OK: no committed file is missing from the working tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
