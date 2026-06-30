"""Document extraction orchestration and timeout estimation.

Handles the core extraction pipeline invocation for both PDF and non-PDF
formats, including timeout estimation (trained regressor + heuristic fallback),
inline persona review, and assessment deduplication via /memory.
"""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()



import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from .structured_output import _write_structured_output
from .timeout import (
    MIN_EXTRACT_TIMEOUT_SECONDS,
    TIMEOUT_MODEL_PATH,
    _safe_float,
    _safe_int,
    estimate_extract_timeout_seconds,
)
from .triage import _slug_for_doc

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Inline review helpers
# ---------------------------------------------------------------------------

def _run_inline_review(
    *,
    pdf_path: Path,
    corpus_root: Path,
    extracted_runs_dir: Path,
    run_id: str = "",
) -> Dict[str, Any] | None:
    """Run inline persona review loop on a freshly extracted PDF.

    Lazy-imports inline_review_loop to avoid hard dependency.
    Returns the review_loop() result dict, or None on import/runtime failure.
    """
    try:
        import sys as _sys
        _quality_check_dir = str(
            Path(__file__).resolve().parents[2] / "extractor-quality-check"
        )
        if _quality_check_dir not in _sys.path:
            _sys.path.insert(0, _quality_check_dir)
        from inline_review_loop import review_loop
        return review_loop(
            pdf_path=pdf_path,
            corpus_root=corpus_root,
            extracted_runs_dir=extracted_runs_dir,
            max_iterations=3,
            run_id=run_id,
        )
    except ImportError as exc:
        print(f"review-pdf inline_review IMPORT_ERROR: {exc}", flush=True)
        logger.warning(f"inline_review_loop not available — skipping inline review: {exc}")
        return {"status": "import_error", "error": str(exc)}
    except Exception as exc:
        print(f"review-pdf inline_review ERROR: {exc}", flush=True)
        logger.error(f"Inline review failed for {pdf_path}: {exc}")
        return {"status": "runtime_error", "error": str(exc)}


_assessed_cache: dict[str, float] = {}  # pdf_hash -> timestamp
_ASSESSED_CACHE_TTL = 3600.0  # 1 hour — re-extracted PDFs get re-reviewed


def _already_assessed(pdf_path: Path) -> bool:
    """Check if /memory already has a pdf_assessment for this file.

    Uses a process-local TTL cache so we only query /memory once per PDF per
    hour.  After TTL expires, we re-check /memory (re-extracted PDFs may have
    a different hash or the assessment may have been superseded).
    Returns False on any error (fail-open: review proceeds).
    """
    try:
        p = pdf_path.resolve()
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        pdf_hash = h.hexdigest()[:16]
    except Exception:
        return False

    now = time.monotonic()
    cached_at = _assessed_cache.get(pdf_hash)
    if cached_at is not None and (now - cached_at) < _ASSESSED_CACHE_TTL:
        return True

    try:
        import sys as _sys
        _quality_check_dir = str(
            Path(__file__).resolve().parents[2] / "extractor-quality-check"
        )
        if _quality_check_dir not in _sys.path:
            _sys.path.insert(0, _quality_check_dir)
        from review_memory import assessment_exists
        exists = assessment_exists(pdf_hash)
        if exists:
            _assessed_cache[pdf_hash] = now
        return exists
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trained timeout regressor for non-PDF formats
# ---------------------------------------------------------------------------

_TIMEOUT_REGRESSOR = None
_TIMEOUT_REGRESSOR_LOADED = False
_REGRESSOR_MODEL_PATH = Path(
    "${HOME}/.claude/skills/create-regressor/models/timeout-estimator__rf/model.joblib"
)
_REGRESSOR_SAFETY_MULTIPLIER = 3.0  # predict * 3 to avoid premature kills
_REGRESSOR_MIN_TIMEOUT = 90          # floor: full pipeline overhead (subprocess + section build + ArangoDB)
_REGRESSOR_MAX_TIMEOUT = 300        # ceiling: never exceed 5 min for non-PDFs


