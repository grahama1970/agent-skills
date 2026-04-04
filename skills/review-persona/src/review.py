#!/usr/bin/env python3
"""
Core review logic for persona validation.

Dimensions:
1. Realism - Is the persona believable for their role/domain?
2. Voice Casting - Are reference actors appropriate?
3. Register Switching - Does the confident/uncertain dynamic work?
4. Media Consumption - Would they realistically consume this content?
5. Technical Accuracy - Is domain terminology correct?
"""

import base64
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from loguru import logger as log

# Skills directory for composing with other skills
SCRIPT_DIR = Path(__file__).parent.parent
SKILLS_DIR = SCRIPT_DIR.parent


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class DimensionScore:
    """Score for a single review dimension."""
    name: str
    score: int
    max_score: int
    issues: list[str] = field(default_factory=list)
    praise: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return (self.score / self.max_score) * 100 if self.max_score > 0 else 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "max_score": self.max_score,
            "percentage": self.percentage,
            "issues": self.issues,
            "praise": self.praise,
            "suggestions": self.suggestions,
        }


@dataclass
class PersonaReview:
    """Complete persona review result."""
    persona_name: str
    template: str
    dimensions: dict[str, DimensionScore] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    research_notes: list[str] = field(default_factory=list)
    visual_notes: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def overall_score(self) -> int:
        if not self.dimensions:
            return 0
        total = sum(d.score for d in self.dimensions.values())
        max_total = sum(d.max_score for d in self.dimensions.values())
        return int((total / max_total) * 100) if max_total > 0 else 0

    @property
    def grade(self) -> str:
        score = self.overall_score
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B+"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"

    @property
    def ready_for_production(self) -> bool:
        return len(self.blockers) == 0 and self.overall_score >= 70

    def to_dict(self) -> dict:
        return {
            "persona": self.persona_name,
            "template": self.template,
            "overall_score": self.overall_score,
            "grade": self.grade,
            "ready_for_production": self.ready_for_production,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "recommendations": self.recommendations,
            "blockers": self.blockers,
            "research_notes": self.research_notes,
            "visual_notes": self.visual_notes,
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """Generate markdown review report."""
        lines = [
            f"# Persona Review: {self.persona_name}",
            "",
            f"## Overall Score: {self.grade} ({self.overall_score}/100)",
            "",
        ]

        # Dimensions
        for dim in self.dimensions.values():
            lines.append(f"### {dim.name} ({dim.score}/{dim.max_score})")
            for p in dim.praise:
                lines.append(f"✓ {p}")
            for i in dim.issues:
                lines.append(f"⚠ {i}")
            for s in dim.suggestions:
                lines.append(f"→ Suggestion: {s}")
            lines.append("")

        # Visual notes
        if self.visual_notes:
            lines.append("### Visual Review Notes")
            for note in self.visual_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Research notes
        if self.research_notes:
            lines.append("### Research Notes")
            for note in self.research_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Recommendations
        if self.recommendations:
            lines.append("## Recommendations")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        # Blockers
        if self.blockers:
            lines.append("## Blockers (Must Fix)")
            for blocker in self.blockers:
                lines.append(f"- ❌ {blocker}")
            lines.append("")

        # Production readiness
        if self.ready_for_production:
            lines.append("## Ready for Production: ✓ YES")
        else:
            lines.append("## Ready for Production: ❌ NO (fix blockers first)")

        return "\n".join(lines)


# =============================================================================
# Persona Loading
# =============================================================================

def load_persona_yaml(path: Path) -> dict:
    """Load persona from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def load_character_sheet(path: Path) -> str:
    """Load character sheet content."""
    if path.exists():
        return path.read_text()
    return ""


# =============================================================================
# Quick Check (No LLM)
# =============================================================================

def quick_check_persona(persona_path: Path) -> list[str]:
    """Quick sanity check for required fields and valid values."""
    issues = []
    persona = load_persona_yaml(persona_path)

    # Required fields
    if not persona.get("name"):
        issues.append("Missing required field: name")
    if not persona.get("template"):
        issues.append("Missing required field: template")

    # Fictional-specific checks
    if persona.get("template") == "fictional":
        if not persona.get("voice_references"):
            issues.append("Fictional persona should have voice_references")
        if not persona.get("media_consumption"):
            issues.append("Fictional persona should have media_consumption")
        if not persona.get("character_sheet_path"):
            issues.append("Consider adding character_sheet_path")

        # Check voice reference weights
        voice_refs = persona.get("voice_references", [])
        if voice_refs:
            total_weight = sum(ref.get("weight", 0) for ref in voice_refs)
            if abs(total_weight - 1.0) > 0.2:
                issues.append(f"Voice reference weights sum to {total_weight:.0%}, should be ~100%")

    # Bridge weights validation
    bridges = persona.get("bridge_weights", {})
    for bridge, weight in bridges.items():
        if not 0.0 <= weight <= 1.0:
            issues.append(f"Invalid bridge weight for {bridge}: {weight} (must be 0.0-1.0)")

    # Character sheet exists
    sheet_path = persona.get("character_sheet_path")
    if sheet_path and not Path(sheet_path).exists():
        issues.append(f"Character sheet not found: {sheet_path}")

    return issues


# =============================================================================
# Standard Review
# =============================================================================

def review_persona(
    persona_path: Path,
    character_sheet_path: Optional[Path] = None,
    images_dir: Optional[Path] = None,
    provider: str = "claude",
    focus_dimensions: Optional[list[str]] = None,
) -> PersonaReview:
    """Standard persona review."""
    persona = load_persona_yaml(persona_path)
    name = persona.get("name", "Unknown")
    template = persona.get("template", "unknown")

    review = PersonaReview(
        persona_name=name,
        template=template,
    )

    # Load character sheet if provided or referenced
    sheet_content = ""
    sheet_path = character_sheet_path or persona.get("character_sheet_path")
    if sheet_path:
        sheet_path = Path(sheet_path)
        if sheet_path.exists():
            sheet_content = sheet_path.read_text()

    # Run dimension reviews
    all_dims = ["realism", "voice_casting", "register_switching", "media_consumption", "technical_accuracy"]
    dims_to_review = focus_dimensions or all_dims

    if "realism" in dims_to_review:
        review.dimensions["realism"] = review_realism(persona, sheet_content)

    if "voice_casting" in dims_to_review:
        review.dimensions["voice_casting"] = review_voice_casting(persona)

    if "register_switching" in dims_to_review:
        review.dimensions["register_switching"] = review_register_switching(persona)

    if "media_consumption" in dims_to_review:
        review.dimensions["media_consumption"] = review_media_consumption(persona)

    if "technical_accuracy" in dims_to_review:
        review.dimensions["technical_accuracy"] = review_technical_accuracy(persona)

    # Visual review if images provided
    if images_dir and images_dir.exists():
        visual_result = _review_images_basic(images_dir, persona, sheet_content)
        review.visual_notes = visual_result

    # Generate recommendations
    review.recommendations = _generate_recommendations(review)

    # Identify blockers
    review.blockers = _identify_blockers(review)

    return review


# =============================================================================
# Dimension Reviews
# =============================================================================

def review_realism(persona: dict, sheet_content: str) -> DimensionScore:
    """Review character realism for the role/domain."""
    dim = DimensionScore(name="Realism", score=0, max_score=25)

    # Check basic realism markers
    role = persona.get("role", "")
    domain = persona.get("domain", "")
    age = _extract_age(persona, sheet_content)

    if role:
        dim.praise.append(f"Role is defined: {role}")
        dim.score += 5
    else:
        dim.issues.append("No role defined")

    if domain:
        dim.praise.append(f"Domain is defined: {domain}")
        dim.score += 5
    else:
        dim.issues.append("No domain defined")

    # Check for realistic details
    quirks = persona.get("quirks", [])
    if len(quirks) >= 3:
        dim.praise.append(f"Rich personality with {len(quirks)} quirks")
        dim.score += 5
    elif quirks:
        dim.praise.append("Some quirks defined")
        dim.score += 3
    else:
        dim.suggestions.append("Add personality quirks for realism")

    # Check for BDI (beliefs, desires, intentions)
    goals = persona.get("goals", [])
    concerns = persona.get("concerns", [])
    if goals and concerns:
        dim.praise.append("Goals and concerns add psychological depth")
        dim.score += 5
    elif goals or concerns:
        dim.score += 3
    else:
        dim.suggestions.append("Add goals and concerns for character depth")

    # Check expertise alignment
    expertise = persona.get("expertise", [])
    if expertise and domain:
        dim.praise.append(f"Expertise aligns with domain: {len(expertise)} areas")
        dim.score += 5
    elif expertise:
        dim.score += 3

    return dim


def review_voice_casting(persona: dict) -> DimensionScore:
    """Review voice reference choices."""
    dim = DimensionScore(name="Voice Casting", score=0, max_score=25)

    voice_refs = persona.get("voice_references", [])

    if not voice_refs:
        dim.issues.append("No voice references defined")
        return dim

    # Check reference count
    if len(voice_refs) >= 2:
        dim.praise.append(f"{len(voice_refs)} voice references for range")
        dim.score += 5
    else:
        dim.score += 3

    # Check registers covered
    registers = [ref.get("register", "") for ref in voice_refs]
    if "confident" in registers and "uncertain" in registers:
        dim.praise.append("Both confident and uncertain registers covered")
        dim.score += 10
    elif "confident" in registers or "uncertain" in registers:
        dim.praise.append("At least one register covered")
        dim.score += 5
    else:
        dim.issues.append("Consider defining registers (confident, uncertain)")

    # Check weights
    total_weight = sum(ref.get("weight", 0) for ref in voice_refs)
    if 0.9 <= total_weight <= 1.1:
        dim.praise.append(f"Weights sum correctly: {total_weight:.0%}")
        dim.score += 5
    else:
        dim.issues.append(f"Weights sum to {total_weight:.0%}, should be ~100%")

    # Check for characteristics
    has_characteristics = any(ref.get("characteristics") for ref in voice_refs)
    if has_characteristics:
        dim.praise.append("Voice characteristics defined")
        dim.score += 5
    else:
        dim.suggestions.append("Add vocal characteristics for each reference")

    return dim


def review_register_switching(persona: dict) -> DimensionScore:
    """Review register switching behavior."""
    dim = DimensionScore(name="Register Switching", score=0, max_score=15)

    reg_switch = persona.get("register_switching", {})

    if not reg_switch:
        # Check if template is fictional
        if persona.get("template") == "fictional":
            dim.issues.append("No register switching defined for fictional persona")
        else:
            dim.score = 10  # Not required for non-fictional
            dim.praise.append("Register switching not required for this template")
        return dim

    # Check triggers
    confident_triggers = reg_switch.get("confident_triggers", [])
    uncertain_triggers = reg_switch.get("uncertain_triggers", [])

    if confident_triggers:
        dim.praise.append(f"Confident triggers defined: {len(confident_triggers)} scenarios")
        dim.score += 5
    else:
        dim.issues.append("Define what triggers confident register")

    if uncertain_triggers:
        dim.praise.append(f"Uncertain triggers defined: {len(uncertain_triggers)} scenarios")
        dim.score += 5
    else:
        dim.issues.append("Define what triggers uncertain register")

    # Check voice mapping
    if reg_switch.get("confident_voice") and reg_switch.get("uncertain_voice"):
        dim.praise.append("Voice references mapped to registers")
        dim.score += 5

    return dim


def review_media_consumption(persona: dict) -> DimensionScore:
    """Review media consumption profile."""
    dim = DimensionScore(name="Media Consumption", score=0, max_score=15)

    media = persona.get("media_consumption", {})

    if not media:
        if persona.get("template") == "fictional":
            dim.issues.append("No media consumption defined for fictional persona")
        else:
            dim.score = 10
            dim.praise.append("Media consumption not required for this template")
        return dim

    # Check categories
    movies = media.get("movies", {})
    books = media.get("books", {})
    youtube = media.get("youtube_channels", {})

    if movies.get("formative"):
        dim.praise.append(f"Formative movies defined: {len(movies['formative'])}")
        dim.score += 4
    else:
        dim.suggestions.append("Add formative movies that shaped the character")

    if books.get("nightstand") or books.get("favorites"):
        dim.praise.append("Books defined")
        dim.score += 3
    else:
        dim.suggestions.append("Add books for character depth")

    if youtube.get("daily"):
        dim.praise.append(f"Daily YouTube channels: {len(youtube['daily'])}")
        dim.score += 4
    else:
        dim.suggestions.append("Add YouTube channels they'd watch")

    # Guilty pleasures add character
    guilty = media.get("guilty_pleasures", []) or persona.get("quirks", [])
    if guilty:
        dim.praise.append("Guilty pleasures add authenticity")
        dim.score += 4

    return dim


def review_technical_accuracy(persona: dict) -> DimensionScore:
    """Review domain terminology accuracy."""
    dim = DimensionScore(name="Technical Accuracy", score=0, max_score=20)

    domain = persona.get("domain", "")
    expertise = persona.get("expertise", [])

    if not domain:
        dim.score = 15  # Can't evaluate without domain
        dim.praise.append("No specific domain to validate")
        return dim

    # Check for domain-specific expertise
    if expertise:
        dim.praise.append(f"Domain expertise areas defined: {len(expertise)}")
        dim.score += 10

        # Check for specific terminology
        expertise_str = " ".join(expertise).lower()

        # Cybersecurity checks
        if "cybersecurity" in domain.lower() or "security" in domain.lower():
            if any(term in expertise_str for term in ["nist", "ac-17", "ia-5", "d3fend", "sparta"]):
                dim.praise.append("Uses real security frameworks/controls")
                dim.score += 10
            else:
                dim.suggestions.append("Add specific security frameworks (NIST, SPARTA, D3FEND)")
    else:
        dim.suggestions.append("Add domain-specific expertise areas")

    return dim


# =============================================================================
# Visual Review
# =============================================================================

def _review_images_basic(images_dir: Path, persona: dict, sheet_content: str) -> list[str]:
    """Basic image review (file-based, no vision LLM yet)."""
    notes = []

    image_files = list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg"))
    notes.append(f"Found {len(image_files)} casting images")

    if len(image_files) < 5:
        notes.append("⚠ Consider adding more casting images for consistency")
    elif len(image_files) >= 20:
        notes.append("✓ Good variety of casting images")

    # Check for variety in filenames (indicating different angles/contexts)
    filenames = [f.stem.lower() for f in image_files]
    has_variety = any(term in " ".join(filenames) for term in ["front", "side", "full", "portrait", "candid"])
    if has_variety:
        notes.append("✓ Images appear to show different angles/contexts")
    else:
        notes.append("⚠ Consider naming images by context (front, side, candid, etc.)")

    return notes


def review_persona_visual(
    persona_path: Path,
    images_dir: Path,
    character_sheet_path: Optional[Path] = None,
    provider: str = "claude",
) -> PersonaReview:
    """Vision-based review of casting images."""
    persona = load_persona_yaml(persona_path)
    name = persona.get("name", "Unknown")
    template = persona.get("template", "unknown")

    review = PersonaReview(
        persona_name=name,
        template=template,
    )

    # Load character sheet
    sheet_content = ""
    sheet_path = character_sheet_path or persona.get("character_sheet_path")
    if sheet_path:
        sheet_path = Path(sheet_path)
        if sheet_path.exists():
            sheet_content = sheet_path.read_text()

    # Basic visual review
    review.visual_notes = _review_images_basic(images_dir, persona, sheet_content)

    # TODO: Add vision LLM integration for detailed analysis
    # This would:
    # 1. Encode images as base64
    # 2. Send to vision-capable LLM with character sheet
    # 3. Get structured feedback on visual match

    review.recommendations.append("For detailed visual review, use vision-capable LLM manually")

    return review


# =============================================================================
# Deep Review (with /dogpile)
# =============================================================================

def deep_review_persona(
    persona_path: Path,
    character_sheet_path: Optional[Path] = None,
    images_dir: Optional[Path] = None,
    research_focus: list[str] = None,
    provider: str = "claude",
) -> PersonaReview:
    """Deep review with /dogpile research."""
    # Start with standard review
    review = review_persona(
        persona_path=persona_path,
        character_sheet_path=character_sheet_path,
        images_dir=images_dir,
        provider=provider,
    )

    persona = load_persona_yaml(persona_path)
    focus = research_focus or ["voice", "domain", "role"]

    # Research voice casting
    if "voice" in focus:
        voice_refs = persona.get("voice_references", [])
        for ref in voice_refs:
            actor = ref.get("name", "")
            register = ref.get("register", "")
            if actor:
                note = f"Research needed: Is {actor} appropriate for {register} register?"
                review.research_notes.append(note)

    # Research domain accuracy
    if "domain" in focus:
        domain = persona.get("domain", "")
        if domain:
            note = f"Research needed: Validate {domain} terminology accuracy"
            review.research_notes.append(note)

    # Research role realism
    if "role" in focus:
        role = persona.get("role", "")
        if role:
            note = f"Research needed: What do real {role}s sound like?"
            review.research_notes.append(note)

    review.recommendations.append("Run /dogpile with research notes to validate findings")

    return review


# =============================================================================
# Helpers
# =============================================================================

def _extract_age(persona: dict, sheet_content: str) -> Optional[int]:
    """Try to extract age from persona or character sheet."""
    # Check persona directly
    if "age" in persona:
        try:
            return int(persona["age"])
        except (ValueError, TypeError):
            pass

    # Check sheet content for age patterns
    import re
    age_match = re.search(r'\*\*Age\*\*\s*\|\s*(\d+)', sheet_content)
    if age_match:
        return int(age_match.group(1))

    return None


def _generate_recommendations(review: PersonaReview) -> list[str]:
    """Generate recommendations from dimension scores."""
    recs = []

    for dim in review.dimensions.values():
        recs.extend(dim.suggestions)

    return recs


def _identify_blockers(review: PersonaReview) -> list[str]:
    """Identify issues that block production use."""
    blockers = []

    # Low overall score
    if review.overall_score < 50:
        blockers.append(f"Overall score too low: {review.overall_score}/100")

    # Critical missing fields for fictional
    if review.template == "fictional":
        if "voice_casting" in review.dimensions:
            vc = review.dimensions["voice_casting"]
            if vc.score < vc.max_score * 0.5:
                blockers.append("Voice casting needs significant improvement")

    return blockers
