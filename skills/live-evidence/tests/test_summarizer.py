"""Tests for extractive card generation and proof boundaries."""

from live_evidence.models import CardStatus, EvidenceSource, Freshness, RetrievalLane
from live_evidence.summarizer import ExtractiveSummarizer


def test_supported_card_uses_source_text() -> None:
    source = EvidenceSource(
        lane=RetrievalLane.RIPGREP,
        label="tau/README.md",
        excerpt="Tau treats every agent output as a claim, not a fact.",
        score=0.88,
        freshness=Freshness.CURRENT,
        repository="tau",
        path="/workspace/tau/README.md",
        line_start=3,
    )
    card = ExtractiveSummarizer().build("How do you contain agents?", "tau", [source])
    assert card.status is CardStatus.SUPPORTED
    assert card.question == "How do you contain agents?"
    assert card.answer == source.excerpt
    assert card.evidence is not None
    assert card.talking_point == source.excerpt
    assert "README.md:3" in card.proof
    assert "README.md:3" in card.evidence
    assert "semantic correctness" in card.qualifier


def test_empty_source_set_is_explicitly_insufficient() -> None:
    card = ExtractiveSummarizer().build("Unknown?", "Current discussion", [])
    assert card.status is CardStatus.INSUFFICIENT
    assert card.question == "Unknown?"
    assert card.answer == "No source-bound support surfaced yet."
    assert card.evidence is not None
    assert card.confidence == 0.0
    assert card.sources == []
