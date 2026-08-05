"""Per-opportunity tailored resume artifacts.

Composes the active ATS base resume with a claim-bound targeted-highlights
section for one opportunity, validates that every added content line is an
approved claim wording (presentation-only delta; tailoring cannot mint
facts), and renders a PDF through the resume repo's exporter. The PDF digest
binds into the application plan's ``resume_digest``/``attachment_digests``.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .util import read_json, sha256_json, stable_id

RESUME_REPO_DEFAULT = Path.home() / "workspace" / "experiments" / "resume"


class ResumeArtifactError(ValueError):
    """Stable tailored-resume artifact error."""


def approved_wordings(claim_snapshot: dict[str, Any], claim_keys: list[str]) -> list[dict[str, str]]:
    by_key = {claim["claim_key"]: claim for claim in claim_snapshot.get("claims", [])}
    rows: list[dict[str, str]] = []
    for key in claim_keys:
        claim = by_key.get(key)
        if claim is None:
            raise ResumeArtifactError(f"UNAPPROVED_CLAIM:{key}")
        wording = claim["wordings"][0]
        rows.append({"claim_key": key, "wording_id": wording["wording_id"], "text": wording["text"]})
    if not rows:
        raise ResumeArtifactError("NO_CLAIMS_SELECTED")
    return rows


def build_variant_markdown(
    base_markdown: str,
    opportunity: dict[str, Any],
    wordings: list[dict[str, str]],
) -> str:
    """Base resume + presentation-only targeted section; no new facts."""

    header = (
        f"## Targeted highlights — {opportunity['title']} at {opportunity['organization']}\n\n"
        + "\n".join(f"- {row['text']}" for row in wordings)
        + "\n"
    )
    # The only added content lines are approved claim wordings; everything
    # else added here is a structural header, which is presentation.
    return base_markdown.rstrip() + "\n\n" + header


def render_pdf(markdown_path: Path, pdf_path: Path, resume_repo: Path = RESUME_REPO_DEFAULT) -> None:
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(resume_repo),
            "resume-job",
            "pdf",
            "--output",
            str(pdf_path),
            "--title",
            markdown_path.stem,
            str(markdown_path),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(resume_repo),
    )
    if proc.returncode != 0 or not pdf_path.exists():
        raise ResumeArtifactError(f"PDF_RENDER_FAILED:{proc.stderr[-300:]}")


def tailor_artifact(
    *,
    skill_dir: Path,
    opportunity: dict[str, Any],
    out_dir: Path,
    resume_repo: Path = RESUME_REPO_DEFAULT,
) -> dict[str, Any]:
    """Produce one claim-bound tailored resume PDF for one opportunity."""

    source = read_json(skill_dir / "config" / "resume_source.json")
    base_path = Path(source["base_markdown"])
    if not base_path.exists():
        raise ResumeArtifactError(f"BASE_RESUME_MISSING:{base_path}")
    claim_snapshot = read_json(skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json")
    wordings = approved_wordings(claim_snapshot, list(opportunity.get("claim_keys", [])))
    variant_md = build_variant_markdown(base_path.read_text(encoding="utf-8"), opportunity, wordings)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = opportunity["opportunity_id"].replace(":", "-")
    md_path = out_dir / f"resume-{slug}.md"
    pdf_path = out_dir / f"resume-{slug}.pdf"
    md_path.write_text(variant_md, encoding="utf-8")
    render_pdf(md_path, pdf_path, resume_repo)
    pdf_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    receipt = {
        "schema": "monitor_opportunities.tailored_resume_artifact.v1",
        "variant_id": stable_id("resume-artifact", {"opportunity": opportunity["opportunity_id"], "wordings": wordings}),
        "opportunity_id": opportunity["opportunity_id"],
        "organization": opportunity["organization"],
        "title": opportunity["title"],
        "base_markdown_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "claim_snapshot_sha256": sha256_json(claim_snapshot),
        "claim_refs": wordings,
        "markdown_path": str(md_path),
        "pdf_path": str(pdf_path),
        "pdf_sha256": pdf_sha,
        "pdf_bytes": pdf_path.stat().st_size,
        "external_effects": False,
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt
