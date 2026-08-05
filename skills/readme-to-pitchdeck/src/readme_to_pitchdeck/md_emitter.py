"""One-way Marp Markdown export of a validated deck bundle.

Emits `deck.md` (Marp front-matter, one slide per `---` section, speaker notes
as HTML comments) plus copied assets, from manifests that pass the same
fail-closed validate_bundle gates as every other target. ONE-WAY by design:
Markdown has no structural slot for claim ids, visibility, or qualifiers, so
edits belong in the YAML manifests — a regenerated deck.md overwrites local
changes. Render with: `marp deck.md --pdf` (or --pptx, image-per-slide).
Failure modes: validation errors raise before anything is written.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from .models import (
    AssetManifest,
    ClaimLedger,
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SourceManifest,
)
from .validation import validate_bundle


def emit_markdown(
    deck: DeckManifest,
    claim_ledger: ClaimLedger,
    source_manifest: SourceManifest,
    asset_manifest: AssetManifest,
    *,
    source_manifest_dir: Path,
    asset_manifest_dir: Path,
    output_dir: Path,
) -> OperationReceipt:
    """Validate the bundle and write Marp-flavored deck.md + assets."""
    report = validate_bundle(
        deck,
        claim_ledger,
        source_manifest,
        asset_manifest,
        source_manifest_dir=source_manifest_dir,
        asset_manifest_dir=asset_manifest_dir,
    )
    errors = [issue for issue in report.issues if issue.severity == "error"]
    if errors:
        detail = "; ".join(f"{issue.code}: {issue.message}" for issue in errors[:5])
        raise ValueError(f"bundle failed claim/source validation: {detail}")

    assets_by_id = {asset.id: asset for asset in asset_manifest.assets}
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_out = output_dir / "assets"

    lines: list[str] = [
        "---",
        "marp: true",
        "theme: default",
        "class: invert",
        "paginate: true",
        f'title: "{deck.deck.title}"',
        "---",
        "",
        f"# {deck.deck.title}",
        "",
        *( [deck.deck.subtitle, ""] if deck.deck.subtitle else [] ),
    ]

    for slide in sorted(deck.slides, key=lambda s: s.order):
        lines.extend(["---", "", f"## {slide.title}", "", slide.message, ""])
        for item in slide.body:
            lines.append(f"- {item}")
        if slide.body:
            lines.append("")
        spec = assets_by_id.get(slide.visual.asset_id) if slide.visual.asset_id else None
        if spec and spec.local_path:
            src = (asset_manifest_dir / spec.local_path).resolve()
            if src.exists():
                assets_out.mkdir(parents=True, exist_ok=True)
                name = f"{spec.id}{src.suffix}"
                shutil.copyfile(src, assets_out / name)
                lines.extend([f"![{spec.alt_text}](assets/{name})", ""])
        if slide.footer:
            lines.extend([f"*{slide.footer}*", ""])
        if slide.notes:
            lines.extend([f"<!-- {slide.notes} -->", ""])

    out_path = output_dir / "deck.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("marp markdown written: {} ({} slides)", out_path, len(deck.slides))

    receipt = OperationReceipt(
        schema="readme_to_pitchdeck.emit_md_receipt.v1",
        operation="emit-md",
        readiness=Readiness.READY,
        mocked=False,
        live=False,
        inputs={"deck_id": deck.deck.id, "slides": str(len(deck.slides))},
        outputs={"deck_md": str(out_path.resolve())},
        counts={"slides": len(deck.slides)},
        gaps=[],
        claims=OperationClaims(
            proves=["deck.md was generated from manifests that passed fail-closed validation."],
            does_not_prove=[
                "Markdown edits stay claim-compliant — this export is one-way; edit the YAML manifests instead.",
                "Marp rendering output quality (marp CLI is not invoked here).",
            ],
        ),
        seam_validation=SeamValidation(kind="emit_md_receipt"),
    )
    from .io import dump_json

    dump_json(receipt, output_dir / "emit_md_receipt.json")
    return receipt
