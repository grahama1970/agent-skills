"""Reviewer persona loading and management.

Loads fictional peer reviewer personas from personas/reviewers.yaml
and provides structured access to their reviewing styles, rubric weights,
expertise, and voice characteristics.

Each persona is used by the cascade to generate reviews with a distinct
perspective — one focuses on soundness, another on novelty, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger


PERSONAS_DIR = Path(__file__).parent.parent / "personas"
REVIEWERS_FILE = PERSONAS_DIR / "reviewers.yaml"


@dataclass
class ReviewerPersona:
    """A fictional peer reviewer with distinct expertise and reviewing style."""

    id: str
    name: str
    pen_name: str = ""
    affiliation: str = ""
    fictional: bool = True
    priority: str = "MEDIUM"
    scope: str = "peer_review"
    taxonomy_hints: list[str] = field(default_factory=list)
    expertise: dict[str, list[str]] = field(default_factory=dict)
    review_style: dict[str, str] = field(default_factory=dict)
    rubric_weights: dict[str, float] = field(default_factory=dict)
    voice: str = ""
    known_biases: dict[str, list[str]] = field(default_factory=dict)
    notes: str = ""

    @property
    def focus(self) -> str:
        """Primary review focus area."""
        return self.review_style.get("focus", "general")

    @property
    def disposition(self) -> str:
        """Reviewing disposition: skeptical, constructive, pragmatic, adversarial."""
        return self.review_style.get("disposition", "constructive")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "pen_name": self.pen_name,
            "affiliation": self.affiliation,
            "expertise": self.expertise,
            "review_style": self.review_style,
            "rubric_weights": self.rubric_weights,
            "voice": self.voice,
            "known_biases": self.known_biases,
        }

    def build_system_prompt(self) -> str:
        """Build a system prompt that embodies this reviewer persona."""
        primary = ", ".join(self.expertise.get("primary", []))
        secondary = ", ".join(self.expertise.get("secondary", []))
        favors = ", ".join(self.known_biases.get("favors", []))
        skeptical = ", ".join(self.known_biases.get("skeptical_of", []))

        return f"""You are {self.name} ({self.affiliation}), a peer reviewer for a top ML venue.

Expertise: {primary}. Secondary: {secondary}.
Reviewing style: {self.review_style.get('focus', 'general')} focus, {self.disposition} disposition.
Voice: {self.voice}

You tend to favor papers with: {favors}.
You are skeptical of: {skeptical}.

Your rubric weights (6 dimensions, 1-4 scale each):
- Soundness: {self.rubric_weights.get('soundness', 0.25):.0%} weight
- Technical Novelty: {self.rubric_weights.get('technical_novelty', 0.15):.0%} weight
- Empirical Novelty: {self.rubric_weights.get('empirical_novelty', 0.15):.0%} weight
- Significance: {self.rubric_weights.get('significance', 0.20):.0%} weight
- Clarity: {self.rubric_weights.get('clarity', 0.15):.0%} weight
- Presentation: {self.rubric_weights.get('presentation', 0.10):.0%} weight

Review the paper section provided. Return a JSON object with:
{{
  "scores": {{
    "soundness": <1-4>,
    "technical_novelty": <1-4>,
    "empirical_novelty": <1-4>,
    "significance": <1-4>,
    "clarity": <1-4>,
    "presentation": <1-4>
  }},
  "overall_score": <1-10 holistic recommendation, DECOUPLED from dimension scores>,
  "confidence": <1-5 self-assessed expertise>,
  "strengths": ["<specific strength with text reference>", ...],
  "weaknesses": ["<specific weakness with actionable fix>", ...],
  "questions": ["<question for authors>", ...],
  "suggestions": ["<concrete improvement>", ...],
  "code_issues": ["<missing or broken code example>", ...]
}}

IMPORTANT: Dimension scores are 1-4 (NeurIPS/ICLR convention).
Overall score is 1-10 HOLISTIC judgment — do NOT mechanically average dimensions.
A fatal flaw in soundness can mean reject even if other dimensions are strong.

Be specific. Cite exact text from the paper. Every weakness must be actionable.
Every strength must reference a concrete contribution, not vague praise."""


def load_reviewers(
    path: Optional[Path] = None,
) -> dict[str, ReviewerPersona]:
    """Load all reviewer personas from YAML config.

    Returns:
        Dict mapping reviewer_id → ReviewerPersona.
    """
    yaml_path = path or REVIEWERS_FILE
    if not yaml_path.exists():
        logger.warning(f"Reviewer personas file not found: {yaml_path}")
        return {}

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    reviewers = {}
    for entry in data.get("reviewers", []):
        persona = ReviewerPersona(
            id=entry["id"],
            name=entry["name"],
            pen_name=entry.get("pen_name", entry["name"]),
            affiliation=entry.get("affiliation", ""),
            fictional=entry.get("fictional", True),
            priority=entry.get("priority", "MEDIUM"),
            scope=entry.get("scope", "peer_review"),
            taxonomy_hints=entry.get("taxonomy_hints", []),
            expertise=entry.get("expertise", {}),
            review_style=entry.get("review_style", {}),
            rubric_weights=entry.get("rubric_weights", {}),
            voice=entry.get("voice", ""),
            known_biases=entry.get("known_biases", {}),
            notes=entry.get("notes", ""),
        )
        reviewers[persona.id] = persona
        logger.debug(f"Loaded reviewer: {persona.id} ({persona.name})")

    logger.info(f"Loaded {len(reviewers)} reviewer personas from {yaml_path}")
    return reviewers
