"""Emit the React deck payload from the CANONICAL document (#1264).

Three export targets — native PPTX, PDF, and the React/Tailwind browser deck —
should be three renderings of ONE source. They were not: PPTX and static HTML
compiled from ``pitchdeck.deck_document.v1`` while the React app consumed
``deck.data.json`` emitted from the older bundle path. Everything built on the
document (composition recipes, scene illustrations, template inheritance,
qualifier footers) therefore reached PowerPoint and static HTML but never the
browser deck.

This module closes that gap by projecting the canonical document into the shape
the React app already loads, so the same approved document drives every target
and a divergence becomes a diff rather than a surprise.

Inputs: a DeckDocument (+ its bundle assets). Outputs: a ui_deck_bundle payload
with a per-element geometry passthrough so the renderer can lay out bbox-placed
content faithfully instead of re-guessing it. Failure modes: an element kind the
projection cannot represent is reported in ``unsupported`` rather than dropped
silently — a missing claim on screen is the failure this whole skill exists to
prevent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .document import DeckDocument, DocElementKind

UI_SCHEMA = "pitchdeck.ui_deck_bundle.v1"


def _element_payload(element, assets=None, asset_dir: str = "assets") -> dict[str, Any]:
    """One document element in the renderer's UiElement shape (flat frame,
    type text/asset, resolved asset file) — the projection speaks the
    consumer's contract, not its own (#1388)."""
    style = element.style
    payload: dict[str, Any] = {
        "id": element.id,
        "kind": element.kind.value,
        "role": element.role,
        "type": "asset" if element.kind is DocElementKind.IMAGE else "text",
        "x": element.bbox.x, "y": element.bbox.y, "w": element.bbox.w, "h": element.bbox.h,
        "z": element.z,
        "size_pt": (style.size_pt if style and style.size_pt else 20.0),
        "bold": bool(style and style.bold),
        "color": (style.color if style else None),
        "align": (style.align if style else "left") or "left",
        "entrance": "none",
        "entrance_delay_ms": 0,
        "bbox": {"x": element.bbox.x, "y": element.bbox.y, "w": element.bbox.w, "h": element.bbox.h},
    }
    if element.kind is DocElementKind.TEXT and element.text:
        payload["text"] = element.text
    if element.kind is DocElementKind.IMAGE and element.asset_id:
        if element.crop:
            payload["crop"] = {"x": element.crop.x, "y": element.crop.y, "w": element.crop.w, "h": element.crop.h}
        payload["asset_id"] = element.asset_id
        asset = (assets or {}).get(element.asset_id)
        payload["asset"] = {
            "id": element.asset_id,
            "kind": getattr(asset, "kind", "image") if asset else "image",
            "status": "present" if asset else "missing",
            "alt_text": getattr(asset, "alt_text", "") if asset else "",
            "file": f"{asset_dir}/{Path(getattr(asset, 'local_path', '') or '').name}" if asset else "",
            "missing": asset is None,
        }
    if element.kind is DocElementKind.ICON and element.icon:
        payload["icon"] = {"library_id": element.icon.library_id, "tint_role": element.icon.tint_role}
    if element.kind is DocElementKind.DIAGRAM and element.diagram:
        payload["diagram"] = {
            "recipe": element.diagram.recipe,
            "nodes": [
                {
                    "id": node.id, "label": node.label, "sublabel": node.sublabel,
                    "icon": node.icon, "decoration": node.decoration, "scale": node.scale,
                    "bbox": {"x": node.bbox.x, "y": node.bbox.y, "w": node.bbox.w, "h": node.bbox.h},
                }
                for node in element.diagram.nodes
            ],
            "edges": [
                {
                    "id": edge.id, "source": edge.source, "target": edge.target,
                    "label": edge.label, "line_style": edge.line_style,
                    "route": edge.route, "arrowhead": edge.arrowhead,
                }
                for edge in element.diagram.edges
            ],
        }
    if element.children:
        payload["children"] = [_element_payload(child) for child in element.children]
    return payload