def _load_timeout_regressor():
    """Lazy-load the trained RF timeout regressor (dict with model + vectorizer)."""
    global _TIMEOUT_REGRESSOR, _TIMEOUT_REGRESSOR_LOADED
    if _TIMEOUT_REGRESSOR_LOADED:
        return _TIMEOUT_REGRESSOR
    _TIMEOUT_REGRESSOR_LOADED = True
    try:
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        import joblib
        if _REGRESSOR_MODEL_PATH.exists():
            _TIMEOUT_REGRESSOR = joblib.load(_REGRESSOR_MODEL_PATH)
    except Exception:
        pass
    return _TIMEOUT_REGRESSOR


def _estimate_non_pdf_timeout(doc_path: str) -> dict:
    """Estimate extraction timeout for non-PDF documents using trained regressor.

    Falls back to conservative heuristic if the model is unavailable.
    """
    p = Path(doc_path)
    ext = p.suffix.lower()
    try:
        file_size_mb = p.stat().st_size / (1024 * 1024)
    except OSError:
        file_size_mb = 0.0

    # Build feature vector matching training schema
    features = {
        "format": ext,
        "page_count": 0,
        "file_size_mb": file_size_mb,
        "domain": "unknown",
        "route": "fast",
        "complexity_score": 0,
        "detected_preset": "unknown",
        "columns": 1,
        "estimated_sections": 0,
        "has_structure": False,
        "section_style": "unknown",
        "font_body_size": 0.0,
        "has_tables": False,
        "table_pages": 0,
        "has_figures": False,
        "image_pages": 0,
        "has_formulas": False,
        "has_requirements": False,
        "max_tables_per_page": 0,
        "has_toc": False,
        "toc_entry_count": 0,
        "estimated_timeout_seconds": 0,
    }

    predicted_ms = None
    model_used = False
    regressor = _load_timeout_regressor()

    if regressor is not None and isinstance(regressor, dict):
        try:
            model = regressor["model"]
            vectorizer = regressor["vectorizer"]
            X = vectorizer.transform([features])
            predicted_ms = float(model.predict(X)[0])
            model_used = True
        except Exception:
            predicted_ms = None

    if predicted_ms is not None and predicted_ms > 0:
        timeout_s = max(
            _REGRESSOR_MIN_TIMEOUT,
            min(_REGRESSOR_MAX_TIMEOUT, predicted_ms / 1000.0 * _REGRESSOR_SAFETY_MULTIPLIER),
        )
    else:
        # Fallback: conservative heuristic
        _light = {".html", ".htm", ".md", ".markdown", ".rst", ".txt", ".text",
                  ".log", ".csv", ".tsv", ".json", ".jsonl", ".xml"}
        timeout_s = 60 if ext in _light else 120

    return {
        "timeout_seconds": timeout_s,
        "timeout_baseline_seconds": timeout_s,
        "step00_page_count": 0,
        "step00_estimated_timeout_seconds": predicted_ms / 1000.0 if predicted_ms else 0,
        "step00_estimated_sections": 0,
        "step00_estimated_sections_regex": 0,
        "step00_estimated_sections_font": 0,
        "step00_estimated_sections_toc": 0,
        "step00_has_structure": False,
        "step00_estimated_table_count": 0,
        "step00_table_pages": 0,
        "step00_image_pages": 0,
        "step00_max_tables_per_page": 0,
        "step00_table_pages_drawing": 0,
        "step00_has_formulas": False,
        "step00_has_figures": False,
        "step00_has_requirements": False,
        "step00_has_tables": False,
        "history_pdf_attempts": 0,
        "history_pdf_timeout_count": 0,
        "history_pdf_timeout_rate": 0.0,
        "history_pdf_last_timeout_seconds": 0,
        "history_pdf_avg_timeout_seconds": 0,
        "history_page_bucket_attempts": 0,
        "history_page_bucket_timeout_count": 0,
        "history_page_bucket_timeout_rate": 0.0,
        "history_page_bucket_last_timeout_seconds": 0,
        "history_page_bucket_avg_timeout_seconds": 0,
        "step00_timeout_source": "regressor_rf" if model_used else "heuristic_fallback",
        "timeout_model_status": "regressor_rf" if model_used else "fallback",
        "timeout_model_used": model_used,
        "timeout_model_risk": 0.0,
        "timeout_model_path": str(_REGRESSOR_MODEL_PATH),
        "timeout_model_metrics": {"predicted_ms": predicted_ms} if predicted_ms else {},
    }


