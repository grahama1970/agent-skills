"""Deterministic regression verdict over comparator defect vectors.

This is the referee for the extraction-repair loop: a repair is promotable
only when the candidate comparison's defect vector is no worse than the
baseline on every blocking dimension, and — when a target class is named —
strictly better on that dimension. Model prose is never consulted.

Schema: ``pdf_lab.regression_verdict.v1``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VERDICT_SCHEMA = "pdf_lab.regression_verdict.v1"

# Dimensions where any increase blocks promotion.
BLOCKING_DIMENSIONS = (
    "missing_expected",
    "ambiguous_expected",
    "unwaived_extras",
    "type_mismatches",
)


def _defect_vector(comparison: dict[str, Any]) -> dict[str, int]:
    vector = comparison.get("defect_vector")
    if isinstance(vector, dict):
        return {key: int(value) for key, value in vector.items()}
    # Legacy v1 comparison: derive what we can.
    return {
        "matched_expected": int(comparison.get("matched_expected_elements", 0)),
        "missing_expected": int(comparison.get("unmatched_expected_elements", 0)),
        "ambiguous_expected": int(comparison.get("ambiguous_expected_elements", 0)),
        "unwaived_extras": int(comparison.get("unmatched_actual_elements", 0)),
        "waived_extras": 0,
        "type_mismatches": 0,
    }


def evaluate_regression(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    target_class: str | None = None,
) -> dict[str, Any]:
    """Compare two comparison payloads; return a typed verdict.

    PASS requires:
    - no blocking dimension increased baseline -> candidate;
    - matched_expected did not decrease;
    - if target_class is given, that dimension strictly decreased.
    """
    base_vector = _defect_vector(baseline)
    cand_vector = _defect_vector(candidate)
    deltas: dict[str, int] = {}
    failures: list[str] = []

    for dimension in BLOCKING_DIMENSIONS:
        before = base_vector.get(dimension, 0)
        after = cand_vector.get(dimension, 0)
        deltas[dimension] = after - before
        if after > before:
            failures.append(f"{dimension} increased: {before} -> {after}")

    matched_before = base_vector.get("matched_expected", 0)
    matched_after = cand_vector.get("matched_expected", 0)
    deltas["matched_expected"] = matched_after - matched_before
    if matched_after < matched_before:
        failures.append(
            f"matched_expected decreased: {matched_before} -> {matched_after}"
        )

    target_result: dict[str, Any] | None = None
    if target_class is not None:
        known = target_class in base_vector or target_class in cand_vector
        before = base_vector.get(target_class, 0)
        after = cand_vector.get(target_class, 0)
        target_result = {
            "target_class": target_class,
            "known_dimension": known,
            "before": before,
            "after": after,
            "strictly_decreased": known and after < before,
        }
        if not known:
            failures.append(f"target_class {target_class!r} is not a known dimension")
        elif after >= before:
            failures.append(
                f"target_class {target_class!r} did not strictly decrease: {before} -> {after}"
            )

    return {
        "schema_version": VERDICT_SCHEMA,
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "deltas": deltas,
        "baseline_defect_vector": base_vector,
        "candidate_defect_vector": cand_vector,
        "target": target_result,
        "semantic_truth": "NOT_CLAIMED",
    }


def run_regression_check(
    baseline_path: Path,
    candidate_path: Path,
    *,
    target_class: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    baseline = json.loads(Path(baseline_path).expanduser().read_text(encoding="utf-8"))
    candidate = json.loads(Path(candidate_path).expanduser().read_text(encoding="utf-8"))
    verdict = evaluate_regression(baseline, candidate, target_class=target_class)
    verdict["baseline_path"] = str(baseline_path)
    verdict["candidate_path"] = str(candidate_path)
    if output_path is not None:
        output_path = Path(output_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return verdict
