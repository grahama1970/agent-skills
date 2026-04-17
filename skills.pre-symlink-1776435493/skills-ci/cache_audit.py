"""Detect and repair corrupted Python files in uv cache and site-packages.

The corruption signature is: third-party packages modified by skills-ci autofix
rules — specifically `import logging` → `from loguru import logger` and
injected "Auto-generated module docstring" docstrings.

Usage:
    python cache_audit.py scan                    # detect corruption
    python cache_audit.py scan --json             # machine-readable output
    python cache_audit.py fix                     # delete corrupted cache dirs
    python cache_audit.py fix --dry-run           # show what would be deleted
"""
from __future__ import annotations

import json
from loguru import logger
import os
import shutil
import sys
from pathlib import Path

# NOTE: We use stdlib logging here, NOT loguru. This module must work even when
# loguru itself is corrupted (which is the exact scenario it diagnoses).

logging.basicConfig(level=logging.INFO, format="%(message)s")

# ── Corruption signatures ────────────────────────────────────────────────────
# These patterns should NEVER appear in third-party packages. Their presence
# means an autofix agent rewrote the file.

CORRUPTION_SIGNATURES = [
    b"Auto-generated module docstring",  # injected by skills-ci insert_module_docstring
]

# Loguru import is only a corruption signal in packages that should NEVER use loguru.
# We check for it separately, excluding loguru's own source and packages that
# legitimately depend on loguru (e.g. sentry_sdk has loguru integration).
LOGURU_IMPORT = b"from loguru import logger"
LOGURU_LEGITIMATE_PACKAGES = {"loguru", "sentry_sdk"}

# Dirs to scan for corruption
CACHE_ROOTS = [
    Path.home() / ".cache" / "uv" / "archive-v0",
    Path.home() / ".cache" / "uv" / "wheels-v4",
]

# Also scan all .venv/lib/*/site-packages across known project dirs
WORKSPACE_ROOTS = [
    Path.home() / "workspace" / "experiments",
]

SKIP_DIRS = {"__pycache__", ".git", "node_modules"}


def _find_site_packages() -> list[Path]:
    """Find all site-packages dirs in workspace venvs."""
    results = []
    for root in WORKSPACE_ROOTS:
        if not root.exists():
            continue
        for venv_dir in root.rglob(".venv"):
            if not venv_dir.is_dir():
                continue
            for sp in venv_dir.rglob("site-packages"):
                if sp.is_dir():
                    results.append(sp)
    return results


def _is_corrupted(path: Path) -> list[str]:
    """Check if a file contains corruption signatures. Returns matching signatures."""
    try:
        content = path.read_bytes()
    except (OSError, PermissionError):
        return []
    matches = []
    for sig in CORRUPTION_SIGNATURES:
        if sig in content:
            matches.append(sig.decode())
    # Check loguru import only in packages that should never use loguru
    if LOGURU_IMPORT in content:
        # Determine the package name from the path
        parts = path.parts
        pkg_name = None
        for i, part in enumerate(parts):
            if part == "site-packages" and i + 1 < len(parts):
                pkg_name = parts[i + 1].split("-")[0].lower()
                break
            if part == "archive-v0" and i + 1 < len(parts):
                pkg_name = parts[i + 1]
                break
        if pkg_name and pkg_name not in LOGURU_LEGITIMATE_PACKAGES:
            matches.append(LOGURU_IMPORT.decode())
    return matches