def _extract_document_to_profile(
    *,
    doc_path: Path,
    extracted_runs_dir: Path,
    extractor_mode: str,
) -> tuple[Path | None, Dict[str, Any]]:
    """Run the extractor pipeline on a document and return (profile_path, timeout_meta).

    Handles PDF validation, timeout estimation, structured output parsing for
    non-PDF formats, and stale run directory cleanup.
    """
    is_pdf = doc_path.suffix.lower() == ".pdf"
    run_dir = extracted_runs_dir / _slug_for_doc(doc_path)
    profile_path = run_dir / "00_profile_detector" / "profile.json"
    structural_path = run_dir / "11_json_exporter" / "structural.json"
    stale_profile_missing_structural = False
    if profile_path.exists():
        if structural_path.exists():
            return profile_path, {
                "timeout_seconds": 0,
                "timeout_baseline_seconds": 0,
                "step00_page_count": 0,
                "step00_estimated_timeout_seconds": 0,
                "step00_estimated_sections": 0,
                "step00_estimated_sections_regex": 0,
                "step00_estimated_sections_font": 0,
                "step00_estimated_sections_toc": 0,
                "step00_has_structure": False,
                "step00_estimated_table_count": 0,
                "step00_table_pages": 0,
                "step00_image_pages": 0,
                "step00_max_tables_per_page": 0,
                "step00_table_pages_drawing": 0,
                "step00_has_formulas": False,
                "step00_has_figures": False,
                "step00_has_requirements": False,
                "step00_has_tables": False,
                "history_pdf_attempts": 0,
                "history_pdf_timeout_count": 0,
                "history_pdf_timeout_rate": 0.0,
                "history_pdf_last_timeout_seconds": 0,
                "history_pdf_avg_timeout_seconds": 0,
                "history_page_bucket_attempts": 0,
                "history_page_bucket_timeout_count": 0,
                "history_page_bucket_timeout_rate": 0.0,
                "history_page_bucket_last_timeout_seconds": 0,
                "history_page_bucket_avg_timeout_seconds": 0,
                "step00_timeout_source": "existing_profile",
                "timeout_model_status": "existing_profile",
                "timeout_model_used": False,
                "timeout_model_risk": 0.0,
                "timeout_model_path": str(TIMEOUT_MODEL_PATH),
                "timeout_model_metrics": {},
            }
        stale_profile_missing_structural = True

    mode_flag = "--offline"
    if extractor_mode == "fast":
        mode_flag = "--fast"
    if extractor_mode == "accurate":
        mode_flag = "--accurate"

    # Timeout estimation: use trained regressor for all formats, fall back to
    # heuristic-based estimator for PDFs or conservative defaults for non-PDFs.
    if is_pdf:
        timeout_meta = estimate_extract_timeout_seconds(doc_path)
    else:
        timeout_meta = _estimate_non_pdf_timeout(doc_path)
    if stale_profile_missing_structural:
        # Try to generate structural.json from existing assembled_content.json
        # or legacy pipeline.duckdb instead of deleting the entire extraction result.
        assembled_path = run_dir / "07_assembled" / "assembled_content.json"
        db_path = run_dir / "pipeline.duckdb"
        if assembled_path.exists() or db_path.exists():
            try:
                import sys as _sys
                _extractor_src = Path(__file__).resolve().parents[4] / "extractor" / "src"
                if str(_extractor_src) not in _sys.path:
                    _sys.path.insert(0, str(_extractor_src))
                from extractor.pipeline.steps.s11_json_exporter import run as _s11_run
                _s11_result = _s11_run(run_dir)
                if _s11_result and Path(_s11_result).exists():
                    print(f"review-pdf backfill_structural ok path={structural_path}", flush=True)
                    return profile_path, {
                        "timeout_seconds": 0,
                        "timeout_baseline_seconds": 0,
                        "step00_page_count": 0,
                        "step00_estimated_timeout_seconds": 0,
                        "step00_estimated_sections": 0,
                        "step00_estimated_sections_regex": 0,
                        "step00_estimated_sections_font": 0,
                        "step00_estimated_sections_toc": 0,
                        "step00_has_structure": False,
                        "step00_estimated_table_count": 0,
                        "step00_table_pages": 0,
                        "step00_image_pages": 0,
                        "step00_max_tables_per_page": 0,
                        "step00_table_pages_drawing": 0,
                        "step00_has_formulas": False,
                        "step00_has_figures": False,
                        "step00_has_requirements": False,
                        "step00_has_tables": False,
                        "history_pdf_attempts": 0,
                        "history_pdf_timeout_count": 0,
                        "history_pdf_timeout_rate": 0.0,
                        "history_pdf_last_timeout_seconds": 0,
                        "history_pdf_avg_timeout_seconds": 0,
                        "history_page_bucket_attempts": 0,
                        "history_page_bucket_timeout_count": 0,
                        "history_page_bucket_timeout_rate": 0.0,
                        "history_page_bucket_last_timeout_seconds": 0,
                        "history_page_bucket_avg_timeout_seconds": 0,
                        "step00_timeout_source": "existing_profile_backfilled_structural",
                        "timeout_model_status": "existing_profile_backfilled_structural",
                        "timeout_model_used": False,
                        "timeout_model_risk": 0.0,
                        "timeout_model_path": str(TIMEOUT_MODEL_PATH),
                        "timeout_model_metrics": {},
                    }
            except Exception as exc:
                print(f"review-pdf backfill_structural failed err={exc}", flush=True)
        # Backfill failed or no duckdb/assembled_content — fall through to re-extraction
        timeout_meta["timeout_model_status"] = "existing_profile_missing_structural_reextract"
        timeout_meta["extract_reused_stale_run_dir"] = False
        try:
            if run_dir.is_symlink():
                # rmtree raises OSError on symlinks; remove symlink + target separately
                target = run_dir.resolve()
                run_dir.unlink()
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
            else:
                shutil.rmtree(run_dir)
        except FileNotFoundError:
            pass
        except Exception as exc:
            timeout_meta["extract_cleanup_error"] = str(exc)
            print(f"review-pdf cleanup_error err={exc} run_dir={run_dir}", flush=True)
            return None, timeout_meta
    extract_timeout = _safe_int(timeout_meta.get("timeout_seconds"), MIN_EXTRACT_TIMEOUT_SECONDS)
    print(
        "review-pdf extract_timeout "
        f"seconds={extract_timeout} "
        f"page_count={timeout_meta.get('step00_page_count', 0)} "
        f"step00_estimated={timeout_meta.get('step00_estimated_timeout_seconds', 0)} "
        f"step00_estimated_sections={timeout_meta.get('step00_estimated_sections', 0)} "
        f"step00_estimated_sections_regex={timeout_meta.get('step00_estimated_sections_regex', 0)} "
        f"step00_estimated_sections_font={timeout_meta.get('step00_estimated_sections_font', 0)} "
        f"step00_estimated_sections_toc={timeout_meta.get('step00_estimated_sections_toc', 0)} "
        f"step00_estimated_table_count={timeout_meta.get('step00_estimated_table_count', 0)} "
        f"step00_table_pages={timeout_meta.get('step00_table_pages', 0)} "
        f"step00_image_pages={timeout_meta.get('step00_image_pages', 0)} "
        f"step00_max_tables_per_page={timeout_meta.get('step00_max_tables_per_page', 0)} "
        f"step00_table_pages_drawing={timeout_meta.get('step00_table_pages_drawing', 0)} "
        f"step00_has_formulas={1 if timeout_meta.get('step00_has_formulas') else 0} "
        f"step00_has_figures={1 if timeout_meta.get('step00_has_figures') else 0} "
        f"step00_has_requirements={1 if timeout_meta.get('step00_has_requirements') else 0} "
        f"step00_has_tables={1 if timeout_meta.get('step00_has_tables') else 0} "
        f"step00_has_structure={1 if timeout_meta.get('step00_has_structure') else 0} "
        f"history_pdf_attempts={timeout_meta.get('history_pdf_attempts', 0)} "
        f"history_pdf_timeout_count={timeout_meta.get('history_pdf_timeout_count', 0)} "
        f"history_pdf_timeout_rate={_safe_float(timeout_meta.get('history_pdf_timeout_rate', 0.0), 0.0):.6f} "
        f"history_pdf_last_timeout_seconds={timeout_meta.get('history_pdf_last_timeout_seconds', 0)} "
        f"history_pdf_avg_timeout_seconds={timeout_meta.get('history_pdf_avg_timeout_seconds', 0)} "
        f"history_page_bucket_attempts={timeout_meta.get('history_page_bucket_attempts', 0)} "
        f"history_page_bucket_timeout_count={timeout_meta.get('history_page_bucket_timeout_count', 0)} "
        f"history_page_bucket_timeout_rate={_safe_float(timeout_meta.get('history_page_bucket_timeout_rate', 0.0), 0.0):.6f} "
        f"history_page_bucket_last_timeout_seconds={timeout_meta.get('history_page_bucket_last_timeout_seconds', 0)} "
        f"history_page_bucket_avg_timeout_seconds={timeout_meta.get('history_page_bucket_avg_timeout_seconds', 0)} "
        f"source={timeout_meta.get('step00_timeout_source', 'fallback')} "
        f"doc={doc_path}",
        flush=True,
    )
    print(
        "review-pdf timeout_model "
        f"status={timeout_meta.get('timeout_model_status', 'unavailable')} "
        f"used={1 if timeout_meta.get('timeout_model_used') else 0} "
        f"risk={timeout_meta.get('timeout_model_risk', 0.0):.4f} "
        f"baseline={timeout_meta.get('timeout_baseline_seconds', extract_timeout)} "
        f"selected={extract_timeout} "
        f"doc={doc_path}",
        flush=True,
    )

    # Skip non-PDF files masquerading as .pdf (e.g. HTML block pages, access-denied responses)
    try:
        file_size = Path(doc_path).stat().st_size
    except OSError:
        file_size = 0
    if is_pdf and file_size > 0:
        try:
            with open(doc_path, "rb") as _fh:
                _header = _fh.read(5)
            if not _header.startswith(b"%PDF"):
                timeout_meta["extract_returncode"] = -1
                timeout_meta["extract_stderr_tail"] = (
                    f"Skipped: not a valid PDF ({file_size} bytes, header={_header[:10]!r}) "
                    f"— likely HTML block page or corrupt download"
                )
                return None, timeout_meta
        except OSError:
            pass  # let extractor handle read errors

    cmd = (
        f"cd {_SKILLS_DIR}/extractor && "
        f'./run.sh "{doc_path}" {mode_flag} --learn --no-interactive --continue-on-error --out "{run_dir}"'
    )
    # For non-PDF batch extraction, skip Schematron LLM (use native HTMLProvider)
    # to avoid hanging on slow/unavailable Ollama endpoints.
    env = None
    if not is_pdf:
        env = os.environ.copy()
        env["EXTRACT_HTML_SKIP_LLM"] = "1"

    # Per-PDF flock: exactly 1 extractor process per PDF at any time.
    # Prevents orphaned workers from supervisor restarts from piling up
    # 79+ extractors on the same file (141 GB RAM incident 2026-03-03).
    import fcntl
    import hashlib
    _lock_dir = Path("/tmp/review_pdf_locks")
    _lock_dir.mkdir(exist_ok=True)
    _lock_name = hashlib.md5(str(doc_path).encode()).hexdigest()[:16]
    _lock_path = _lock_dir / f"{_lock_name}.lock"
    _lock_fd = open(_lock_path, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _lock_fd.close()
        timeout_meta["extract_returncode"] = -1
        timeout_meta["extract_stderr_tail"] = (
            f"Skipped: another extractor is already processing {Path(doc_path).name}"
        )
        return None, timeout_meta

    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=extract_timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            f"review-pdf extract timed out after {extract_timeout}s for {doc_path}"
        )
        timeout_meta["extract_timed_out"] = True
        return None, timeout_meta
    finally:
        _lock_fd.close()

    # Always capture returncode + stdout tail regardless of exit code
    timeout_meta["extract_returncode"] = proc.returncode
    timeout_meta["extract_stdout_tail"] = "\n".join(proc.stdout.splitlines()[-10:])

    if proc.returncode != 0:
        timeout_meta["extract_returncode"] = proc.returncode
        timeout_meta["extract_stderr_tail"] = "\n".join(proc.stderr.splitlines()[-3:])
        # With --continue-on-error, pipeline exits rc=1 even when all stages
        # complete successfully (any individual stage warning triggers non-zero).
        # Check for output files before declaring failure.
        if profile_path.exists() and structural_path.exists():
            timeout_meta["extract_nonzero_but_complete"] = True
            return profile_path, timeout_meta

        # For non-PDFs: structured extractor outputs JSON to stdout.
        # Try to parse it and write to expected locations.
        if not is_pdf and proc.stdout.strip():
            written = _write_structured_output(proc.stdout, run_dir, doc_path)
            if written:
                timeout_meta["extract_nonzero_but_structured_output"] = True
                return profile_path, timeout_meta

        return None, timeout_meta

    # Check standard pipeline output locations (PDF path)
    if profile_path.exists() and structural_path.exists():
        return profile_path, timeout_meta

    # Fallback: forced-preset runs write pipeline_context.json instead of running S00.
    # If structural.json exists but profile.json doesn't, generate a minimal profile.json
    # from pipeline_context.json so downstream scoring works.
    context_json = run_dir / "pipeline_context.json"
    if not profile_path.exists() and structural_path.exists() and context_json.exists():
        try:
            import json as _json
            ctx = _json.loads(context_json.read_text())
            profile_dir = profile_path.parent
            profile_dir.mkdir(parents=True, exist_ok=True)
            minimal_profile = {
                "domain": ctx.get("preset_name", "unknown"),
                "page_count": 0,
                "file_size_mb": 0.0,
                "estimated_timeout_seconds": 0,
                "layout": {},
                "hierarchy": {},
                "elements": {},
                "preset_match": {"matched": ctx.get("preset_name"), "confidence": 1.0, "forced": True},
                "route": "forced_preset",
                "complexity_score": 0.0,
                "thresholds_hit": [],
                "detected_preset": ctx.get("preset_name"),
                "file": str(doc_path),
                "timestamp": ctx.get("timestamp", 0),
                "duration_ms": 0,
            }
            profile_path.write_text(_json.dumps(minimal_profile, indent=2))
            print(f"review-pdf generated_profile_from_context preset={ctx.get('preset_name')} path={profile_path}", flush=True)
            return profile_path, timeout_meta
        except Exception as exc:
            print(f"review-pdf profile_from_context_failed err={exc}", flush=True)

    # For non-PDFs: structured extractor outputs JSON to stdout.
    # Parse and write to expected disk locations.
    if not is_pdf and proc.stdout.strip():
        written = _write_structured_output(proc.stdout, run_dir, doc_path)
        if written:
            return profile_path, timeout_meta

    found = sorted(run_dir.rglob("00_profile_detector/profile.json"))
    if found:
        candidate = found[0]
        candidate_run = candidate.parent.parent
        candidate_structural = candidate_run / "11_json_exporter" / "structural.json"
        if candidate_structural.exists():
            return candidate, timeout_meta
        timeout_meta["extract_missing_structural"] = True
        timeout_meta["extract_structural_path"] = str(candidate_structural)
        timeout_meta["extract_stderr_tail"] = "\n".join(proc.stderr.splitlines()[-10:])
        timeout_meta["extract_stdout_tail"] = "\n".join(proc.stdout.splitlines()[-10:])
        return None, timeout_meta
    timeout_meta["extract_missing_structural"] = True
    timeout_meta["extract_structural_path"] = str(structural_path)
    timeout_meta["extract_stderr_tail"] = "\n".join(proc.stderr.splitlines()[-10:])
    timeout_meta["extract_stdout_tail"] = "\n".join(proc.stdout.splitlines()[-10:])
    return None, timeout_meta


# Backward compatibility alias
_extract_pdf_to_profile = _extract_document_to_profile


def _ingest_code_via_treesitter(
    code_path: Path,
    memory_scope: str = "datalake_code",
) -> bool:
    """Route a code file through /treesitter -> /memory.

    Returns True on success, False on failure.
    """
    from .triage import TREESITTER_DIR

    if not TREESITTER_DIR.exists():
        logger.warning(f"treesitter skill not found at {TREESITTER_DIR}")
        return False
    cmd = (
        f'cd {TREESITTER_DIR} && '
        f'./run.sh symbols "{code_path}" --json --scope "{memory_scope}"'
    )
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 0:
            return True
        logger.warning(
            f"treesitter failed for {code_path} rc={proc.returncode} "
            f"stderr={proc.stderr.splitlines()[-1] if proc.stderr else ''}"
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"treesitter timed out for {code_path}")
    except Exception as exc:
        logger.warning(f"treesitter error for {code_path}: {exc}")
    return False
