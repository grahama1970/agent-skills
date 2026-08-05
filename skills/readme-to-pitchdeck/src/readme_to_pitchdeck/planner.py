from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .io import SkillError, dump_json, dump_yaml, expand_path, slugify, write_text
from .markdown import (
    MarkdownDocument,
    MarkdownSection,
    candidate_sentences,
    compact_text,
    first_strong_phrase,
    parse_markdown,
)
from .models import (
    AssetKind,
    AssetManifest,
    AssetSpec,
    AssetStatus,
    Claim,
    ClaimGuard,
    ClaimKind,
    ClaimLedger,
    ClaimRisk,
    ClaimStatus,
    DeckManifest,
    DeckMeta,
    DeckSourcePolicy,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
    SlideLayout,
    SlideSpec,
    SourceManifest,
    SourceRef,
    SourceSpec,
    Visibility,
    VisualSpec,
    VisualType,
)


_STATUS_WORDS = re.compile(
    r"\b(ready|implemented|demonstrated|working|complete|closed|passed|production|deployed|operational)\b",
    re.IGNORECASE,
)
_PROOF_WORDS = re.compile(r"\b(proof|receipt|evidence|test|commit|sha|count|records?)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d[\d,._-]*\b")


def _claim_kind(section: str, text: str) -> ClaimKind:
    value = f"{section} {text}".lower()
    if any(token in value for token in ("collaboration", "next step", "call to action", "contact")):
        return ClaimKind.ASK
    if any(token in value for token in ("remaining", "closure", "roadmap", "known gap", "not yet")):
        return ClaimKind.ROADMAP
    if _PROOF_WORDS.search(value) or _NUMBER_RE.search(value):
        return ClaimKind.PROOF
    if _STATUS_WORDS.search(value):
        return ClaimKind.STATUS
    if any(token in value for token in ("why", "north star", "principle", "boundary")):
        return ClaimKind.THESIS
    if any(token in value for token in ("product", "overview", "what is", "one view")):
        return ClaimKind.PRODUCT
    return ClaimKind.CANDIDATE


def _risk_for(kind: ClaimKind, text: str) -> tuple[ClaimRisk, str | None]:
    if kind in {ClaimKind.PROOF, ClaimKind.STATUS} or _STATUS_WORDS.search(text):
        return (
            ClaimRisk.HIGH,
            "Verify this status against the pinned source commit and current evidence before external use.",
        )
    if kind in {ClaimKind.PRODUCT, ClaimKind.THESIS, ClaimKind.ROADMAP}:
        return ClaimRisk.MEDIUM, None
    return ClaimRisk.LOW, None


def _resolve_source_manifest(manifest: SourceManifest, manifest_path: Path) -> SourceManifest:
    resolved_sources: list[SourceSpec] = []
    for source in manifest.sources:
        resolved = source.model_copy(
            update={"path": str(expand_path(source.path, base_dir=manifest_path.parent))}
        )
        path = Path(resolved.path)
        if resolved.required and not path.exists():
            raise SkillError(
                f"Required source '{resolved.id}' is missing at {path}. "
                "Set the path or environment variable in source_manifest.yaml."
            )
        resolved_sources.append(resolved)
    return manifest.model_copy(update={"sources": resolved_sources})


def _included_section(source: SourceSpec, section: str) -> bool:
    lowered = section.lower()
    if source.include_sections and not any(value.lower() in lowered for value in source.include_sections):
        return False
    if source.exclude_sections and any(value.lower() in lowered for value in source.exclude_sections):
        return False
    return True


