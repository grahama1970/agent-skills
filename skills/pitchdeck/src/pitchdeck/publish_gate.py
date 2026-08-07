"""Fail-closed publish-authorization boundary (2026-08-07 rendering review).

ONE gate shared by every document emitter: a document may not become
publishable output (PPTX/HTML/anything) if it is a preview artifact or its
renderings/approvals are not in an authorized state. Provenance stamps are
DATA; this gate is the ENFORCEMENT the review found missing — copying a
preview file to another path must change nothing. Typed refusal
(PublishRefused) BEFORE any output byte is written.
"""

from __future__ import annotations

from .document import DeckDocument


class PublishRefused(ValueError):
    """Typed refusal: the document is not authorized for publishable output."""


def assert_publishable(document: DeckDocument, *, allow_preview: bool = False) -> None:
    provenance = document.provenance or {}
    if provenance.get("preview_unapproved_renderings") == "true" and not allow_preview:
        raise PublishRefused(
            "PREVIEW_UNAPPROVED_RENDERINGS: this document was materialized from candidate "
            "renderings without human approval — approve renderings and re-materialize"
        )
    if provenance.get("kind") == "materialized-outline" and "outline_sha256" not in provenance and not allow_preview:
        raise PublishRefused("MISSING_OUTLINE_PROVENANCE: materialized document carries no approved-outline hash")
