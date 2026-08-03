"""Claim-bound resume variant compiler for Stage 0 local artifacts."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .util import read_json, sha256_bytes, sha256_json, stable_id, utc_now, write_json


def _claim_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if snapshot.get("schema") != "monitor_opportunities.claim_snapshot.v1" or snapshot.get("active") is not True:
        raise ValueError("active claim snapshot required")
    claims = snapshot.get("claims", [])
    return {
        claim["claim_key"]: claim
        for claim in claims
        if claim.get("approved") is True and claim.get("stale") is not True and claim.get("expired") is not True
    }


def _posting(posting_key: str) -> dict[str, Any]:
    if posting_key != "fixture:eligible-ai-architect":
        raise ValueError(f"unknown fixture posting: {posting_key}")
    return {
        "posting_key": posting_key,
        "opportunity_id": "opp:a:eligible-ai-architect",
        "title": "Principal AI Architect",
        "organization": "Acme Aerospace",
        "ats_provider": "greenhouse",
        "observed": ["Greenhouse-hosted apply surface", "JD emphasizes governed AI platforms"],
        "selected_claim_keys": [
            "claim:arcos:acert-architect",
            "claim:pdf-oxide:document-extraction",
            "claim:memory:retrieval-platform",
        ],
    }


def _paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def _write_docx(path: Path, lines: list[str]) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(_paragraph(line) for line in lines)}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        docx.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        docx.writestr("word/document.xml", document)


def _validate_no_prohibited_delta(lines: list[str], approved_texts: set[str]) -> list[str]:
    prohibited = []
    for line in lines:
        if line.startswith("Target role:"):
            continue
        if line and line not in approved_texts and not line.startswith(("Resume variant", "Selected claims")):
            prohibited.append(line)
    return prohibited


def _line_kind(line: str, approved_texts: set[str]) -> str:
    if line in approved_texts:
        return "approved_claim"
    if line.startswith("Target role:"):
        return "target_language"
    return "presentation"


def tailor(posting_key: str, claims_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = read_json(claims_path)
    posting = _posting(posting_key)
    claims = _claim_map(snapshot)
    selected = []
    for key in posting["selected_claim_keys"]:
        claim = claims.get(key)
        if claim is None:
            raise ValueError(f"missing approved claim: {key}")
        selected.append(claim)

    lines = [
        f"Resume variant for {posting['organization']}",
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
        claim_refs.append({"claim_key": claim["claim_key"], "wording_id": wording["wording_id"]})

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
        "claim_snapshot_sha256": sha256_json(snapshot),
        "claim_refs": claim_refs,
        "rendered_statements": rendered_statements,
        "artifact_refs": [str(text_path), str(docx_path)],
        "status": "WOULD_PRESENT_STAGE0",
    }
    profile = {
        "schema": "monitor_opportunities.screening_interface_profile.v1",
        "observed": posting["observed"],
        "inferred": ["Use ATS-readable plain text and single-column DOCX."],
        "unknowns": ["Employer ranking weights and recruiter workflow are unknown."],
        "confidence": 0.72,
    }
    diff = {
        "schema": "monitor_opportunities.presentation_diff.v1",
        "allowed_changes": ["selection", "ordering", "heading", "target_summary", "formatting"],
        "prohibited_changes": [],
    }
    receipt = {
        "schema": "monitor_opportunities.tailoring_receipt.v1",
        "generated_at": utc_now(),
        "mocked": False,
        "live": True,
        "external_effects": False,
        "variant_id": variant["variant_id"],
        "resume_txt_sha256": sha256_bytes(text_path.read_bytes()),
        "resume_docx_sha256": sha256_bytes(docx_path.read_bytes()),
        "claim_snapshot_sha256": variant["claim_snapshot_sha256"],
        "non_claims": ["This receipt proves local claim-bound rendering only, not employer selection."],
    }
    write_json(out_dir / "claim-snapshot.json", snapshot)
    write_json(out_dir / "screening-interface-profile.json", profile)
    write_json(out_dir / "resume-variant.json", variant)
    write_json(out_dir / "presentation-diff.json", diff)
    write_json(out_dir / "tailoring-receipt.json", receipt)
    return receipt