def _make_claims(
    manifest: SourceManifest,
    documents: dict[str, MarkdownDocument],
) -> ClaimLedger:
    claims: list[Claim] = []
    used_ids: set[str] = set()

    for source in manifest.sources:
        document = documents.get(source.id)
        if document is None:
            continue
        section_counts: dict[str, int] = defaultdict(int)
        for section, text, line in candidate_sentences(document):
            if not _included_section(source, section):
                continue
            section_counts[section] += 1
            base = f"{source.id}-{slugify(section)}-{section_counts[section]:02d}"
            claim_id = slugify(base, fallback=f"claim-{len(claims)+1:03d}")
            while claim_id in used_ids:
                claim_id = f"{claim_id}-{len(used_ids)+1}"
            used_ids.add(claim_id)
            kind = _claim_kind(section, text)
            risk, qualifier = _risk_for(kind, text)
            claims.append(
                Claim(
                    id=claim_id,
                    text=text,
                    kind=kind,
                    visibility=source.visibility,
                    source_refs=[
                        SourceRef(
                            source_id=source.id,
                            section=section,
                            locator=f"line {line}",
                        )
                    ],
                    risk=risk,
                    status=ClaimStatus.CANDIDATE,
                    required_qualifier=qualifier,
                    notes="Auto-extracted candidate; human approval is required.",
                )
            )

    public_source = next(
        (source for source in manifest.sources if source.visibility == Visibility.PUBLIC),
        manifest.sources[0],
    )
    for index, text in enumerate(manifest.policy.mandatory_non_claims, start=1):
        claim_id = f"non-claim-{index:02d}-{slugify(text)[:36]}"
        while claim_id in used_ids:
            claim_id += "-x"
        used_ids.add(claim_id)
        claims.append(
            Claim(
                id=claim_id,
                text=text,
                kind=ClaimKind.NON_CLAIM,
                visibility=Visibility.PUBLIC,
                source_refs=[
                    SourceRef(
                        source_id=public_source.id,
                        section="Source policy / responsible use",
                        locator="mandatory_non_claims",
                    )
                ],
                risk=ClaimRisk.MANDATORY_NON_CLAIM,
                status=ClaimStatus.APPROVED,
                notes="Mandatory boundary language supplied by the source policy.",
            )
        )

    return ClaimLedger(project_name=manifest.project_name, claims=claims)


def _asset_kind(src: str, section: str) -> AssetKind:
    value = f"{src} {section}".lower()
    if "screenshot" in value or "capture" in value:
        return AssetKind.SCREENSHOT
    if "logo" in value or "mark" in value or "helmet" in value:
        return AssetKind.LOGO
    if "diagram" in value or "flow" in value or "architecture" in value:
        return AssetKind.DIAGRAM
    return AssetKind.ILLUSTRATION


def _make_assets(
    manifest: SourceManifest,
    documents: dict[str, MarkdownDocument],
) -> AssetManifest:
    assets: list[AssetSpec] = []
    used_ids: set[str] = set()
    for source in manifest.sources:
        document = documents.get(source.id)
        if document is None:
            continue
        source_root = Path(source.path).parent
        for index, image in enumerate(document.images, start=1):
            raw_id = f"{source.id}-{slugify(image.section)}-{index:02d}"
            asset_id = slugify(raw_id, fallback=f"asset-{len(assets)+1:03d}")
            while asset_id in used_ids:
                asset_id += "-x"
            used_ids.add(asset_id)

            local_path: str | None = None
            status = AssetStatus.PLANNED
            if image.src.startswith(("http://", "https://")):
                source_url = image.src
            else:
                source_url = None
                resolved = expand_path(image.src, base_dir=source_root)
                local_path = str(resolved)
                status = AssetStatus.PRESENT if resolved.exists() else AssetStatus.MISSING

            kind = _asset_kind(image.src, image.section)
            generation_brief = None
            if status != AssetStatus.PRESENT:
                generation_brief = (
                    f"Create or recapture a slide-safe {kind.value} for '{image.section}' at 16:9. "
                    "Keep text out of generated imagery; use native slide labels and retain source/capture metadata."
                )

            assets.append(
                AssetSpec(
                    id=asset_id,
                    kind=kind,
                    visibility=source.visibility,
                    local_path=local_path,
                    source_url=source_url,
                    required=False,
                    alt_text=image.alt or f"Visual for {image.section}",
                    target_aspect="16:9",
                    status=status,
                    generation_brief=generation_brief,
                    source_ref=SourceRef(
                        source_id=source.id,
                        section=image.section,
                        locator=f"line {image.line}",
                    ),
                )
            )
    return AssetManifest(project_name=manifest.project_name, assets=assets)


