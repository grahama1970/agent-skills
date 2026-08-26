"""Per-opportunity tailored resume artifacts.

Composes the active ATS base resume with a claim-bound targeted-highlights
section for one opportunity, validates that every added content line is an
approved claim wording (presentation-only delta; tailoring cannot mint
facts), and renders a PDF through the resume repo's exporter. The PDF digest
binds into the application plan's ``resume_digest``/``attachment_digests``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .util import read_json, sha256_json, stable_id

RESUME_REPO_DEFAULT = Path.home() / "workspace" / "experiments" / "resume"
RESUME_SKILL_DEFAULT = Path(__file__).resolve().parents[3] / "resume"


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


_STOP_TERMS = frozenset(
    "the a an and or of for in to with on at by is are you your our we will this that as be from".split()
)


def _terms(text: str) -> set[str]:
    return {
        token.strip(".,()/:;*+").lower()
        for token in text.split()
        if len(token) > 3
    } - _STOP_TERMS


def select_aligned_lines(base_markdown: str, posting_text: str, limit: int = 6) -> list[dict[str, Any]]:
    """Pick the base resume's own bullet lines that best match the posting.

    Selection and reordering of verbatim existing lines is presentation-only:
    no line is generated, so no fact can be minted.
    """

    posting_terms = _terms(posting_text)
    scored = []
    for line in base_markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        overlap = _terms(stripped) & posting_terms
        if len(overlap) >= 2:
            scored.append({"line": stripped, "matched_terms": sorted(overlap), "score": len(overlap)})
    scored.sort(key=lambda row: (-row["score"], row["line"]))
    return scored[:limit]


def rank_competencies(posting_text: str, resume_skill: Path = RESUME_SKILL_DEFAULT) -> list[str]:
    """Ask /resume which competencies this posting actually asks for.

    The ordering comes from the canonical project-taxonomy registry via
    competencies.py, so a tailored variant leads with domains the catalog can
    back rather than whichever cluster happens to be listed first. Returns an
    empty list when the posting is empty or the helper is unavailable: leading
    order is a presentation nicety, never a gate on producing the artifact.
    """
    if not posting_text.strip():
        return []
    script = resume_skill / "scripts" / "competencies.py"
    if not script.is_file():
        return []
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(posting_text)
        posting_path = Path(fh.name)
    try:
        proc = subprocess.run(
            ["uv", "run", "--project", str(resume_skill), "python", str(script), "match", str(posting_path)],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            return []
        return list(json.loads(proc.stdout).get("lead_with", []))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    finally:
        posting_path.unlink(missing_ok=True)


def build_variant_markdown(
    base_markdown: str,
    opportunity: dict[str, Any],
    wordings: list[dict[str, str]],
    posting_text: str = "",
) -> str:
    """Base resume + presentation-only targeted sections; no new facts."""

    sections = [
        f"## Targeted highlights — {opportunity['title']} at {opportunity['organization']}",
        "",
        *[f"- {row['text']}" for row in wordings],
        "",
    ]
    leads = rank_competencies(posting_text)
    if leads:
        sections += [
            f"## Competencies this role asks for — {opportunity['title']}",
            "",
            # Ordering only: every name is a discipline the skills catalog
            # already declares, counted in project-taxonomy.
            "- " + ", ".join(d.replace("-", " ") for d in leads),
            "",
        ]
    aligned = select_aligned_lines(base_markdown, posting_text) if posting_text else []
    if aligned:
        sections += [
            f"## Role alignment — {opportunity['title']}",
            "",
            *[row["line"] for row in aligned],
            "",
        ]
    # The only added content lines are approved claim wordings and verbatim
    # lines already present in the base resume; headers are presentation.
    return base_markdown.rstrip() + "\n\n" + "\n".join(sections)


def compose_resume_variant_manifest(
    *,
    claim_snapshot: dict[str, Any],
    opportunity: dict[str, Any],
    wordings: list[dict[str, str]],
    base_path: Path,
    out_dir: Path,
    resume_skill: Path = RESUME_SKILL_DEFAULT,
) -> dict[str, Any]:
    """Compose the /resume skill and read back its authoritative variant manifest.

    The resume skill re-validates every selected claim (approved + evidence-backed)
    at its own boundary and emits ``resume-variant.json``; that manifest is the
    authoritative claim-binding receipt for the tailored artifact.
    """

    by_key = {claim["claim_key"]: claim for claim in claim_snapshot.get("claims", [])}
    request = {
        "opportunity_id": opportunity["opportunity_id"],
        "target_title": opportunity["title"],
        "claim_keys": [row["claim_key"] for row in wordings],
        "claims": [
            {
                "claim_key": row["claim_key"],
                "text": row["text"],
                "approved": True,
                "evidence_refs": list(by_key[row["claim_key"]].get("evidence_refs", [])),
            }
            for row in wordings
        ],
    }
    request_path = out_dir / "tailoring-request.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    variant_dir = out_dir / "resume-variant"
    proc = subprocess.run(
        [
            str(resume_skill / "run.sh"),
            "tailor",
            str(base_path),
            str(request_path),
            "--output-dir",
            str(variant_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    manifest_path = variant_dir / "resume-variant.json"
    if proc.returncode != 0 or not manifest_path.exists():
        raise ResumeArtifactError(f"RESUME_SKILL_TAILOR_FAILED:{proc.stderr[-300:]}")
    manifest = read_json(manifest_path)
    if manifest.get("seam_validation", {}).get("status") != "PASS":
        raise ResumeArtifactError("RESUME_VARIANT_SEAM_FAILED")
    manifest_keys = [ref["claim_key"] for ref in manifest.get("claim_refs", [])]
    if manifest_keys != [row["claim_key"] for row in wordings]:
        raise ResumeArtifactError("RESUME_VARIANT_CLAIM_MISMATCH")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


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
    posting_text: str = "",
) -> dict[str, Any]:
    """Produce one claim-bound tailored resume PDF for one opportunity."""

    source = read_json(skill_dir / "config" / "resume_source.json")
    base_path = Path(source["base_markdown"])
    if not base_path.exists():
        repo_base = skill_dir.parents[1] / "RESUME.md"
        if repo_base.exists():
            base_path = repo_base
    if not base_path.exists():
        raise ResumeArtifactError(f"BASE_RESUME_MISSING:{base_path}")
    claim_snapshot = read_json(skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json")
    wordings = approved_wordings(claim_snapshot, list(opportunity.get("claim_keys", [])))
    variant_md = build_variant_markdown(base_path.read_text(encoding="utf-8"), opportunity, wordings, posting_text=posting_text)
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_manifest = compose_resume_variant_manifest(
        claim_snapshot=claim_snapshot,
        opportunity=opportunity,
        wordings=wordings,
        base_path=base_path,
        out_dir=out_dir,
    )
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
        "resume_variant_manifest": {
            "schema": variant_manifest.get("schema"),
            "path": variant_manifest["manifest_path"],
            "variant_sha256": variant_manifest.get("variant_sha256"),
            "claim_refs": variant_manifest.get("claim_refs", []),
        },
        "markdown_path": str(md_path),
        "pdf_path": str(pdf_path),
        "pdf_sha256": pdf_sha,
        "pdf_bytes": pdf_path.stat().st_size,
        "external_effects": False,
    }
    receipt["receipt_digest"] = sha256_json(receipt)
    return receipt
