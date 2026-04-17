"""Adaptive extraction parameter mapping for the inline review loop.

Maps persona review issue codes and debug-pdf pattern names to concrete
extraction flags and environment variable overrides, so re-extraction
on subsequent iterations actually changes behavior.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from loguru import logger

# ---------------------------------------------------------------------------
# Issue codes from persona review -> extraction parameters
# ---------------------------------------------------------------------------
ISSUE_CODE_PARAMS: Dict[str, Dict[str, Any]] = {
    # Section issues -- each maps to env vars that ACTUALLY change S04 behavior.
    # STAGE04_NORMALIZE_WRAPPERS=1 is already the default, so it's a no-op.
    # Instead, vary S03_CONFIDENCE_MIN (default 0.80) and font offset behavior.
    "section_alignment_critical": {
        "env": {
            "S03_CONFIDENCE_MIN": "0.60",  # Trust more S03 verdicts to find missed sections
            "STAGE04_COLOR_ENRICH": "1",
        },
    },
    "section_alignment_low": {
        "env": {
            "S03_CONFIDENCE_MIN": "0.50",  # Lower S03 threshold to find more sections
        },
    },
    "section_oversegmentation": {
        "env": {
            "S03_CONFIDENCE_MIN": "0.90",  # Raise S03 threshold to reject false headings
        },
    },
    # Table issues -- vary CAMELOT_LINE_SCALE aggressively (default=15).
    # TABLE_MULTI_PAGE_MERGE_ENABLED is already true in .env, so omitted.
    "table_recall_critical": {
        "env": {
            "CAMELOT_LINE_SCALE_DEFAULT": "40",
            "TABLE_EXTRACTION_DPI": "300",
            "TABLE_MULTI_PAGE_MERGE_MIN_IOU": "0.15",
            "TABLE_FILTER_MIN_ROWS": "2",
        },
        # NOTE: --accurate requires LLM (Chutes.ai) which is unavailable in
        # worker environments.  Camelot env vars are what improve table recall;
        # --offline mode still runs full Camelot extraction.
    },
    "table_recall_low": {
        "env": {
            "CAMELOT_LINE_SCALE_DEFAULT": "25",
            "TABLE_FILTER_MIN_ROWS": "2",
        },
    },
    "table_overextraction": {
        "env": {
            "CAMELOT_LINE_SCALE_DEFAULT": "40",  # Higher = fewer false detections
            "TABLE_FILTER_MIN_ROWS": "4",  # Require more rows to qualify as table
            "TABLE_FILTER_MIN_DENSITY": "0.25",  # Higher density filter
        },
    },
    # Content coverage
    "content_coverage_critical": {"flags": ["--auto-ocr"]},
    "content_coverage_low": {},
    "content_overextract_critical": {
        "env": {
            "STAGE04_COLOR_ENRICH": "0",  # Disable color enrichment that may duplicate
        },
    },
    "content_overextract_high": {
        "env": {
            "STAGE04_COLOR_ENRICH": "0",
        },
    },
    # Duplicate content -- tighten dedup thresholds
    "duplicate_content_high": {
        "env": {
            "STAGE04_COLOR_ENRICH": "0",  # Color enrichment can introduce dupes
        },
    },
    "duplicate_content_warn": {},  # MEDIUM severity -- won't block PASS
    # Math/equation
    "equation_recall_critical": {"preset": "arxiv"},
    "math_symbol_loss": {"preset": "arxiv"},
    # Element types
    "unknown_element_type": {},
}

# debug-pdf pattern names -> extraction parameters
DEBUG_PATTERN_PARAMS: Dict[str, Dict[str, Any]] = {
    "scanned_no_ocr": {"flags": ["--auto-ocr", "--ocr-force"], "preset": "archive_scanned"},
    "multi_column": {"preset": "arxiv"},
    "split_tables": {
        "env": {
            "CAMELOT_LINE_SCALE_DEFAULT": "40",
            "TABLE_MULTI_PAGE_MERGE_MIN_IOU": "0.15",
        },
    },
    "section_under_segmentation": {"env": {"S03_CONFIDENCE_MIN": "0.50"}},
    "math_symbols_lost": {"preset": "arxiv"},
    "mil_spec_reference": {"preset": "requirements_spec"},
    "aerospace_spec": {"preset": "requirements_spec"},
    "itar_export_control": {"preset": "requirements_spec"},
    "symbol_fonts": {"flags": ["--auto-ocr", "--ocr-force"]},
    "low_block_density": {"flags": ["--auto-ocr"]},
    "toc_noise": {"env": {"STAGE04_NORMALIZE_WRAPPERS": "1"}},
    "toc_leaders_in_headers": {"env": {"STAGE04_NORMALIZE_WRAPPERS": "1"}},
    "header_footer_bleed": {"env": {"STAGE04_NORMALIZE_WRAPPERS": "1"}},
}


def compute_adaptive_params(
    review_result: Dict[str, Any],
    run_dir: Path,
    iteration: int = 1,
) -> Dict[str, Any]:
    """Map review issues + debug-pdf patterns to extraction parameters.

    Dual-source approach:
    1. Issue codes from persona review (always available)
    2. debug-pdf patterns from review_debug_pdf.json (when escalation ran)

    iteration controls parameter variation: later iterations use more
    aggressive values to avoid re-extracting with identical settings.

    Returns dict with keys: preset, extra_flags, env_overrides.
    """
    params: Dict[str, Any] = {
        "preset": None,
        "extra_flags": [],
        "env_overrides": {},
    }

    # -- Source 1: Issue codes from persona review --------------------------
    issues = review_result.get("issues", [])
    issue_codes = {iss.get("code", "") for iss in issues if isinstance(iss, dict)}
    # Also check escalation jobs for issue codes baked into reason text
    for job in review_result.get("escalation_jobs", []):
        reason = job.get("reason", "")
        if "table" in reason.lower():
            issue_codes.add("table_recall_critical")
        if "section" in reason.lower():
            issue_codes.add("section_alignment_critical")

    for code in issue_codes:
        mapping = ISSUE_CODE_PARAMS.get(code, {})
        if mapping.get("preset") and not params["preset"]:
            params["preset"] = mapping["preset"]
        params["extra_flags"].extend(mapping.get("flags", []))
        params["env_overrides"].update(mapping.get("env", {}))

    # -- Source 2: debug-pdf output file (if escalation wrote it) -----------
    debug_path = run_dir / "review_debug_pdf.json"
    if debug_path.exists():
        try:
            with open(debug_path) as f:
                debug_data = json.load(f)
            patterns = set(debug_data.get("patterns", []))
            pages = debug_data.get("pages", 0)
            is_scanned = debug_data.get("is_scanned", False)

            # Scanned detection from debug-pdf
            if is_scanned:
                params["extra_flags"].extend(["--auto-ocr", "--ocr-force"])
                if not params["preset"]:
                    params["preset"] = "archive_scanned"

            # Section count hint from page count
            if "section_under_segmentation" in patterns and pages > 0:
                estimated = max(5, pages // 4)
                params["env_overrides"]["CONTRACT_EXPECT_SECTIONS"] = str(estimated)

            for pattern in patterns:
                mapping = DEBUG_PATTERN_PARAMS.get(pattern, {})
                if mapping.get("preset") and not params["preset"]:
                    params["preset"] = mapping["preset"]
                params["extra_flags"].extend(mapping.get("flags", []))
                params["env_overrides"].update(mapping.get("env", {}))

            logger.info(
                f"Debug-pdf patterns: {sorted(patterns)[:8]} "
                f"pages={pages} scanned={is_scanned}"
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Could not read debug-pdf output: {exc}")

    # -- Iteration-aware variation ------------------------------------------
    # If we're on iteration 2+, the previous params didn't help enough.
    # Vary key parameters so re-extraction is NOT identical.
    if iteration >= 2:
        # Escalate CAMELOT_LINE_SCALE: iter2=40, iter3=60
        line_scale = 40 + (iteration - 2) * 20
        if "CAMELOT_LINE_SCALE_DEFAULT" in params["env_overrides"]:
            params["env_overrides"]["CAMELOT_LINE_SCALE_DEFAULT"] = str(line_scale)
        # Enable strategy predictor on iter 2+ (model exists at default path)
        params["env_overrides"]["USE_STRATEGY_PREDICTOR"] = "true"
        # Bump DPI on iter 3+
        if iteration >= 3:
            params["env_overrides"]["TABLE_EXTRACTION_DPI"] = "400"

    # Deduplicate flags
    params["extra_flags"] = list(dict.fromkeys(params["extra_flags"]))

    has_changes = params["preset"] or params["extra_flags"] or params["env_overrides"]
    if has_changes:
        logger.info(
            f"Adaptive params (iter={iteration}): preset={params['preset']} "
            f"flags={params['extra_flags']} "
            f"env={list(params['env_overrides'].keys())}"
        )

    return params