def _section_items(section: MarkdownSection | None, *, max_items: int = 4) -> list[str]:
    if section is None:
        return []
    items = section.bullets[:max_items]
    if len(items) < max_items:
        items.extend(section.paragraphs[1 : 1 + (max_items - len(items))])
    return [compact_text(item, 170) for item in items if item.strip()][:max_items]


def _section_message(section: MarkdownSection | None, fallback: str) -> str:
    if section is None:
        return fallback
    if section.paragraphs:
        return compact_text(section.paragraphs[0], 360)
    if section.bullets:
        return compact_text(section.bullets[0], 360)
    return fallback


def _source_ref(source_id: str, section: MarkdownSection | str) -> SourceRef:
    if isinstance(section, MarkdownSection):
        return SourceRef(source_id=source_id, section=section.heading, locator=f"line {section.line}")
    return SourceRef(source_id=source_id, section=section)


def _claims_for(
    ledger: ClaimLedger,
    source_id: str,
    section: str,
    *, limit: int = 3,
) -> list[str]:
    result: list[str] = []
    for claim in ledger.claims:
        if claim.kind == ClaimKind.NON_CLAIM:
            continue
        for ref in claim.source_refs:
            if ref.source_id == source_id and (ref.section or "").lower() == section.lower():
                result.append(claim.id)
                if len(result) >= limit:
                    return result
    return result


def _notes_for(claim_ids: list[str], ledger: ClaimLedger, source_refs: list[SourceRef]) -> str:
    claim_map = {claim.id: claim for claim in ledger.claims}
    lines = ["Draft slide generated from README source material."]
    qualifiers = [
        claim_map[claim_id].required_qualifier
        for claim_id in claim_ids
        if claim_id in claim_map and claim_map[claim_id].required_qualifier
    ]
    if qualifiers:
        lines.append("Required qualifiers:")
        lines.extend(f"- {qualifier}" for qualifier in dict.fromkeys(qualifiers))
    lines.append("Sources:")
    for ref in source_refs:
        label = ref.source_id
        if ref.section:
            label += f" — {ref.section}"
        if ref.locator:
            label += f" ({ref.locator})"
        lines.append(f"- {label}")
    lines.append("Human review required before external use.")
    return "\n".join(lines)


def _find(document: MarkdownDocument, keywords: list[str]) -> MarkdownSection | None:
    return document.find_section(keywords)


def _add_slide(
    slides: list[SlideSpec],
    *,
    role: str,
    layout: SlideLayout,
    title: str,
    message: str,
    visibility: Visibility,
    source_refs: list[SourceRef],
    claim_ids: list[str],
    ledger: ClaimLedger,
    body: list[str] | None = None,
    visual: VisualSpec | None = None,
    non_claim_ids: list[str] | None = None,
) -> None:
    order = len(slides) + 1
    slides.append(
        SlideSpec(
            id=slugify(f"{order:02d}-{role}"),
            order=order,
            role=role,
            layout=layout,
            visibility=visibility,
            title=title[:120],
            message=message[:500],
            body=body or [],
            source_refs=source_refs,
            claim_ids=claim_ids + (non_claim_ids or []),
            visual=visual or VisualSpec(),
            claim_guard=ClaimGuard(
                allowed_claim_ids=claim_ids,
                requires_non_claim_ids=non_claim_ids or [],
            ),
            notes=_notes_for(claim_ids + (non_claim_ids or []), ledger, source_refs),
        )
    )


