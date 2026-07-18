"""pdf_lab.extraction_discrepancy.v1 records and the second-pass backlog.

The backlog artifact (pdf-lab-second-pass-backlog.json) was previously
consumed and audited by status-report but produced by nothing. These tests
pin the producer: fingerprint stability, dedup semantics, validator
admissibility, and the status-report consumption contract
(finding_count / backlog_count).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.discrepancy import (  # noqa: E402
    BACKLOG_SCHEMA,
    DISCREPANCY_SCHEMA,
    OWNER_LAYERS,
    build_discrepancy,
    build_second_pass_backlog,
    compute_defect_key,
    compute_observation_id,
    validate_discrepancy,
    write_second_pass_backlog,
)

PDF_SHA = "sha256:" + "a" * 64


def _finding(fid, *, page=12, kind="table_false_positive", target="actual:p12:table:0", fix="tighten frame filter"):
    return {
        "finding_id": fid,
        "kind": kind,
        "classification": "page_frame_false_positive",
        "page": page,
        "target_id": target,
        "target_bbox": [0.1, 0.1, 0.9, 0.9],
        "reason": "near page frame with sparse pseudo-columns",
        "recommended_engine_fix": fix,
    }


def test_defect_key_stable_across_repairs():
    kwargs = dict(
        source_pdf_sha256=PDF_SHA,
        page=193,
        region_anchor="actual:p193:block:31",
        expected_semantic_role="paragraph_block",
        discrepancy_class="body_text_as_chrome",
    )
    key1 = compute_defect_key(**kwargs)
    key2 = compute_defect_key(**kwargs)
    assert key1 == key2
    assert key1.startswith("sha256:") and len(key1) == 7 + 64

    obs1 = compute_observation_id(
        defect_key=key1,
        extractor_commit="commit-a",
        preset_hash="sha256:" + "b" * 64,
        expected_contract_hash="sha256:" + "c" * 64,
        comparison_receipt_hash="sha256:" + "d" * 64,
    )
    obs2 = compute_observation_id(
        defect_key=key1,
        extractor_commit="commit-b",
        preset_hash="sha256:" + "b" * 64,
        expected_contract_hash="sha256:" + "c" * 64,
        comparison_receipt_hash="sha256:" + "d" * 64,
    )
    assert obs1 != obs2, "new extractor commit = new observation"


def test_defect_key_normalizes_anchor_whitespace_and_case():
    base = dict(
        source_pdf_sha256=PDF_SHA,
        page=1,
        expected_semantic_role="paragraph",
        discrepancy_class="missing_text",
    )
    assert compute_defect_key(region_anchor="  Modern   Information Systems ", **base) == (
        compute_defect_key(region_anchor="modern information systems", **base)
    )


def test_build_discrepancy_valid_and_tamper_detected():
    record = build_discrepancy(
        source_pdf_sha256=PDF_SHA,
        page=28,
        discrepancy_class="missing_expected",
        expected_semantic_role="section_heading",
        region_anchor="INTRODUCTION",
        owner_layer="pdf_oxide_core_bug",
        evidence={"comparison_miss_reason": "below_iou_threshold"},
        recommended_engine_fix="promote post-merge heading",
    )
    assert record["schema_version"] == DISCREPANCY_SCHEMA
    validate_discrepancy(record)

    tampered = dict(record, page=29)
    with pytest.raises(ValueError, match="defect_key does not match"):
        validate_discrepancy(tampered)


def test_validator_rejects_unknown_owner_layer():
    with pytest.raises(ValueError, match="owner_layer"):
        build_discrepancy(
            source_pdf_sha256=PDF_SHA,
            page=1,
            discrepancy_class="x",
            expected_semantic_role="y",
            region_anchor="z",
            owner_layer="somebody_else",
            evidence={"e": 1},
        )
    assert "human_contract_ambiguity" in OWNER_LAYERS


def test_backlog_dedups_by_defect_key_and_counts_observations():
    findings = [
        _finding("f1"),
        _finding("f2"),  # same page/target/kind -> same defect_key
        _finding("f3", page=259, kind="prose_false_positive", target="actual:p259:table:0"),
    ]
    backlog = build_second_pass_backlog(
        findings,
        source_pdf_sha256=PDF_SHA,
        extractor_commit="0.3.74",
    )
    assert backlog["schema_version"] == BACKLOG_SCHEMA
    assert backlog["finding_count"] == 3
    assert backlog["backlog_count"] == 2
    dup = next(e for e in backlog["entries"] if e["page"] == 12)
    assert dup["observation_count"] == 2
    assert dup["has_engine_fix_guidance"] is True
    assert dup["proposed_owner_layer"] == "pdf_oxide_core_bug"


def test_backlog_satisfies_status_report_contract(tmp_path):
    findings = [_finding("f1"), _finding("f2", page=259, target="actual:p259:table:0")]
    path = write_second_pass_backlog(
        tmp_path, findings, source_pdf_sha256=PDF_SHA
    )
    assert path.name == "pdf-lab-second-pass-backlog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    # status_report.py: second_pass_backlog_tracked requires
    # finding_count >= agent_resolved_count; backlog_count is reported.
    assert payload["finding_count"] >= len(findings)
    assert isinstance(payload["backlog_count"], int)


def test_finding_without_fix_guidance_is_flagged():
    backlog = build_second_pass_backlog([_finding("f1", fix=None)])
    assert backlog["entries"][0]["has_engine_fix_guidance"] is False
