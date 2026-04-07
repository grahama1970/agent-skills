#!/usr/bin/env python3
"""
Inline per-PDF reviewer: score + persona review + /memory storage.

Self-contained module that takes a single extracted PDF profile,
scores it against S00 estimates, runs Margaret/Jennifer persona
evaluation, searches /memory for related past reviews, and stores
the structured assessment in ArangoDB.

Usage:
    from inline_reviewer import review_pdf
    result = review_pdf(profile_path, corpus_root)
"""
from __future__ import annotations

from loguru import logger

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# sys.path setup — load verify.* from review-pdf, annealing from this dir
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REVIEW_PDF_DIR = _THIS_DIR.parent / "review-pdf"

_SKILLS_DIR = _THIS_DIR.parent  # pi-mono/.pi/skills — for common.* imports

for _p in [str(_REVIEW_PDF_DIR), str(_THIS_DIR), str(_SKILLS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Evict stale cached modules (safe for long-running processes)
for _mod in list(sys.modules):
    if _mod == "verify" or _mod.startswith("verify."):
        del sys.modules[_mod]

# ---------------------------------------------------------------------------
# Imports from review-pdf/verify
# ---------------------------------------------------------------------------
from verify.analysis import (
    analyze_flattened_data,
    analyze_pdf_source,
    analyze_s11_structural,
    analyze_sections_data,
    extract_s00_estimates,
    resolve_doc_inputs,
)
from verify.scoring import build_issues, dimension_scores, overall_from_dimensions

# ---------------------------------------------------------------------------
# Imports from extractor-quality-check (same dir)
# ---------------------------------------------------------------------------
from annealing import (
    get_coverage_pct,
    jennifer_evaluates,
    margaret_evaluates,
    reconcile,
)

# ---------------------------------------------------------------------------
# Memory integration (split to review_memory.py for line-count limit)
# ---------------------------------------------------------------------------
from review_memory import (
    extract_review_taxonomy as _extract_review_taxonomy,
    search_related_reviews as _search_related_reviews,
    store_assessment as _store_assessment,
    store_lesson_for_failure as _store_lesson_for_failure,
    create_cross_pdf_edges as _create_cross_pdf_edges,
    ingest_content_to_memory as _ingest_content_to_memory,
    find_related_reviews,
)


def _pdf_hash(pdf_path: str | Path) -> str:
    """Compute short hash of PDF file for dedup."""
    p = Path(pdf_path)
    if p.exists():
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    return hashlib.sha256(str(p).encode()).hexdigest()[:16]


def _infer_sector(pdf_path: str) -> str:
    """Infer corpus sector from path components."""
    parts = Path(pdf_path).parts
    known_sectors = {
        "arxiv", "defense", "archive_org", "inbox", "fetcher_results",
        "stress_test_pdfs", "ietf", "nasa", "nist", "dtic", "faa",
        "industry", "adversarial", "edge_cases",
    }
    for part in parts:
        if part.lower() in known_sectors:
            return part.lower()
    return "unknown"


def _build_estimate_delta(estimates: Dict[str, Any], actual: Dict[str, Any]) -> Dict[str, Any]:
    """Build human-readable S00 estimate vs actual extracted comparison.

    Returns dict with per-element deltas for /interview display:
        {"sections": {"estimated": 12, "actual": 8, "missing": 4, "label": "4 missing"},
         "tables": ..., "figures": ..., "requirements": ..., "equations": ...}
    """
    delta: Dict[str, Any] = {}
    _ELEMENT_MAP = {
        "sections": ("estimated_sections", "section_count"),
        "tables": ("estimated_table_count", "table_count"),
        "figures": ("image_pages", "figure_count"),
    }
    for name, (est_key, act_key) in _ELEMENT_MAP.items():
        est = estimates.get(est_key, 0) or 0
        act = actual.get(act_key, 0) or 0
        diff = act - est
        if est == 0 and act == 0:
            label = "none expected, none found"
        elif est == 0:
            label = f"{act} found (none estimated)"
        elif diff == 0:
            label = "match"
        elif diff < 0:
            label = f"{abs(diff)} missing"
        else:
            label = f"{diff} extra"
        delta[name] = {"estimated": est, "actual": act, "diff": diff, "label": label}

    # Requirements: boolean estimate vs count
    est_req = estimates.get("has_requirements", False)
    act_req = actual.get("requirement_count", 0) or 0
    if est_req and act_req == 0:
        delta["requirements"] = {"estimated": True, "actual": 0, "diff": -1, "label": "expected but none found"}
    elif not est_req and act_req > 0:
        delta["requirements"] = {"estimated": False, "actual": act_req, "diff": act_req, "label": f"{act_req} found (none estimated)"}
    else:
        delta["requirements"] = {"estimated": est_req, "actual": act_req, "diff": 0, "label": "match" if est_req else "none expected"}

    # Equations: boolean estimate vs count
    est_eq = estimates.get("has_formulas", False)
    act_eq = actual.get("equation_count", 0) or 0
    if est_eq and act_eq == 0:
        delta["equations"] = {"estimated": True, "actual": 0, "diff": -1, "label": "expected but none found"}
    elif not est_eq and act_eq > 0:
        delta["equations"] = {"estimated": False, "actual": act_eq, "diff": act_eq, "label": f"{act_eq} found (none estimated)"}
    else:
        delta["equations"] = {"estimated": est_eq, "actual": act_eq, "diff": 0, "label": "match" if est_eq else "none expected"}

    # Summary: count elements with gaps
    gaps = [name for name, d in delta.items() if d.get("diff", 0) < 0]
    extras = [name for name, d in delta.items() if isinstance(d.get("diff"), (int, float)) and d["diff"] > 0]
    delta["_summary"] = {
        "gaps": gaps,
        "extras": extras,
        "gap_count": len(gaps),
        "has_gaps": len(gaps) > 0,
    }
    return delta


def _score_single_pdf(profile_path: Path) -> Dict[str, Any]:
    """Score a single PDF from its profile path.

    Returns dict with estimates, actual, source, issues, dims, overall,
    pdf_path, run_dir, and raw Issue objects for escalation.
    """
    inputs = resolve_doc_inputs(profile_path)
    profile_data = json.loads(profile_path.read_text())
    context_path = inputs.get("context_path")
    context_data = json.loads(context_path.read_text()) if context_path and Path(context_path).exists() else {}

    # Get actual counts from best available source
    if inputs.get("structural_path") and Path(inputs["structural_path"]).exists():
        structural_data = json.loads(Path(inputs["structural_path"]).read_text())
        actual = analyze_s11_structural(structural_data)
    elif inputs.get("flattened_path") and Path(inputs["flattened_path"]).exists():
        flat_raw = json.loads(Path(inputs["flattened_path"]).read_text())
        if isinstance(flat_raw, dict):
            flat_raw = flat_raw.get("data", flat_raw.get("items", []))
        actual = analyze_flattened_data(flat_raw)
    elif inputs.get("sections_path") and Path(inputs["sections_path"]).exists():
        sections_data = json.loads(Path(inputs["sections_path"]).read_text())
        actual = analyze_sections_data(sections_data)
    else:
        return {"error": "No structural/flattened/sections data found"}

    estimates = extract_s00_estimates(profile_data, context_data)
    source = analyze_pdf_source(inputs.get("pdf_path"))

    issues, ratio_metrics = build_issues(estimates, actual, source)
    dims = dimension_scores(estimates, actual, source, ratio_metrics)
    overall = overall_from_dimensions(dims, issues)

    # Build human-readable estimate delta: "S00 estimated X, got Y"
    estimate_delta = _build_estimate_delta(estimates, actual)

    return {
        "estimates": estimates,
        "actual": actual,
        "estimate_delta": estimate_delta,
        "source": source,
        "issues": issues,  # raw Issue objects (for escalation)
        "issues_dicts": [
            {"code": i.code, "severity": i.severity, "message": i.message,
             "root_cause": i.root_cause, "recommendation": i.recommendation}
            for i in issues
        ],
        "ratio_metrics": ratio_metrics,
        "dimensions": {
            name: {"score": d["score"], "state": d["state"], "weight": d["weight"]}
            for name, d in dims.items()
        },
        "overall": overall,
        "pdf_path": str(inputs.get("pdf_path", "")),
        "run_dir": str(inputs.get("run_dir", "")),
    }


def review_pdf(
    profile_path: Path,
    corpus_root: Path,
    run_id: str = "",
    max_related_reviews: int = 5,
) -> Dict[str, Any]:
    """Review a single extracted PDF: score, persona evaluate, store in /memory.

    Args:
        profile_path: Path to 00_profile_detector/profile.json
        corpus_root: Root of the corpus directory
        run_id: Optional run identifier
        max_related_reviews: Max related reviews to search from /memory

    Returns:
        {
            "pdf_path": str,
            "pdf_hash": str,
            "overall_score": float,
            "grade": str,
            "verdict": "PASS"|"WARN"|"FAIL",
            "dimensions": dict,
            "issues_dicts": list,
            "margaret": {"verdict": str, "weighted_score": float, "issues": list, "says": str},
            "jennifer": {"verdict": str, "weighted_score": float, "issues": list, "says": str},
            "reconciled": {"decision": str, "consensus": bool, ...},
            "related_reviews": list,
            "escalation_jobs": list,
            "memory_assessment_id": str|None,
            "memory_lesson_id": str|None,
            "timestamp": str,
            "sector": str,
        }
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Step 1: Score the PDF
    score_result = _score_single_pdf(profile_path)
    if "error" in score_result:
        return {
            "pdf_path": str(profile_path),
            "pdf_hash": "",
            "error": score_result["error"],
            "overall_score": 0.0,
            "grade": "F",
            "verdict": "FAIL",
            "dimensions": {},
            "issues_dicts": [],
            "margaret": {"verdict": "FAIL", "weighted_score": 0.0, "issues": ["No data"], "says": "Cannot evaluate without data"},
            "jennifer": {"verdict": "FAIL", "weighted_score": 0.0, "issues": ["No data"], "says": "Cannot evaluate without data"},
            "reconciled": {"decision": "STOP_AND_FIX", "consensus": True},
            "related_reviews": [],
            "escalation_jobs": [],
            "memory_assessment_id": None,
            "memory_lesson_id": None,
            "graph_edge_ids": [],
            "timestamp": timestamp,
            "sector": "unknown",
        }

    pdf_path = score_result["pdf_path"]
    pdf_hash = _pdf_hash(pdf_path) if pdf_path else ""
    sector = _infer_sector(pdf_path) if pdf_path else "unknown"
    overall = score_result["overall"]

    # Step 2: Run persona evaluations
    # Build dimension averages dict for persona functions
    dim_scores_for_persona = {
        name: d["score"] for name, d in score_result["dimensions"].items()
        if d.get("state") not in ("not_available", "unknown")
    }
    _skipped = len(score_result["dimensions"]) - len(dim_scores_for_persona)
    if _skipped:
        print(f"review-pdf inline_review dim_filter skipped={_skipped} measurable={len(dim_scores_for_persona)} pdf={pdf_path}", flush=True)

    # When no dimensions are measurable (scanned images, empty structure),
    # personas cannot evaluate — defer to scoring system's verdict.
    if not dim_scores_for_persona:
        print(f"review-pdf inline_review no_measurable_dims defer_to_scoring verdict={overall['verdict']} pdf={pdf_path}", flush=True)
        margaret_result = {"verdict": overall["verdict"], "weighted_score": overall["score"], "issues": [], "says": "No measurable dimensions — defer to scoring."}
        jennifer_result = {"verdict": overall["verdict"], "weighted_score": overall["score"], "issues": [], "says": "No measurable dimensions — defer to scoring."}
        # SKIP unmeasurable docs (scanned images, empty structure) instead of
        # ESCALATE — escalation floods the queue with docs that cannot improve
        # without OCR/layout upgrades, which are pipeline-level changes.
        reconciled = {"decision": "CONTINUE" if overall["verdict"] == "PASS" else "SKIP", "reason": "no_measurable_dimensions"}
    else:
        fail_ratio = 1.0 if overall["verdict"] == "FAIL" else (0.5 if overall["verdict"] == "WARN" else 0.0)
        critical_count = overall.get("critical_issues", 0)
        critical_ratio = min(1.0, critical_count / 3.0) if critical_count > 0 else 0.0

        # Coverage estimate (for annealing thresholds)
        # Dynamically compute from disk instead of hardcoding to a phase.
        try:
            from convergence_tracker import _estimate_coverage
            coverage_pct = _estimate_coverage(corpus_root)
        except Exception:
            coverage_pct = 93.0  # Fallback to known approximate corpus coverage

        margaret_result = margaret_evaluates(
            coverage_pct=coverage_pct,
            dim_scores=dim_scores_for_persona,
            fail_ratio=fail_ratio,
            critical_ratio=critical_ratio,
            run_metrics={"overall_score": overall["score"]},
            state={},
        )
        jennifer_result = jennifer_evaluates(
            coverage_pct=coverage_pct,
            dim_scores=dim_scores_for_persona,
            fail_ratio=fail_ratio,
            critical_ratio=critical_ratio,
            run_metrics={"overall_score": overall["score"]},
            state={},
        )
        reconciled = reconcile(margaret_result, jennifer_result)

    # Derive effective verdict from reconciled persona decision.
    # Personas use batch-level annealing thresholds (min_score=0.90 at Refinement)
    # which are inappropriate for per-PDF verdicts — individual PDFs can legitimately
    # score below the batch average threshold.  Personas DIAGNOSE but should not
    # escalate a per-PDF verdict to FAIL when scoring says WARN/PASS.
    # They can upgrade PASS→WARN (flag concerns) but not WARN→FAIL.
    _DECISION_TO_VERDICT = {
        "CONTINUE": "PASS",
        "STOP_AND_FIX": "WARN",
        "ESCALATE": "WARN",  # Was FAIL — persona ESCALATE now caps at WARN for per-PDF
    }
    persona_verdict = _DECISION_TO_VERDICT.get(reconciled["decision"], "WARN")
    _VSEV = {"PASS": 0, "WARN": 1, "FAIL": 2}
    effective_verdict = max(
        overall["verdict"], persona_verdict, key=lambda v: _VSEV.get(v, 0)
    )

    # Step 3: Search /memory for related past reviews
    worst_dim = min(
        score_result["dimensions"].items(),
        key=lambda x: x[1]["score"],
    )[0] if score_result["dimensions"] else "unknown"

    related_reviews = _search_related_reviews(
        pdf_hash=pdf_hash,
        sector=sector,
        worst_dimension=worst_dim,
        max_results=max_related_reviews,
    )

    # Step 4: Generate escalation jobs for WARN/FAIL (uses effective verdict)
    escalation_jobs_list = []
    if effective_verdict in ("WARN", "FAIL"):
        try:
            from verify.escalation import escalation_jobs as make_escalation_jobs

            raw_issues = score_result["issues"]
            pdf_p = Path(pdf_path) if pdf_path else None
            run_dir = Path(score_result["run_dir"]) if score_result.get("run_dir") else Path(".")
            esc_jobs = make_escalation_jobs(raw_issues, pdf_p, run_dir, estimates=score_result.get("estimates"))
            escalation_jobs_list = [j.as_dict() for j in esc_jobs]
            issue_codes = [i.code for i in raw_issues] if raw_issues else []
            print(
                f"review-pdf escalation_jobs count={len(escalation_jobs_list)} "
                f"issue_codes={issue_codes[:10]} "
                f"auto_exec={sum(1 for j in escalation_jobs_list if j.get('auto_executable'))} "
                f"pdf={pdf_path}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"review-pdf escalation_error error={exc!r} pdf={pdf_path}",
                flush=True,
            )

    # Extract taxonomy for the review result (enables multi-hop graph traversal)
    review_summary = (
        f"{sector} {effective_verdict} score={overall['score']:.3f} "
        f"margaret={margaret_result['verdict']} jennifer={jennifer_result['verdict']} "
        f"{' '.join(score_result['dimensions'].keys())}"
    )
    taxonomy = _extract_review_taxonomy(review_summary)

    # Build result
    result = {
        "pdf_path": pdf_path,
        "pdf_hash": pdf_hash,
        "overall_score": overall["score"],
        "grade": overall["grade"],
        "verdict": effective_verdict,
        "scoring_verdict": overall["verdict"],  # raw scoring pipeline verdict
        "estimate_delta": score_result.get("estimate_delta", {}),
        "dimensions": score_result["dimensions"],
        "issues_dicts": score_result["issues_dicts"],
        "estimates": score_result.get("estimates", {}),  # S00 metadata for remediation tagging
        "margaret": margaret_result,
        "jennifer": jennifer_result,
        "reconciled": reconciled,
        "related_reviews": related_reviews,
        "escalation_jobs": escalation_jobs_list,
        "memory_assessment_id": None,
        "memory_lesson_id": None,
        "timestamp": timestamp,
        "sector": sector,
        "bridge_tags": taxonomy["bridge_tags"],
        "taxonomy": taxonomy["collection_tags"],
    }

    # Step 5: Store in /memory
    assessment_key, assessment_problem = _store_assessment(result, run_id)
    result["memory_assessment_id"] = assessment_key
    result["memory_assessment_problem"] = assessment_problem

    # Step 5b: Create cross-PDF graph edges (supersedes + related)
    edge_ids = _create_cross_pdf_edges(
        assessment_key, related_reviews, result,
        from_problem=assessment_problem,
    )
    result["graph_edge_ids"] = edge_ids

    # Step 5c: Ingest extracted CONTENT into /memory (PASS/WARN only)
    # This is what enables multi-hop graph traversal with taxonomy bridge_tags.
    # Without this, only assessment lessons reach /memory — the actual extracted
    # text/tables/figures never get indexed for persona queries.
    # Uses /memory learn() API exclusively — NO bespoke ArangoDB connections.
    result["content_ingested"] = None
    if effective_verdict in ("PASS", "WARN"):
        try:
            ingest_result = _ingest_content_to_memory(
                profile_path=profile_path,
                pdf_hash=pdf_hash,
                pdf_path=pdf_path,
                sector=sector,
                assessment_key=assessment_key,
                extraction_grade=overall.get("grade", ""),
                extraction_score=overall.get("score", 0.0),
            )
            result["content_ingested"] = ingest_result
            if ingest_result and ingest_result.get("learned", 0) > 0:
                print(
                    f"review-pdf content_ingest learned={ingest_result['learned']} "
                    f"edges={ingest_result.get('edges', 0)} "
                    f"pdf={pdf_path}",
                    flush=True,
                )
                # Record in discovery cache so we don't re-extract
                try:
                    from pdf_discovery import mark_ingested
                    mark_ingested(Path(pdf_path))
                except Exception:
                    pass  # Non-critical — next run will still match on extracted_runs/
        except Exception as exc:
            print(
                f"review-pdf content_ingest_error error={exc!r} pdf={pdf_path}",
                flush=True,
            )
            result["content_ingested"] = {"error": str(exc)}

    # Step 5d: Shadow S00 co-evolutionary feedback
    # Store the actual table extraction outcome as training signal for the
    # Shadow S00 classifier. This enables the co-evolutionary loop:
    # S00 features → shadow classifier → S05 strategy → inline review → feedback → retrain
    try:
        # Add create-table-classifier scripts to path for feedback module
        _fb_scripts = str(Path(__file__).resolve().parent.parent / "create-table-classifier" / "scripts")
        if _fb_scripts not in sys.path:
            sys.path.insert(0, _fb_scripts)
        import importlib
        _shadow_fb_mod = importlib.import_module("shadow_s00_feedback")
        # Load S00 profile for features
        s00_profile = {}
        s00_profile_path = profile_path.parent / "00_profile_detector" / "profile.json"
        if s00_profile_path.exists():
            s00_profile = json.loads(s00_profile_path.read_text())
        elif profile_path.exists():
            s00_profile = json.loads(profile_path.read_text())

        if s00_profile:
            # Get table_fidelity from dimensions
            dims = score_result.get("dimensions", {})
            table_fid = dims.get("table_fidelity", {})
            table_fid_score = table_fid.get("score", 0.0) if isinstance(table_fid, dict) else 0.0

            # Read S05 output for actual table counts and shadow prediction
            actual_tables = 0
            stream_tables = 0
            shadow_pred = None
            run_dir = profile_path.parent.parent  # profile_path is .../00_profile_detector/profile.json
            s05_path = run_dir / "05_table_extractor" / "json_output" / "05_tables.json"
            if s05_path.exists():
                try:
                    s05_data = json.loads(s05_path.read_text())
                    actual_tables = s05_data.get("table_count", 0)
                    # Count stream-mode tables from strategies
                    qs = s05_data.get("quality_summary", {})
                    shadow_pred = qs.get("shadow_s00") or None
                    # Count tables extracted via stream strategy
                    for t in s05_data.get("tables", []):
                        if "stream" in (t.get("strategy", "") or "").lower():
                            stream_tables += 1
                except (json.JSONDecodeError, OSError):
                    pass

            _shadow_fb_mod.record_shadow_feedback(
                pdf_hash=pdf_hash,
                s00_profile=s00_profile,
                s05_actual_tables=actual_tables,
                s05_stream_tables=stream_tables,
                table_fidelity_score=table_fid_score,
                shadow_prediction=shadow_pred,
                source_pdf=str(pdf_path),
            )
            # Check if enough feedback accumulated for retrain
            if _shadow_fb_mod.check_retrain():
                try:
                    retrain_result = _shadow_fb_mod.trigger_retrain()
                    print(f"[shadow-lego] Retrained Shadow S00: {retrain_result}", flush=True)
                except Exception as e:
                    print(f"[shadow-lego] Retrain failed: {e}", flush=True)
    except Exception as e:
        logger.debug("inline reviewer feedback failed: {}", e)

    # Step 6: For WARN/FAIL (effective verdict), also store a lesson
    if effective_verdict in ("WARN", "FAIL"):
        lesson_key = _store_lesson_for_failure(result, assessment_key, assessment_problem)
        result["memory_lesson_id"] = lesson_key

    return result


if __name__ == "__main__":
    import typer

    def _cli(
        profile_path: Path = typer.Argument(..., help="Path to profile.json"),
        corpus_root: Path = typer.Option(Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "extractor_corpus", help="Corpus root directory"),
        run_id: str = typer.Option("", help="Run identifier"),
        output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Inline PDF reviewer."""
        result = review_pdf(profile_path, corpus_root, run_id)

        if output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"PDF: {result['pdf_path']}")
            print(f"Score: {result['overall_score']:.4f} ({result['grade']})")
            print(f"Verdict: {result['verdict']}")
            print(f"Margaret: {result['margaret']['verdict']} ({result['margaret']['weighted_score']:.3f})")
            print(f"Jennifer: {result['jennifer']['verdict']} ({result['jennifer']['weighted_score']:.3f})")
            print(f"Reconciled: {result['reconciled']['decision']}")
            ed = result.get('estimate_delta', {})
            if ed:
                for name in ('sections', 'tables', 'figures', 'requirements', 'equations'):
                    d = ed.get(name, {})
                    if d and d.get('label') != 'none expected':
                        print(f"  {name}: est={d.get('estimated')} actual={d.get('actual')} → {d.get('label')}")
            if result['related_reviews']:
                print(f"Related reviews: {len(result['related_reviews'])}")
            if result['escalation_jobs']:
                print(f"Escalation jobs: {len(result['escalation_jobs'])}")
            if result['memory_assessment_id']:
                print(f"Assessment stored: {result['memory_assessment_id']}")
            if result['memory_lesson_id']:
                print(f"Lesson stored: {result['memory_lesson_id']}")

    typer.run(_cli)
