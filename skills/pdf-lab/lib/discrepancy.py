"""Normalized extraction-discrepancy records and the second-pass backlog.

Two schemas:

- ``pdf_lab.extraction_discrepancy.v1`` — one immutable, deduplicatable
  record per discrepancy. The model may PROPOSE field values, but this
  module's deterministic validator decides whether a record is admissible.
- ``pdf_lab.second_pass_backlog.v1`` — the engineering backlog artifact
  (``pdf-lab-second-pass-backlog.json``) that converts agent-resolved
  findings (each carrying a ``recommended_engine_fix``) into durable,
  fingerprinted work items for a downstream fixing agent. ``status-report``
  audits runs against this file; before this module nothing produced it.

Fingerprints:

- ``defect_key`` is stable across repairs: it identifies WHAT is wrong
  (document, page, region/text anchor, expected role, discrepancy class).
- ``observation_id`` identifies one OBSERVATION of that defect under a
  specific extractor commit / preset / expected contract / comparison.
  A repeated observation updates the existing backlog entry (same
  defect_key) instead of duplicating it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

DISCREPANCY_SCHEMA = "pdf_lab.extraction_discrepancy.v1"
BACKLOG_SCHEMA = "pdf_lab.second_pass_backlog.v1"

# Owner routing vocabulary. A discrepancy must be routed to exactly one
# owner layer before a repair agent may act on it.
OWNER_LAYERS = (
    "pdf_oxide_core_bug",
    "document_preset_bug",
    "comparison_or_canonicalization_bug",
    "second_pass_or_harness_bug",
    "human_contract_ambiguity",
    "accepted_extra_or_not_a_bug",
    "blocked_missing_evidence",
)

_REQUIRED_FIELDS = (
    "schema_version",
    "defect_key",
    "observation_id",
    "source_pdf_sha256",
    "page",
    "discrepancy_class",
    "expected_semantic_role",
    "region_anchor",
    "owner_layer",
    "evidence",
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_anchor(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:200]


def compute_defect_key(
    *,
    source_pdf_sha256: str,
    page: int,
    region_anchor: str,
    expected_semantic_role: str,
    discrepancy_class: str,
) -> str:
    material = "\n".join(
        [
            source_pdf_sha256,
            str(int(page)),
            _normalize_anchor(region_anchor),
            expected_semantic_role or "",
            discrepancy_class or "",
        ]
    )
    return f"sha256:{_sha256_text(material)}"


def compute_observation_id(
    *,
    defect_key: str,
    extractor_commit: str,
    preset_hash: str,
    expected_contract_hash: str,
    comparison_receipt_hash: str,
) -> str:
    material = "\n".join(
        [
            defect_key,
            extractor_commit or "",
            preset_hash or "",
            expected_contract_hash or "",
            comparison_receipt_hash or "",
        ]
    )
    return f"sha256:{_sha256_text(material)}"


def build_discrepancy(
    *,
    source_pdf_sha256: str,
    page: int,
    discrepancy_class: str,
    expected_semantic_role: str,
    region_anchor: str,
    owner_layer: str,
    evidence: dict[str, Any],
    goal: dict[str, Any] | None = None,
    expected_element: dict[str, Any] | None = None,
    actual_elements: list[dict[str, Any]] | None = None,
    extractor_commit: str = "",
    preset_hash: str = "",
    expected_contract_hash: str = "",
    comparison_receipt_hash: str = "",
    second_pass_decision_receipt: str | None = None,
    severity: str = "normal",
    recommended_engine_fix: str | None = None,
    missing_evidence: list[str] | None = None,
    non_claims: list[str] | None = None,
) -> dict[str, Any]:
    defect_key = compute_defect_key(
        source_pdf_sha256=source_pdf_sha256,
        page=page,
        region_anchor=region_anchor,
        expected_semantic_role=expected_semantic_role,
        discrepancy_class=discrepancy_class,
    )
    record = {
        "schema_version": DISCREPANCY_SCHEMA,
        "defect_key": defect_key,
        "observation_id": compute_observation_id(
            defect_key=defect_key,
            extractor_commit=extractor_commit,
            preset_hash=preset_hash,
            expected_contract_hash=expected_contract_hash,
            comparison_receipt_hash=comparison_receipt_hash,
        ),
        "goal": goal,
        "source_pdf_sha256": source_pdf_sha256,
        "page": int(page),
        "discrepancy_class": discrepancy_class,
        "expected_semantic_role": expected_semantic_role,
        "region_anchor": _normalize_anchor(region_anchor),
        "expected_element": expected_element,
        "actual_elements": actual_elements or [],
        "extractor_commit": extractor_commit,
        "preset_hash": preset_hash,
        "expected_contract_hash": expected_contract_hash,
        "comparison_receipt_hash": comparison_receipt_hash,
        "second_pass_decision_receipt": second_pass_decision_receipt,
        "owner_layer": owner_layer,
        "severity": severity,
        "recommended_engine_fix": recommended_engine_fix,
        "missing_evidence": missing_evidence or [],
        "non_claims": non_claims
        or [
            "This record does not claim the repair approach is correct.",
            "This record does not claim semantic ground truth beyond the cited evidence.",
        ],
        "evidence": evidence,
    }
    validate_discrepancy(record)
    return record


def validate_discrepancy(record: dict[str, Any]) -> None:
    """Deterministic admissibility gate. Raises ValueError on violation."""
    if not isinstance(record, dict):
        raise ValueError("discrepancy record must be a dict")
    for field in _REQUIRED_FIELDS:
        if field not in record or record[field] in (None, ""):
            raise ValueError(f"discrepancy record missing required field: {field}")
    if record["schema_version"] != DISCREPANCY_SCHEMA:
        raise ValueError(
            f"unsupported schema_version: {record['schema_version']!r}"
        )
    if record["owner_layer"] not in OWNER_LAYERS:
        raise ValueError(
            f"owner_layer must be one of {OWNER_LAYERS}; got {record['owner_layer']!r}"
        )
    for key_field in ("defect_key", "observation_id"):
        value = str(record[key_field])
        if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
            raise ValueError(f"{key_field} must be a sha256:<hex64> fingerprint")
    if not isinstance(record["page"], int) or record["page"] < 0:
        raise ValueError("page must be a non-negative integer")
    if not isinstance(record["evidence"], dict) or not record["evidence"]:
        raise ValueError("evidence must be a non-empty dict")
    # Recompute the defect_key: the fingerprint must be derivable from the
    # record's own fields, never trusted from the producer.
    recomputed = compute_defect_key(
        source_pdf_sha256=record["source_pdf_sha256"],
        page=record["page"],
        region_anchor=record["region_anchor"],
        expected_semantic_role=record["expected_semantic_role"],
        discrepancy_class=record["discrepancy_class"],
    )
    if recomputed != record["defect_key"]:
        raise ValueError("defect_key does not match record fields (tampered or stale)")


_FINDING_OWNER_HINTS = {
    "table_row_fragment": "pdf_oxide_core_bug",
    "table_false_positive": "pdf_oxide_core_bug",
    "page_frame_false_positive": "pdf_oxide_core_bug",
    "prose_false_positive": "pdf_oxide_core_bug",
    "sidebar_watermark_bleed": "document_preset_bug",
    "bbox_only_miss": "comparison_or_canonicalization_bug",
}


def build_second_pass_backlog(
    findings: list[dict[str, Any]],
    *,
    source_pdf_sha256: str = "",
    extractor_commit: str = "",
    preset_hash: str = "",
    expected_contract_hash: str = "",
    comparison_receipt_hash: str = "",
    goal: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Convert agent-resolved findings into the fingerprinted backlog.

    Findings without a recommended_engine_fix are still tracked (a
    suppressed defect with no repair guidance is itself backlog), but they
    are flagged so the status report can demand guidance.
    """
    entries: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for finding in findings:
        page = int(finding.get("page") or 0)
        kind = str(finding.get("kind") or finding.get("classification") or "unknown")
        anchor_source = str(
            finding.get("target_id")
            or finding.get("element_id")
            or finding.get("finding_id")
            or ""
        )
        defect_key = compute_defect_key(
            source_pdf_sha256=source_pdf_sha256,
            page=page,
            region_anchor=anchor_source,
            expected_semantic_role=str(finding.get("type") or kind),
            discrepancy_class=kind,
        )
        if defect_key in seen:
            entries[seen[defect_key]]["observation_count"] += 1
            continue
        seen[defect_key] = len(entries)
        entries.append(
            {
                "defect_key": defect_key,
                "observation_id": compute_observation_id(
                    defect_key=defect_key,
                    extractor_commit=extractor_commit,
                    preset_hash=preset_hash,
                    expected_contract_hash=expected_contract_hash,
                    comparison_receipt_hash=comparison_receipt_hash,
                ),
                "observation_count": 1,
                "finding_id": finding.get("finding_id"),
                "page": page,
                "kind": kind,
                "classification": finding.get("classification"),
                "target_id": finding.get("target_id"),
                "target_bbox": finding.get("target_bbox") or finding.get("bbox"),
                "reason": finding.get("reason"),
                "recommended_engine_fix": finding.get("recommended_engine_fix"),
                "has_engine_fix_guidance": bool(finding.get("recommended_engine_fix")),
                "proposed_owner_layer": _FINDING_OWNER_HINTS.get(
                    kind, "pdf_oxide_core_bug"
                ),
                "status": "open",
            }
        )

    return {
        "schema_version": BACKLOG_SCHEMA,
        "created_at": created_at,
        "goal": goal,
        "source_pdf_sha256": source_pdf_sha256,
        "extractor_commit": extractor_commit,
        "preset_hash": preset_hash,
        "expected_contract_hash": expected_contract_hash,
        # finding_count / backlog_count are the fields status_report.py
        # audits (second_pass_backlog_tracked requires finding_count >=
        # agent_resolved_count).
        "finding_count": len(findings),
        "backlog_count": len(entries),
        "entries": entries,
    }


def write_second_pass_backlog(
    output_dir: Path,
    findings: list[dict[str, Any]],
    **kwargs: Any,
) -> Path:
    backlog = build_second_pass_backlog(findings, **kwargs)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pdf-lab-second-pass-backlog.json"
    path.write_text(
        json.dumps(backlog, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path
