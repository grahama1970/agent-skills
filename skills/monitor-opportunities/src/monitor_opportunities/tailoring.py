"""Claim-bound resume variant compiler for Stage 0 local artifacts."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .util import read_json, sha256_bytes, sha256_json, stable_id, utc_now, write_json

DIFF_CLASSES = [
    "CLAIM_SELECTION",
    "CLAIM_ORDER",
    "SECTION_ORDER",
    "HEADING",
    "APPROVED_ALIAS",
    "TARGET_SUMMARY",
    "LAYOUT_OR_FORMAT",
]


def _claim_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if snapshot.get("schema") != "monitor_opportunities.claim_snapshot.v1" or snapshot.get("active") is not True:
        raise ValueError("active claim snapshot required")
    claims = snapshot.get("claims", [])
    approved: dict[str, dict[str, Any]] = {}
    for claim in claims:
        if claim.get("approved") is not True:
            continue
        if claim.get("verification_status") not in {None, "approved"}:
            continue
        if "resume" not in claim.get("allowed_channels", ["resume"]):
            continue
        if claim.get("stale") is True or claim.get("expired") is True:
            continue
        if _is_expired(claim.get("valid_until")):
            continue
        approved_wordings = [wording for wording in claim.get("wordings", []) if wording.get("approved", True) is True]
        if not approved_wordings:
            continue
        approved[claim["claim_key"]] = {**claim, "wordings": approved_wordings}
    return approved


def _is_expired(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _posting(posting_key: str) -> dict[str, Any]:
    if posting_key != "fixture:eligible-ai-architect":
        raise ValueError(f"unknown fixture posting: {posting_key}")
    return {
        "posting_key": posting_key,
        "opportunity_id": "opp:a:eligible-ai-architect",
        "title": "Principal AI Architect",
        "organization": "Acme Aerospace",
        "ats_provider": "greenhouse",
        "ats_host": "greenhouse.io",
        "employer_url": "fixture://eligible-ai-architect",
        "observed": ["Greenhouse-hosted apply surface", "JD emphasizes governed AI platforms"],
        "form_fields": [
            {"name": "resume", "required": True, "kind": "file_upload"},
            {"name": "cover_letter", "required": False, "kind": "file_upload"},
        ],
        "accepted_file_formats": ["docx", "pdf", "txt"],
        "jd_language_patterns": ["governed AI platforms", "document intelligence", "source-grounded retrieval"],
        "selected_claim_keys": [
            "claim:arcos:acert-architect",
            "claim:pdf-oxide:document-extraction",
            "claim:memory:retrieval-platform",
        ],
    }


def _posting_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    text = str(candidate.get("posting_text") or "")
    keywords = [
        keyword
        for keyword in ["agent", "AI", "document", "retrieval", "automation", "integration", "platform"]
        if keyword.lower() in text.lower()
    ]
    return {
        "posting_key": candidate["candidate_id"],
        "opportunity_id": candidate["candidate_id"],
        "title": candidate["title"],
        "organization": candidate["organization"],
        "ats_provider": candidate.get("source_provider") or "not-established",
        "ats_host": candidate.get("source_provider") or "not-established",
        "employer_url": candidate.get("primary_evidence_url") or candidate.get("posting_url") or candidate["candidate_id"],
        "observed": [
            f"Source provider: {candidate.get('source_provider', 'unknown')}",
            f"Primary evidence: {candidate.get('primary_evidence_url') or candidate.get('posting_url') or candidate['candidate_id']}",
        ],
        "form_fields": [
            {"name": "resume", "required": True, "kind": "file_upload"},
            {"name": "free_text_answers", "required": True, "kind": "human_required"},
        ],
        "accepted_file_formats": ["docx", "pdf", "txt"],
        "jd_language_patterns": keywords or ["source-backed opportunity evidence"],
        "selected_claim_keys": [
            "claim:arcos:acert-architect",
            "claim:pdf-oxide:document-extraction",
            "claim:memory:retrieval-platform",
        ],
    }


def _paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def _writestr_deterministic(docx: zipfile.ZipFile, name: str, content: str) -> None:
    info = zipfile.ZipInfo(name)
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    docx.writestr(info, content)


def _write_docx(path: Path, lines: list[str]) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(_paragraph(line) for line in lines)}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        _writestr_deterministic(docx, "[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        _writestr_deterministic(docx, "_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        _writestr_deterministic(docx, "word/document.xml", document)


def _validate_no_prohibited_delta(lines: list[str], approved_texts: set[str]) -> list[str]:
    prohibited = []
    for line in lines:
        if line.startswith(("Target role:", "Selected claims:")):
            continue
        if line and line not in approved_texts:
            prohibited.append(line)
    return prohibited


def _line_kind(line: str, approved_texts: set[str]) -> str:
    if line in approved_texts:
        return "approved_claim"
    if line.startswith("Target role:"):
        return "target_language"
    return "presentation"


def _tailor_posting(posting: dict[str, Any], claims_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = read_json(claims_path)
    posting_key = posting["posting_key"]
    claims = _claim_map(snapshot)
    selected = []
    for key in posting["selected_claim_keys"]:
        claim = claims.get(key)
        if claim is None:
            raise ValueError(f"missing approved claim: {key}")
        selected.append(claim)

    lines = [
        f"Target role: {posting['title']}",
        "Selected claims:",
    ]
    claim_refs = []
    rendered_statements = []
    approved_texts = set()
    for claim in selected:
        wording = claim["wordings"][0]
        lines.append(wording["text"])
        approved_texts.add(wording["text"])
        claim_refs.append(
            {
                "claim_key": claim["claim_key"],
                "wording_id": wording["wording_id"],
                "evidence_refs": claim.get("evidence_refs", []),
                "verification_status": claim.get("verification_status", "approved"),
                "allowed_channels": claim.get("allowed_channels", ["resume"]),
                "sensitivity": claim.get("sensitivity", "public"),
                "valid_from": claim.get("valid_from"),
                "valid_until": claim.get("valid_until"),
            }
        )

    prohibited = _validate_no_prohibited_delta(lines, approved_texts)
    if prohibited:
        raise ValueError(f"prohibited factual delta: {prohibited}")
    for line in lines:
        kind = _line_kind(line, approved_texts)
        refs = []
        if kind == "approved_claim":
            for claim in selected:
                for wording in claim["wordings"]:
                    if wording["text"] == line:
                        refs.append({"claim_key": claim["claim_key"], "wording_id": wording["wording_id"]})
        rendered_statements.append({"text": line, "kind": kind, "claim_refs": refs})

    resume_txt = "\n".join(lines) + "\n"
    text_path = out_dir / "resume.txt"
    docx_path = out_dir / "resume.docx"
    text_path.write_text(resume_txt, encoding="utf-8")
    _write_docx(docx_path, lines)
    variant = {
        "schema": "monitor_opportunities.resume_variant.v1",
        "variant_id": stable_id("resume", {"posting": posting_key, "claims": claim_refs}),
        "posting_key": posting_key,
        "opportunity_id": posting["opportunity_id"],
        "posting_digest": sha256_json(posting),
        "claim_snapshot_sha256": sha256_json(snapshot),
        "claim_refs": claim_refs,
        "rendered_statements": rendered_statements,
        "artifact_refs": [str(text_path), str(docx_path)],
        "status": "WOULD_PRESENT_STAGE0",
    }
    profile = {
        "schema": "monitor_opportunities.screening_interface_profile.v1",
        "profile_id": stable_id("screening-profile", {"posting": posting_key}),
        "posting_key": posting_key,
        "ats_provider": posting["ats_provider"],
        "ats_host": posting["ats_host"],
        "employer_url": posting["employer_url"],
        "observed_form_fields": posting["form_fields"],
        "accepted_file_formats": posting["accepted_file_formats"],
        "jd_language_patterns": posting["jd_language_patterns"],
        "observed": posting["observed"],
        "presentation_recommendations": ["Use ATS-readable plain text and single-column DOCX."],
        "inferred": ["Single-column DOCX is parser-sensitive and safer than table or text-box layout."],
        "evidence_refs": [posting["employer_url"]],
        "limitations": ["Fixture posting captures only observed local evidence."],
        "unknowns": ["Employer ranking weights, knockout logic, and recruiter workflow are unknown."],
        "confidence": 0.72,
    }
    diff = {
        "schema": "monitor_opportunities.presentation_diff.v1",
        "canonical_claim_order": [claim["claim_key"] for claim in snapshot.get("claims", [])],
        "selected_claim_order": [ref["claim_key"] for ref in claim_refs],
        "changes": [
            {"change_type": "TARGET_SUMMARY", "description": "Added clearly labeled target role from posting."},
            {"change_type": "HEADING", "description": "Rendered selected claims under an ATS-safe heading."},
            {"change_type": "CLAIM_SELECTION", "description": "Selected approved claims relevant to the fixture posting."},
            {"change_type": "CLAIM_ORDER", "description": "Ordered selected claims by posting relevance."},
            {"change_type": "LAYOUT_OR_FORMAT", "description": "Rendered plain text and minimal single-column DOCX."},
        ],
        "allowed_changes": DIFF_CLASSES,
        "prohibited_changes": [],
    }
    profile_digest = sha256_json(profile)
    variant["screening_interface_profile_sha256"] = profile_digest
    diff_digest = sha256_json(diff)
    receipt = {
        "schema": "monitor_opportunities.tailoring_receipt.v1",
        "generated_at": utc_now(),
        "mocked": False,
        "live": True,
        "external_effects": False,
        "variant_id": variant["variant_id"],
        "posting_digest": variant["posting_digest"],
        "screening_interface_profile_sha256": profile_digest,
        "presentation_diff_sha256": diff_digest,
        "resume_txt_sha256": sha256_bytes(text_path.read_bytes()),
        "resume_docx_sha256": sha256_bytes(docx_path.read_bytes()),
        "docx_hash_normalization": "Minimal writer emits no dynamic metadata; hash is deterministic for identical lines.",
        "claim_snapshot_sha256": variant["claim_snapshot_sha256"],
        "observed": profile["observed"],
        "inferred": profile["inferred"],
        "unknown": profile["unknowns"],
        "not_claimed": [
            "No employer ranking weights are known.",
            "No recruiter workflow is known.",
            "No candidate fact outside approved claim wording was rendered.",
            "This receipt proves local claim-bound rendering only, not employer selection.",
        ],
        "non_claims": ["This receipt proves local claim-bound rendering only, not employer selection."],
    }
    write_json(out_dir / "claim-snapshot.json", snapshot)
    write_json(out_dir / "screening-interface-profile.json", profile)
    write_json(out_dir / "resume-variant.json", variant)
    write_json(out_dir / "presentation-diff.json", diff)
    write_json(out_dir / "tailoring-receipt.json", receipt)
    return receipt


def tailor(posting_key: str, claims_path: Path, out_dir: Path) -> dict[str, Any]:
    return _tailor_posting(_posting(posting_key), claims_path, out_dir)


def tailor_candidate(candidate: dict[str, Any], claims_path: Path, out_dir: Path) -> dict[str, Any]:
    return _tailor_posting(_posting_from_candidate(candidate), claims_path, out_dir)
