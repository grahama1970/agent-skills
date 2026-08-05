"""Bundle revision CAS and near-atomic multi-file writes (roundtable session 1).

Every mutating operation goes through commit_bundle_write: it compare-and-swaps
the bundle's revision counter (rejecting stale edits with RevisionConflict so
two surfaces editing the same base produce one success and one 409, never a
lost update), writes each payload to a temp file in the same directory, then
os.replace()s them (atomic per file, near-atomic as a set), and bumps the
revision last. The revision travels in emitted bundles so clients can send
base_revision with every edit.

Undo support: before each commit, the ABOUT-TO-BE-OVERWRITTEN contents of the
touched files are archived under .history/<revision>/ (the revision they
belonged to). undo_last_write restores the most recent archived revision's
files and commits that restore through the same CAS path, so an undo is itself
a new revision (redo = undo of the undo) and never bypasses validation-free
byte restore of previously-validated states. Failure modes: no history ->
NoHistory; concurrent edit between read and undo -> RevisionConflict.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from loguru import logger

REVISION_FILE = ".revision"
HISTORY_DIR = ".history"
HISTORY_KEEP = 50


class RevisionConflict(ValueError):
    """Raised when expected_revision does not match the bundle's current revision."""


class NoHistory(ValueError):
    """Raised when undo is requested but no archived revision exists."""


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
    _archive_prior_state(bundle_dir, revision, files.keys())
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


def _archive_prior_state(bundle_dir: Path, revision: int, targets) -> None:
    """Snapshot the current contents of the files a commit is about to replace."""
    archive = bundle_dir / HISTORY_DIR / str(revision)
    for target in targets:
        if not target.exists():
            continue
        rel = target.relative_to(bundle_dir)
        dest = archive / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, dest)
    _prune_history(bundle_dir)


def _prune_history(bundle_dir: Path) -> None:
    history = bundle_dir / HISTORY_DIR
    if not history.is_dir():
        return
    revisions = sorted((d for d in history.iterdir() if d.name.isdigit()), key=lambda d: int(d.name))
    for stale in revisions[:-HISTORY_KEEP]:
        shutil.rmtree(stale, ignore_errors=True)


def undo_history(bundle_dir: Path) -> list[int]:
    """Archived revisions available to undo, oldest first."""
    history = bundle_dir / HISTORY_DIR
    if not history.is_dir():
        return []
    return sorted(int(d.name) for d in history.iterdir() if d.name.isdigit())


def undo_last_write(bundle_dir: Path) -> int:
    """Restore the newest archived revision's files as a NEW committed revision.

    The restore goes through commit_bundle_write, so the pre-undo state is
    itself archived first — undoing an undo is redo. The consumed archive dir
    is removed after a successful restore.
    """
    available = undo_history(bundle_dir)
    if not available:
        raise NoHistory(f"no archived revisions under {bundle_dir / HISTORY_DIR}; nothing to undo")
    newest = available[-1]
    archive = bundle_dir / HISTORY_DIR / str(newest)
    files: dict[Path, str] = {}
    for path in sorted(p for p in archive.rglob("*") if p.is_file()):
        files[bundle_dir / path.relative_to(archive)] = path.read_text(encoding="utf-8")
    if not files:
        shutil.rmtree(archive, ignore_errors=True)
        raise NoHistory(f"archived revision {newest} was empty; nothing to undo")
    committed = commit_bundle_write(bundle_dir, files)
    shutil.rmtree(archive, ignore_errors=True)
    logger.info("undo: restored revision {} state as revision {} ({} files)", newest, committed, len(files))
    return committed
