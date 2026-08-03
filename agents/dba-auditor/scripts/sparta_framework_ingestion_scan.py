#!/usr/bin/env python3
"""Dewey SPARTA framework ingestion gap scan.

Detects:
  - Frameworks configured in worksheets.yaml but missing/thin in corpus
  - Referenced target_types (EMB3D, CSF, BSI) with no materialized controls
  - Case-duplicate framework populations
  - Known upstream staleness risks (e.g. Heimdall 800-53r4 vs corpus 2025.1)

Read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml

MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", "/home/graham/workspace/experiments/memory"))
SPARTA_ROOT = Path(os.environ.get("SPARTA_ROOT", "/home/graham/workspace/experiments/sparta"))
MEMORY_SRC = MEMORY_ROOT / "src"
if str(MEMORY_SRC) not in sys.path:
    sys.path.insert(0, str(MEMORY_SRC))

from graph_memory.arango_client import get_db  # noqa: E402

WORKSHEETS = SPARTA_ROOT / "config" / "worksheets.yaml"
OUTPUT_BASE = Path(
    os.environ.get(
        "DEWEY_FRAMEWORK_INGESTION_OUTPUT",
        "/mnt/storage12tb/skills/review-db/outputs/dewey-framework-ingestion",
    )
)

# Frameworks we expect as first-class control populations (from worksheets + pipeline).
CANONICAL_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "SPARTA": {"aliases": ["sparta", "SPARTA"], "min_expected": 300, "source": "SPARTA-Data.xlsx"},
    "NIST": {"aliases": ["nist", "NIST", "NIST_800_53"], "min_expected": 900, "source": "NIST References with SSG"},
    "CWE": {"aliases": ["cwe", "CWE"], "min_expected": 800, "source": "cwe.xml / MITRE"},
    "ATT_CK_Enterprise": {"aliases": ["ATT_CK_Enterprise", "attack", "ATT&CK"], "min_expected": 600, "source": "enterprise-attack.json"},
    "ATT_CK_Mobile": {"aliases": ["ATT_CK_Mobile", "attack_mobile"], "min_expected": 150, "source": "mobile-attack.json"},
    "ATT_CK_ICS": {"aliases": ["ATT_CK_ICS", "attack_ics"], "min_expected": 100, "source": "ics-attack.json"},
    "CAPEC": {"aliases": ["CAPEC", "capec"], "min_expected": 500, "source": "MITRE CAPEC"},
    "D3FEND": {"aliases": ["D3FEND", "d3fend"], "min_expected": 150, "source": "D3FEND MITRE"},
    "ESA": {"aliases": ["ESA", "esa", "ESA_Shield", "esa_shield"], "min_expected": 100, "source": "ESA space shield"},
    "NVD": {"aliases": ["NVD", "nvd"], "min_expected": 1000, "source": "NVD/CVE feed"},
    "ISO": {"aliases": ["ISO", "iso", "ISO_27001"], "min_expected": 15, "source": "ISO 27001 References worksheet"},
    "NASA": {"aliases": ["NASA", "nasa"], "min_expected": 10, "source": "NASABPG worksheet"},
    "EMB3D": {"aliases": ["EMB3D", "emb3d"], "min_expected": 1, "source": "MITRE EMB3D API"},
}

# Referenced in SPARTA relationships/worksheets but not yet a corpus population.
REFERENCED_NOT_MATERIALIZED = {
    "csf_control": {
        "label": "NIST CSF 2.0",
        "notes": "Referenced in D3FEND Techniques column 'CSF 2.0'; no csf controls in sparta_controls.",
        "owner_lane": "ingest-sparta/external_source_ingestion",
    },
    "emb3d_threat": {
        "label": "MITRE EMB3D threats",
        "notes": "Worksheet + target_type configured; emb3d external source has 0 controls in corpus.",
        "owner_lane": "ingest-sparta/stage_01b_load_external",
    },
    "emb3d_mitigation": {
        "label": "MITRE EMB3D mitigations",
        "notes": "Same EMB3D dataset as threats; 0 materialized.",
        "owner_lane": "ingest-sparta/stage_01b_load_external",
    },
    "bsi_threat": {
        "label": "BSI threats",
        "notes": "Referenced in SPARTA Techniques; only a handful of BSI string matches in corpus.",
        "owner_lane": "ingest-sparta/worksheet_or_external",
    },
    "bsi_measure": {
        "label": "BSI security measures",
        "notes": "Referenced in D3FEND Techniques; not a first-class framework population.",
        "owner_lane": "ingest-sparta/worksheet_or_external",
    },
    "do326a": {
        "label": "DO-326A airworthiness security",
        "notes": "Stage 01b_load_external lists DO-326A PDF source; 0 controls in corpus.",
        "owner_lane": "ingest-sparta/stage_01b_load_external",
    },
    "arp4754a": {
        "label": "ARP4754A systems development",
        "notes": "Stage 01b_load_external lists ARP4754A PDF source; 0 controls in corpus.",
        "owner_lane": "ingest-sparta/stage_01b_load_external",
    },
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def _norm_fw(fw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fw.lower()).strip("_")


def corpus_framework_counts(db: Any) -> dict[str, int]:
    rows = list(db.aql.execute("""
        FOR c IN sparta_controls
            FILTER c.deprecated != true
            COLLECT fw = c.source_framework WITH COUNT INTO n
            RETURN {framework: fw, count: n}
    """))
    return {str(r["framework"]): int(r["count"]) for r in rows}


def aggregate_canonical(counts: dict[str, int]) -> dict[str, int]:
    agg: dict[str, int] = {}
    alias_to_canon = {}
    for canon, meta in CANONICAL_FRAMEWORKS.items():
        for alias in meta["aliases"]:
            alias_to_canon[_norm_fw(alias)] = canon
    for fw, n in counts.items():
        canon = alias_to_canon.get(_norm_fw(fw), None)
        key = canon or fw
        agg[key] = agg.get(key, 0) + n
    return agg


def case_duplicate_groups(counts: dict[str, int]) -> list[dict[str, Any]]:
    by_upper: dict[str, list[dict[str, Any]]] = {}
    for fw, n in counts.items():
        by_upper.setdefault(fw.upper(), []).append({"name": fw, "count": n})
    groups = []
    for upper, variants in by_upper.items():
        if len(variants) > 1:
            groups.append({"canonical_upper": upper, "variants": variants, "total": sum(v["count"] for v in variants)})
    groups.sort(key=lambda g: -g["total"])
    return groups


def referenced_target_presence(db: Any) -> dict[str, int]:
    """Heuristic presence counts for referenced-but-external target types."""
    out: dict[str, int] = {}
    out["emb3d_threat"] = int(
        list(
            db.aql.execute(
                """
        FOR c IN sparta_controls
            FILTER CONTAINS(LOWER(c.source_framework || ""), "emb3d")
            COLLECT WITH COUNT INTO n RETURN n
    """
            )
        )[0]
        or 0
    )
    out["emb3d_mitigation"] = out["emb3d_threat"]
    out["csf_control"] = int(
        list(
            db.aql.execute(
                """
        FOR c IN sparta_controls
            FILTER CONTAINS(LOWER(c.source_framework || ""), "csf")
               OR CONTAINS(LOWER(c.control_id || ""), "csf")
            COLLECT WITH COUNT INTO n RETURN n
    """
            )
        )[0]
        or 0
    )
    out["bsi_threat"] = int(
        list(
            db.aql.execute(
                """
        FOR c IN sparta_controls
            FILTER CONTAINS(LOWER(c.name || ""), "bsi")
               OR CONTAINS(LOWER(c.control_id || ""), "bsi")
            COLLECT WITH COUNT INTO n RETURN n
    """
            )
        )[0]
        or 0
    )
    out["bsi_measure"] = out["bsi_threat"]
    for key in ("do326a", "arp4754a"):
        out[key] = int(
            list(
                db.aql.execute(
                    f"""
            FOR c IN sparta_controls
                FILTER CONTAINS(LOWER(c.name || ""), "{key}")
                   OR CONTAINS(LOWER(c.control_id || ""), "{key}")
                COLLECT WITH COUNT INTO n RETURN n
        """
                )
            )[0]
            or 0
        )
    return out


def version_staleness_signals(db: Any) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    # Heimdall mapping provenance on CWE docs
    n = int(
        list(
            db.aql.execute(
                """
        FOR c IN sparta_controls
            FILTER STARTS_WITH(c.control_id, "CWE-")
            FILTER c.nist_source == "mitre_heimdall_800-53r4"
            COLLECT WITH COUNT INTO n RETURN n
    """
            )
        )[0]
        or 0
    )
    if n:
        signals.append(
            {
                "id": "cwe_nist_heimdall_rev4",
                "kind": "upstream_staleness_risk",
                "scale": n,
                "message": f"{n} CWE docs use MITRE Heimdall NIST SP 800-53 Rev 4 mapping; corpus stamped 2025.1 — verify NIST 800-53r5 crosswalk refresh.",
                "owner_lane": "ingest-sparta/ingest_cwe_nist",
                "action": "Re-run ingest_cwe_nist.py --download and reconcile NIST→SPARTA edges.",
            }
        )

    versions = list(
        db.aql.execute(
            """
        FOR c IN sparta_controls
            FILTER c.source_version != null
            COLLECT fw = c.source_framework, ver = c.source_version WITH COUNT INTO n
            RETURN {framework: fw, version: ver, count: n}
    """
        )
    )
    sparta_versions = {r["version"] for r in versions if str(r.get("framework", "")).upper() == "SPARTA"}
    config_version = None
    if WORKSHEETS.is_file():
        cfg = yaml.safe_load(WORKSHEETS.read_text(encoding="utf-8"))
        config_version = cfg.get("source_version")
    if config_version and sparta_versions and config_version not in sparta_versions:
        signals.append(
            {
                "id": "sparta_source_version_drift",
                "kind": "config_corpus_drift",
                "message": f"worksheets.yaml source_version={config_version} but corpus SPARTA versions={sorted(sparta_versions)}",
                "owner_lane": "ingest-sparta/pipeline_reingest",
                "action": "Confirm whether SPARTA-Data.xlsx v3.1 re-ingest is needed.",
            }
        )
    return signals


def build_ingestion_opportunities(db: Any) -> dict[str, Any]:
    raw_counts = corpus_framework_counts(db)
    canonical = aggregate_canonical(raw_counts)
    dupes = case_duplicate_groups(raw_counts)
    referenced = referenced_target_presence(db)
    staleness = version_staleness_signals(db)

    gaps: list[dict[str, Any]] = []
    for canon, meta in CANONICAL_FRAMEWORKS.items():
        count = int(canonical.get(canon, 0))
        min_exp = int(meta["min_expected"])
        if count < min_exp:
            gaps.append(
                {
                    "id": f"missing_or_thin_{canon.lower()}",
                    "category": "framework_ingestion",
                    "kind": "ingestion",
                    "impact": "high" if count == 0 else "medium",
                    "framework": canon,
                    "corpus_count": count,
                    "min_expected": min_exp,
                    "source": meta["source"],
                    "owner_lane": "ingest-sparta/pipeline",
                    "action": f"Ingest or refresh {canon} from {meta['source']}.",
                }
            )

    for target, meta in REFERENCED_NOT_MATERIALIZED.items():
        present = int(referenced.get(target, 0))
        if present == 0:
            gaps.append(
                {
                    "id": f"new_category_{target}",
                    "category": "new_control_category",
                    "kind": "ingestion",
                    "impact": "medium" if target.startswith("bsi") else "high",
                    "label": meta["label"],
                    "corpus_count": present,
                    "owner_lane": meta["owner_lane"],
                    "action": f"Ingest new control category: {meta['label']}.",
                    "notes": meta["notes"],
                }
            )

    for sig in staleness:
        gaps.append(
            {
                "id": sig["id"],
                "category": "upstream_refresh",
                "kind": "verification",
                "impact": "medium",
                "owner_lane": sig["owner_lane"],
                "action": sig["action"],
                "notes": sig.get("message"),
                "scale": sig.get("scale"),
            }
        )

    if dupes:
        gaps.append(
            {
                "id": "framework_case_duplicates",
                "category": "schema_normalization",
                "kind": "mechanical",
                "impact": "medium",
                "owner_lane": "ops-arango/mechanical_repair",
                "action": "Normalize source_framework casing before ingesting new populations.",
                "details": dupes[:8],
                "scale": len(dupes),
            }
        )

    gaps.sort(key=lambda g: (0 if g.get("impact") == "high" else 1, str(g.get("id"))))
    for i, g in enumerate(gaps, 1):
        g["rank"] = i

    return {
        "schema": "dewey_framework_ingestion_scan.v1",
        "generated_at": _now(),
        "corpus_framework_counts_raw": raw_counts,
        "corpus_framework_counts_canonical": canonical,
        "case_duplicate_groups": dupes,
        "ingestion_gaps": gaps,
        "summary": {
            "gap_count": len(gaps),
            "missing_entirely": [g["id"] for g in gaps if g.get("corpus_count") == 0],
            "high_impact": [g["id"] for g in gaps if g.get("impact") == "high"],
        },
        "freshness_guidance": {
            "when_to_brave_search": "Use brave-search when local worksheets/corpus cannot confirm whether MITRE/NIST/SPARTA released a newer catalog version.",
            "when_to_github_search": "Use github-search/gh read-only for MITRE CTI repos, heimdall_tools CSV, NIST/OSCAL repos, and upstream release tags.",
            "dewey_tools": ["brave-search", "github-search", "gh readonly"],
            "check_sources": [
                "https://attack.mitre.org/",
                "https://d3fend.mitre.org/",
                "https://emb3d.mitre.org/",
                "https://csrc.nist.gov/projects/cprt/catalog",
                "https://sparta.aerospace.org/",
            ],
        },
        "non_claims": [
            "This scan does not call upstream APIs or assert latest vendor versions.",
            "Thin ISO/NASA counts may match worksheet expectations, not ingestion failure.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    db = get_db()
    report = build_ingestion_opportunities(db)
    out = args.out or (OUTPUT_BASE / f"framework_ingestion_{report['generated_at']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
