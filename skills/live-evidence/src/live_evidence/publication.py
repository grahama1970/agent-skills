"""Deterministic reducer for card publication.

The live runtime can have separate logical roles proposing questions, answering
them, and reviewing the answer. This reducer is the shared choke point: it
turns one reviewed card candidate plus current state into an auditable decision
and a new visible-card projection.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    CardPublicationDecision,
    CardStatus,
    EvidenceCard,
    EvidenceSource,
    PublicationStatus,
)


@dataclass(frozen=True)
class PublicationReduction:
    decision: CardPublicationDecision
    cards: list[EvidenceCard]
    mark_active_answered: bool = False


def reduce_card_publication(
    *,
    displayed_cards: list[EvidenceCard],
    incoming: EvidenceCard,
    active_question_id: str | None,
    active_question_revision: int,
    question_last_revision: dict[str, int],
    max_cards: int,
) -> PublicationReduction:
    """Return a visibility decision and the resulting card projection.

    The reducer is intentionally deterministic and side-effect free. It never
    trusts producer success prose: malformed provenance, missing question
    identity, future revisions, stale same-question completions, and weaker
    duplicates fail closed with typed reason codes.
    """

    displayed = next(
        (item for item in displayed_cards if item.question_id == incoming.question_id),
        None,
    )
    base_reasons = _provenance_rejections(incoming)
    if base_reasons:
        return _held(incoming, displayed_cards, base_reasons)

    question_id = incoming.question_id
    assert question_id is not None  # guaranteed by _provenance_rejections

    if question_id == active_question_id:
        if incoming.question_revision > active_question_revision:
            return _superseded(
                incoming,
                displayed_cards,
                ["future_question_revision_not_authored"],
            )
        if incoming.question_revision != active_question_revision:
            if _newer_displayed_blocks(displayed, incoming):
                return _superseded(
                    incoming,
                    displayed_cards,
                    ["stale_revision_blocked_by_newer_visible_card"],
                )
            if not _card_should_replace(displayed, incoming):
                return _held(
                    incoming,
                    displayed_cards,
                    ["weaker_duplicate_card_reconciled"],
                )
            cards = _replace_at_front(displayed_cards, incoming, max_cards)
            return _visible(
                incoming,
                cards,
                ["older_supported_revision_visible_until_current_answer_lands"],
                active_question_id,
                active=True,
            )

        if not _card_should_replace(displayed, incoming):
            return _held(incoming, displayed_cards, ["weaker_duplicate_card_reconciled"])
        cards = _replace_at_front(displayed_cards, incoming, max_cards)
        reason = (
            "visible_replaces_same_question_card"
            if displayed is not None
            else "visible_current_question_card"
        )
        return _visible(incoming, cards, [reason], active_question_id, active=True)

    last_revision = question_last_revision.get(question_id)
    if last_revision is not None and incoming.question_revision > last_revision:
        return _superseded(
            incoming,
            displayed_cards,
            ["future_question_revision_not_authored"],
        )
    if _newer_displayed_blocks(displayed, incoming):
        return _superseded(
            incoming,
            displayed_cards,
            ["background_stale_revision_blocked_by_newer_visible_card"],
        )
    if not _card_should_replace(displayed, incoming):
        return _held(incoming, displayed_cards, ["background_weaker_duplicate_reconciled"])

    cards = [
        item for item in displayed_cards if item.question_id != incoming.question_id
    ]
    cards.insert(min(1, len(cards)), incoming)
    cards = cards[:max_cards]
    return _visible(
        incoming,
        cards,
        ["visible_background_question_card"],
        active_question_id,
        active=False,
    )


def _provenance_rejections(card: EvidenceCard) -> list[str]:
    reasons: list[str] = []
    if card.question_id is None:
        reasons.append("missing_question_identity")
    if card.question_revision <= 0:
        reasons.append("missing_question_revision")
    if card.status is CardStatus.SUPPORTED:
        if not card.sources:
            reasons.append("supported_card_missing_sources")
        elif not all(_source_has_resolvable_provenance(source) for source in card.sources):
            reasons.append("unresolved_source_provenance")
    return reasons


def _source_has_resolvable_provenance(source: EvidenceSource) -> bool:
    return bool(source.path or source.url or source.repository or source.metadata.get("_key"))


def _card_should_replace(displayed: EvidenceCard | None, incoming: EvidenceCard) -> bool:
    """Keep a source-backed card visible over later weak revisions."""

    if displayed is None:
        return True
    if incoming.status is CardStatus.SUPPORTED:
        return True
    return displayed.status is CardStatus.INSUFFICIENT


def _newer_displayed_blocks(displayed: EvidenceCard | None, incoming: EvidenceCard) -> bool:
    if displayed is None:
        return False
    if (displayed.question_revision or 0) <= (incoming.question_revision or 0):
        return False
    return not (
        displayed.status is CardStatus.INSUFFICIENT
        and incoming.status is CardStatus.SUPPORTED
    )


def _replace_at_front(
    displayed_cards: list[EvidenceCard], incoming: EvidenceCard, max_cards: int
) -> list[EvidenceCard]:
    cards = [item for item in displayed_cards if item.question_id != incoming.question_id]
    cards.insert(0, incoming)
    if len(cards) <= max_cards:
        return cards
    pinned = [item for item in cards if item.pinned]
    unpinned = [item for item in cards if not item.pinned]
    return (pinned + unpinned)[:max_cards]


def _visible(
    incoming: EvidenceCard,
    cards: list[EvidenceCard],
    reasons: list[str],
    active_question_id: str | None,
    *,
    active: bool,
) -> PublicationReduction:
    return PublicationReduction(
        decision=_decision(
            incoming,
            PublicationStatus.VISIBLE,
            reasons,
            cards,
            active_question_id,
            active=active,
        ),
        cards=cards,
        mark_active_answered=active,
    )


def _held(
    incoming: EvidenceCard,
    cards: list[EvidenceCard],
    reasons: list[str],
) -> PublicationReduction:
    return PublicationReduction(
        decision=_decision(incoming, PublicationStatus.HELD, reasons, cards, None),
        cards=list(cards),
    )


def _superseded(
    incoming: EvidenceCard,
    cards: list[EvidenceCard],
    reasons: list[str],
) -> PublicationReduction:
    return PublicationReduction(
        decision=_decision(incoming, PublicationStatus.SUPERSEDED, reasons, cards, None),
        cards=list(cards),
    )


def _decision(
    incoming: EvidenceCard,
    status: PublicationStatus,
    reasons: list[str],
    cards: list[EvidenceCard],
    active_question_id: str | None,
    *,
    active: bool = False,
) -> CardPublicationDecision:
    source_refs = [_source_ref(source) for source in incoming.sources]
    transcript_refs = []
    if incoming.question_id is not None and incoming.question_revision > 0:
        transcript_refs.append(
            f"question:{incoming.question_id}:revision:{incoming.question_revision}"
        )
    return CardPublicationDecision(
        status=status,
        reason_codes=reasons,
        card_id=incoming.card_id,
        question_id=incoming.question_id,
        question_revision=incoming.question_revision,
        answer_revision=incoming.question_revision,
        transcript_refs=transcript_refs,
        source_refs=source_refs,
        rank_components={
            "active_question_match": active,
            "active_question_id": active_question_id or "",
            "status_weight": 1 if incoming.status is CardStatus.SUPPORTED else 0,
            "source_count": len(incoming.sources),
            "visible_index": _visible_index(cards, incoming.card_id),
        },
        visible_card_ids=[card.card_id for card in cards],
    )


def _source_ref(source: EvidenceSource) -> str:
    locator = source.path or source.url or source.repository or source.metadata.get("_key") or ""
    return f"{source.lane.value}:{source.source_id}:{locator}"


def _visible_index(cards: list[EvidenceCard], card_id: str) -> int:
    for index, card in enumerate(cards):
        if card.card_id == card_id:
            return index
    return -1
