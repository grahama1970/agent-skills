"""Timeout estimation and prediction for review-pdf extraction.

Purpose:
- estimate extraction timeouts based on PDF complexity, page count, and history.
- invoke the timeout risk prediction model from create-classifier.

Inputs:
- PDF file path, S00 profile hints, historical extraction log data.

Outputs:
- timeout configuration dicts with seconds, features, and model metadata.

Failure modes:
- missing model or inference failures degrade gracefully to baseline estimates.
"""

from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from loguru import logger

MIN_EXTRACT_TIMEOUT_SECONDS = 900
MAX_EXTRACT_TIMEOUT_SECONDS = 86400
EXTRACT_TIMEOUT_MULTIPLIER = 5
SECONDS_PER_PAGE_FLOOR = 12
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
CREATE_CLASSIFIER_DIR = _SKILLS_DIR / "create-classifier"
TIMEOUT_MODEL_PATH = CREATE_CLASSIFIER_DIR / "models/timeout_predictor/model.joblib"
TIMEOUT_MODEL_MIN_RISK_FOR_ADJUST = 0.20

# learn-timeout skill — GradientBoosting-based timeout prediction (preferred)
LEARN_TIMEOUT_SKILL = _SKILLS_DIR / "learn-timeout"
if not (LEARN_TIMEOUT_SKILL / "run.sh").exists():
    # Fallback paths
    for _p in [Path.home() / ".pi" / "skills" / "learn-timeout",
               Path.home() / ".claude" / "skills" / "learn-timeout"]:
        if (_p / "run.sh").exists():
            LEARN_TIMEOUT_SKILL = _p
            break