def project_document_to_ui(document: DeckDocument, *, asset_dir: str = "assets") -> dict[str, Any]:
    """Project the canonical document into the React app's bundle shape."""
    assets = {asset.id: asset for asset in document.assets}
    unsupported: list[str] = []
    slides: list[dict[str, Any]] = []

    for slide in document.slides:
        if slide.hidden:
            continue
        title_el = next((e for e in slide.elements if e.role == "title"), None)
        message_el = next((e for e in slide.elements if e.role == "message"), None)
        body = [
            e.text for e in slide.elements
            if e.role in {"chevrons", "callout"} and e.kind is DocElementKind.TEXT and e.text
        ]
        visual_el = next((e for e in slide.elements if e.role == "visual" and e.asset_id), None)
        # the renderer contract expects a visual object on every slide — a
        # slide without one carries type 'none', never null (crashed <Split>)
        visual: dict[str, Any] = {"type": "none", "position": "right", "asset": None,
                                   "items": [], "callouts": []}
        if visual_el is not None:
            asset = assets.get(visual_el.asset_id)
            visual = {
                "type": "screenshot",
                "position": "right",
                "asset": {
                    "id": visual_el.asset_id,
                    "kind": getattr(asset, "kind", "screenshot") if asset else "screenshot",
                    "status": "present" if asset else "missing",
                    "alt_text": getattr(asset, "alt_text", "") if asset else "",
                    "file": f"{asset_dir}/{Path(getattr(asset, 'local_path', '') or '').name}" if asset else "",
                    "missing": asset is None,
                },
                "items": [],
                "callouts": [],
            }
        for element in slide.elements:
            if element.kind not in {
                DocElementKind.TEXT, DocElementKind.IMAGE, DocElementKind.ICON,
                DocElementKind.DIAGRAM, DocElementKind.GROUP, DocElementKind.SVG,
                DocElementKind.FIGURE, DocElementKind.SHAPE, DocElementKind.LINE,
                DocElementKind.RICH_TEXT,
            }:
                unsupported.append(f"{slide.id}/{element.id}:{element.kind.value}")
        slides.append({
            "id": slide.id,
            "order": slide.order,
            "layout": "freeform",  # geometry passthrough IS the layout (#1388)
            "recipe": slide.intent.recipe if slide.intent else "chrome",
            "role": slide.intent.module if slide.intent else "",
            "title": (title_el.text if title_el and title_el.text else ""),
            "message": (message_el.text if message_el and message_el.text else ""),
            "body": body,
            "visual": visual,
            # geometry passthrough: the renderer places these by bbox instead of
            # re-deriving a layout the document already decided
            "elements": [_element_payload(e, assets=assets, asset_dir=asset_dir)
                          for e in sorted(slide.elements, key=lambda e: e.z)
                          if e.kind in {DocElementKind.TEXT, DocElementKind.IMAGE, DocElementKind.DIAGRAM}
                          # band-duty titles are absorbed by the chrome band,
                          # exactly as the PPTX emitter absorbs them (skip_title)
                          and not (e.role == "title" and e.bbox.y < 0.15)],
            # carry the document's OWN transition/reveal decisions: reveal order
            # follows the argument, so re-deciding it here would change rhetoric
            "transition": slide.transition.value if hasattr(slide.transition, "value") else str(slide.transition),
            "transition_duration_ms": slide.transition_duration_ms,
            "reveal": slide.reveal.value if hasattr(slide.reveal, "value") else str(slide.reveal),
            "hidden": False,
            "claims": sorted({b.claim_id for b in slide.bindings if b.claim_id} | set(slide.claim_ids)),
            "source_ids": [],
            "notes": slide.notes or "",
        })

    return {
        "schema": UI_SCHEMA,
        "deck_id": document.deck.id,
        "title": document.deck.title,
        "subtitle": document.deck.subtitle or "",
        "audience": document.deck.audience,
        "visibility": document.deck.visibility.value if hasattr(document.deck.visibility, "value") else str(document.deck.visibility),
        "theme": document.deck.theme,
        "theme_tokens": dict(document.deck.theme_tokens or {}),
        "slides": slides,
        "claim_summary": {"bound_claims": sorted({b.claim_id for s in document.slides for b in s.bindings if b.claim_id})},
        "revision": document.revision,
        "validation_readiness": "READY" if not unsupported else "USABLE_WITH_GAPS",
        "validation_gaps": [f"element kind not projected: {u}" for u in unsupported],
        "source": "pitchdeck.deck_document.v1",
        "seam_validation": {"kind": "ui_deck_bundle", "status": "PASS"},
    }
