"""P29: local-memory-sync — Detect local Claude Code memory files not synced to ArangoDB.

Scans ~/.claude/projects/*/memory/*.md for files that have changed since
last sync and optionally upserts them as lessons in ArangoDB so all agents
can retrieve the knowledge.

Inputs: filesystem (local memory files), state file (last-synced hashes),
        ArangoDB via db.get_db().
Outputs: ProbeResult with list of unsynced files and optional auto-fix.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe
from probes.tier1_autofix import log_autofix

MEMORY_GLOB = Path.home() / ".claude/projects/*/memory/*.md"
STATE_FILE = config.STATE_DIR / "local_memory_hashes.json"
SCOPE_PREFIX = "claude_local_memory"

# Max file size to sync (skip huge files)
MAX_FILE_SIZE = 50_000  # 50KB


def _scan_memory_files() -> list[Path]:
    """Find all local Claude Code memory markdown files."""
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    files = sorted(base.glob("*/memory/*.md"))
    return [f for f in files if f.stat().st_size <= MAX_FILE_SIZE]


def _hash_file(path: Path) -> str:
    """SHA-256 of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_state() -> dict:
    """Load previously synced file hashes."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    """Persist synced file hashes."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _project_scope(path: Path) -> str:
    """Derive a scope name from the project directory path.

    ~/.claude/projects/-home-graham-workspace-streamdeck/memory/MEMORY.md
    -> streamdeck
    """
    # The project dir is 2 levels up from the .md file
    project_dir = path.parent.parent.name  # e.g. -home-graham-workspace-streamdeck
    # Take last segment after splitting on workspace- or experiments-
    for sep in ("workspace-", "experiments-"):
        if sep in project_dir:
            return project_dir.split(sep)[-1]
    # Fallback: last hyphen-separated segment
    return project_dir.rsplit("-", 1)[-1]


def _lesson_key(path: Path) -> str:
    """Generate a stable ArangoDB _key from file path.

    Uses project scope + filename (without .md) to create unique key.
    """
    scope = _project_scope(path)
    stem = path.stem.lower().replace(" ", "_")
    # ArangoDB keys: alphanumeric + _ + -
    key = re.sub(r"[^a-z0-9_-]", "_", f"local_memory__{scope}__{stem}")
    return key[:254]  # ArangoDB max key length


def _sync_file_to_arango(db, path: Path) -> bool:
    """Upsert a local memory file as a lesson in ArangoDB."""
    content = path.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return False

    scope = _project_scope(path)
    key = _lesson_key(path)

    # Extract title from first heading or filename
    title = path.stem.replace("_", " ").replace("-", " ").title()
    for line in content.split("\n"):
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break

    doc = {
        "_key": key,
        "title": f"[Local Memory] {title}",
        "problem": f"Knowledge from local Claude Code memory file: {path.name} (project: {scope})",
        "playbook": content,
        "scope": SCOPE_PREFIX,
        "tags": [
            "local_memory",
            f"project:{scope}",
            f"file:{path.name}",
        ],
        "source": str(path),
        "source_type": "local_memory_file",
        "updated_at": int(time.time()),
    }

    try:
        coll = db.collection("lessons")
        if coll.has(key):
            coll.update({"_key": key, **{k: v for k, v in doc.items() if k != "_key"}})
        else:
            coll.insert(doc)
        return True
    except Exception as e:
        logger.warning("Failed to sync {} to ArangoDB: {}", path.name, e)
        return False


@register_probe("P29", "local-memory-sync", tier=1, auto_fixable=True)
def probe_local_memory_sync(autofix: bool = False) -> ProbeResult:
    """Check for local memory files not synced to ArangoDB."""
    files = _scan_memory_files()
    if not files:
        return ProbeResult(
            probe_id="P29", name="local-memory-sync", tier=1,
            status=ProbeStatus.PASS,
            message="No local memory files found",
            auto_fixable=True,
        )

    state = _load_state()
    changed = []
    unchanged = []

    for f in files:
        current_hash = _hash_file(f)
        stored_hash = state.get(str(f))
        if stored_hash != current_hash:
            changed.append(f)
        else:
            unchanged.append(f)

    if not changed:
        return ProbeResult(
            probe_id="P29", name="local-memory-sync", tier=1,
            status=ProbeStatus.PASS,
            message=f"All {len(files)} local memory files in sync",
            details={"total": len(files), "changed": 0},
            auto_fixable=True,
        )

    # Report changed files
    changed_info = [
        {"path": str(f), "project": _project_scope(f), "name": f.name}
        for f in changed
    ]

    fix_applied = False
    synced = 0

    if autofix:
        try:
            from db import get_db
            db = get_db()

            t0 = time.time()
            for f in changed:
                if _sync_file_to_arango(db, f):
                    # Update state hash after successful sync
                    state[str(f)] = _hash_file(f)
                    synced += 1

            _save_state(state)
            duration = time.time() - t0
            log_autofix("P29", synced, len(changed) - synced, duration)
            fix_applied = synced > 0
            logger.info("Synced {}/{} local memory files to ArangoDB in {:.1f}s",
                        synced, len(changed), duration)

        except Exception as e:
            logger.error("Auto-fix failed for local-memory-sync: {}", e)

    if fix_applied:
        status = ProbeStatus.FIXED
        msg = f"Synced {synced}/{len(changed)} changed files to ArangoDB ({len(files)} total)"
    else:
        status = ProbeStatus.WARN
        msg = f"{len(changed)} of {len(files)} local memory files not synced to ArangoDB"

    return ProbeResult(
        probe_id="P29", name="local-memory-sync", tier=1,
        status=status,
        message=msg,
        details={
            "total": len(files),
            "changed": len(changed),
            "synced": synced,
            "files": changed_info,
        },
        auto_fixable=True,
        fix_applied=fix_applied,
    )