def scan_cache(json_output: bool = False) -> dict:
    """Scan uv cache and site-packages for corrupted files.

    Returns a dict with corruption details.
    """
    corrupted_dirs: dict[str, dict] = {}
    corrupted_files: list[dict] = []
    total_scanned = 0

    # Scan uv cache archive dirs
    for cache_root in CACHE_ROOTS:
        if not cache_root.exists():
            logger.info("Cache root not found: %s", cache_root)
            continue
        logger.info("Scanning %s", cache_root)
        for pyfile in cache_root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in pyfile.parts):
                continue
            total_scanned += 1
            matches = _is_corrupted(pyfile)
            if matches:
                # Identify the package dir (first child of cache_root)
                try:
                    rel = pyfile.relative_to(cache_root)
                    package_dir = cache_root / rel.parts[0]
                except (ValueError, IndexError):
                    package_dir = pyfile.parent

                pkg_key = str(package_dir)
                if pkg_key not in corrupted_dirs:
                    corrupted_dirs[pkg_key] = {
                        "path": pkg_key,
                        "package": rel.parts[0] if len(rel.parts) > 0 else "unknown",
                        "corrupted_files": 0,
                        "signatures": set(),
                    }
                corrupted_dirs[pkg_key]["corrupted_files"] += 1
                corrupted_dirs[pkg_key]["signatures"].update(matches)

                corrupted_files.append({
                    "file": str(pyfile),
                    "package_dir": pkg_key,
                    "signatures": matches,
                })

    # Scan site-packages
    for sp_dir in _find_site_packages():
        logger.info("Scanning %s", sp_dir)
        for pyfile in sp_dir.rglob("*.py"):
            if any(part in SKIP_DIRS for part in pyfile.parts):
                continue
            total_scanned += 1
            matches = _is_corrupted(pyfile)
            if matches:
                # Package dir is the first-level child of site-packages
                try:
                    rel = pyfile.relative_to(sp_dir)
                    package_name = rel.parts[0] if rel.parts else "unknown"
                except ValueError:
                    package_name = "unknown"

                pkg_key = str(sp_dir / package_name)
                if pkg_key not in corrupted_dirs:
                    corrupted_dirs[pkg_key] = {
                        "path": pkg_key,
                        "package": package_name,
                        "corrupted_files": 0,
                        "signatures": set(),
                    }
                corrupted_dirs[pkg_key]["corrupted_files"] += 1
                corrupted_dirs[pkg_key]["signatures"].update(matches)

                corrupted_files.append({
                    "file": str(pyfile),
                    "package_dir": pkg_key,
                    "signatures": matches,
                })

    # Convert sets to lists for JSON serialization
    for d in corrupted_dirs.values():
        d["signatures"] = sorted(d["signatures"])

    result = {
        "total_scanned": total_scanned,
        "corrupted_dirs": len(corrupted_dirs),
        "corrupted_files": len(corrupted_files),
        "dirs": sorted(corrupted_dirs.values(), key=lambda x: -x["corrupted_files"]),
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if not corrupted_dirs:
            print(f"CLEAN: Scanned {total_scanned} files, no corruption found")
        else:
            print(f"CORRUPTED: {len(corrupted_dirs)} dirs, {len(corrupted_files)} files "
                  f"(scanned {total_scanned})")
            print()
            print(f"{'Package':40s}  {'Files':>6s}  Signatures")
            print("-" * 80)
            for d in result["dirs"][:30]:
                sigs = ", ".join(s[:30] for s in d["signatures"])
                print(f"{d['package']:40s}  {d['corrupted_files']:>6d}  {sigs}")

    return result


def _find_venv_root(path: Path) -> Path | None:
    """Walk up from a path to find the .venv* ancestor dir."""
    for parent in path.parents:
        if parent.name.startswith(".venv"):
            return parent
    return None


def fix_cache(dry_run: bool = False) -> dict:
    """Nuke corrupted uv cache and rebuild corrupted venvs.

    Strategy:
    - uv cache: purge entirely (uv cache clean)
    - venvs: delete the ENTIRE .venv* dir (not individual packages), then uv sync
      Deleting individual package dirs leaves the venv in a broken partial state.
    """
    scan_result = scan_cache(json_output=False)

    if scan_result["corrupted_dirs"] == 0:
        print("\nNothing to fix")
        return scan_result

    # Collect unique venv roots and cache dirs
    venv_roots: set[Path] = set()
    cache_dirs: set[Path] = set()

    for d in scan_result["dirs"]:
        path = Path(d["path"])
        if ".cache/uv" in d["path"]:
            cache_dirs.add(path)
        else:
            venv_root = _find_venv_root(path)
            if venv_root:
                venv_roots.add(venv_root)

    print(f"\n{'DRY RUN: ' if dry_run else ''}Fixing {len(cache_dirs)} cache dirs, "
          f"{len(venv_roots)} corrupted venvs")

    # Fix 1: Purge uv cache entirely
    deleted_cache = 0
    if cache_dirs:
        print(f"\n--- UV Cache ({len(cache_dirs)} corrupted dirs) ---")
        print("  Purging entire uv cache (uv cache clean)")
        if not dry_run:
            import subprocess
            subprocess.run(["uv", "cache", "clean"], capture_output=True)
            deleted_cache = len(cache_dirs)

    # Fix 2: Delete entire corrupted venvs and rebuild
    deleted_venvs = 0
    rebuilt = 0
    rebuild_failed = 0
    if venv_roots:
        print(f"\n--- Corrupted venvs ({len(venv_roots)}) ---")
        for venv in sorted(venv_roots):
            skill_dir = venv.parent
            has_pyproject = (skill_dir / "pyproject.toml").exists()
            print(f"  {'[DRY] ' if dry_run else ''}rm -rf {venv}"
                  f"{' → uv sync' if has_pyproject else ''}")
            if not dry_run:
                shutil.rmtree(venv, ignore_errors=True)
                deleted_venvs += 1
                if has_pyproject:
                    import subprocess
                    result = subprocess.run(
                        ["uv", "sync"],
                        cwd=str(skill_dir),
                        capture_output=True,
                        timeout=120,
                    )
                    if result.returncode == 0:
                        rebuilt += 1
                    else:
                        rebuild_failed += 1
                        print(f"    REBUILD FAILED: {skill_dir.name}")

    if not dry_run:
        print(f"\nDeleted {deleted_cache} cache dirs, "
              f"{deleted_venvs} venvs ({rebuilt} rebuilt, {rebuild_failed} failed)")

    return {
        **scan_result,
        "deleted_cache": deleted_cache,
        "deleted_venvs": deleted_venvs,
        "rebuilt": rebuilt,
        "rebuild_failed": rebuild_failed,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: cache_audit.py {scan|fix} [--json] [--dry-run]")
        return 1

    command = sys.argv[1]
    flags = set(sys.argv[2:])

    if command == "scan":
        result = scan_cache(json_output="--json" in flags)
        return 1 if result["corrupted_dirs"] > 0 else 0
    elif command == "fix":
        result = fix_cache(dry_run="--dry-run" in flags)
        return 1 if result["corrupted_dirs"] > 0 and "--dry-run" in flags else 0
    else:
        print(f"Unknown command: {command}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
