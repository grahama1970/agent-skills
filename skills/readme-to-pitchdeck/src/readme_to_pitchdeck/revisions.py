"""Bundle revision CAS and near-atomic multi-file writes (roundtable session 1).

Every mutating operation goes through commit_bundle_write: it compare-and-swaps
the bundle's revision counter (rejecting stale edits with RevisionConflict so
two surfaces editing the same base produce one success and one 409, never a
lost update), writes each payload to a temp file in the same directory, then
os.replace()s them (atomic per file, near-atomic as a set), and bumps the
revision last. The revision travels in emitted bundles so clients can send
base_revision with every edit.
"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

REVISION_FILE = ".revision"


class RevisionConflict(ValueError):
    """Raised when expected_revision does not match the bundle's current revision."""


def current_revision(bundle_dir: Path) -> int:
    path = bundle_dir / REVISION_FILE
    try:
        return int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def commit_bundle_write(
    bundle_dir: Path,
    files: dict[Path, str],
    *,
    expected_revision: int | None = None,
) -> int:
    """CAS-check, write all payloads via temp+replace, bump and return revision."""
    revision = current_revision(bundle_dir)
    if expected_revision is not None and expected_revision != revision:
        raise RevisionConflict(
            f"revision conflict: edit was based on revision {expected_revision} "
            f"but the bundle is at revision {revision}; reload and retry"
        )
    for target, payload in files.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f".{target.name}.tmp"
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, target)
    next_revision = revision + 1
    rev_tmp = bundle_dir / f".{REVISION_FILE}.tmp"
    rev_tmp.write_text(str(next_revision), encoding="utf-8")
    os.replace(rev_tmp, bundle_dir / REVISION_FILE)
    logger.debug("bundle write committed: revision {} -> {} ({} files)", revision, next_revision, len(files))
    return next_revision
