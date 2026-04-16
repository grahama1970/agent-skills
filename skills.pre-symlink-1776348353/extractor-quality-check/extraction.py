"""PDF extraction and timeout utilities for the inline review loop.

Handles running the extractor pipeline on a single PDF, computing
filesystem-safe slugs, and adaptive timeout estimation via the
page-count ML classifier.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_EXTRACT_TIMEOUT = 21600  # 6 hours (matches EXTRACTOR_PIPELINE_TIMEOUT)

# Timeout classifier integration -- uses existing page-count-based ML model
try:
    from verify.timeout import estimate_extract_timeout_seconds as _estimate_timeout
    HAS_TIMEOUT_CLASSIFIER = True
except ImportError:
    HAS_TIMEOUT_CLASSIFIER = False


def slug_for_pdf(pdf_path: Path) -> str:
    """Generate a filesystem-safe slug for a PDF path.

    MUST match discovery.py:_slug_for_doc() -- uses MD5 hash suffix to avoid
    collisions between files with the same stem in different directories.
    """
    digest = hashlib.md5(
        str(pdf_path.resolve()).encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    stem = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in pdf_path.stem)
    return f"{stem}_{digest}"


def extract_pdf(
    pdf_path: Path,
    extracted_runs_dir: Path,
    force_reextract: bool = False,
    preset: Optional[str] = None,
    extra_flags: Optional[List[str]] = None,
    env_overrides: Optional[Dict[str, str]] = None,
) -> Optional[Path]:
    """Extract a PDF using the extractor pipeline.

    Args:
        pdf_path: Path to the PDF file.
        extracted_runs_dir: Where to store extraction output.
        force_reextract: Clear previous output and re-extract.
        preset: Force a specific extractor preset (arxiv, requirements_spec, etc.).
        extra_flags: Additional CLI flags (--accurate, --auto-ocr, etc.).
        env_overrides: Environment variable overrides for stage tuning.

    Returns profile_path if successful, None if failed.
    """
    slug = slug_for_pdf(pdf_path)
    run_dir = extracted_runs_dir / slug
    profile_path = run_dir / "00_profile_detector" / "profile.json"
    structural_path = run_dir / "11_json_exporter" / "structural.json"

    # If force re-extract, clear existing output
    if force_reextract and (run_dir.exists() or run_dir.is_symlink()):
        logger.info(f"Clearing previous extraction at {run_dir}")
        if run_dir.is_symlink():
            # rmtree raises on symlinks; unlink symlink, then clear target
            target = run_dir.resolve()
            run_dir.unlink()
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
        else:
            shutil.rmtree(run_dir, ignore_errors=True)

    # Check if already extracted
    if profile_path.exists() and structural_path.exists():
        return profile_path

    # Build extraction command with adaptive parameters
    # Always use --offline: LLM (--accurate) requires Chutes.ai which is
    # unavailable in worker environments.  Table quality improvements come
    # from env var tuning (CAMELOT_LINE_SCALE_DEFAULT, TABLE_EXTRACTION_DPI).
    #
    # IMPORTANT: run.sh sources extractor/.env with `set -a` which OVERWRITES
    # subprocess env dict values (e.g. TABLE_EXTRACTION_DPI=200 in .env beats
    # our override of 300).  Fix: source .env first for baseline config, then
    # re-export our overrides so they win.  This preserves .env defaults for
    # vars we don't override while letting adaptive params take effect.
    if env_overrides:
        logger.info(
            f"Extraction env overrides: "
            f"{', '.join(f'{k}={v}' for k, v in env_overrides.items())}"
        )
    _skills_dir = str(Path(__file__).resolve().parent.parent)
    _pi_mono = Path(__file__).resolve().parent.parent.parent.parent
    _candidate = _pi_mono / "extractor"
    if not (_candidate / "src/extractor").exists():
        _candidate = _pi_mono.parent / "extractor"
    extractor_root = str(_candidate)
    extractor_skill = f"{_skills_dir}/extractor"
    # Source .env for baseline, then re-export our overrides to win
    re_exports = ""
    if env_overrides:
        re_exports = " && " + " && ".join(
            f"export {k}={v}" for k, v in env_overrides.items()
        )
    cmd_parts = [
        f'cd {extractor_skill} &&',
        f'set -a && source "{extractor_root}/.env" && set +a{re_exports} &&',
        f'"{extractor_root}/.venv/bin/python" "{extractor_skill}/extract.py"',
        f'"{pdf_path}" --offline --learn --no-interactive --continue-on-error --out "{run_dir}"',
    ]
    if preset:
        cmd_parts.append(f"--preset {preset}")
    if extra_flags:
        # Filter any mode flags that may leak in from old config
        mode_flags = {"--offline", "--accurate", "--fast"}
        seen = set()
        for flag in extra_flags:
            if flag not in seen and flag not in mode_flags:
                cmd_parts.append(flag)
                seen.add(flag)
    cmd = " ".join(cmd_parts)

    # Also pass env overrides via subprocess env dict for any code that
    # reads os.environ directly (before run.sh .env sourcing).
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    extract_timeout = int(env.get(
        "EXTRACTOR_PIPELINE_TIMEOUT", str(DEFAULT_EXTRACT_TIMEOUT)
    ))

    if preset or extra_flags or env_overrides:
        logger.info(
            f"Adaptive extraction: preset={preset} "
            f"flags={extra_flags or []} env_keys={list((env_overrides or {}).keys())}"
        )
    print(f"review-pdf _extract_pdf cmd={cmd[:200]} pdf={pdf_path.name}", flush=True)
    logger.info(f"Extracting {pdf_path} -> {run_dir}")
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=extract_timeout,
            check=False,
            start_new_session=True,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"Extraction timed out after {extract_timeout}s for {pdf_path}")
        return None

    # Check for output files (--continue-on-error may exit non-zero)
    if profile_path.exists() and structural_path.exists():
        return profile_path

    if profile_path.exists():
        # Profile exists but no structural -- partial extraction
        logger.warning(f"Partial extraction: profile exists but no structural for {pdf_path}")
        return profile_path

    logger.error(
        f"Extraction failed for {pdf_path}: rc={proc.returncode} "
        f"stderr={proc.stderr[-200:] if proc.stderr else 'empty'}"
    )
    print(
        f"review-pdf _extract_pdf FAILED rc={proc.returncode} "
        f"stderr={proc.stderr[-300:] if proc.stderr else 'empty'} "
        f"stdout_tail={proc.stdout[-200:] if proc.stdout else 'empty'} "
        f"pdf={pdf_path.name}",
        flush=True,
    )
    return None


def compute_remediation_timeout(pdf_path: Path, fallback: int) -> int:
    """Use the timeout classifier to compute a per-PDF remediation timeout.

    Falls back to static timeout if classifier is unavailable.
    The classifier uses page count, ML model risk scoring, and historical
    extraction patterns for accurate per-PDF timeout prediction.
    """
    if not HAS_TIMEOUT_CLASSIFIER:
        return fallback
    try:
        timeout_meta = _estimate_timeout(pdf_path)
        # Use the classifier's timeout with a 1.5x safety margin for remediation
        classified_timeout = int(timeout_meta.get("timeout_seconds", fallback) * 1.5)
        # Clamp: at least 300s (5 min), at most 21600s (6 hrs)
        return max(300, min(classified_timeout, 21600))
    except Exception:
        return fallback
