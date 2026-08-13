"""Deployment attestation: what code, config, and credentials actually ran.

webgpt eval review P0 #06. The failure class is "works when I run it, fails at
02:00": PATH, working directory, shell, uv, timezone, secret, or deployed-code
drift between an interactive shell and the scheduler's minimal environment.
This skill has already been bitten three times by exactly that — an empty
systemd env with no API keys, an expired SAM credential, and a quota-exhausted
Brave key — each of which looked like "no opportunities today".

Every run records the identity of what executed so a later reader can tell a
data change from a deployment change:
  code       git revision + dirty state of the skill tree
  deps       uv.lock hash
  config     hash over the skill's config/ directory
  runtime    python executable, version, timezone, whether stdin is a TTY
             (an interactive shell is NOT the scheduled environment)
  creds      preflight: which required credentials are PRESENT (never values)

Credential preflight reports presence only. Values are never read, logged, or
hashed into anything that could round-trip.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ATTESTATION_SCHEMA = "monitor_opportunities.run_attestation.v1"

# Credentials the nightly needs. Presence only — never the value.
REQUIRED_CREDENTIALS = ("SAM_GOV_API_KEY", "BRAVE_API_KEY")
OPTIONAL_CREDENTIALS = ("BRAVE_API_KEY_PAID", "BUZZ_IDENTITY_KEY", "GITHUB_TOKEN")


def _git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _hash_dir(path: Path, suffixes: tuple[str, ...] = (".json", ".yaml", ".yml")) -> str:
    """Stable hash over a config directory's contents."""
    if not path.is_dir():
        return ""
    digest = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in suffixes):
        digest.update(str(f.relative_to(path)).encode("utf-8"))
        try:
            digest.update(f.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:16]


def credential_preflight() -> dict[str, Any]:
    """Which credentials are present. Presence only, never values."""
    present = {name: bool(os.environ.get(name)) for name in REQUIRED_CREDENTIALS}
    optional = {name: bool(os.environ.get(name)) for name in OPTIONAL_CREDENTIALS}
    missing = sorted(n for n, ok in present.items() if not ok)
    return {
        "required_present": present,
        "optional_present": optional,
        "missing_required": missing,
        "ok": not missing,
    }


def attest(skill_dir: Path | None = None) -> dict[str, Any]:
    """Build the attestation for this process."""
    skill_dir = skill_dir or Path(__file__).resolve().parents[2]
    repo = skill_dir.parents[1]
    dirty = _git(["status", "--porcelain", "--", str(skill_dir)], repo)
    lock = skill_dir / "uv.lock"
    creds = credential_preflight()
    # An interactive TTY means a human ran this by hand; the scheduled
    # environment has no TTY. Recording it stops "works for me" from being
    # mistaken for "works at 02:00".
    try:
        interactive = sys.stdin.isatty()
    except (ValueError, OSError):
        interactive = False
    return {
        "schema": ATTESTATION_SCHEMA,
        "code": {
            "git_revision": _git(["rev-parse", "HEAD"], repo)[:12],
            "git_revision_full": _git(["rev-parse", "HEAD"], repo),
            "git_branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
            "skill_tree_dirty": bool(dirty),
            "dirty_file_count": len([ln for ln in dirty.splitlines() if ln.strip()]),
        },
        "deps": {
            "uv_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()[:16]
            if lock.exists() else "",
        },
        "config": {"config_dir_sha256": _hash_dir(skill_dir / "config")},
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "timezone": time.tzname[0] if time.tzname else "",
            "cwd": str(Path.cwd()),
            "interactive_tty": interactive,
            "environment": "interactive_shell" if interactive else "non_interactive",
        },
        "credentials": creds,
        # A run whose required credentials are absent produced its results
        # WITHOUT those sources; that must never read as "nothing out there".
        "ok": creds["ok"],
    }
