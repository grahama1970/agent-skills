"""Machine-readable JSON report for evidence case lab.

Parallel to lab_report.py (REPORT.md) — same data, structured for
ingestion by dashboards, CI gates, convergence tracking, and downstream tools.
"""
from __future__ import annotations

import json
from pathlib import Path

from diagnosis import DiagnosisResult


def write_json_report(diag: DiagnosisResult, results: list[dict], path: Path) -> None:
    """Write report.json — machine-readable version of REPORT.md."""
    s = diag.summary()

    verdicts = [_build_verdict(r, diag) for r in results]

    report = {
        "report_type": "evidence_case_lab",
        "version": "1.0",
        "summary": {
            "total": s["total"],
            "correct": s["correct"],
            "needs_human_review": s["needs_human_review"],
            "fp_rate": round(s["fp_rate"], 4),
            "fn_rate": round(s["fn_rate"], 4),
            "breakdown": {
                "grounding_failures": s.get("grounding_failures", 0),
                "false_positives": s.get("false_positives", 0),
                "false_negatives": s.get("false_negatives", 0),
                "grounding_warnings": s.get("grounding_warnings", 0),
                "technique_scatter": s.get("technique_scatter", 0),
            },
        },
        "timing": _timing_stats(results),
        "verdicts": verdicts,
    }

    path.write_text(json.dumps(report, indent=2, default=str))


def _build_verdict(r: dict, diag: DiagnosisResult) -> dict:
    """Build a single verdict entry with all evidence chains."""
    qid = r.get("id", "?")
    expected = r.get("expected", "?")
    actual = r.get("actual_verdict", "?")
    ge = r.get("grounding_evidence", {}) or {}
    res_map = ge.get("resolution_map", {}) if isinstance(ge, dict) else {}

    match = expected == actual or (expected == "not_satisfied" and actual == "inconclusive")
    unresolved = ge.get("unresolved_id_like", 0) if isinstance(ge, dict) else 0
    if match:
        verdict_status = "ok"
    elif actual == "satisfied" and unresolved > 0:
        verdict_status = "review"
    else:
        verdict_status = "wrong"

    v: dict = {
        "id": qid,
        "question": r.get("question", "?"),
        "expected": expected,
        "actual": actual,
        "verdict": verdict_status,
        "timing_ms": r.get("total_ms", 0),
    }

    # Include non-empty evidence fields
    for key in ("annotations", "decomposition", "entities", "gate_trace", "evidence_items"):
        if r.get(key):
            v[key] = r[key]

    if res_map:
        v["resolution_map"] = res_map
    if ge and ge != {}:
        v["grounding_evidence"] = ge

    # Diagnosis (only for problems)
    diag_entry = _find_diag_entry(qid, diag)
    if diag_entry:
        root_cause = diag_entry.get("root_cause", "unknown")
        v["diagnosis"] = {
            "root_cause": root_cause,
            "detail": diag_entry.get("detail", ""),
            "category": _diag_category(qid, diag),
        }
        if verdict_status != "ok":
            corrected = "not_satisfied" if actual == "satisfied" else "satisfied"
            v["diagnosis"]["next_action"] = _next_action_text(root_cause)
            v["diagnosis"]["correction_command"] = (
                f'./run.sh correct {qid} {corrected} --reason "<why>"'
            )

    return v


def _timing_stats(results: list[dict]) -> dict:
    timings = [r.get("total_ms", 0) for r in results if r.get("total_ms", 0) > 0]
    if not timings:
        return {}
    return {
        "avg_ms": round(sum(timings) / len(timings), 1),
        "total_ms": round(sum(timings), 1),
        "min_ms": round(min(timings), 1),
        "max_ms": round(max(timings), 1),
        "count": len(timings),
    }


def _find_diag_entry(qid: str, diag: DiagnosisResult) -> dict | None:
    for bucket in (diag.grounding_warnings, diag.grounding_failures,
                   diag.false_positives, diag.false_negatives, diag.technique_scatter):
        for item in bucket:
            if item.get("id") == qid:
                return item
    return None


def _diag_category(qid: str, diag: DiagnosisResult) -> str:
    for name, bucket in [
        ("grounding_warning", diag.grounding_warnings),
        ("grounding_failure", diag.grounding_failures),
        ("false_positive", diag.false_positives),
        ("false_negative", diag.false_negatives),
        ("technique_scatter", diag.technique_scatter),
        ("correct", diag.correct),
    ]:
        if any(item.get("id") == qid for item in bucket):
            return name
    return "unknown"


def _next_action_text(root_cause: str) -> str:
    actions = {
        "false_negative": (
            "Pipeline gap — corpus has evidence but recall failed. "
            "Run /memory clarify to identify missing bridge, then re-run."
        ),
        "grounding_failure": (
            "Fabricated entity — system hallucinated an answer from keyword matches. "
            "Correct the verdict."
        ),
        "false_positive": (
            "Out-of-scope question answered — system needs scope boundary. "
            "Run /memory clarify to teach the boundary, then re-run."
        ),
    }
    return actions.get(root_cause, "Review the evidence and correct if needed.")
