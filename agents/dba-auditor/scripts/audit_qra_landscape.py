#!/usr/bin/env python3
"""Dewey QRA landscape audit — coverage, reasonableness, control-to-control backlog.

Answers:
  - Which controls have valid direct QRAs vs missing vs terminal disposition?
  - Which existing QRAs are relationship/comparison vs canonical?
  - How many adversarial-retained QRAs exist (expected for /create-evidence-case negatives)?
  - What control-to-control comparison jobs are gated but not yet materialized?
  - Is create-evidence-case pass rate in the healthy ~10-15% band?

Read-only. Writes report JSON under review-db outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", "/home/graham/workspace/experiments/memory"))
MEMORY_SRC = MEMORY_ROOT / "src"
if str(MEMORY_SRC) not in sys.path:
    sys.path.insert(0, str(MEMORY_SRC))
if str(MEMORY_ROOT) not in sys.path:
    sys.path.insert(0, str(MEMORY_ROOT))

from graph_memory.arango_client import get_db  # noqa: E402

OUTPUT_BASE = Path(
    os.environ.get(
        "DEWEY_QRA_AUDIT_OUTPUT",
        "/mnt/storage12tb/skills/review-db/outputs/dewey-qra-audits",
    )
)

# /create-evidence-case: SATISFIED is the minority class; ~10-15% is healthy for mixed banks.
EVIDENCE_CASE_HEALTHY_SATISFIED_RATE = (0.10, 0.15)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def _aql_scalar(db: Any, query: str, bind: dict[str, Any] | None = None) -> int:
    cur = db.aql.execute(query, bind_vars=bind or {})
    row = cur.next() if not cur.empty() else 0
    return int(row or 0)


def qra_corpus_inventory(db: Any) -> dict[str, Any]:
    """Aggregate QRA buckets without loading full documents."""
    by_collection: dict[str, int] = {}
    for coll in ("sparta_qra", "sparta_qra_canonical", "sparta_qra_relationship"):
        if db.has_collection(coll):
            by_collection[coll] = _aql_scalar(db, f"RETURN LENGTH(FOR d IN {coll} RETURN 1)")

    sparta_qra = by_collection.get("sparta_qra", 0)
    if not sparta_qra:
        return {"by_collection": by_collection, "sparta_qra": {}}

    buckets = db.aql.execute("""
        LET adv = LENGTH(
            FOR q IN sparta_qra
                FILTER q.adversarial == true OR q.adversarial_retained == true
                RETURN 1
        )
        LET rel = LENGTH(
            FOR q IN sparta_qra
                FILTER CONTAINS(LOWER(q.prompt_kind || ""), "relationship")
                    OR CONTAINS(LOWER(q.qra_type || ""), "relationship")
                    OR CONTAINS(LOWER(q.qra_type || ""), "comparison")
                    OR q.control_a_id != null
                RETURN 1
        )
        LET ctrl_cmp = LENGTH(
            FOR q IN sparta_qra
                FILTER q.prompt_kind == "sparta_technique_related_controls_relationship"
                RETURN 1
        )
        LET with_ec = LENGTH(
            FOR q IN sparta_qra
                FILTER IS_OBJECT(q.evidence_case)
                RETURN 1
        )
        LET excluded = LENGTH(
            FOR q IN sparta_qra
                FILTER q.normal_coverage_excluded == true
                    OR q.review_status IN ["rejected", "superseded", "quarantined"]
                RETURN 1
        )
        LET valid_direct = LENGTH(
            FOR q IN sparta_qra
                FILTER q.normal_coverage_excluded != true
                FILTER q.adversarial_retained != true
                FILTER q.review_status NOT IN ["rejected", "superseded", "quarantined"]
                FILTER LENGTH(TRIM(q.question || "")) >= 8
                FILTER LENGTH(TRIM(q.answer || "")) >= 20
                FILTER CONTAINS(LOWER(q.prompt_kind || ""), "relationship") == false
                FILTER CONTAINS(LOWER(q.qra_type || ""), "relationship") == false
                FILTER CONTAINS(LOWER(q.qra_type || ""), "comparison") == false
                FILTER q.target_control_id == null
                RETURN 1
        )
        RETURN {
            adversarial_or_retained: adv,
            relationship_or_comparison: rel,
            control_to_control_materialized: ctrl_cmp,
            with_evidence_case: with_ec,
            coverage_excluded_or_rejected: excluded,
            valid_direct_style_estimate: valid_direct
        }
    """).next()

    verdict_counts = {}
    cur = db.aql.execute("""
        FOR q IN sparta_qra
            FILTER q.verdict != null
            COLLECT v = UPPER(q.verdict) WITH COUNT INTO n
            RETURN {verdict: v, count: n}
    """)
    for item in cur:
        verdict_counts[str(item["verdict"])] = int(item["count"])

    evidence_status = {}
    cur = db.aql.execute("""
        FOR q IN sparta_qra
            FILTER q.evidence_case_status != null
            COLLECT s = q.evidence_case_status WITH COUNT INTO n
            RETURN {status: s, count: n}
    """)
    for item in cur:
        evidence_status[str(item["status"])] = int(item["count"])

    return {
        "by_collection": by_collection,
        "sparta_qra": {
            **buckets,
            "verdict_counts": verdict_counts,
            "evidence_case_status_counts": evidence_status,
        },
    }


def source_text_coverage(manifest_limit: int) -> dict[str, Any]:
    try:
        from scripts.validation.source_text_qra_coverage import scan
    except ModuleNotFoundError:
        from source_text_qra_coverage import scan
    return scan(manifest_limit=manifest_limit, artifact_dir=None)


def control_to_control_backlog(db: Any) -> dict[str, Any]:
    try:
        from scripts.validation._health_checks import _summarize_sparta_control_to_control_gated_backlog
    except ModuleNotFoundError:
        from _health_checks import _summarize_sparta_control_to_control_gated_backlog

    controls = list(db.aql.execute("""
        FOR c IN sparta_controls
            FILTER c.deprecated != true
            FILTER c.source_framework IN ["SPARTA", "sparta"]
            RETURN c
    """, ttl=120))

    existing = set()
    cur = db.aql.execute("""
        FOR q IN sparta_qra
            FILTER q.prompt_kind == "sparta_technique_related_controls_relationship"
            FILTER q.technique_id != null AND q.control_a_id != null AND q.control_b_id != null
            RETURN [q.technique_id, q.control_a_id, q.control_b_id]
    """, ttl=120)
    for trip in cur:
        if isinstance(trip, list) and len(trip) == 3:
            existing.add((str(trip[0]), str(trip[1]), str(trip[2])))

    summary = _summarize_sparta_control_to_control_gated_backlog(controls, existing)
    return {
        "raw_candidate_pairs": summary.get("sparta_control_to_control_raw_candidate_pairs"),
        "gated_pairs_pending": summary.get("sparta_control_to_control_gated_pairs"),
        "materialized_control_to_control_qras": len(existing),
        "gated_skip_reasons": summary.get("sparta_control_to_control_gated_skip_reasons"),
        "top_techniques_by_gated_pairs": [
            {
                "technique_id": row["technique_id"],
                "gated_candidate_pairs": row["gated_candidate_pairs"],
            }
            for row in (summary.get("sparta_control_to_control_gated_by_technique") or [])[:15]
        ],
        "sample_pending_jobs": [
            {
                "job_id": job.get("job_id"),
                "technique_id": job.get("identity", {}).get("technique_id"),
                "control_a_id": job.get("identity", {}).get("control_a_id"),
                "control_b_id": job.get("identity", {}).get("control_b_id"),
            }
            for job in (summary.get("sparta_control_to_control_gated_jobs") or [])[:25]
        ],
    }


def evidence_case_pass_rate_guidance(db: Any, inventory: dict[str, Any]) -> dict[str, Any]:
    """Estimate /create-evidence-case SATISFIED band on labeled subsets only."""
    sp = inventory.get("sparta_qra") or {}
    total = int((inventory.get("by_collection") or {}).get("sparta_qra") or 0)
    satisfied = int((sp.get("verdict_counts") or {}).get("SATISFIED", 0))
    inconclusive = int((sp.get("verdict_counts") or {}).get("INCONCLUSIVE", 0))
    not_sat = int((sp.get("verdict_counts") or {}).get("NOT_SATISFIED", 0))
    labeled = satisfied + inconclusive + not_sat
    labeled_rate = (satisfied / labeled) if labeled else None

    # Relationship/comparison banks are adversarial-rich; expect low SATISFIED on fresh runs.
    rel_labeled = db.aql.execute("""
        LET rel = (
            FOR q IN sparta_qra
                FILTER CONTAINS(LOWER(q.prompt_kind || ""), "relationship")
                    OR CONTAINS(LOWER(q.qra_type || ""), "relationship")
                    OR CONTAINS(LOWER(q.qra_type || ""), "comparison")
                    OR q.control_a_id != null
                RETURN q
        )
        LET labeled = LENGTH(FOR q IN rel FILTER q.verdict != null RETURN 1)
        LET sat = LENGTH(FOR q IN rel FILTER UPPER(q.verdict || "") == "SATISFIED" RETURN 1)
        LET inc = LENGTH(FOR q IN rel FILTER UPPER(q.verdict || "") == "INCONCLUSIVE" RETURN 1)
        LET notsat = LENGTH(FOR q IN rel FILTER UPPER(q.verdict || "") == "NOT_SATISFIED" RETURN 1)
        RETURN {relationship_total: LENGTH(rel), labeled, satisfied: sat, inconclusive: inc, not_satisfied: notsat}
    """).next()

    lo, hi = EVIDENCE_CASE_HEALTHY_SATISFIED_RATE
    rel_l = int(rel_labeled.get("labeled") or 0)
    rel_sat = int(rel_labeled.get("satisfied") or 0)
    rel_rate = (rel_sat / rel_l) if rel_l else None

    if rel_l >= 20:
        rate_for_band = rel_rate
        band_source = "relationship_comparison_subset"
    elif labeled >= 100:
        rate_for_band = labeled_rate
        band_source = "verdict_labeled_subset"
    else:
        rate_for_band = None
        band_source = "insufficient_labeled_subset"

    if rate_for_band is None:
        band = "unknown_insufficient_evidence_case_labels"
    elif rate_for_band < lo:
        band = "below_expected_band_healthy_for_adversarial_banks"
    elif rate_for_band > hi:
        band = "above_expected_band_review_for_false_positives"
    else:
        band = "within_expected_10_15_percent_band"

    return {
        "total_sparta_qra": total,
        "verdict_labeled_qras": labeled,
        "verdict_unlabeled_qras": max(total - labeled, 0),
        "verdict_labeled_satisfied": satisfied,
        "verdict_labeled_inconclusive": inconclusive,
        "verdict_labeled_not_satisfied": not_sat,
        "verdict_labeled_satisfied_rate": round(labeled_rate, 4) if labeled_rate is not None else None,
        "relationship_comparison_subset": rel_labeled,
        "relationship_satisfied_rate": round(rel_rate, 4) if rel_rate is not None else None,
        "band_evaluated_on": band_source,
        "expected_satisfied_rate_band": f"{int(lo*100)}-{int(hi*100)}%",
        "assessment": band,
        "notes": (
            "Most legacy QRAs lack create-evidence-case verdict labels; do not treat q.verdict=SATISFIED "
            "on canonical rows as proof the evidence-case gate passed. For control-to-control and adversarial "
            "banks, expect ~10-15% SATISFIED on fresh /create-evidence-case runs; INCONCLUSIVE/NOT_SATISFIED "
            "are valuable negative rows. Dewey should queue missing direct QRAs separately from comparison jobs."
        ),
    }


def build_report(manifest_limit: int) -> dict[str, Any]:
    db = get_db()
    inventory = qra_corpus_inventory(db)
    coverage = source_text_coverage(manifest_limit)
    c2c = control_to_control_backlog(db)
    guidance = evidence_case_pass_rate_guidance(db, inventory)

    controls = coverage.get("controls") or {}
    missing_gen = int(controls.get("qra_missing_generation_required") or 0)
    missing_term = int(controls.get("qra_missing_terminal_non_generation_required") or 0)

    recommendations: list[str] = []
    if missing_gen:
        recommendations.append(
            f"Queue {missing_gen} controls for canonical/direct QRA generation (source_text_qra_coverage manifest)."
        )
    if c2c.get("gated_pairs_pending", 0):
        recommendations.append(
            f"Materialize up to {c2c['gated_pairs_pending']} gated SPARTA control-to-control comparison QRAs "
            "(adversarial-rich; expect low /create-evidence-case SATISFIED rate)."
        )
    adv = int((inventory.get("sparta_qra") or {}).get("adversarial_or_retained") or 0)
    if adv:
        recommendations.append(
            f"Retain {adv} adversarial QRAs as negative training/eval rows; exclude from direct coverage counts."
        )
    rel = guidance.get("relationship_comparison_subset") or {}
    rel_l = int(rel.get("labeled") or 0)
    rel_rate = guidance.get("relationship_satisfied_rate")
    if rel_l >= 20 and rel_rate is not None and rel_rate > EVIDENCE_CASE_HEALTHY_SATISFIED_RATE[1]:
        recommendations.append(
            "Relationship/comparison QRAs show high SATISFIED rate — run /create-evidence-case canary on a sample; "
            "adversarial banks should stay near 10-15% SATISFIED."
        )
    elif int(guidance.get("verdict_labeled_qras") or 0) >= 100 and int(
        guidance.get("verdict_labeled_inconclusive") or 0
    ) == 0 and int(guidance.get("verdict_labeled_not_satisfied") or 0) == 0:
        recommendations.append(
            "q.verdict labels look like generation stamps (100% SATISFIED, no INCONCLUSIVE). "
            "Run assurance/create-evidence-case spot checks before trusting labeled SATISFIED rows."
        )

    return {
        "schema": "dewey_qra_landscape_audit.v1",
        "generated_at": _now(),
        "inventory": inventory,
        "source_text_qra_coverage": {
            "status": coverage.get("status"),
            "summary": coverage.get("summary"),
            "qra_disposition_counts": controls.get("qra_disposition_counts"),
            "qra_missing_generation_required": missing_gen,
            "qra_missing_terminal_non_generation_required": missing_term,
            "controls_with_valid_qra": controls.get("qra_ok"),
            "controls_in_scope": controls.get("qra_scope"),
        },
        "control_to_control_backlog": c2c,
        "create_evidence_case_pass_rate": guidance,
        "recommendations": recommendations,
        "non_claims": [
            "This audit does not run /create-evidence-case live on every QRA.",
            "Relationship QRAs do not satisfy direct per-control coverage.",
            "Low SATISFIED rate on comparison/adversarial banks is expected, not a defect.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-limit", type=int, default=50)
    parser.add_argument("--out", type=Path, help="optional output path")
    parser.add_argument("--print-json", action="store_true", default=True)
    args = parser.parse_args()

    report = build_report(args.manifest_limit)
    out = args.out
    if out is None:
        OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_BASE / f"qra_landscape_{report['generated_at']}.json"
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.print_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
