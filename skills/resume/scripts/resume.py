"""Validate canonical Markdown resumes and compile evidence-bound variants.

Inputs are a Markdown source and, for tailoring, a JSON request containing typed
claim records. Outputs are either a deterministic validation report or a Markdown
variant plus a JSON manifest. The command fails closed for missing files, malformed
requests, unapproved claims, missing evidence, and output write errors.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from loguru import logger


app = typer.Typer(add_completion=False, no_args_is_help=True)


class ResumeInputError(ValueError):
    """Raised when a resume source or tailoring request violates the contract."""


@dataclass(frozen=True, slots=True)
class Claim:
    """A validated, approved claim that can cross into a resume variant."""

    claim_key: str
    text: str
    approved: bool
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: Any) -> "Claim":
        """Parse and validate one external claim record."""
        if not isinstance(payload, dict):
            raise ResumeInputError("each claim must be a JSON object")
        claim_key = payload.get("claim_key")
        text = payload.get("text")
        evidence_refs = payload.get("evidence_refs")
        if not isinstance(claim_key, str) or not claim_key.strip():
            raise ResumeInputError("claim_key must be a non-empty string")
        if not isinstance(text, str) or not text.strip():
            raise ResumeInputError(f"claim {claim_key!r} has no text")
        if payload.get("approved") is not True:
            raise ResumeInputError(f"claim {claim_key!r} is not approved")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise ResumeInputError(f"claim {claim_key!r} has no evidence_refs")
        if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_refs):
            raise ResumeInputError(f"claim {claim_key!r} has an invalid evidence ref")
        return cls(claim_key.strip(), text.strip(), True, tuple(evidence_refs))


@dataclass(frozen=True, slots=True)
class TailoringRequest:
    """Validated request crossing from opportunity monitoring into this skill."""

    opportunity_id: str
    target_title: str
    target_terms: tuple[str, ...]
    claim_keys: tuple[str, ...]
    claims: tuple[Claim, ...]

    @classmethod
    def from_payload(cls, payload: Any) -> "TailoringRequest":
        """Parse and validate a tailoring request at the producer boundary."""
        if not isinstance(payload, dict):
            raise ResumeInputError("tailoring request must be a JSON object")
        opportunity_id = payload.get("opportunity_id")
        target_title = payload.get("target_title")
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise ResumeInputError("opportunity_id must be a non-empty string")
        if not isinstance(target_title, str) or not target_title.strip():
            raise ResumeInputError("target_title must be a non-empty string")

        raw_terms = payload.get("target_terms", [])
        raw_keys = payload.get("claim_keys", [])
        raw_claims = payload.get("claims", [])
        if not isinstance(raw_terms, list) or any(not isinstance(x, str) for x in raw_terms):
            raise ResumeInputError("target_terms must be a list of strings")
        if not isinstance(raw_keys, list) or any(not isinstance(x, str) for x in raw_keys):
            raise ResumeInputError("claim_keys must be a list of strings")
        claims = tuple(Claim.from_payload(item) for item in raw_claims) if isinstance(raw_claims, list) else ()
        if not isinstance(raw_claims, list):
            raise ResumeInputError("claims must be a list")
        by_key = {claim.claim_key: claim for claim in claims}
        selected = tuple(key.strip() for key in raw_keys if key.strip())
        if len(set(selected)) != len(selected):
            raise ResumeInputError("claim_keys must be unique")
        missing = [key for key in selected if key not in by_key]
        if missing:
            raise ResumeInputError(f"selected claims missing from request: {', '.join(missing)}")
        return cls(
            opportunity_id.strip(),
            target_title.strip(),
            tuple(term.strip() for term in raw_terms if term.strip()),
            selected,
            claims,
        )


def sha256_bytes(data: bytes) -> str:
    """Return a stable SHA-256 digest for an emitted artifact."""
    return hashlib.sha256(data).hexdigest()


def read_source(source: Path) -> str:
    """Read a Markdown source and reject empty or unresolved content."""
    if not source.is_file():
        raise ResumeInputError(f"resume source does not exist: {source}")
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ResumeInputError("resume source is empty")
    if not any(line.startswith("# ") for line in text.splitlines()):
        raise ResumeInputError("resume source must contain a top-level Markdown heading")
    forbidden = ("TODO", "TBD", "<PLACEHOLDER>", "{{", "}}")
    found = [marker for marker in forbidden if marker in text]
    if found:
        raise ResumeInputError(f"resume source contains unresolved markers: {', '.join(found)}")
    return text


def load_request(path: Path) -> TailoringRequest:
    """Load and validate a JSON tailoring request."""
    if not path.is_file():
        raise ResumeInputError(f"tailoring request does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResumeInputError(f"invalid tailoring JSON: {exc.msg}") from exc
    return TailoringRequest.from_payload(payload)


def render_variant(source: str, request: TailoringRequest) -> str:
    """Render a presentation-only variant without changing source claims."""
    selected = {claim.claim_key: claim for claim in request.claims}
    lines = [
        f"# Resume Variant: {request.target_title}",
        "",
        f"Opportunity: {request.opportunity_id}",
        "",
        "## Selected Claim Evidence",
        "",
    ]
    for key in request.claim_keys:
        claim = selected[key]
        refs = ", ".join(claim.evidence_refs)
        lines.extend((f"- {claim.text}", f"  Evidence: {refs}"))
    if request.target_terms:
        lines.extend(("", "## Target Terms", "", ", ".join(request.target_terms)))
    lines.extend(("", "## Canonical Resume", "", source.rstrip(), ""))
    return "\n".join(lines)


def write_variant(source: Path, request_path: Path, output_dir: Path) -> Path:
    """Compile a variant and manifest after all inputs pass validation."""
    source_text = read_source(source)
    request = load_request(request_path)
    variant_text = render_variant(source_text, request)
    output_dir.mkdir(parents=True, exist_ok=True)
    variant_path = output_dir / "resume.md"
    manifest_path = output_dir / "resume-variant.json"
    variant_bytes = variant_text.encode("utf-8")
    variant_path.write_bytes(variant_bytes)
    manifest = {
        "schema": "resume.variant.v1",
        "variant_id": f"resume:{request.opportunity_id}",
        "opportunity_id": request.opportunity_id,
        "target_title": request.target_title,
        "source_path": str(source),
        "source_sha256": sha256_bytes(source_text.encode("utf-8")),
        "variant_sha256": sha256_bytes(variant_bytes),
        "claim_refs": [
            {"claim_key": claim.claim_key, "evidence_refs": list(claim.evidence_refs)}
            for claim in (next(item for item in request.claims if item.claim_key == key) for key in request.claim_keys)
        ],
        "artifact_refs": [str(variant_path), str(manifest_path)],
        "status": "WOULD_PRESENT_STAGE0",
        "seam_validation": {"kind": "resume.variant.v1", "status": "PASS"},
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


@app.command()
def validate(source: Path = typer.Argument(..., exists=False, readable=True)) -> None:
    """Validate a canonical Markdown resume source."""
    try:
        text = read_source(source)
    except (OSError, ResumeInputError) as exc:
        logger.error("resume validation failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({"status": "PASS", "path": str(source), "bytes": len(text.encode("utf-8"))}))


@app.command()
def tailor(
    source: Path = typer.Argument(..., exists=False, readable=True),
    request: Path = typer.Argument(..., exists=False, readable=True),
    output_dir: Path = typer.Option(..., "--output-dir", "-o", file_okay=False),
) -> None:
    """Compile one claim-bound Markdown variant and its manifest."""
    try:
        manifest_path = write_variant(source, request, output_dir)
    except (OSError, ResumeInputError) as exc:
        logger.error("resume tailoring failed: {}", exc)
        raise typer.Exit(code=1) from exc
    typer.echo(str(manifest_path))


if __name__ == "__main__":
    app()
