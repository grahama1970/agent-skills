"""
Review Generator for review-music skill.

Combines LLM analysis with HMT mapping to produce complete music reviews
in the format required by the Horus persona and /memory integration.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from ..features.aggregator import extract_all_features
from ..taxonomy import map_features_to_bridges, get_episodic_associations
from ..analysis.llm_analyzer import analyze_with_llm, analyze_without_llm


@dataclass
class ReviewResult:
    """Structured result from music review generation."""

    # Core identification
    title: str = ""
    artist: str = ""
    source: str = ""  # File path or YouTube URL

    # Audio features (extracted)
    features: Dict = field(default_factory=dict)

    # HMT taxonomy mapping
    bridge_attributes: List[str] = field(default_factory=list)
    collection_tags: Dict = field(default_factory=dict)
    tactical_tags: List[str] = field(default_factory=list)
    episodic_associations: List[str] = field(default_factory=list)

    # LLM analysis
    summary: str = ""
    music_theory: Dict = field(default_factory=dict)
    production: Dict = field(default_factory=dict)
    emotional_arc: Dict = field(default_factory=dict)
    use_cases: List[str] = field(default_factory=list)
    similar_artists: List[str] = field(default_factory=list)

    # Metadata
    confidence: float = 0.0
    analysis_method: str = ""  # "llm" or "rule_based"
    generated_at: str = ""
    version: str = "1.0.0"

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_memory_format(self) -> Dict:
        """
        Convert to format suitable for /memory integration.

        Returns a dictionary matching the memory skill's expected format:
        - category: "music"
        - title: Track title
        - bridge_attributes: List of bridges
        - collection_tags: Domain, thematic_weight, function
        - tactical_tags: List of tactical uses
        - content: Summary and key details
        """
        return {
            "category": "music",
            "title": self.title or self.source,
            "artist": self.artist,
            "bridge_attributes": self.bridge_attributes,
            "collection_tags": self.collection_tags,
            "tactical_tags": self.tactical_tags,
            "episodic_associations": self.episodic_associations,
            "content": self._format_memory_content(),
            "metadata": {
                "source": self.source,
                "bpm": self.features.get("rhythm", {}).get("bpm"),
                "key": self.features.get("harmony", {}).get("scale"),
                "duration": self.features.get("metadata", {}).get("duration_seconds"),
                "confidence": self.confidence,
                "generated_at": self.generated_at,
            }
        }

    def _format_memory_content(self) -> str:
        """Format content for memory storage."""
        lines = [self.summary]

        if self.emotional_arc:
            mood = self.emotional_arc.get("primary_mood", "")
            intensity = self.emotional_arc.get("intensity", "")
            if mood or intensity:
                lines.append(f"Mood: {mood} ({intensity} intensity)")

        if self.bridge_attributes:
            lines.append(f"Bridges: {', '.join(self.bridge_attributes)}")

        if self.use_cases:
            lines.append(f"Use cases: {', '.join(self.use_cases[:3])}")

        return "\n".join(lines)


def generate_review(
    source: Union[str, Path],
    title: Optional[str] = None,
    artist: Optional[str] = None,
    use_llm: bool = True,
    llm_provider: str = "anthropic",
    llm_model: Optional[str] = None,
    include_lyrics: bool = True,
    language: str = "en",
) -> ReviewResult:
    """
    Generate a complete music review with HMT mapping.

    Args:
        source: Audio file path or YouTube URL
        title: Track title (optional, defaults to filename)
        artist: Artist name (optional)
        use_llm: Whether to use LLM for analysis (requires API key)
        llm_provider: LLM provider ("anthropic" or "openai")
        llm_model: Specific model to use
        include_lyrics: Whether to transcribe lyrics
        language: Language for lyrics transcription

    Returns:
        ReviewResult with complete review data
    """
    source_str = str(source)

    # Default title from filename if not provided
    if not title:
        if source_str.startswith("http"):
            title = "YouTube Track"
        else:
            title = Path(source_str).stem

    # Extract audio features
    features = extract_all_features(
        source,
        include_lyrics=include_lyrics,
        language=language,
    )

    # Map features to HMT taxonomy
    taxonomy_result = map_features_to_bridges(features)

    # Get episodic associations
    episodic = get_episodic_associations(taxonomy_result["bridge_attributes"])

    # Run LLM or rule-based analysis
    if use_llm:
        try:
            analysis = analyze_with_llm(
                features,
                provider=llm_provider,
                model=llm_model,
            )
            analysis_method = "llm"
        except (ImportError, ValueError) as e:
            # Fall back to rule-based if LLM unavailable
            analysis = analyze_without_llm(features)
            analysis_method = "rule_based"
            analysis["_fallback_reason"] = str(e)
    else:
        analysis = analyze_without_llm(features)
        analysis_method = "rule_based"

    # Build review result
    result = ReviewResult(
        title=title,
        artist=artist or "",
        source=source_str,
        features=features,
        bridge_attributes=taxonomy_result["bridge_attributes"],
        collection_tags=taxonomy_result["collection_tags"],
        tactical_tags=taxonomy_result["tactical_tags"],
        episodic_associations=episodic,
        summary=analysis.get("summary", ""),
        music_theory=analysis.get("music_theory", {}),
        production=analysis.get("production", {}),
        emotional_arc=analysis.get("emotional_arc", {}),
        use_cases=analysis.get("use_cases", []),
        similar_artists=analysis.get("similar_artists", []),
        confidence=max(
            taxonomy_result.get("confidence", 0.5),
            analysis.get("confidence", 0.5),
        ),
        analysis_method=analysis_method,
        generated_at=datetime.utcnow().isoformat(),
    )

    return result


def generate_review_from_features(
    features: Dict,
    title: str = "Unknown Track",
    artist: str = "",
    source: str = "",
    use_llm: bool = True,
    llm_provider: str = "anthropic",
    llm_model: Optional[str] = None,
) -> ReviewResult:
    """
    Generate a review from pre-extracted features.

    Useful when features have already been extracted separately.

    Args:
        features: Pre-extracted features from extract_all_features()
        title: Track title
        artist: Artist name
        source: Original source path/URL
        use_llm: Whether to use LLM for analysis
        llm_provider: LLM provider
        llm_model: Specific model

    Returns:
        ReviewResult with complete review data
    """
    # Map features to HMT taxonomy
    taxonomy_result = map_features_to_bridges(features)

    # Get episodic associations
    episodic = get_episodic_associations(taxonomy_result["bridge_attributes"])

    # Run analysis
    if use_llm:
        try:
            analysis = analyze_with_llm(
                features,
                provider=llm_provider,
                model=llm_model,
            )
            analysis_method = "llm"
        except (ImportError, ValueError):
            analysis = analyze_without_llm(features)
            analysis_method = "rule_based"
    else:
        analysis = analyze_without_llm(features)
        analysis_method = "rule_based"

    # Build review result
    result = ReviewResult(
        title=title,
        artist=artist,
        source=source,
        features=features,
        bridge_attributes=taxonomy_result["bridge_attributes"],
        collection_tags=taxonomy_result["collection_tags"],
        tactical_tags=taxonomy_result["tactical_tags"],
        episodic_associations=episodic,
        summary=analysis.get("summary", ""),
        music_theory=analysis.get("music_theory", {}),
        production=analysis.get("production", {}),
        emotional_arc=analysis.get("emotional_arc", {}),
        use_cases=analysis.get("use_cases", []),
        similar_artists=analysis.get("similar_artists", []),
        confidence=max(
            taxonomy_result.get("confidence", 0.5),
            analysis.get("confidence", 0.5),
        ),
        analysis_method=analysis_method,
        generated_at=datetime.utcnow().isoformat(),
    )

    return result


def save_review(review: ReviewResult, output_path: Union[str, Path]) -> Path:
    """
    Save review to JSON file.

    Args:
        review: ReviewResult to save
        output_path: Output file path

    Returns:
        Path to saved file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(review.to_json())

    return output_path


def load_review(path: Union[str, Path]) -> ReviewResult:
    """
    Load review from JSON file.

    Args:
        path: Path to review JSON file

    Returns:
        ReviewResult loaded from file
    """
    with open(path) as f:
        data = json.load(f)

    return ReviewResult(**data)
