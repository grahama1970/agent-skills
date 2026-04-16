"""Pydantic models for paper analysis, diagnostics, and review results."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SentenceModel(BaseModel):
    id: str
    text: str
    word_count: int


class ParagraphModel(BaseModel):
    id: str
    text: str
    sentences: list[SentenceModel]
    word_count: int


class SectionModel(BaseModel):
    id: str
    title: str
    level: int = 1
    paragraphs: list[ParagraphModel]


class PaperModel(BaseModel):
    source_path: str
    title: str
    abstract: str | None = None
    sections: list[SectionModel]
    raw_text: str


class DiagnosticsSummary(BaseModel):
    sentence_mean: float
    sentence_stddev: float
    paragraph_mean: float
    paragraph_stddev: float
    lexical_diversity: float
    repeated_openings: list[str] = Field(default_factory=list)
    repeated_transitions: list[str] = Field(default_factory=list)
    hedge_density: float
    certainty_density: float
    passive_voice_signals: int
    section_coverage: dict[str, list[str]] = Field(default_factory=dict)


class PersonaProfile(BaseModel):
    name: str
    goals: list[str] = Field(default_factory=list)
    stylistic_traits: list[str] = Field(default_factory=list)
    rhetorical_preferences: list[str] = Field(default_factory=list)
    preferred_markers: list[str] = Field(default_factory=list)
    discouraged_markers: list[str] = Field(default_factory=list)
    hedging_target: str = "medium"
    assertiveness_target: str = "medium"
    section_affinity: dict[str, float] = Field(default_factory=dict)
    anti_patterns: list[str] = Field(default_factory=list)


class PersonaAlignmentResult(BaseModel):
    section_id: str
    section_title: str
    intended_persona: str | None
    alignment_score: float
    style_alignment: float
    rhetorical_alignment: float
    epistemic_alignment: float
    section_fitness: float
    issues: list[str] = Field(default_factory=list)
    recommendation: str


class RevisionItem(BaseModel):
    priority: int
    target: str
    category: str
    issue: str
    action: str


class HumanizationReport(BaseModel):
    """Signals that indicate AI-generated text."""
    ai_signals: list[str] = Field(default_factory=list)
    human_signals: list[str] = Field(default_factory=list)
    humanization_score: float = 0.0


class ReviewDimension(BaseModel):
    name: str
    score: float
    weight: float
    issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class SectionReview(BaseModel):
    section_id: str
    section_title: str
    persona: str | None = None
    dimensions: list[ReviewDimension] = Field(default_factory=list)
    weighted_score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    paper: PaperModel
    diagnostics: DiagnosticsSummary
    humanization: HumanizationReport
    persona_alignment: list[PersonaAlignmentResult]
    revision_plan: list[RevisionItem]
    cross_persona_consistency: float
    cross_persona_issues: list[str] = Field(default_factory=list)
    section_reviews: list[SectionReview] = Field(default_factory=list)
    overall_score: float = 0.0


class BatchResult(BaseModel):
    path: Path
    success: bool
    analysis: AnalysisResult | None = None
    error: str | None = None
    timing_ms: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)
