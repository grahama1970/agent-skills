"""Identity ledger and footer identity strip (#1314, voice layer slice 4).

Every reference slide in the author's corpus carries a footer identity strip:
a mark row at bottom-left, a release/attribution line, and a page number.
Blind judges named its ABSENCE as the strongest remaining authorship tell.

The strip cannot be copied wholesale: the corpus decks carry sponsor logos and
a DoD release marking that are facts about THOSE programs, not about a product
deck. So identity is a ledger, not a template. Only entries present in the
ledger render, each one carries its own provenance, and an entry whose
provenance is missing raises rather than printing an unattributed mark.

Inputs: an IdentityLedger (usually derived from the deck document plus explicit
author-supplied facts). Outputs: the resolved strip elements. Failure modes:
requesting a release marking with no ledger fact raises IdentityRefused —
fabricating an approval marking is the one failure this module must never have.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel


class IdentityRefused(RuntimeError):
    """Raised when a strip element was requested without a licensing fact."""


class IdentityFact(StrictModel):
    """One attributable identity element with its source."""

    kind: Literal["wordmark", "release_marking", "sponsor_mark", "deck_family"]
    text: str = Field(min_length=1)
    provenance: str = Field(
        min_length=1,
        description="Where this fact comes from: deck title, author approval, program record.",
    )

    @model_validator(mode="after")
    def marking_needs_authority(self) -> "IdentityFact":
        # A release marking asserts an authorization decision. Derivations from
        # deck metadata are not authorization; only a named human approval is.
        if self.kind == "release_marking" and "approval" not in self.provenance.lower():
            raise IdentityRefused(
                f"release marking '{self.text}' has provenance '{self.provenance}' — "
                "a release marking requires explicit author approval, never derivation"
            )
        return self


class IdentityLedger(StrictModel):
    schema_: Literal["pitchdeck.identity_ledger.v1"] = Field(
        default="pitchdeck.identity_ledger.v1", alias="schema"
    )
    facts: list[IdentityFact] = Field(default_factory=list)

    def of_kind(self, kind: str) -> IdentityFact | None:
        return next((f for f in self.facts if f.kind == kind), None)


def ledger_from_document(deck_title: str) -> IdentityLedger:
    """The minimum honest ledger: the product's own wordmark.

    The deck title is a fact about the deck, so the wordmark is always
    licensed. Sponsor marks and release markings are NOT derivable and stay
    absent until the author supplies them."""
    wordmark = deck_title.split("—")[0].strip()
    return IdentityLedger(
        facts=[IdentityFact(kind="wordmark", text=wordmark, provenance="deck title (self-evident)")]
    )


def strip_texts(ledger: IdentityLedger) -> dict[str, str]:
    """Resolve what the footer strip may actually print."""
    resolved: dict[str, str] = {}
    for kind in ("wordmark", "deck_family", "release_marking"):
        fact = ledger.of_kind(kind)
        if fact is not None:
            resolved[kind] = fact.text
    return resolved
