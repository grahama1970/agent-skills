#!/usr/bin/env python3
"""Stratified sample monitoring for the extractor quality-check pipeline.

Scores a stratified random sample of extracted PDFs (profile.json + structural.json)
directly from disk — no LLM, no network — and feeds the results through the
Margaret Chen + Jennifer Cheung persona evaluations.

Split from batch_review.py to keep individual modules under 800 lines.
"""

import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from annealing import (
    CATASTROPHIC_FAIL_PCT,
    CATASTROPHIC_SCORE_THRESHOLD,
    SPOT_FIX_WORST_COUNT,
    get_annealing_thresholds,
    get_coverage_pct,
    jennifer_evaluates,
    margaret_evaluates,
    reconcile,
)

# Paths
SKILL_DIR = Path(__file__).parent
COLLECTOR_SCRIPT = SKILL_DIR / "datalake_state_collector.py"


# ── Shared state utilities ──
# These are used by both batch_sampling and batch_review.


def _collect_state() -> dict:
    """Run the state collector and parse output."""
    try:
        result = subprocess.run(
            [sys.executable, str(COLLECTOR_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        print(f"[batch_review] state collector failed: {e}", file=sys.stderr)
    return {}


def _compute_coverage_pct(state: dict) -> float:
    """Extract coverage percentage from collected state.

    Uses the disk-scanned coverage_pct if available (set by state_collector
    when gap_plan sector_counts are empty). Falls back to annealing formula.
    """
    coverage = state.get("coverage", {})

    # Prefer direct coverage_pct from disk scan
    if coverage.get("coverage_pct") is not None and coverage.get("source") == "disk_scan":
        return coverage["coverage_pct"]

    # Fallback to sector_counts-based calculation
    sector_counts = coverage.get("sector_counts", {})
    return get_coverage_pct(sector_counts)


# ── Stratified sample monitoring ──


def _extract_sector_from_path(profile_path: Path, corpus_root: Path) -> str:
    """Extract sector from profile path relative to corpus root."""
    try:
        relative = profile_path.relative_to(corpus_root)
        return relative.parts[0]
    except (ValueError, IndexError):
        return "unknown"


def _load_s00_metadata(profile_path: Path) -> dict:
    """Load S00 profile metadata for content-type-aware sampling."""
    try:
        data = json.loads(profile_path.read_text())
        elements = data.get("elements", {}) or {}
        return {
            "has_tables": bool(elements.get("tables", False)),
            "has_figures": bool(elements.get("figures", False)),
            "has_formulas": bool(elements.get("formulas", False)),
            "table_count": int(elements.get("estimated_table_count", 0)),
            "domain": str(data.get("domain", "unknown")),
            "layout_columns": int((data.get("layout", {}) or {}).get("columns", 1)),
        }
    except Exception:
        return {}


def _stratified_sample(
    profiles_by_sector: dict[str, list[Path]],
    per_sector: int,
    seed: int,
) -> list[Path]:
    """Pick per_sector profiles from each sector with content-type diversity.

    Guarantees representation of table-heavy, formula-heavy, and multi-column
    documents in each sector sample when available.  Remaining slots filled
    randomly.
    """
    rng = random.Random(seed)
    sample = []
    for _sector, paths in sorted(profiles_by_sector.items()):
        if len(paths) <= per_sector:
            sample.extend(paths)
            continue

        # Load S00 metadata for content-type-aware selection
        meta_cache: dict[str, dict] = {}
        for p in paths:
            meta_cache[str(p)] = _load_s00_metadata(p)

        # Reserve slots for content-type diversity (1 each if available)
        reserved: list[Path] = []
        remaining = list(paths)

        # 1. One table-heavy doc (table_count >= 5)
        table_heavy = [p for p in remaining if meta_cache.get(str(p), {}).get("table_count", 0) >= 5]
        if table_heavy and len(reserved) < per_sector:
            pick = rng.choice(table_heavy)
            reserved.append(pick)
            remaining.remove(pick)

        # 2. One formula doc
        formula_docs = [p for p in remaining if meta_cache.get(str(p), {}).get("has_formulas", False)]
        if formula_docs and len(reserved) < per_sector:
            pick = rng.choice(formula_docs)
            reserved.append(pick)
            remaining.remove(pick)

        # 3. One multi-column doc
        multi_col = [p for p in remaining if meta_cache.get(str(p), {}).get("layout_columns", 1) >= 2]
        if multi_col and len(reserved) < per_sector:
            pick = rng.choice(multi_col)
            reserved.append(pick)
            remaining.remove(pick)

        # Fill remaining slots randomly
        slots_left = per_sector - len(reserved)
        if slots_left > 0 and remaining:
            if len(remaining) <= slots_left:
                reserved.extend(remaining)
            else:
                reserved.extend(rng.sample(remaining, slots_left))

        sample.extend(reserved)
    return sample


def stratified_sample_review(
    corpus_root: Path,
    sample_per_sector: int = 3,
    run_id: str = "",
) -> dict:
    """Score a stratified random sample of extracted PDFs.

    Reads profile.json + structural.json directly from disk — no LLM,
    no network, ~10ms per PDF. Designed to run every ~60s in the
    supervisor polling loop.

    Returns:
        {
            "sample_size": int,
            "sectors_sampled": {sector: count},
            "dimension_scores": {dim: avg_score},
            "overall_score": float,
            "grade": str,
            "verdict_distribution": {"PASS": n, "WARN": n, "FAIL": n},
            "fail_pct": float,
            "worst_pdfs": [{"path": str, "score": float, "issues": [...]}],
            "decision": "CONTINUE" | "SPOT_FIX" | "RESTART",
            "margaret_result": dict,
            "jennifer_result": dict,
            "reconciled": dict,
            "timestamp": str,
        }
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Import review-pdf modules lazily to avoid hard dependency at import time.
    # The verify/ package uses relative imports (from .models import ...) so we
    # must add its parent (review-pdf/) to sys.path so "import verify.analysis"
    # triggers proper package loading.
    #
    # IMPORTANT: In long-running processes (supervisor), sys.modules caches stale
    # versions of verify.* modules.  Evict them so Python re-imports from disk
    # each call — edits to analysis.py / scoring.py are picked up without restart.
    review_pdf_dir = (
        Path(os.path.expanduser("~/workspace/experiments/pi-mono"))
        / ".pi" / "skills" / "review-pdf"
    )
    if str(review_pdf_dir) not in sys.path:
        sys.path.insert(0, str(review_pdf_dir))

    # Evict cached verify.* modules so we always import fresh from disk
    for _mod_name in list(sys.modules):
        if _mod_name == "verify" or _mod_name.startswith("verify."):
            del sys.modules[_mod_name]

    try:
        from verify.analysis import (
            collect_profiles, resolve_doc_inputs, extract_s00_estimates,
            analyze_s11_structural, analyze_flattened_data, analyze_sections_data,
            analyze_pdf_source,
        )
        from verify.scoring import build_issues, dimension_scores, overall_from_dimensions
        from verify.reporting import aggregate_reports
    except ImportError as e:
        return {
            "sample_size": 0,
            "sectors_sampled": {},
            "dimension_scores": {},
            "overall_score": 0.0,
            "grade": "F",
            "verdict_distribution": {},
            "fail_pct": 0.0,
            "worst_pdfs": [],
            "decision": "CONTINUE",
            "margaret_result": {},
            "jennifer_result": {},
            "reconciled": {},
            "error": f"import_failed: {e}",
            "timestamp": timestamp,
        }

    # 1. Discover all profile.json files
    all_profiles = collect_profiles(corpus_root, limit=None)
    if not all_profiles:
        return {
            "sample_size": 0,
            "sectors_sampled": {},
            "dimension_scores": {},
            "overall_score": 0.0,
            "grade": "F",
            "verdict_distribution": {},
            "fail_pct": 0.0,
            "worst_pdfs": [],
            "decision": "CONTINUE",
            "margaret_result": {},
            "jennifer_result": {},
            "reconciled": {},
            "reason": "no_profiles_found",
            "timestamp": timestamp,
        }

    # 2. Filter to only those with structural.json, flattened data, OR sections data
    complete_profiles = []
    for p in all_profiles:
        inputs = resolve_doc_inputs(p)
        if (inputs.get("structural_path") is not None
                or inputs.get("flattened_path") is not None
                or inputs.get("sections_path") is not None):
            complete_profiles.append(p)

    if not complete_profiles:
        return {
            "sample_size": 0,
            "sectors_sampled": {},
            "dimension_scores": {},
            "overall_score": 0.0,
            "grade": "F",
            "verdict_distribution": {},
            "fail_pct": 0.0,
            "worst_pdfs": [],
            "decision": "CONTINUE",
            "margaret_result": {},
            "jennifer_result": {},
            "reconciled": {},
            "reason": "no_complete_extractions",
            "timestamp": timestamp,
        }

    # 3. Group by sector
    profiles_by_sector: dict[str, list[Path]] = {}
    for p in complete_profiles:
        sector = _extract_sector_from_path(p, corpus_root)
        profiles_by_sector.setdefault(sector, []).append(p)

    # 4. Stratified sample (deterministic seed per hour for stability)
    seed = int(time.time()) // 3600
    sampled = _stratified_sample(profiles_by_sector, sample_per_sector, seed)

    # 5. Score each profile using single_report's underlying logic
    reports = []
    scored_pdfs = []  # For worst-PDF tracking
    pdf_escalation_data = []  # (issues, pdf_path, run_dir) for escalation job generation
    for profile_path in sampled:
        try:
            inputs = resolve_doc_inputs(profile_path)
            profile_data = json.loads(profile_path.read_text())
            context_path = inputs.get("context_path")
            context_data = json.loads(context_path.read_text()) if context_path else {}
            structural_path = inputs.get("structural_path")
            flattened_path = inputs.get("flattened_path")
            sections_path = inputs.get("sections_path")
            if structural_path is None and flattened_path is None and sections_path is None:
                continue

            estimates = extract_s00_estimates(profile_data, context_data)
            if structural_path is not None:
                structural_data = json.loads(structural_path.read_text())
                actual = analyze_s11_structural(structural_data)
            elif flattened_path is not None:
                flat_raw = json.loads(flattened_path.read_text())
                if isinstance(flat_raw, dict):
                    flat_raw = flat_raw.get("data", flat_raw.get("items", []))
                if not isinstance(flat_raw, list):
                    flat_raw = []
                actual = analyze_flattened_data(flat_raw)
            else:
                sections_data = json.loads(sections_path.read_text())
                actual = analyze_sections_data(sections_data)
            source = analyze_pdf_source(inputs.get("pdf_path"))
            issues, ratio_metrics = build_issues(estimates, actual, source)
            dims = dimension_scores(estimates, actual, source, ratio_metrics)
            overall = overall_from_dimensions(dims, issues)

            # Keep raw Issue objects + paths for escalation job generation
            pdf_escalation_data.append((
                issues,
                inputs.get("pdf_path"),
                inputs["run_dir"],
            ))

            report = {
                "doc_id": profile_data.get("file", str(profile_path)),
                "dimensions": dims,
                "overall": overall,
                "issues": [
                    {"code": i.code, "severity": i.severity, "message": i.message}
                    if hasattr(i, "code") else i
                    for i in issues
                ],
            }
            reports.append(report)

            scored_pdfs.append({
                "path": str(inputs.get("pdf_path") or profile_path),
                "score": overall["score"],
                "grade": overall["grade"],
                "verdict": overall["verdict"],
                "issues": [
                    i.code if hasattr(i, "code") else str(i)
                    for i in issues[:5]
                ],
                "_esc_idx": len(pdf_escalation_data) - 1,  # index into pdf_escalation_data
            })
        except Exception as exc:
            print(f"[stratified_sample] score failed for {profile_path}: {exc}", file=sys.stderr)
            continue

    if not reports:
        return {
            "sample_size": 0,
            "sectors_sampled": {s: len(v) for s, v in profiles_by_sector.items()},
            "dimension_scores": {},
            "overall_score": 0.0,
            "grade": "F",
            "verdict_distribution": {},
            "fail_pct": 0.0,
            "worst_pdfs": [],
            "decision": "CONTINUE",
            "margaret_result": {},
            "jennifer_result": {},
            "reconciled": {},
            "reason": "all_scores_failed",
            "timestamp": timestamp,
        }

    # 6. Aggregate
    agg = aggregate_reports(reports, run_id=run_id or "stratified_sample")

    # Bug fix: aggregate_reports computes dimension averages including 0.7 scores
    # for not_available/unknown dimensions, and overall_average_score as an
    # unweighted mean of those.  Compute correctly from per-PDF reports.
    #
    # Dimension averages: exclude not_available/unknown dimensions per-PDF
    _dim_sums: dict[str, float] = {}
    _dim_counts: dict[str, int] = {}
    for _report in reports:
        for _name, _payload in _report.get("dimensions", {}).items():
            _state = _payload.get("state", "")
            if _state in ("not_available", "unknown"):
                continue
            _dim_sums[_name] = _dim_sums.get(_name, 0.0) + float(_payload.get("score", 0.0))
            _dim_counts[_name] = _dim_counts.get(_name, 0) + 1
    dim_averages = {
        _name: _dim_sums[_name] / _dim_counts[_name]
        for _name in _dim_sums
        if _dim_counts[_name] > 0
    }
    # Overall: mean of per-PDF overall scores (which already properly handle
    # weight redistribution and unknown/not_available exclusion)
    if scored_pdfs:
        overall_avg = sum(p["score"] for p in scored_pdfs) / len(scored_pdfs)
    else:
        overall_avg = agg.get("overall_average_score", 0.0)

    # Verdict distribution
    verdict_counts = agg.get("verdict_counts", {"PASS": 0, "WARN": 0, "FAIL": 0})
    total_verdicts = sum(verdict_counts.values())
    fail_pct = (100.0 * verdict_counts.get("FAIL", 0) / total_verdicts) if total_verdicts > 0 else 0.0

    # Worst PDFs (bottom N by score)
    scored_pdfs.sort(key=lambda x: x["score"])
    worst_pdfs = scored_pdfs[:SPOT_FIX_WORST_COUNT]

    # Sectors actually sampled
    sectors_sampled: dict[str, int] = {}
    for p in sampled:
        s = _extract_sector_from_path(p, corpus_root)
        sectors_sampled[s] = sectors_sampled.get(s, 0) + 1

    # 7. Coverage for annealing phase lookup
    coverage_pct = _compute_coverage_pct(_collect_state())
    thresholds = get_annealing_thresholds(coverage_pct)

    # 8. Feed to personas (lightweight — uses dimension averages, no run_metrics)
    margaret_result = margaret_evaluates(
        coverage_pct=coverage_pct,
        dim_scores=dim_averages,
        fail_ratio=fail_pct / 100.0,
        critical_ratio=0.0,
        run_metrics={},
        state={},
    )
    jennifer_result = jennifer_evaluates(
        coverage_pct=coverage_pct,
        dim_scores=dim_averages,
        fail_ratio=fail_pct / 100.0,
        critical_ratio=0.0,
        run_metrics={},
        state={},
    )
    reconciled = reconcile(margaret_result, jennifer_result)

    # 9. Decision: CONTINUE / SPOT_FIX / RESTART
    both_fail = margaret_result["verdict"] == "FAIL" and jennifer_result["verdict"] == "FAIL"
    if (
        overall_avg < CATASTROPHIC_SCORE_THRESHOLD
        or fail_pct > CATASTROPHIC_FAIL_PCT
        # both_fail only catastrophic when score is in F-grade territory;
        # at B/C grade it means "not at target yet", not "kill the process"
        or (both_fail and overall_avg < 0.65)
    ):
        decision = "RESTART"
    elif overall_avg < thresholds["min_score"]:
        decision = "SPOT_FIX"
    elif both_fail:
        # Personas flag dimension-level concerns (e.g. table_fidelity) but
        # overall quality meets the phase threshold.  Log the concern but
        # allow CONTINUE — persona diagnostics feed remediation, not block.
        decision = "CONTINUE"
    else:
        decision = "CONTINUE"

    # Grade from overall average
    if overall_avg >= 0.95:
        grade = "A+"
    elif overall_avg >= 0.88:
        grade = "A"
    elif overall_avg >= 0.78:
        grade = "B"
    elif overall_avg >= 0.65:
        grade = "C"
    else:
        grade = "F"

    # 10. Generate escalation jobs for FAIL/WARN PDFs (for remediation)
    # Also generate when both personas FAIL but overall meets threshold (CONTINUE
    # with dimension-level concerns) — personas diagnose AND trigger fixes.
    all_escalation_jobs = []
    _generate_esc = (decision in ("SPOT_FIX", "RESTART") or both_fail) and pdf_escalation_data
    if _generate_esc:
        try:
            from verify.escalation import escalation_jobs as make_escalation_jobs
        except ImportError:
            make_escalation_jobs = None

        if make_escalation_jobs is not None:
            for scored in scored_pdfs:
                if scored["verdict"] not in ("FAIL", "WARN"):
                    continue
                esc_idx = scored.get("_esc_idx")
                if esc_idx is None or esc_idx >= len(pdf_escalation_data):
                    continue
                issues_raw, pdf_path, run_dir = pdf_escalation_data[esc_idx]
                pdf_p = Path(pdf_path) if pdf_path else None
                run_p = Path(run_dir) if run_dir else Path(".")
                esc_jobs = make_escalation_jobs(issues_raw, pdf_p, run_p)
                for j in esc_jobs:
                    all_escalation_jobs.append(j.as_dict())

            # Deduplicate by command
            seen_cmds: set[str] = set()
            deduped: list[dict] = []
            for j in all_escalation_jobs:
                if j["command"] not in seen_cmds:
                    seen_cmds.add(j["command"])
                    deduped.append(j)
            all_escalation_jobs = deduped

    return {
        "sample_size": len(reports),
        "sectors_sampled": sectors_sampled,
        "dimension_scores": dim_averages,
        "overall_score": round(overall_avg, 4),
        "grade": grade,
        "verdict_distribution": verdict_counts,
        "fail_pct": round(fail_pct, 1),
        "worst_pdfs": worst_pdfs,
        "escalation_jobs": all_escalation_jobs,
        "decision": decision,
        "margaret_result": margaret_result,
        "jennifer_result": jennifer_result,
        "reconciled": reconciled,
        "phase": thresholds["phase_name"],
        "coverage_pct": coverage_pct,
        "timestamp": timestamp,
    }
