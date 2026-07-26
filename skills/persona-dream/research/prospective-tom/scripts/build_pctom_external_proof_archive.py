#!/usr/bin/env python3
"""Ingest the /tmp proof roots cited by GOAL.md into a durable in-repo archive.

GOAL.md hash-cites receipts that live under /tmp. `/tmp` is configured with
`D /tmp 1777 root root 30d`, so those paths are removed on boot and aged out
after 30 days. This script copies the cited receipts and their sibling
artifacts into the research namespace and records a hash-bound manifest so the
citations survive.

Inputs:  GOAL.md (source of cited paths), the cited /tmp paths themselves.
Outputs: evidence/external-proof-archive/<root>/... copies, plus one manifest.
Failures: a cited path that no longer exists is recorded as a missing entry;
          it is never silently dropped.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import (
    ROOT_DEFAULT,
    SCHEMA_PREFIX,
    file_sha256,
    now_iso,
    stable_json_sha256,
    write_json,
)

CITATION_RE = re.compile(r"/tmp/persona-dream-[A-Za-z0-9._/\-]*")
ARCHIVE_REL = "evidence/external-proof-archive"
MANIFEST_REL = "evidence/pctom-external-proof-archive.v1.json"
TOPLEVEL_BUCKET = "_toplevel"
DEFAULT_DEPTH = 2
SKIP_DIRS = {".venv", "site-packages", "node_modules", "__pycache__", ".git"}


def cited_paths(goal_md: Path) -> list[str]:
    """Distinct /tmp citations in GOAL.md, longest-first so prefixes collapse."""
    raw = {match.rstrip(".,;:") for match in CITATION_RE.findall(goal_md.read_text(encoding="utf-8"))}
    return sorted(p for p in raw if len(p) > len("/tmp/persona-dream-"))


def collect_files(source: str, depth: int) -> list[Path]:
    """Artifacts for one citation: the file itself, or a filtered walk.

    Two rules, because a depth bound alone gets this wrong in both directions:

    - Every ``.json`` is taken at any depth. Aggregate receipts reference
      per-case receipts (``gate5_scoring_receipt.json`` and friends) that sit
      three or more levels down; a depth-2 cut silently dropped 14357 of them.
    - Other file types are taken only above ``depth``, which keeps the shallow
      stdout/txt/cfg captures without pulling in generated media and binaries.

    ``SKIP_DIRS``, plus any directory holding a ``pyvenv.cfg``, removes vendored
    and virtualenv trees: regenerable, not evidence, and uv writes a ``*``
    ``.gitignore`` inside them that would keep them out of the commit anyway.
    """
    path = Path(source)
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    base = str(path).rstrip("/").count(os.sep)
    found: list[Path] = []
    for current, dirs, files in os.walk(path):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS and not (Path(current) / d / "pyvenv.cfg").exists()
        ]
        shallow = current.count(os.sep) - base < depth
        found.extend(Path(current) / f for f in files if shallow or f.endswith(".json"))
    return sorted(found)


def proof_root(source: str) -> tuple[Path, str]:
    """The /tmp/persona-dream-* directory a citation belongs to.

    Keying the bucket on the immediate parent collides: many roots carry the
    same generic subdirectory names (output/, coverage/, success/), so distinct
    runs would overwrite each other in one bucket.

    Returns (root to relativise against, bucket name). A citation that is a bare
    file directly under /tmp has no proof-root directory of its own, so it goes
    into one flat bucket rather than producing a self-named empty path.
    """
    parts = Path(source).parts
    if len(parts) < 3 or parts[1] != "tmp":
        raise ValueError(f"unexpected_citation_shape:{source}")
    root = Path(parts[0]) / parts[1] / parts[2]
    if root.is_dir():
        return root, root.name
    return root.parent, TOPLEVEL_BUCKET


def build(root: Path, goal_md: Path, depth: int) -> dict[str, Any]:
    archive_root = root / ARCHIVE_REL
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    copied_files = 0
    copied_bytes = 0

    for source in cited_paths(goal_md):
        if not Path(source).exists():
            missing.append(source)
            continue
        found = collect_files(source, depth)
        if not found:
            # Path exists but carries no file at this depth.
            entries.append({"source": source, "file_count": 0, "files": []})
            continue

        src_root, bucket_name = proof_root(source)
        bucket = archive_root / bucket_name
        files: list[dict[str, Any]] = []
        for item in found:
            relative = item.relative_to(src_root)
            target = bucket / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            digest = file_sha256(target)
            if digest != file_sha256(item):  # copy integrity, not a trust claim
                raise RuntimeError(f"copy_digest_mismatch:{item}")
            size = target.stat().st_size
            copied_files += 1
            copied_bytes += size
            files.append({
                "path": f"{ARCHIVE_REL}/{bucket_name}/{relative.as_posix()}",
                "sha256": digest,
                "size_bytes": size,
            })
        entries.append({"source": source, "file_count": len(files), "files": files})

    entries.sort(key=lambda row: row["source"])
    manifest = {
        "schema": f"{SCHEMA_PREFIX}.pctom_external_proof_archive.v1",
        "created_at": now_iso(),
        "root": str(ROOT_DEFAULT),
        "status": "EXTERNAL_PROOF_ARCHIVE_BUILT" if not missing else "EXTERNAL_PROOF_ARCHIVE_INCOMPLETE",
        "goal_md": str(goal_md),
        "goal_md_sha256": file_sha256(goal_md),
        "dir_walk_depth": depth,
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "missing_sources": sorted(missing),
        "entries": entries,
        "counts": {
            "cited_sources": len(entries) + len(missing),
            "archived_sources": len(entries),
            "missing_sources": len(missing),
            "files": copied_files,
            "bytes": copied_bytes,
        },
        "claims": {
            "proves": [
                "the files cited by GOAL.md were readable at archive time",
                "each archived copy matches its source digest byte-for-byte",
                "the archive is inside the repository and no longer depends on /tmp retention",
            ],
            "does_not_prove": [
                "the correctness of any archived receipt's own claims",
                "that artifacts deeper than dir_walk_depth were preserved",
                "live re-execution of any archived run",
            ],
        },
    }
    manifest["entries_sha256"] = stable_json_sha256(entries)
    write_json(root / MANIFEST_REL, manifest)
    return manifest


def verify(root: Path) -> dict[str, Any]:
    """Re-read every archived copy and confirm it still matches the manifest."""
    manifest_path = root / MANIFEST_REL
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked = 0
    for entry in manifest["entries"]:
        for row in entry["files"]:
            target = root / row["path"]
            if not target.exists():
                errors.append(f"missing_archived_file:{row['path']}")
                continue
            if file_sha256(target) != row["sha256"]:
                errors.append(f"archived_file_sha256_mismatch:{row['path']}")
            checked += 1
    if stable_json_sha256(manifest["entries"]) != manifest["entries_sha256"]:
        errors.append("entries_sha256_mismatch")
    return {
        "schema": f"{SCHEMA_PREFIX}.pctom_external_proof_archive_audit.v1",
        "created_at": now_iso(),
        "status": "PASS_EXTERNAL_PROOF_ARCHIVE" if not errors else "BLOCKED_EXTERNAL_PROOF_ARCHIVE",
        "manifest_sha256": file_sha256(manifest_path),
        "files_checked": checked,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive GOAL.md-cited /tmp proof receipts into the repo.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--goal", type=Path, default=Path("skills/persona-dream/GOAL.md"))
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--verify", action="store_true", help="audit an existing archive instead of building")
    args = parser.parse_args()

    result = verify(args.root) if args.verify else build(args.root, args.goal, args.depth)
    print(json.dumps(result if args.verify else {k: v for k, v in result.items() if k != "entries"}, indent=2, sort_keys=True))
    return 1 if str(result["status"]).startswith("BLOCKED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
