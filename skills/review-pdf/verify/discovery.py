"""Document discovery and extraction orchestration for review-pdf.

Purpose:
- discover extractable files (PDF, DOCX, HTML, PPTX, XLSX, etc.) under a root path,
  manage profiles, and run extractions via the unified extractor pipeline.
- route code files (*.py, *.js, etc.) to /treesitter for AST-level parsing.
- check /memory for hard_tail quarantined documents before extraction (via recall()).

Inputs:
- root input path, existing profile lists, extraction options.

Outputs:
- lists of profile paths, extraction event logs.

Failure modes:
- missing fd binary falls back to os.walk; extraction failures are logged as events.
- /memory unavailable: hard-tail quarantine silently skipped (graceful degradation).

This module is the main entry point. Implementation is split across:
- triage.py: constants, quarantine checks, preflight triage, slug generation
- table_reextract.py: table-density prioritization and re-extraction queue
- structured_output.py: structured document output writer for non-PDF formats
- extraction.py: extraction pipeline invocation, timeout estimation, inline review
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



import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from loguru import logger

from .models import DEFAULT_EXTRACTED_RUNS_DIR
from .utils import safe_json

# Re-export from sub-modules for backward compatibility
from .triage import (  # noqa: F401
    EXTRACTABLE_EXTENSIONS,
    CODE_EXTENSIONS,
    GENERATED_DIR_NAMES,
    GENERATED_DIR_PREFIXES,
    TREESITTER_DIR,
    _check_hard_tail_quarantine,
    _hard_tail_cache,
    _preflight_triage,
    _slug_for_doc,
    _slug_for_pdf,
)
from .table_reextract import (  # noqa: F401
    TABLE_REEXTRACT_ENABLED as _TABLE_REEXTRACT_ENABLED,
    TABLE_REEXTRACT_PER_CYCLE as _TABLE_REEXTRACT_PER_CYCLE,
    _find_table_heavy_reextraction_candidates,
    _profile_has_s05c,
    _queue_table_reextractions,
    _read_s00_table_pages,
)
from .structured_output import _write_structured_output  # noqa: F401
from .extraction import (  # noqa: F401
    _already_assessed,
    _assessed_cache,
    _estimate_non_pdf_timeout,
    _extract_document_to_profile,
    _extract_pdf_to_profile,
    _ingest_code_via_treesitter,
    _run_inline_review,
)


def _discover_extractable_files(
    input_path: Path, max_results: int | None = None, include_generated: bool = False
) -> Iterator[Path]:
    """Discover all extractable document files under input_path.

    Yields PDFs first (highest priority), then other document formats.
    Code files are excluded -- they route through /treesitter separately.
    """
    _extractable_suffixes = {ext.lower() for ext in EXTRACTABLE_EXTENSIONS}

    def is_generated_path(path: Path) -> bool:
        parts = [part.lower() for part in path.parts]
        for part in parts:
            if part in GENERATED_DIR_NAMES:
                return True
            if any(part.startswith(prefix) for prefix in GENERATED_DIR_PREFIXES):
                return True
        return False

    if input_path.is_file():
        if input_path.suffix.lower() in _extractable_suffixes and (
            include_generated or not is_generated_path(input_path.resolve())
        ):
            yield input_path
        return

    # Use fd/fdfind with -e (extension) flags.
    # On Ubuntu, fd is installed as 'fdfind'.
    fd_bin = "fdfind" if shutil.which("fdfind") else "fd"
    cmd = [
        fd_bin,
        "--hidden",
        "--no-ignore",
        "--follow",
    ]
    for ext in sorted(EXTRACTABLE_EXTENSIONS):
        cmd.extend(["-e", ext.lstrip(".")])
    if not include_generated:
        for pattern in (
            "**/extracted_runs/**",
            "**/debug_output/**",
            "**/reports/**",
            "**/results/**",
            "**/results_iteration_*/**",
            "**/results_iter*/**",
        ):
            cmd.extend(["--exclude", pattern])
    if max_results is not None and max_results > 0:
        # Request more than needed so we can prioritize PDFs
        cmd.extend(["--max-results", str(max_results * 3)])
    # fd requires a match-all pattern before the search path
    cmd.extend([".", str(input_path)])

    def _yield_prioritized(candidates: list[Path], limit: int | None) -> Iterator[Path]:
        """Yield PDFs first (table-heavy PDFs highest priority), then other formats."""
        pdfs = [c for c in candidates if c.suffix.lower() == ".pdf"]
        others = [c for c in candidates if c.suffix.lower() != ".pdf"]

        # Sort PDFs by table density if we can infer it from corpus profiles.
        # This ensures table-heavy PDFs are extracted first, feeding the
        # continuous classifier learning loop.
        if _TABLE_REEXTRACT_ENABLED and pdfs:
            _table_score_cache: dict[str, int] = {}
            for p in pdfs:
                # Check if there's a results/<slug>/00_profile_detector/profile.json
                slug = _slug_for_doc(p)
                for parent in p.parents:
                    rd = parent / "results" / slug / "00_profile_detector" / "profile.json"
                    if rd.exists():
                        _table_score_cache[str(p)] = _read_s00_table_pages(rd)
                        break
            # Sort: table-heavy first, then alphabetical for consistency
            pdfs.sort(key=lambda p: (-_table_score_cache.get(str(p), 0), p.name))

        count = 0
        for c in pdfs + others:
            if limit is not None and count >= limit:
                return
            yield c
            count += 1

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if proc.returncode == 0:
            raw: list[Path] = []
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                candidate = Path(line.strip()).resolve()
                if include_generated or not is_generated_path(candidate):
                    raw.append(candidate)
            yield from _yield_prioritized(raw, max_results)
            return
        logger.warning(
            f"fd discovery returned non-zero ({proc.returncode}); falling back to os.walk"
        )
    except FileNotFoundError:
        logger.warning("fd not available; falling back to os.walk for discovery")
    except subprocess.TimeoutExpired:
        logger.warning(
            f"fd discovery timed out under {input_path}; falling back to os.walk"
        )

    # os.walk fallback -- collect then prioritize
    raw_walk: list[Path] = []
    for root_dir, _, files in os.walk(input_path):
        if not include_generated:
            parts = [part.lower() for part in Path(root_dir).parts]
            if any(
                part in GENERATED_DIR_NAMES
                or any(part.startswith(prefix) for prefix in GENERATED_DIR_PREFIXES)
                for part in parts
            ):
                continue
        for name in files:
            candidate = (Path(root_dir) / name).resolve()
            if candidate.suffix.lower() not in _extractable_suffixes:
                continue
            if not include_generated and is_generated_path(candidate):
                continue
            raw_walk.append(candidate)
    yield from _yield_prioritized(raw_walk, max_results)


# Backward compatibility alias
_discover_pdf_files = _discover_extractable_files


def _profile_source_set(profiles: List[Path]) -> set[str]:
    """Build a set of resolved source file paths from profile JSON files."""
    sources: set[str] = set()
    for profile_path in profiles:
        profile = safe_json(profile_path)
        source = profile.get("file")
        if isinstance(source, str) and source:
            sources.add(str(Path(source).resolve()))
    return sources


def _filter_profiles(
    profiles: List[Path], *, include_generated: bool
) -> List[Path]:
    """Filter profiles, optionally excluding those from generated directories."""
    if include_generated:
        return profiles

    filtered: List[Path] = []
    for profile in profiles:
        profile_payload = safe_json(profile)
        source = profile_payload.get("file")
        if isinstance(source, str) and source:
            source_path = Path(source).resolve()
            parts = [part.lower() for part in source_path.parts]
            is_generated_source = any(
                part in GENERATED_DIR_NAMES
                or any(part.startswith(prefix) for prefix in GENERATED_DIR_PREFIXES)
                for part in parts
            )
            if is_generated_source:
                continue
        filtered.append(profile)
    return filtered


# ---------------------------------------------------------------------------
# Merge classifier continuous retraining
# ---------------------------------------------------------------------------

_RETRAIN_STATE_FILE = Path("/tmp/merge_classifier_retrain_state.json")
_RETRAIN_INTERVAL_SECONDS = 3600 * 4  # Retrain at most every 4 hours
_RETRAIN_MIN_NEW_PROFILES = 20  # Need at least 20 new S05c profiles since last retrain

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_COLLECT_SCRIPT = _SKILLS_DIR / "create-table-classifier" / "scripts" / "collect_merge_data.py"
_CLASSIFIER_LAB = _SKILLS_DIR / "classifier-lab"


def _maybe_retrain_merge_classifier(corpus_root: Path) -> None:
    """Check if enough new training data has accumulated and retrain if so.

    This runs after each extraction cycle. It:
    1. Counts S05c profiles vs last retrain count
    2. If enough new data (>= _RETRAIN_MIN_NEW_PROFILES), runs collect + retrain
    3. Updates state file with timestamp and profile count
    """
    import json as _json

    try:
        state = {}
        if _RETRAIN_STATE_FILE.exists():
            state = _json.loads(_RETRAIN_STATE_FILE.read_text())

        last_retrain = state.get("last_retrain_time", 0)
        last_s05c_count = state.get("s05c_count", 0)

        # Rate limit: don't retrain more than once per interval
        if time.time() - last_retrain < _RETRAIN_INTERVAL_SECONDS:
            return

        # Count current S05c profiles
        current_s05c = 0
        results_dir = corpus_root / "results"
        if results_dir.exists():
            for run_dir in results_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                s05c = run_dir / "05c_merged_tables" / "05c_merged_tables.json"
                if s05c.exists():
                    current_s05c += 1

        new_since_retrain = current_s05c - last_s05c_count
        if new_since_retrain < _RETRAIN_MIN_NEW_PROFILES:
            return

        print(
            f"review-pdf merge_classifier_retrain "
            f"new_s05c={new_since_retrain} total_s05c={current_s05c} "
            f"triggering retrain...",
            flush=True,
        )

        # Step 1: Collect new training data
        if _COLLECT_SCRIPT.exists():
            try:
                proc = subprocess.run(
                    ["python3", str(_COLLECT_SCRIPT), str(corpus_root),
                     "--skip-images", "--limit", "2000"],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(_COLLECT_SCRIPT.parent.parent),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if proc.returncode == 0:
                    print(
                        f"review-pdf merge_classifier_data_collected stdout={proc.stdout[-200:] if proc.stdout else ''}",
                        flush=True,
                    )
                else:
                    logger.warning(f"collect_merge_data failed: {proc.stderr[-300:] if proc.stderr else ''}")
                    return
            except Exception as exc:
                logger.warning(f"collect_merge_data error: {exc}")
                return

        # Step 2: Retrain with classifier-lab
        features_jsonl = _SKILLS_DIR / "create-table-classifier" / "data" / "merge_features.jsonl"
        if features_jsonl.exists() and _CLASSIFIER_LAB.exists():
            try:
                retrain_cmd = [
                    str(_CLASSIFIER_LAB / "run.sh"), "tabular-benchmark",
                    "--labels-jsonl", str(features_jsonl),
                    "--backbones", "logistic_regression,gradient_boosting,random_forest",
                    "--output-dir", str(_SKILLS_DIR / "create-table-classifier" / "models" / "merge-classifier-final"),
                ]
                proc = subprocess.run(
                    retrain_cmd, capture_output=True, text=True, timeout=600,
                    cwd=str(_CLASSIFIER_LAB),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if proc.returncode == 0:
                    print(
                        f"review-pdf merge_classifier_retrained "
                        f"s05c_count={current_s05c}",
                        flush=True,
                    )
                else:
                    logger.warning(f"classifier retrain failed: {proc.stderr[-300:] if proc.stderr else ''}")
            except Exception as exc:
                logger.warning(f"classifier retrain error: {exc}")

        # Update state
        state["last_retrain_time"] = time.time()
        state["s05c_count"] = current_s05c
        _RETRAIN_STATE_FILE.write_text(_json.dumps(state))

    except Exception as exc:
        logger.warning(f"merge classifier retrain check failed: {exc}")


def ensure_profiles(
    *,
    input_path: Path,
    profiles: List[Path],
    extract_missing: bool,
    extracted_runs_dir: Path,
    extractor_mode: str,
    max_new_profiles: int | None = None,
    include_generated: bool = False,
    inline_review: bool = False,
    corpus_root: Path | None = None,
    inline_review_run_id: str = "",
) -> Tuple[List[Path], List[Dict[str, Any]]]:
    """Discover extractable documents without profiles and extract them.

    Handles all formats supported by the extractor provider registry.
    Code files are routed to /treesitter instead.
    Returns the merged profile list and a list of extraction event dicts.
    """
    if not extract_missing:
        return profiles, []
    if max_new_profiles == 0:
        return profiles, []

    extracted_runs_dir.mkdir(parents=True, exist_ok=True)
    existing_sources = _profile_source_set(profiles)
    existing_run_dirs = [profile.parent.parent.resolve() for profile in profiles]
    events: List[Dict[str, Any]] = []
    new_count = 0
    merged = list(profiles)

    # Continuous learning: queue table-heavy PDFs for re-extraction with classifier.
    # This removes them from existing_sources so the discovery loop picks them up.
    reextract_count = _queue_table_reextractions(
        profiles, existing_sources, extracted_runs_dir,
        input_path=input_path,
        corpus_root=corpus_root,
        max_reextracts=_TABLE_REEXTRACT_PER_CYCLE,
    )

    discovery_limit = max_new_profiles if max_new_profiles is not None else None
    print(
        "review-pdf discover_docs "
        f"root={input_path} "
        f"max_new_profiles={max_new_profiles if max_new_profiles is not None else 'unbounded'}",
        flush=True,
    )
    scanned = 0
    code_ingested = 0
    for doc_path in _discover_extractable_files(
        input_path,
        max_results=discovery_limit,
        include_generated=include_generated,
    ):
        scanned += 1
        if scanned == 1 or scanned % 100 == 0:
            print(
                "review-pdf discover_progress "
                f"scanned={scanned} extracted_new={new_count} "
                f"latest={doc_path}",
                flush=True,
            )
        if max_new_profiles is not None and new_count >= max_new_profiles:
            break
        resolved = str(doc_path.resolve())
        if resolved in existing_sources:
            continue
        doc_resolved = doc_path.resolve()
        if any(run_dir in doc_resolved.parents for run_dir in existing_run_dirs):
            continue

        is_pdf = doc_path.suffix.lower() == ".pdf"

        # Hard-tail quarantine: skip documents previously marked as hard_tail in /memory.
        if _check_hard_tail_quarantine(doc_path):
            print(
                "review-pdf discover_progress "
                f"status=hard_tail_quarantined doc={resolved}",
                flush=True,
            )
            events.append({"pdf": resolved, "status": "hard_tail_quarantined"})
            continue

        # Preflight triage: only for PDFs (fitz-based corruption/security check).
        # Non-PDFs don't need PyMuPDF validation.
        if is_pdf:
            triage = _preflight_triage(doc_path)
            if triage:
                reason = triage["reason"]
                detail = triage.get("detail", "")
                security = triage.get("security", False)
                print(
                    "review-pdf extract_missing "
                    f"status=preflight_failed "
                    f"reason={reason} detail={detail} security={security} "
                    f"doc={resolved}",
                    flush=True,
                )
                events.append({"pdf": resolved, "status": "preflight_failed", **triage})
                continue

        profile_path, timeout_meta = _extract_document_to_profile(
            doc_path=doc_path,
            extracted_runs_dir=extracted_runs_dir,
            extractor_mode=extractor_mode,
        )
        if profile_path is None:
            timed_out = bool(timeout_meta.get("extract_timed_out"))
            missing_structural = bool(timeout_meta.get("extract_missing_structural"))
            stderr_tail = timeout_meta.get("extract_stderr_tail", "").replace("\n", " | ")[:200]
            stdout_tail = timeout_meta.get("extract_stdout_tail", "").replace("\n", " | ")[:200]
            rc = timeout_meta.get("extract_returncode", "")
            print(
                "review-pdf extract_missing "
                f"status=extract_failed timed_out={1 if timed_out else 0} "
                f"missing_structural={1 if missing_structural else 0} "
                f"rc={rc} "
                f"stderr={stderr_tail!r} "
                f"stdout_tail={stdout_tail!r} "
                f"doc={resolved}",
                flush=True,
            )
            events.append(
                {"pdf": resolved, "status": "extract_failed", **timeout_meta}
            )
            continue
        if str(timeout_meta.get("timeout_model_status")) in ("existing_profile", "existing_profile_backfilled_structural"):
            merged.append(profile_path)
            existing_sources.add(resolved)
            print(
                "review-pdf extract_missing "
                "status=cached_profile "
                f"doc={resolved}",
                flush=True,
            )
            event = {
                "pdf": resolved,
                "status": "cached_profile",
                "profile_path": str(profile_path),
                **timeout_meta,
            }

            # Inline review for cached profiles -- the point is to LEARN,
            # not just scan past them.  Score, persona-review, store in
            # /memory, remediate if WARN/FAIL.
            # Skip if already assessed -- re-reviewing unchanged extractions
            # produces identical results (flat trajectory).
            # Set FORCE_REVIEW=1 to bypass (recalibration after pipeline fixes).
            force_review = os.environ.get("FORCE_REVIEW", "") == "1"
            if inline_review and corpus_root is not None:
                if not force_review and _already_assessed(doc_path):
                    print(
                        "review-pdf inline_review_skip "
                        f"reason=already_assessed doc={resolved}",
                        flush=True,
                    )
                    event["inline_review"] = {"skipped": True, "reason": "already_assessed"}
                    events.append(event)
                    continue
                review_result = _run_inline_review(
                    pdf_path=doc_path,
                    corpus_root=corpus_root,
                    extracted_runs_dir=extracted_runs_dir,
                    run_id=inline_review_run_id,
                )
                if review_result is not None:
                    if review_result.get("status") in ("import_error", "runtime_error"):
                        event["inline_review"] = {
                            "skipped": True,
                            "reason": review_result["status"],
                            "error": review_result.get("error", ""),
                        }
                    else:
                        event["inline_review"] = {
                            "verdict": review_result.get("final_verdict", "FAIL"),
                            "score": review_result.get("final_score", 0.0),
                            "iterations": review_result.get("iterations", 0),
                            "converged": review_result.get("converged", False),
                        }
                        print(
                            "review-pdf inline_review "
                            f"verdict={review_result.get('final_verdict')} "
                            f"score={review_result.get('final_score', 0.0):.3f} "
                            f"iterations={review_result.get('iterations', 0)} "
                            f"converged={review_result.get('converged', False)} "
                            f"doc={resolved}",
                            flush=True,
                        )

            events.append(event)
            continue
        merged.append(profile_path)
        existing_sources.add(resolved)
        new_count += 1
        print(
            "review-pdf extract_missing "
            f"status=extracted new_count={new_count} doc={resolved}",
            flush=True,
        )
        event = {
            "pdf": resolved,
            "status": "extracted",
            "profile_path": str(profile_path),
            **timeout_meta,
        }

        # Inline persona review: score + persona review + store in /memory
        if inline_review and corpus_root is not None:
            review_result = _run_inline_review(
                pdf_path=doc_path,
                corpus_root=corpus_root,
                extracted_runs_dir=extracted_runs_dir,
                run_id=inline_review_run_id,
            )
            if review_result is not None:
                if review_result.get("status") in ("import_error", "runtime_error"):
                    event["inline_review"] = {
                        "skipped": True,
                        "reason": review_result["status"],
                        "error": review_result.get("error", ""),
                    }
                else:
                    event["inline_review"] = {
                        "verdict": review_result.get("final_verdict", "FAIL"),
                        "score": review_result.get("final_score", 0.0),
                        "iterations": review_result.get("iterations", 0),
                        "converged": review_result.get("converged", False),
                    }
                    print(
                        "review-pdf inline_review "
                        f"verdict={review_result.get('final_verdict')} "
                        f"score={review_result.get('final_score', 0.0):.3f} "
                        f"iterations={review_result.get('iterations', 0)} "
                        f"converged={review_result.get('converged', False)} "
                        f"doc={resolved}",
                        flush=True,
                    )

        events.append(event)

    dedup: Dict[str, Path] = {}
    for profile_path in merged:
        dedup[str(profile_path.resolve())] = profile_path

    # Continuous learning: trigger classifier retrain if enough new S05c data.
    if _TABLE_REEXTRACT_ENABLED and new_count > 0:
        _maybe_retrain_merge_classifier(input_path)

    return list(dedup.values()), events


def filter_profiles(
    profiles: List[Path], *, include_generated: bool
) -> List[Path]:
    """Public wrapper for profile filtering."""
    return _filter_profiles(profiles, include_generated=include_generated)