def _make_deck(
    manifest: SourceManifest,
    documents: dict[str, MarkdownDocument],
    ledger: ClaimLedger,
    assets: AssetManifest,
    max_slides: int,
) -> DeckManifest:
    allowed_public_ids = set(manifest.policy.public_deck_source_ids)
    public_sources = [
        source
        for source in manifest.sources
        if source.visibility == Visibility.PUBLIC
        and (not allowed_public_ids or source.id in allowed_public_ids)
        and source.id in documents
    ]
    if not public_sources:
        raise SkillError("No readable public source is available for a public deck plan.")

    primary = public_sources[0]
    doc = documents[primary.id]
    slides: list[SlideSpec] = []
    intro_claims = [
        claim.id
        for claim in ledger.claims
        if claim.visibility == Visibility.PUBLIC
        and any(ref.source_id == primary.id and ref.section == "Introduction" for ref in claim.source_refs)
    ][:2]
    tagline = first_strong_phrase(Path(primary.path)) or (doc.intro[0] if doc.intro else manifest.deck_title)
    cover_ref = [_source_ref(primary.id, "Introduction")]
    _add_slide(
        slides,
        role="cover",
        layout=SlideLayout.COVER,
        title=doc.title or manifest.deck_title,
        message=compact_text(tagline, 300),
        visibility=Visibility.PUBLIC,
        source_refs=cover_ref,
        claim_ids=intro_claims,
        ledger=ledger,
    )

    planned_sections: list[tuple[str, list[str], SlideLayout, str, str]] = [
        ("problem", ["problem", "challenge", "failure mode"], SlideLayout.STATEMENT, "The problem", "Why the current workflow fails"),
        ("thesis", ["why", "north star", "principles", "boundaries"], SlideLayout.THREE_CARDS, "The thesis", "What must remain true"),
        ("product", ["product in one view", "overview", "at a glance", "product"], SlideLayout.SPLIT, "The product", "What the product changes"),
        ("how-it-works", ["how it works", "architecture", "workflow"], SlideLayout.FLOW, "How it works", "From source material to an inspectable decision"),
    ]

    consumed_sections: set[str] = set()
    for role, keywords, layout, title, fallback in planned_sections:
        if len(slides) >= max_slides - 3:
            break
        section = _find(doc, keywords)
        if section is None or section.heading in consumed_sections:
            continue
        consumed_sections.add(section.heading)
        refs = [_source_ref(primary.id, section)]
        claim_ids = _claims_for(ledger, primary.id, section.heading)
        items = _section_items(section)
        visual = VisualSpec()
        if layout == SlideLayout.FLOW:
            flow_items = items or [compact_text(p, 80) for p in section.paragraphs[:5]]
            if len(flow_items) >= 2:
                visual = VisualSpec(type=VisualType.NATIVE_DIAGRAM, items=flow_items[:6])
        _add_slide(
            slides,
            role=role,
            layout=layout,
            title=title,
            message=_section_message(section, fallback),
            body=items,
            visibility=Visibility.PUBLIC,
            source_refs=refs,
            claim_ids=claim_ids,
            ledger=ledger,
            visual=visual,
        )

    asset_by_source_section: dict[tuple[str, str], AssetSpec] = {}
    for asset in assets.assets:
        if asset.visibility != Visibility.PUBLIC or not asset.source_ref:
            continue
        key = (asset.source_ref.source_id, asset.source_ref.section or "")
        if asset.kind != AssetKind.LOGO and key not in asset_by_source_section:
            asset_by_source_section[key] = asset

    for section in doc.sections:
        if len(slides) >= max_slides - 3:
            break
        key = (primary.id, section.heading)
        asset = asset_by_source_section.get(key)
        if asset is None or section.heading in consumed_sections:
            continue
        consumed_sections.add(section.heading)
        refs = [_source_ref(primary.id, section)]
        claim_ids = _claims_for(ledger, primary.id, section.heading)
        _add_slide(
            slides,
            role=f"product-view-{slugify(section.heading)}",
            layout=SlideLayout.SCREENSHOT,
            title=section.heading,
            message=_section_message(section, f"Inspect {section.heading} in context."),
            body=_section_items(section, max_items=3),
            visibility=Visibility.PUBLIC,
            source_refs=refs,
            claim_ids=claim_ids,
            ledger=ledger,
            visual=VisualSpec(
                type=VisualType.SCREENSHOT if asset.kind == AssetKind.SCREENSHOT else VisualType.IMAGE,
                asset_id=asset.id,
                caption=f"Source visual from {section.heading}; verify capture freshness before use.",
            ),
        )

    status = _find(doc, ["current status", "proof", "demonstrated", "evidence"])
    if status and len(slides) < max_slides - 2:
        refs = [_source_ref(primary.id, status)]
        _add_slide(
            slides,
            role="proof-today",
            layout=SlideLayout.PROOF_CARDS,
            title="What is established today",
            message=_section_message(status, "Use dated, scoped proof rather than readiness theater."),
            body=_section_items(status, max_items=4),
            visibility=Visibility.PUBLIC,
            source_refs=refs,
            claim_ids=_claims_for(ledger, primary.id, status.heading, limit=4),
            ledger=ledger,
        )
        consumed_sections.add(status.heading)

    gaps = _find(doc, ["remaining", "closure gates", "known gaps", "roadmap", "in integration"])
    if gaps and len(slides) < max_slides - 1:
        refs = [_source_ref(primary.id, gaps)]
        _add_slide(
            slides,
            role="honest-gaps",
            layout=SlideLayout.ROADMAP,
            title="What remains open",
            message=_section_message(gaps, "Keep open work visible and scoped."),
            body=_section_items(gaps, max_items=5),
            visibility=Visibility.PUBLIC,
            source_refs=refs,
            claim_ids=_claims_for(ledger, primary.id, gaps.heading, limit=4),
            ledger=ledger,
        )
        consumed_sections.add(gaps.heading)

    # Fill sparse decks from additional substantive sections before the ask.
    for section in doc.sections:
        if len(slides) >= max(7, max_slides - 1):
            break
        if section.heading in consumed_sections or not section.text:
            continue
        if any(token in section.heading.lower() for token in ("responsible use", "license", "go deeper", "collaboration", "next step", "contact")):
            continue
        refs = [_source_ref(primary.id, section)]
        _add_slide(
            slides,
            role=f"section-{slugify(section.heading)}",
            layout=SlideLayout.STATEMENT,
            title=section.heading,
            message=_section_message(section, section.heading),
            body=_section_items(section, max_items=4),
            visibility=Visibility.PUBLIC,
            source_refs=refs,
            claim_ids=_claims_for(ledger, primary.id, section.heading),
            ledger=ledger,
        )
        consumed_sections.add(section.heading)

    ask = _find(doc, ["collaboration", "next step", "evaluate", "contact"])
    ask_ref = [_source_ref(primary.id, ask or "Collaboration / next step")]
    ask_claims = _claims_for(ledger, primary.id, ask.heading, limit=3) if ask else []
    non_claim_ids = [claim.id for claim in ledger.claims if claim.kind == ClaimKind.NON_CLAIM]
    non_claim_text = [claim.text for claim in ledger.claims if claim.kind == ClaimKind.NON_CLAIM]
    ask_message = _section_message(
        ask,
        "Use one representative claim to test workflow fit, evidence boundaries, and the next collaboration step.",
    )
    _add_slide(
        slides,
        role="collaboration-ask",
        layout=SlideLayout.COLLABORATION,
        title="A useful next conversation",
        message=ask_message,
        body=_section_items(ask, max_items=3) or [
            "Workflow co-design",
            "Integration design",
            "Deployment and governance planning",
        ],
        visibility=Visibility.PUBLIC,
        source_refs=ask_ref,
        claim_ids=ask_claims,
        ledger=ledger,
        non_claim_ids=non_claim_ids,
    )
    if non_claim_text:
        slides[-1].notes += "\nMandatory non-claims:\n" + "\n".join(f"- {text}" for text in non_claim_text)

    if len(slides) > max_slides:
        slides = slides[: max_slides - 1] + [slides[-1]]
        for index, slide in enumerate(slides, start=1):
            slide.order = index
            slide.id = slugify(f"{index:02d}-{slide.role}")

    return DeckManifest(
        deck=DeckMeta(
            id=slugify(f"{manifest.project_name}-public"),
            title=manifest.deck_title,
            subtitle=tagline,
            audience=manifest.audience,
            visibility=Visibility.PUBLIC,
            target_editor="google_slides",
            theme="dark_cyan_evidence",
            source_policy=DeckSourcePolicy.PUBLIC_ONLY,
        ),
        slides=slides,
    )


