#!/usr/bin/env python3
"""Dewey SPARTA dataset improvement opportunity scan.

Combines monitor-sparta health, QRA landscape, and mechanical/semantic
classification into a prioritized opportunity backlog for dataset improvement.

Read-only. Output: review-db/dewey-sparta-opportunities/
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", "/home/graham/workspace/experiments/memory"))
AGENT_SKILLS = Path(os.environ.get("AGENT_SKILLS_ROOT", "/home/graham/workspace/experiments/agent-skills"))
AUDIT_SCRIPT = AGENT_SKILLS / "agents/dba-auditor/scripts/audit_qra_landscape.py"
FRAMEWORK_SCAN_SCRIPT = AGENT_SKILLS / "agents/dba-auditor/scripts/sparta_framework_ingestion_scan.py"
FOCUS_SCRIPT = AGENT_SKILLS / "agents/dba-auditor/scripts/dewey_nightly_focus.py"
CLASSIFY_SCRIPT = AGENT_SKILLS / "agents/dba-auditor/scripts/db_repair_session.py"
OUTPUT_BASE = Path(
    os.environ.get(
        "DEWEY_SPARTA_OPPORTUNITIES_OUTPUT",
        "/mnt/storage12tb/skills/review-db/outputs/dewey-sparta-opportunities",
    )
)

# Opportunity templates keyed by monitor dimension or audit signal.
OPPORTUNITY_CATALOG: dict[str, dict[str, str]] = {
    "qra_coverage_per_control": {
        "category": "qra_direct_coverage",
        "owner_lane": "monitor-sparta/qra_generation",
        "kind": "semantic",
        "impact": "high",
        "action": "Generate canonical/direct QRAs for in-scope controls missing valid coverage.",
    },
    "control_to_control_backlog": {
        "category": "qra_adversarial_enrichment",
        "owner_lane": "monitor-sparta/qra_relationship_generation",
        "kind": "semantic",
        "impact": "medium",
        "action": "Materialize gated SPARTA control-to-control comparison QRAs (adversarial bank).",
    },
    "description_completeness": {
        "category": "control_metadata",
        "owner_lane": "monitor-sparta/description_synthesis",
        "kind": "semantic",
        "impact": "high",
        "action": "Replace stub/placeholder control descriptions with source-backed text.",
    },
    "qra_stub_grounding": {
        "category": "qra_quality",
        "owner_lane": "monitor-sparta/qra_course_correction",
        "kind": "semantic",
        "impact": "medium",
        "action": "Re-ground or quarantine QRAs tied to stub-described controls.",
    },
    "sparta_relationship_integrity": {
        "category": "graph_hygiene",
        "owner_lane": "ops-arango/mechanical_repair",
        "kind": "mechanical",
        "impact": "high",
        "action": "Repair null edge_type, orphan endpoints, and relationship integrity gaps.",
    },
    "inline_embedding_policy": {
        "category": "embedding_hygiene",
        "owner_lane": "ops-arango/embeddings_fix",
        "kind": "mechanical",
        "impact": "medium",
        "action": "Remove inline embedding arrays; rely on Qdrant semantic sync.",
    },
    "framework_name_normalization": {
        "category": "schema_normalization",
        "owner_lane": "ops-arango/mechanical_repair",
        "kind": "mechanical",
        "impact": "medium",
        "action": "Normalize source_framework casing duplicates.",
    },
    "source_control_field_parity": {
        "category": "schema_normalization",
        "owner_lane": "ops-arango/mechanical_repair",
        "kind": "mechanical",
        "impact": "medium",
        "action": "Align source_control_id and related control field parity.",
    },
    "evidence_case_verdict_calibration": {
        "category": "qra_quality",
        "owner_lane": "assurance/create-evidence-case",
        "kind": "verification",
        "impact": "medium",
        "action": "Run create-evidence-case canary on labeled SATISFIED QRAs; expect ~10-15% pass on mixed banks.",
    },
    "control_text_gaps": {
        "category": "source_text",
        "owner_lane": "monitor-sparta/source_text_backfill",
        "kind": "semantic",
        "impact": "high",
        "action": "Backfill missing or stub source text before QRA generation.",
    },
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_monitor_health() -> dict[str, Any]:
    proc = subprocess.run(
        ["uv", "run", "python", "scripts/validation/monitor_sparta.py", "health", "--json"],
        cwd=MEMORY_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if not (proc.stdout or "").strip():
        raise RuntimeError(f"monitor health failed: {(proc.stderr or '')[-1500:]}")
    return json.loads(proc.stdout)


def classify_health(health: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tmp = OUTPUT_BASE / "_tmp_health.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(health), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(CLASSIFY_SCRIPT), "classify", str(tmp)],
        capture_output=True,
        text=True,
    )
    tmp.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"classify failed: {proc.stderr}")
    return json.loads(proc.stdout).get("buckets") or {}


def run_qra_landscape(manifest_limit: int) -> dict[str, Any]:
    audit = _load_module(AUDIT_SCRIPT, "audit_qra_landscape")
    return audit.build_report(manifest_limit)


def load_nightly_focus() -> dict[str, Any] | None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("dewey_nightly_focus", FOCUS_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import httpx
    with httpx.Client(base_url=os.environ.get("MEMORY_URL", "http://127.0.0.1:8601"), timeout=30.0) as client:
        active = mod._list_active(client)
    active.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
    return active[0] if active else None


def run_framework_ingestion_scan() -> dict[str, Any]:
    scan = _load_module(FRAMEWORK_SCAN_SCRIPT, "sparta_framework_ingestion_scan")
    from graph_memory.arango_client import get_db
    return scan.build_ingestion_opportunities(get_db())


def _opp(
    opp_id: str,
    *,
    scale: int | str | None = None,
    details: dict[str, Any] | None = None,
    priority: int | None = None,
    **catalog_key: str,
) -> dict[str, Any]:
    key = catalog_key.get("catalog_key") or opp_id
    meta = OPPORTUNITY_CATALOG.get(key, {})
    item = {
        "id": opp_id,
        "category": meta.get("category", "other"),
        "kind": meta.get("kind", "unknown"),
        "impact": meta.get("impact", "medium"),
        "owner_lane": meta.get("owner_lane", "human_review"),
        "action": meta.get("action", "Review monitor dimension and queue repair."),
        "scale": scale,
        "priority": priority,
        "details": details or {},
    }
    return item


def build_opportunities(health: dict[str, Any], qra_report: dict[str, Any], framework_report: dict[str, Any], nightly_focus: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for gap in framework_report.get("ingestion_gaps") or []:
        opportunities.append(
            {
                "id": gap.get("id"),
                "category": gap.get("category", "framework_ingestion"),
                "kind": gap.get("kind", "ingestion"),
                "impact": gap.get("impact", "medium"),
                "owner_lane": gap.get("owner_lane", "ingest-sparta/pipeline"),
                "action": gap.get("action"),
                "scale": gap.get("corpus_count", gap.get("scale")),
                "priority": 95 if gap.get("impact") == "high" else 65,
                "details": {k: gap[k] for k in ("framework", "label", "notes", "source", "min_expected") if k in gap},
            }
        )
    checks = {c.get("dimension"): c for c in (health.get("checks") or []) if c.get("dimension")}
    buckets = classify_health(health)

    for check in checks.values():
        if check.get("ok"):
            continue
        dim = str(check.get("dimension") or "")
        if dim not in OPPORTUNITY_CATALOG:
            continue
        scale = (check.get("details") or {}).get("total_missing") or check.get("message")
        opportunities.append(
            _opp(dim, catalog_key=dim, scale=scale, details={"check": check}, priority=70 if dim.endswith("coverage") else 50)
        )

    cov = qra_report.get("source_text_qra_coverage") or {}
    missing_gen = int(cov.get("qra_missing_generation_required") or 0)
    if missing_gen:
        opportunities.append(
            _opp(
                "direct_qra_generation_backlog",
                catalog_key="qra_coverage_per_control",
                scale=missing_gen,
                priority=90,
                details={"controls_with_valid_qra": cov.get("controls_with_valid_qra"), "controls_in_scope": cov.get("controls_in_scope")},
            )
        )

    stub_text = int((cov.get("summary") or {}).get("control_text_missing_or_stub") or 0)
    if stub_text:
        opportunities.append(
            _opp("control_text_gaps", catalog_key="control_text_gaps", scale=stub_text, priority=85, details={"summary": cov.get("summary")})
        )

    c2c = qra_report.get("control_to_control_backlog") or {}
    pending = int(c2c.get("gated_pairs_pending") or 0)
    if pending:
        opportunities.append(
            _opp(
                "control_to_control_comparison_backlog",
                catalog_key="control_to_control_backlog",
                scale=pending,
                priority=75,
                details={
                    "raw_candidate_pairs": c2c.get("raw_candidate_pairs"),
                    "sample_jobs": (c2c.get("sample_pending_jobs") or [])[:5],
                },
            )
        )

    pass_rate = qra_report.get("create_evidence_case_pass_rate") or {}
    labeled = int(pass_rate.get("verdict_labeled_qras") or 0)
    if labeled >= 100 and int(pass_rate.get("verdict_labeled_inconclusive") or 0) == 0:
        opportunities.append(
            _opp(
                "evidence_case_verdict_calibration",
                catalog_key="evidence_case_verdict_calibration",
                scale=labeled,
                priority=60,
                details=pass_rate,
            )
        )

    rel = int((qra_report.get("inventory") or {}).get("sparta_qra", {}).get("relationship_or_comparison") or 0)
    materialized = int((qra_report.get("inventory") or {}).get("sparta_qra", {}).get("control_to_control_materialized") or 0)
    if rel < 200 and pending > 0:
        opportunities.append(
            _opp(
                "adversarial_qra_bank_underdeveloped",
                catalog_key="control_to_control_backlog",
                scale=f"{materialized} materialized / {pending} gated pending",
                priority=72,
                details={"relationship_qras": rel, "note": "Adversarial banks improve create-evidence-case discrimination; low SATISFIED rate is expected."},
            )
        )

    # Mechanical opportunities from classify bucket
    for check in buckets.get("mechanical") or []:
        dim = str(check.get("dimension") or "")
        if dim in OPPORTUNITY_CATALOG and not any(o["id"] == dim for o in opportunities):
            opportunities.append(_opp(dim, catalog_key=dim, scale=check.get("message"), details={"check": check}, priority=80))


    if nightly_focus:
        focus_lanes = nightly_focus.get("monitor_sparta_lanes") or []
        focus_dims = nightly_focus.get("monitor_health_dimensions") or []
        for opp in opportunities:
            lane = str(opp.get("owner_lane") or "")
            oid = str(opp.get("id") or "")
            boost = 0
            if any(fl in lane or fl in oid for fl in focus_lanes):
                boost += 15
            if any(fd in oid for fd in focus_dims):
                boost += 10
            if boost:
                opp["priority"] = int(opp.get("priority") or 0) + boost
                opp["human_focus_boost"] = boost
        opportunities.append(
            {
                "id": "human_nightly_focus",
                "category": "human_directive",
                "kind": "focus",
                "impact": "high",
                "owner_lane": "dba_auditor/monitor-sparta",
                "action": nightly_focus.get("focus_objective"),
                "scale": nightly_focus.get("_key"),
                "priority": 100,
                "details": {
                    "monitor_sparta_lanes": focus_lanes,
                    "monitor_health_dimensions": focus_dims,
                    "acceptance_checks": nightly_focus.get("acceptance_checks"),
                    "ask_run_id": nightly_focus.get("ask_run_id"),
                },
            }
        )

    # De-dupe by id, keep highest priority
    by_id: dict[str, dict[str, Any]] = {}
    for opp in opportunities:
        cur = by_id.get(opp["id"])
        if cur is None or int(opp.get("priority") or 0) > int(cur.get("priority") or 0):
            by_id[opp["id"]] = opp

    ranked = sorted(by_id.values(), key=lambda o: (-int(o.get("priority") or 0), str(o.get("id"))))
    for i, opp in enumerate(ranked, start=1):
        opp["rank"] = i
    return ranked


def build_report(manifest_limit: int) -> dict[str, Any]:
    health = run_monitor_health()
    qra = run_qra_landscape(manifest_limit)
    framework = run_framework_ingestion_scan()
    nightly_focus = load_nightly_focus()
    opportunities = build_opportunities(health, qra, framework, nightly_focus)
    passed = sum(1 for c in health.get("checks") or [] if c.get("ok"))
    total = len(health.get("checks") or [])
    mechanical = [o for o in opportunities if o.get("kind") == "mechanical"]
    semantic = [o for o in opportunities if o.get("kind") == "semantic"]

    return {
        "schema": "dewey_sparta_dataset_opportunities.v1",
        "generated_at": _now(),
        "monitor_health": {"passed": passed, "total": total},
        "human_nightly_focus": nightly_focus,
        "improvement_opportunities": opportunities,
        "summary": {
            "opportunity_count": len(opportunities),
            "mechanical_count": len(mechanical),
            "semantic_count": len(semantic),
            "top_3": [o["id"] for o in opportunities[:3]],
        },
        "framework_ingestion_ref": {
            "gap_count": (framework.get("summary") or {}).get("gap_count"),
            "missing_entirely": (framework.get("summary") or {}).get("missing_entirely"),
            "high_impact": (framework.get("summary") or {}).get("high_impact"),
        },
        "qra_landscape_ref": {
            "missing_direct_qras": (qra.get("source_text_qra_coverage") or {}).get("qra_missing_generation_required"),
            "control_to_control_pending": (qra.get("control_to_control_backlog") or {}).get("gated_pairs_pending"),
        },
        "execution_guidance": {
            "mechanical_first": "Use db_repair_session.py repair for backup-gated mechanical fixes.",
            "semantic_queue": "Queue semantic opportunities to monitor-sparta lanes; do not inline bulk generation in one Dewey session.",
            "adversarial_qras": "Control-to-control comparisons enrich the dataset; expect ~10-15% create-evidence-case SATISFIED on fresh runs.",
        },
        "non_claims": [
            "Opportunity scan does not mutate the corpus.",
            "Ranking is heuristic; human or project agent approves execution order.",
            "High QRA count does not mean coverage is complete.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-limit", type=int, default=50)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report(args.manifest_limit)
    out = args.out or (OUTPUT_BASE / f"opportunities_{report['generated_at']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
