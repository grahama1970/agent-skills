"""NVMe staging and HDD archival for learn-datalake extracted runs.

Purpose:
- Point review-pdf extracted_runs at fast NVMe during extraction.
- Archive completed runs to HDD after each cycle.

Inputs:
- NVMe staging path, HDD archive path, symlink path.

Outputs:
- Side effects: directory creation, symlink management, file moves.
"""

from __future__ import annotations

import os
import shutil

from loguru import logger

from config import (
    DEFERRED_REVIEW_PATH,
    QUESTION_BOOK_PATH,
    REVIEW_PDF_EXTRACTED_RUNS_HDD,
    REVIEW_PDF_EXTRACTED_RUNS_NVME,
    REVIEW_PDF_EXTRACTED_RUNS_SYMLINK,
)


def setup_nvme_staging() -> None:
    """Point the review-pdf extracted_runs symlink at NVMe staging dir.

    Layout:
    - NVMe staging: extracted_runs_staging/ (fast writes during extraction)
    - HDD archive:  /mnt/storage12tb/skills/review-pdf/extracted_runs/ (long-term)
    - Symlink:      review-pdf/extracted_runs -> extracted_runs_staging/

    After each cycle, archive_extracted_to_hdd() moves completed runs
    from NVMe to HDD and leaves symlinks so review-pdf still finds them.
    """
    staging = REVIEW_PDF_EXTRACTED_RUNS_NVME
    staging.mkdir(parents=True, exist_ok=True)
    REVIEW_PDF_EXTRACTED_RUNS_HDD.mkdir(parents=True, exist_ok=True)

    symlink = REVIEW_PDF_EXTRACTED_RUNS_SYMLINK
    if symlink.is_symlink():
        current_target = symlink.resolve()
        if current_target == staging.resolve():
            logger.info(f"nvme_staging already_active symlink={symlink} -> {staging}")
            return
        symlink.unlink()
    elif symlink.is_dir():
        if not staging.exists() or not any(staging.iterdir()):
            shutil.rmtree(staging, ignore_errors=True)
            symlink.rename(staging)
        else:
            shutil.rmtree(symlink)

    symlink.symlink_to(staging)

    hdd_dir = REVIEW_PDF_EXTRACTED_RUNS_HDD
    if hdd_dir.is_dir():
        for entry in hdd_dir.iterdir():
            if entry.is_dir():
                link_in_staging = staging / entry.name
                if not link_in_staging.exists():
                    link_in_staging.symlink_to(entry)

    logger.info(
        f"nvme_staging activated symlink={symlink} -> {staging} "
        f"hdd_archive={hdd_dir}"
    )

    os.environ["PDF_LAB_QUESTION_BOOK"] = str(QUESTION_BOOK_PATH)
    QUESTION_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Also set deferred review path for /interview integration
    os.environ["DEFERRED_REVIEW_PATH"] = str(DEFERRED_REVIEW_PATH)
    logger.info(f"question_book env set path={QUESTION_BOOK_PATH}")


def archive_extracted_to_hdd() -> int:
    """Move completed extraction runs from NVMe staging to HDD.

    For each real directory in the NVMe staging dir:
    1. Move it to HDD archive
    2. Replace with a symlink pointing to the HDD location

    Returns the number of runs archived.
    """
    staging = REVIEW_PDF_EXTRACTED_RUNS_NVME
    hdd_dir = REVIEW_PDF_EXTRACTED_RUNS_HDD
    if not staging.is_dir():
        return 0

    archived = 0
    for entry in sorted(staging.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            continue
        dest = hdd_dir / entry.name
        if dest.exists():
            shutil.rmtree(entry)
            entry.symlink_to(dest)
            archived += 1
            continue
        try:
            shutil.move(str(entry), str(dest))
            entry.symlink_to(dest)
            archived += 1
        except OSError as exc:
            logger.warning(f"archive_to_hdd failed entry={entry.name} err={exc}")
    if archived:
        logger.info(f"archive_to_hdd moved={archived} staging={staging} hdd={hdd_dir}")
    return archived