def _speaker_notes(deck: DeckManifest) -> str:
    blocks: list[str] = [f"# Speaker notes — {deck.deck.title}"]
    for slide in sorted(deck.slides, key=lambda value: value.order):
        blocks.extend(
            [
                "",
                f"## {slide.order}. {slide.title}",
                "",
                slide.notes or "No notes supplied.",
            ]
        )
    return "\n".join(blocks)


def plan_bundle(
    source_manifest: SourceManifest,
    *,
    source_manifest_path: Path,
    output_dir: Path,
    max_slides: int = 12,
) -> OperationReceipt:
    if max_slides < 6 or max_slides > 20:
        raise SkillError("--max-slides must be between 6 and 20")

    resolved = _resolve_source_manifest(source_manifest, source_manifest_path)
    documents: dict[str, MarkdownDocument] = {}
    gaps: list[str] = []
    for source in resolved.sources:
        path = Path(source.path)
        if not path.exists():
            gaps.append(f"Optional source missing: {source.id} at {path}")
            continue
        documents[source.id] = parse_markdown(path)

    ledger = _make_claims(resolved, documents)
    assets = _make_assets(resolved, documents)
    deck = _make_deck(resolved, documents, ledger, assets, max_slides)

    output_dir.mkdir(parents=True, exist_ok=True)
    dump_yaml(resolved, output_dir / "source_manifest.resolved.yaml")
    dump_yaml(ledger, output_dir / "claim_ledger.yaml")
    dump_yaml(assets, output_dir / "asset_manifest.yaml")
    dump_yaml(deck, output_dir / "deck.public.yaml")
    write_text(output_dir / "speaker_notes.md", _speaker_notes(deck))

    candidate_claims = sum(1 for claim in ledger.claims if claim.status == ClaimStatus.CANDIDATE)
    missing_assets = sum(1 for asset in assets.assets if asset.status != AssetStatus.PRESENT)
    if candidate_claims:
        gaps.append(f"{candidate_claims} claims remain candidate and require human review")
    if missing_assets:
        gaps.append(f"{missing_assets} assets are missing, remote, stale, or planned")

    receipt = OperationReceipt(
        schema="readme_to_pitchdeck.plan_receipt.v1",
        operation="plan",
        readiness=Readiness.USABLE_WITH_GAPS if gaps else Readiness.READY,
        mocked=False,
        live=False,
        inputs={"source_manifest": str(source_manifest_path.resolve())},
        outputs={
            "source_manifest": str((output_dir / "source_manifest.resolved.yaml").resolve()),
            "claim_ledger": str((output_dir / "claim_ledger.yaml").resolve()),
            "asset_manifest": str((output_dir / "asset_manifest.yaml").resolve()),
            "deck_manifest": str((output_dir / "deck.public.yaml").resolve()),
            "speaker_notes": str((output_dir / "speaker_notes.md").resolve()),
        },
        counts={
            "sources": len(resolved.sources),
            "read_sources": len(documents),
            "claims": len(ledger.claims),
            "candidate_claims": candidate_claims,
            "assets": len(assets.assets),
            "slides": len(deck.slides),
        },
        gaps=gaps,
        claims=OperationClaims(
            proves=[
                "A typed candidate deck manifest was generated from the listed local README sources.",
                "Public/private visibility and mandatory non-claims were preserved in machine-readable artifacts.",
            ],
            does_not_prove=[
                "The README claims match the current codebase or runtime.",
                "Candidate claims are approved for external use.",
                "Screenshots are current or visually approved.",
                "The product is production-ready, certified, accredited, or deployed.",
            ],
        ),
        seam_validation=SeamValidation(kind="plan_receipt"),
    )
    dump_json(receipt, output_dir / "plan_receipt.json")
    return receipt