LEARN_DATALAKE_RUNS_DIR = _SKILLS_DIR / "learn-datalake" / "state" / "runs"
TIMEOUT_HISTORY_MAX_LOG_FILES = 60
_TIMEOUT_HISTORY_CACHE: Dict[str, Any] | None = None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _predict_via_learn_timeout(
    pdf_path: Path,
    page_count: int,
    table_pages: int = 0,
    estimated_table_count: int = 0,
    image_pages: int = 0,
    has_formulas: bool = False,
    has_requirements: bool = False,
    has_tables: bool = False,
    has_figures: bool = False,
    domain: str = "general",
    estimated_sections: int = 0,
    file_size_mb: float = 0.0,
) -> Dict[str, Any] | None:
    """Try learn-timeout skill for GradientBoosting-based timeout prediction.

    Returns full prediction dict on success, None on failure (caller falls through
    to existing baseline + classifier logic).
    """
    if not (LEARN_TIMEOUT_SKILL / "run.sh").exists():
        return None

    features = {
        "task_type": "pdf_extraction",
        "page_count": page_count,
        "file_size_mb": round(file_size_mb, 2),
        "table_pages": table_pages,
        "estimated_table_count": estimated_table_count,
        "image_pages": image_pages,
        "has_tables": has_tables,
        "has_figures": has_figures,
        "has_formulas": has_formulas,
        "has_requirements": has_requirements,
        "estimated_sections": estimated_sections,
        "domain": domain,
    }
    try:
        result = subprocess.run(
            [str(LEARN_TIMEOUT_SKILL / "run.sh"), "predict", json.dumps(features)],
            capture_output=True, text=True, timeout=10,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            prediction = json.loads(result.stdout.strip())
            recommended = prediction.get("recommended_timeout_seconds")
            if recommended and recommended > 0:
                return prediction
    except Exception as exc:
        logger.debug(f"learn-timeout prediction failed: {exc}")
    return None


def _page_bucket(page_count: int) -> str:
    if page_count <= 25:
        return "le25"
    if page_count <= 75:
        return "26_75"
    if page_count <= 200:
        return "76_200"
    if page_count <= 500:
        return "201_500"
    if page_count <= 1000:
        return "501_1000"
    return "gt1000"


def _parse_kv_line(line: str, prefix: str) -> Dict[str, str] | None:
    text = line.strip()
    if not text.startswith(prefix):
        return None
    payload = text[len(prefix) :].strip()
    parsed: Dict[str, str] = {}
    body = payload
    if " pdf=" in payload:
        body, pdf_value = payload.rsplit(" pdf=", 1)
        parsed["pdf"] = pdf_value.strip()
    for token in body.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _timeout_multiplier_cap(page_count: int) -> float:
    if page_count <= 0:
        return 2.0
    if page_count <= 100:
        return 1.5
    if page_count <= 300:
        return 2.0
    if page_count <= 1000:
        return 2.5
    return 3.0


def _timeout_history_defaults() -> Dict[str, Any]:
    return {
        "attempts": 0,
        "timeout_count": 0,
        "timeout_seconds_sum": 0,
        "last_timeout_seconds": 0,
    }


def _update_timeout_history_stats(target: Dict[str, Any], timeout_seconds: int, timed_out: bool) -> None:
    target["attempts"] = int(target.get("attempts", 0)) + 1
    if timed_out:
        target["timeout_count"] = int(target.get("timeout_count", 0)) + 1
    if timeout_seconds > 0:
        target["timeout_seconds_sum"] = int(target.get("timeout_seconds_sum", 0)) + timeout_seconds
        target["last_timeout_seconds"] = timeout_seconds


def _build_timeout_history_cache() -> Dict[str, Any]:
    by_pdf: Dict[str, Dict[str, Any]] = {}
    by_bucket: Dict[str, Dict[str, Any]] = {}
    if not LEARN_DATALAKE_RUNS_DIR.exists():
        return {"by_pdf": by_pdf, "by_bucket": by_bucket}
    log_files = sorted(
        LEARN_DATALAKE_RUNS_DIR.glob("learn_datalake_*.log"),
        key=lambda item: item.stat().st_mtime,
    )
    if len(log_files) > TIMEOUT_HISTORY_MAX_LOG_FILES:
        log_files = log_files[-TIMEOUT_HISTORY_MAX_LOG_FILES:]
    for log_path in log_files:
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        last_policy_by_pdf: Dict[str, Dict[str, Any]] = {}
        for line in lines:
            policy = _parse_kv_line(line, "review-pdf extract_timeout ")
            if policy:
                pdf = str(policy.get("pdf") or "").strip()
                if not pdf:
                    continue
                page_count = _safe_int(policy.get("page_count"), 0)
                last_policy_by_pdf[pdf] = {
                    "page_count": page_count,
                    "timeout_seconds": _safe_int(policy.get("seconds"), 0),
                    "bucket": _page_bucket(page_count),
                }
                continue
            outcome = _parse_kv_line(line, "review-pdf extract_missing ")
            if not outcome:
                continue
            status = str(outcome.get("status") or "").strip()
            if status not in {"extracted", "extract_failed"}:
                continue
            pdf = str(outcome.get("pdf") or "").strip()
            if not pdf:
                continue
            policy = last_policy_by_pdf.get(pdf, {})
            page_count = _safe_int(policy.get("page_count"), 0)
            timeout_seconds = _safe_int(policy.get("timeout_seconds"), 0)
            bucket = str(policy.get("bucket") or _page_bucket(page_count))
            timed_out = status == "extract_failed" and _safe_bool(outcome.get("timed_out"), False)
            pdf_stats = by_pdf.setdefault(pdf, _timeout_history_defaults())
            bucket_stats = by_bucket.setdefault(bucket, _timeout_history_defaults())
            _update_timeout_history_stats(pdf_stats, timeout_seconds, timed_out)
            _update_timeout_history_stats(bucket_stats, timeout_seconds, timed_out)
    return {"by_pdf": by_pdf, "by_bucket": by_bucket}


def _timeout_history_features(pdf_path: Path, page_count: int) -> Dict[str, Any]:
    global _TIMEOUT_HISTORY_CACHE
    if _TIMEOUT_HISTORY_CACHE is None:
        _TIMEOUT_HISTORY_CACHE = _build_timeout_history_cache()
    by_pdf = _TIMEOUT_HISTORY_CACHE.get("by_pdf", {})
    by_bucket = _TIMEOUT_HISTORY_CACHE.get("by_bucket", {})
    pdf_key = str(pdf_path.resolve())
    bucket_key = _page_bucket(page_count)
    pdf_stats = by_pdf.get(pdf_key, _timeout_history_defaults())
    bucket_stats = by_bucket.get(bucket_key, _timeout_history_defaults())
    pdf_attempts = max(0, _safe_int(pdf_stats.get("attempts"), 0))
    pdf_timeout_count = max(0, _safe_int(pdf_stats.get("timeout_count"), 0))
    bucket_attempts = max(0, _safe_int(bucket_stats.get("attempts"), 0))
    bucket_timeout_count = max(0, _safe_int(bucket_stats.get("timeout_count"), 0))
    return {
        "history_pdf_attempts": pdf_attempts,
        "history_pdf_timeout_count": pdf_timeout_count,
        "history_pdf_timeout_rate": round(
            (float(pdf_timeout_count) / float(pdf_attempts)) if pdf_attempts > 0 else 0.0,
            6,
        ),
        "history_pdf_last_timeout_seconds": max(
            0, _safe_int(pdf_stats.get("last_timeout_seconds"), 0)
        ),
        "history_pdf_avg_timeout_seconds": max(
            0,
            int(
                round(
                    float(_safe_int(pdf_stats.get("timeout_seconds_sum"), 0)) / float(pdf_attempts)
                )
            )
            if pdf_attempts > 0
            else 0,
        ),
        "history_page_bucket_attempts": bucket_attempts,
        "history_page_bucket_timeout_count": bucket_timeout_count,
        "history_page_bucket_timeout_rate": round(
            (float(bucket_timeout_count) / float(bucket_attempts)) if bucket_attempts > 0 else 0.0,
            6,
        ),
        "history_page_bucket_last_timeout_seconds": max(
            0, _safe_int(bucket_stats.get("last_timeout_seconds"), 0)
        ),
        "history_page_bucket_avg_timeout_seconds": max(
            0,
            int(
                round(
                    float(_safe_int(bucket_stats.get("timeout_seconds_sum"), 0))
                    / float(bucket_attempts)
                )
            )
            if bucket_attempts > 0
            else 0,
        ),
    }


def _step00_profile_hint(pdf_path: Path) -> Dict[str, Any]:
    """Get S00 estimate hints via extractor --profile-only.

    This uses the same extractor wrapper as full extraction, but runs only profile detection
    so we can scale subprocess timeout for very large/complex PDFs.
    """
    cmd = (
        f"cd {_SKILLS_DIR}/extractor && "
        f'./run.sh "{pdf_path}" --profile-only --no-interactive'
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"review-pdf step00 hint timeout for {pdf_path}")
        return {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"review-pdf step00 hint failure for {pdf_path}: {exc}")
        return {}

    if proc.returncode != 0:
        stderr_tail = "\n".join(proc.stderr.splitlines()[-3:])
        logger.warning(
            f"review-pdf step00 hint non-zero rc={proc.returncode} pdf={pdf_path} "
            f"stderr_tail={stderr_tail}"
        )
        return {}

    payload: Dict[str, Any] = {}
    try:
        stdout = proc.stdout.strip()
        json_start = stdout.find("{")
        if json_start < 0:
            raise ValueError("no-json-object-found")
        candidate = stdout[json_start:]
        loaded = json.loads(candidate)
        if isinstance(loaded, dict):
            payload = loaded
    except Exception:
        logger.warning(f"review-pdf step00 hint parse failed for {pdf_path}")
        return {}
    return payload


def _predict_timeout_risk(
    *,
    pdf_path: Path,
    page_count: int,
    step00_estimated_timeout_seconds: int,
    baseline_timeout_seconds: int,
    timeout_source: str,
    feature_meta: Dict[str, Any],
) -> Dict[str, Any]:
    if not TIMEOUT_MODEL_PATH.exists():
        return {"timeout_model_status": "missing_model"}

    cmd = (
        f"cd {CREATE_CLASSIFIER_DIR} && "
        "./run.sh timeout-infer "
        f"--model-path {json.dumps(str(TIMEOUT_MODEL_PATH))} "
        f"--page-count {max(0, int(page_count))} "
        f"--step00-estimated-timeout-seconds {max(0, int(step00_estimated_timeout_seconds))} "
        f"--baseline-timeout-seconds {max(0, int(baseline_timeout_seconds))} "
        f"--timeout-source {json.dumps(str(timeout_source))} "
        f"--step00-estimated-sections {max(0, _safe_int(feature_meta.get('step00_estimated_sections'), 0))} "
        f"--step00-estimated-sections-regex {max(0, _safe_int(feature_meta.get('step00_estimated_sections_regex'), 0))} "
        f"--step00-estimated-sections-font {max(0, _safe_int(feature_meta.get('step00_estimated_sections_font'), 0))} "
        f"--step00-estimated-sections-toc {max(0, _safe_int(feature_meta.get('step00_estimated_sections_toc'), 0))} "
        f"--step00-estimated-table-count {max(0, _safe_int(feature_meta.get('step00_estimated_table_count'), 0))} "
        f"--step00-table-pages {max(0, _safe_int(feature_meta.get('step00_table_pages'), 0))} "
        f"--step00-image-pages {max(0, _safe_int(feature_meta.get('step00_image_pages'), 0))} "
        f"--step00-max-tables-per-page {max(0, _safe_int(feature_meta.get('step00_max_tables_per_page'), 0))} "
        f"--step00-table-pages-drawing {max(0, _safe_int(feature_meta.get('step00_table_pages_drawing'), 0))} "
        f"--step00-has-formulas {1 if _safe_bool(feature_meta.get('step00_has_formulas'), False) else 0} "
        f"--step00-has-figures {1 if _safe_bool(feature_meta.get('step00_has_figures'), False) else 0} "
        f"--step00-has-requirements {1 if _safe_bool(feature_meta.get('step00_has_requirements'), False) else 0} "
        f"--step00-has-tables {1 if _safe_bool(feature_meta.get('step00_has_tables'), False) else 0} "
        f"--step00-has-structure {1 if _safe_bool(feature_meta.get('step00_has_structure'), False) else 0} "
        f"--history-pdf-attempts {max(0, _safe_int(feature_meta.get('history_pdf_attempts'), 0))} "
        f"--history-pdf-timeout-count {max(0, _safe_int(feature_meta.get('history_pdf_timeout_count'), 0))} "
        f"--history-pdf-timeout-rate {max(0.0, _safe_float(feature_meta.get('history_pdf_timeout_rate'), 0.0))} "
        f"--history-pdf-last-timeout-seconds {max(0, _safe_int(feature_meta.get('history_pdf_last_timeout_seconds'), 0))} "
        f"--history-pdf-avg-timeout-seconds {max(0, _safe_int(feature_meta.get('history_pdf_avg_timeout_seconds'), 0))} "
        f"--history-page-bucket-attempts {max(0, _safe_int(feature_meta.get('history_page_bucket_attempts'), 0))} "
        f"--history-page-bucket-timeout-count {max(0, _safe_int(feature_meta.get('history_page_bucket_timeout_count'), 0))} "
        f"--history-page-bucket-timeout-rate {max(0.0, _safe_float(feature_meta.get('history_page_bucket_timeout_rate'), 0.0))} "
        f"--history-page-bucket-last-timeout-seconds {max(0, _safe_int(feature_meta.get('history_page_bucket_last_timeout_seconds'), 0))} "
        f"--history-page-bucket-avg-timeout-seconds {max(0, _safe_int(feature_meta.get('history_page_bucket_avg_timeout_seconds'), 0))} "
        f"--pdf {json.dumps(str(pdf_path))}"
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except subprocess.TimeoutExpired:
        return {"timeout_model_status": "infer_timeout"}
    except Exception:
        return {"timeout_model_status": "infer_error"}

    if proc.returncode != 0:
        return {
            "timeout_model_status": "infer_failed",
            "timeout_model_stderr_tail": "\n".join(proc.stderr.splitlines()[-3:]),
        }

    try:
        stdout = proc.stdout.strip()
        json_start = stdout.find("{")
        if json_start < 0:
            raise ValueError("no-json-object")
        payload = json.loads(stdout[json_start:])
        risk = float(payload.get("timeout_risk", 0.0))
        return {
            "timeout_model_status": "ok",
            "timeout_model_risk": max(0.0, min(1.0, risk)),
            "timeout_model_metrics": payload.get("metrics", {}),
            "timeout_model_trained_at": payload.get("trained_at"),
        }
    except Exception:
        return {"timeout_model_status": "infer_parse_failed"}


def estimate_extract_timeout_seconds(pdf_path: Path) -> Dict[str, Any]:
    """Estimate timeout for extraction of the given PDF.

    Returns a dict with timeout_seconds and rich metadata about how it was derived.
    """
    hint = _step00_profile_hint(pdf_path)
    page_count = _safe_int(hint.get("page_count"), 0)
    estimated_timeout = _safe_int(hint.get("estimated_timeout_seconds"), 0)
    timeout_source = str(hint.get("timeout_source") or "fallback")
    hierarchy = hint.get("hierarchy", {}) if isinstance(hint.get("hierarchy"), dict) else {}
    elements = hint.get("elements", {}) if isinstance(hint.get("elements"), dict) else {}
    hint_tables = hint.get("tables")
    hint_figures = hint.get("figures")
    hint_formulas = hint.get("formulas")
    hint_requirements = hint.get("requirements")

    feature_meta: Dict[str, Any] = {
        "step00_estimated_sections": _safe_int(hierarchy.get("estimated_sections"), 0),
        "step00_estimated_sections_regex": _safe_int(
            hierarchy.get("estimated_sections_regex"), 0
        ),
        "step00_estimated_sections_font": _safe_int(
            hierarchy.get("estimated_sections_font"), 0
        ),
        "step00_estimated_sections_toc": _safe_int(hierarchy.get("estimated_sections_toc"), 0),
        "step00_has_structure": _safe_bool(
            hierarchy.get("has_structure"),
            _safe_int(hint.get("toc_entry_count"), 0) > 0,
        ),
        "step00_estimated_table_count": _safe_int(
            elements.get("estimated_table_count"), _safe_int(hint.get("estimated_table_count"), 0)
        ),
        "step00_table_pages": _safe_int(
            elements.get("table_pages"), _safe_int(hint.get("table_pages"), 0)
        ),
        "step00_image_pages": _safe_int(
            elements.get("image_pages"), _safe_int(hint.get("image_pages"), 0)
        ),
        "step00_max_tables_per_page": _safe_int(
            elements.get("max_tables_per_page"), _safe_int(hint.get("max_tables_per_page"), 0)
        ),
        "step00_table_pages_drawing": _safe_int(
            elements.get("table_pages_drawing"), _safe_int(hint.get("table_pages_drawing"), 0)
        ),
        "step00_has_formulas": _safe_bool(elements.get("formulas"), _safe_bool(hint_formulas, False)),
        "step00_has_figures": _safe_bool(elements.get("figures"), _safe_bool(hint_figures, False)),
        "step00_has_requirements": _safe_bool(
            elements.get("requirements"), _safe_bool(hint_requirements, False)
        ),
        "step00_has_tables": _safe_bool(elements.get("tables"), _safe_bool(hint_tables, False)),
    }
    feature_meta.update(_timeout_history_features(pdf_path, page_count))

    # --- Priority 1: learn-timeout skill (GradientBoosting, uncapped) ---
    file_size_mb = _safe_float(hint.get("file_size_mb"), 0.0)
    if file_size_mb <= 0 and pdf_path.exists():
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)

    lt_prediction = _predict_via_learn_timeout(
        pdf_path=pdf_path,
        page_count=page_count,
        table_pages=feature_meta.get("step00_table_pages", 0),
        estimated_table_count=feature_meta.get("step00_estimated_table_count", 0),
        image_pages=feature_meta.get("step00_image_pages", 0),
        has_formulas=feature_meta.get("step00_has_formulas", False),
        has_requirements=feature_meta.get("step00_has_requirements", False),
        has_tables=feature_meta.get("step00_has_tables", False),
        has_figures=feature_meta.get("step00_has_figures", False),
        domain=str(hint.get("domain", "general")),
        estimated_sections=feature_meta.get("step00_estimated_sections", 0),
        file_size_mb=file_size_mb,
    )

    if lt_prediction is not None:
        lt_timeout = max(
            MIN_EXTRACT_TIMEOUT_SECONDS,
            min(MAX_EXTRACT_TIMEOUT_SECONDS, int(lt_prediction["recommended_timeout_seconds"])),
        )
        logger.debug(
            f"learn-timeout accepted: {lt_timeout}s "
            f"(estimated={lt_prediction.get('estimated_seconds')}s, "
            f"risk={lt_prediction.get('risk_label')}) for {pdf_path.name}"
        )
        return {
            "timeout_seconds": lt_timeout,
            "timeout_baseline_seconds": lt_timeout,
            "step00_page_count": page_count,
            "step00_estimated_timeout_seconds": estimated_timeout,
            "step00_timeout_source": "learn-timeout",
            "timeout_model_status": "learn-timeout",
            "timeout_model_used": True,
            "timeout_model_risk": round(_safe_float(lt_prediction.get("risk_probability"), 0.0), 6),
            "timeout_model_path": str(LEARN_TIMEOUT_SKILL),
            "timeout_model_metrics": {
                "model_version": lt_prediction.get("model_version", "unknown"),
                "estimated_seconds": lt_prediction.get("estimated_seconds"),
                "confidence_interval": lt_prediction.get("confidence_interval"),
                "risk_label": lt_prediction.get("risk_label"),
            },
            **feature_meta,
        }

    # --- Priority 2: Legacy baseline + create-classifier risk model ---
    by_estimate = estimated_timeout * EXTRACT_TIMEOUT_MULTIPLIER if estimated_timeout > 0 else 0
    by_pages = page_count * SECONDS_PER_PAGE_FLOOR if page_count > 0 else 0

    baseline = max(MIN_EXTRACT_TIMEOUT_SECONDS, by_estimate, by_pages)
    baseline = min(MAX_EXTRACT_TIMEOUT_SECONDS, baseline)

    timeout_model_meta = _predict_timeout_risk(
        pdf_path=pdf_path,
        page_count=page_count,
        step00_estimated_timeout_seconds=estimated_timeout,
        baseline_timeout_seconds=baseline,
        timeout_source=timeout_source,
        feature_meta=feature_meta,
    )
    risk = float(timeout_model_meta.get("timeout_model_risk", 0.0))
    used = bool(timeout_model_meta.get("timeout_model_status") == "ok") and risk >= TIMEOUT_MODEL_MIN_RISK_FOR_ADJUST
    selected = baseline
    if used:
        multiplier_cap = _timeout_multiplier_cap(page_count)
        scaled_multiplier = 1.0 + (max(0.0, min(1.0, risk)) * (multiplier_cap - 1.0))
        scaled = int(round(float(baseline) * scaled_multiplier))
        selected = min(MAX_EXTRACT_TIMEOUT_SECONDS, max(baseline, scaled))

    return {
        "timeout_seconds": selected,
        "timeout_baseline_seconds": baseline,
        "step00_page_count": page_count,
        "step00_estimated_timeout_seconds": estimated_timeout,
        "step00_timeout_source": timeout_source,
        "timeout_model_status": timeout_model_meta.get("timeout_model_status", "unavailable"),
        "timeout_model_used": used,
        "timeout_model_risk": round(risk, 6),
        "timeout_model_path": str(TIMEOUT_MODEL_PATH),
        "timeout_model_metrics": timeout_model_meta.get("timeout_model_metrics", {}),
        **feature_meta,
    }
