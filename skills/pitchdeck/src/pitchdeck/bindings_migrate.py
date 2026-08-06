"""Migrate a deck manifest to ContentIR bindings (roundtable session 2).

Auto-classification per webclaude's migration rule: a string containing a
bound claim's exact ledger text -> claim_quote; a string containing a bound
claim's required qualifier -> qualifier; everything else stays UNBOUND by
default (blocking publish until triaged). --triage-rest non_claim marks the
remainder non_claim in one pass — only appropriate when a human is reviewing
the result (e.g. curated fixtures), because it launders untriaged prose.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from .models import BindingKind, ClaimLedger, DeckManifest, TextBinding


def migrate_bindings(
    bundle_dir: Path,
    *,
    deck_name: str = "deck.public.yaml",
    triage_rest: str = "unbound",
) -> dict[str, int]:
    from .io import load_yaml
    from .revisions import commit_bundle_write

    deck = load_yaml(bundle_dir / deck_name, DeckManifest)
    ledger = load_yaml(bundle_dir / "claim_ledger.yaml", ClaimLedger)
    claims = {c.id: c for c in ledger.claims}
    counts = {"claim_quote": 0, "qualifier": 0, "non_claim": 0, "unbound": 0, "kept": 0}

    new_slides = []
    for slide in deck.slides:
        existing = {b.path for b in slide.bindings}
        counts["kept"] += len(existing)
        strings: list[tuple[str, str]] = [("title", slide.title), ("message", slide.message)]
        strings += [(f"body:{i}", line) for i, line in enumerate(slide.body)]
        strings += [(f"element:{e.id}", e.text or "") for e in slide.elements if e.type == "text"]
        strings += [(f"visual.items:{i}", item) for i, item in enumerate(slide.visual.items)]
        bindings = list(slide.bindings)
        slide_claims = [claims[cid] for cid in slide.claim_ids if cid in claims]
        for path, text in strings:
            if path in existing or not text.strip():
                continue
            lowered = text.strip().lower()
            match = next((c for c in slide_claims if c.text.strip().lower() in lowered), None)
            if match is not None:
                bindings.append(TextBinding(path=path, kind=BindingKind.CLAIM_QUOTE, claim_id=match.id))
                counts["claim_quote"] += 1
                continue
            qual = next(
                (c for c in slide_claims if c.required_qualifier and c.required_qualifier.strip().lower() in lowered),
                None,
            )
            if qual is not None:
                bindings.append(TextBinding(path=path, kind=BindingKind.QUALIFIER, claim_id=qual.id))
                counts["qualifier"] += 1
                continue
            if triage_rest == "non_claim":
                bindings.append(TextBinding(path=path, kind=BindingKind.NON_CLAIM))
                counts["non_claim"] += 1
            else:
                counts["unbound"] += 1
        new_slides.append(slide.model_copy(update={"bindings": bindings}))

    updated = DeckManifest.model_validate(
        {
            **deck.model_dump(mode="json", by_alias=True),
            "slides": [s.model_dump(mode="json", by_alias=True) for s in new_slides],
        }
    )
    commit_bundle_write(
        bundle_dir,
        {
            bundle_dir / deck_name: yaml.safe_dump(
                updated.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            )
        },
    )
    logger.info("bindings migrated: {}", counts)
    return counts
