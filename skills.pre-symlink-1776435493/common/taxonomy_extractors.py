#!/usr/bin/env python3
"""Content-specific taxonomy extractors.

Each extractor handles a specific content type (music, movie, book, etc.)
and returns a TaxonomyExtractionResult.
"""

from typing import Any, Dict, List, Optional

from common.taxonomy_types import (
    CollectionTags,
    ContentType,
    TaxonomyExtractionResult,
)
from common.taxonomy_indicators import (
    BOOK_BRIDGE_INDICATORS,
    MOVIE_BRIDGE_INDICATORS,
)
from common.taxonomy_core import (
    _extract_bridges_from_text,
    _check_lore_entities,
    _get_episodic_associations,
    create_verifier,
    _HMT_AVAILABLE,
    _VERIFIER_AVAILABLE,
    MUSIC_BRIDGE_INDICATORS as _MUSIC_BRIDGE_INDICATORS,
    TACTICAL_TO_CONCEPTUAL,
    create_music_verifier,
)


# ==============================================================================
# CONTENT-SPECIFIC EXTRACTORS
# ==============================================================================

def _extract_music_features(
    title: str,
    artist: str,
    tags: List[str],
    audio_features: Optional[Dict],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for music content."""
    # Use canonical HMT verifier if available
    if _HMT_AVAILABLE:
        verifier = create_music_verifier()
        music_entry = {"title": title, "artist": artist, "channel": artist, "tags": tags}
        hmt_features = verifier.extract_features(music_entry)

        bridge_attributes = hmt_features.get("bridge_attributes", [])
        dimensions = hmt_features.get("dimensions", {})
        confidence = hmt_features.get("confidence", 0.5)
        tactical_tags = hmt_features.get("tactical_tags", [])
    else:
        # Fallback extraction
        bridge_attributes, _ = _extract_bridges_from_text(combined_text, _MUSIC_BRIDGE_INDICATORS or {})
        dimensions = {}
        confidence = 0.3
        tactical_tags = ["Score", "Recall"]

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.MUSIC.value,
        bridge_attributes=bridge_attributes,
        collection_tags=CollectionTags(
            domain=dimensions.get("domain", []),
            thematic_weight=dimensions.get("thematic_weight", []),
            function=dimensions.get("function", ["Contemplation"]),
            perspective=[],
        ),
        tactical_tags=tactical_tags,
        episodic_associations=episodic,
        dimensions=dimensions,
        confidence=confidence,
        raw_matches={},
        participants={},
    )


def _extract_movie_features(
    title: str,
    tags: List[str],
    emotion: str,
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for movie content."""
    # Extract bridges from movie indicators
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, MOVIE_BRIDGE_INDICATORS)

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Map emotion to bridge
    emotion_bridge_map = {
        "rage": "Corruption",
        "anger": "Corruption",
        "sorrow": "Fragility",
        "regret": "Fragility",
        "camaraderie": "Loyalty",
        "triumphant": "Resilience",
        "dread": "Corruption",
        "tension": "Stealth",
    }
    if emotion and emotion.lower() in emotion_bridge_map:
        bridge = emotion_bridge_map[emotion.lower()]
        if bridge not in bridge_attributes:
            bridge_attributes.append(bridge)

    # Determine function
    function = "Contemplation"
    if "Resilience" in bridge_attributes:
        function = "Battle"
    elif "Fragility" in bridge_attributes:
        function = "Mourning"
    elif "Corruption" in bridge_attributes:
        function = "Dread"
    elif "Stealth" in bridge_attributes:
        function = "Tension"

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.MOVIE.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[emotion.capitalize()] if emotion else [],
            function=[function],
            perspective=["Visual"],
        ),
        tactical_tags=["Score", "Immerse"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"emotion": emotion, "tags": tags},
        participants={},
    )


def _extract_book_features(
    title: str,
    author: str,
    genre: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for book/audiobook content."""
    # Extract bridges from book indicators
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, BOOK_BRIDGE_INDICATORS)

    # Check for lore entities
    lore_bridges = _check_lore_entities(combined_text)
    bridge_attributes = list(set(bridge_attributes + lore_bridges))[:3]

    # Warhammer 40K / Horus Heresy detection
    is_wh40k = any(k in combined_text for k in ["warhammer", "40k", "40,000", "horus", "primarch", "astartes", "black library"])

    # Get episodic associations
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    # Determine domain
    domain = []
    if is_wh40k:
        domain.append("Lore")
    if genre:
        domain.append(genre)

    return TaxonomyExtractionResult(
        content_type=ContentType.BOOK.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=domain,
            thematic_weight=[],
            function=["Study"] if is_wh40k else ["Entertainment"],
            perspective=["Literary"],
        ),
        tactical_tags=["Recall", "Invoke"] if is_wh40k else ["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"author": author, "genre": genre, "is_wh40k": is_wh40k},
        participants={},
    )


def _extract_youtube_features(
    title: str,
    channel: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for YouTube content."""
    # Delegate to music extractor for music channels
    music_indicators = ["music", "song", "album", "track", "official video", "lyrics"]
    is_music = any(ind in combined_text for ind in music_indicators)

    if is_music:
        return _extract_music_features(title, channel, tags, None, combined_text)

    # Check for lore content
    lore_indicators = ["warhammer", "40k", "horus heresy", "lore", "luetin", "oculus imperia"]
    is_lore = any(ind in combined_text for ind in lore_indicators)

    if is_lore:
        return _extract_lore_features(title, tags, combined_text)

    # Default YouTube extraction
    bridge_attributes, scores = _extract_bridges_from_text(combined_text, MOVIE_BRIDGE_INDICATORS)
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.YOUTUBE.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[],
            function=["Education"],
            perspective=["Digital"],
        ),
        tactical_tags=["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=max(scores.values()) if scores else 0.3,
        raw_matches={"channel": channel},
        participants={},
    )


def _extract_lore_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for Warhammer 40K lore content."""
    # Check for lore entities first
    bridge_attributes = _check_lore_entities(combined_text)

    # Use main verifier if available
    if _VERIFIER_AVAILABLE:
        verifier = create_verifier(ContentType.LORE)
        features = verifier.extract_features({"content": combined_text, "collection": "lore"})
        if features.bridge_attributes:
            bridge_attributes = list(set(bridge_attributes + features.bridge_attributes))
        confidence = features.confidence
    else:
        confidence = 0.5 if bridge_attributes else 0.3

    bridge_attributes = bridge_attributes[:3]
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=ContentType.LORE.value,
        bridge_attributes=bridge_attributes,
        collection_tags=CollectionTags(
            domain=["Lore"],
            thematic_weight=[],
            function=["Study"],
            perspective=["Narrative"],
        ),
        tactical_tags=["Invoke", "Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
        participants={},
    )


def _extract_operational_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for operational/technical content."""
    if _VERIFIER_AVAILABLE:
        verifier = create_verifier(ContentType.OPERATIONAL)
        features = verifier.extract_features({"content": combined_text, "collection": "operational"})
        bridge_attributes = features.bridge_attributes
        tactical_tags = features.tactical_tags
        confidence = features.confidence
    else:
        bridge_attributes = []
        tactical_tags = []
        confidence = 0.3

        # Fallback operational extraction
        op_indicators = {
            "Resilience": ["error handling", "fault tolerance", "redundancy", "uptime"],
            "Fragility": ["technical debt", "legacy", "brittle", "single point"],
            "Corruption": ["memory leak", "state bug", "race condition"],
            "Precision": ["optimized", "efficient", "algorithmic"],
            "Loyalty": ["security", "auth", "encryption", "access control"],
        }
        for bridge, indicators in op_indicators.items():
            for ind in indicators:
                if ind in combined_text:
                    bridge_attributes.append(bridge)
                    break

    return TaxonomyExtractionResult(
        content_type=ContentType.OPERATIONAL.value,
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=["Code"],
            thematic_weight=[],
            function=["Fix"],
            perspective=["Technical"],
        ),
        tactical_tags=tactical_tags or ["Model"],
        episodic_associations=[],
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
        participants={},
    )


def _extract_security_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for SPARTA security content."""
    if _VERIFIER_AVAILABLE:
        verifier = create_verifier(ContentType.SECURITY)
        features = verifier.extract_features({"content": combined_text, "collection": "sparta"})
        bridge_attributes = features.bridge_attributes
        tactical_tags = features.tactical_tags
        confidence = features.confidence
    else:
        bridge_attributes = []
        tactical_tags = []
        confidence = 0.3

        # Use tactical-to-conceptual mapping
        for tactical, bridge in TACTICAL_TO_CONCEPTUAL.items() if TACTICAL_TO_CONCEPTUAL else {}:
            if tactical.lower() in combined_text:
                bridge_attributes.append(bridge)
                tactical_tags.append(tactical)

    return TaxonomyExtractionResult(
        content_type=ContentType.SECURITY.value,
        bridge_attributes=list(set(bridge_attributes))[:3],
        collection_tags=CollectionTags(
            domain=["Security"],
            thematic_weight=[],
            function=["Defend"],
            perspective=["Risk"],
        ),
        tactical_tags=list(set(tactical_tags)) or ["Detect"],
        episodic_associations=[],
        dimensions={},
        confidence=confidence,
        raw_matches={"tags": tags},
        participants={},
    )


def _extract_session_features(
    title: str,
    tags: List[str],
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Extract features for agent conversation session content."""
    text = combined_text.lower()
    attrs: Dict[str, float] = {}

    # Precision: debugging, type errors, exact fixes
    precision_kw = ["debug", "type error", "fix", "exact", "specific", "pinpoint", "root cause", "traceback"]
    attrs["Precision"] = min(1.0, sum(0.15 for k in precision_kw if k in text))

    # Resilience: retry, recovery, workaround, fallback
    resilience_kw = ["retry", "recover", "workaround", "fallback", "resilient", "handle error", "robust"]
    attrs["Resilience"] = min(1.0, sum(0.15 for k in resilience_kw if k in text))

    # Fragility: broke, regression, flaky, unstable
    fragility_kw = ["broke", "regression", "flaky", "unstable", "brittle", "failed", "crash"]
    attrs["Fragility"] = min(1.0, sum(0.15 for k in fragility_kw if k in text))

    # Corruption: stale, outdated, wrong, incorrect, misleading
    corruption_kw = ["stale", "outdated", "wrong", "incorrect", "misleading", "corrupt", "inconsistent"]
    attrs["Corruption"] = min(1.0, sum(0.15 for k in corruption_kw if k in text))

    # Loyalty: consistent, reliable, pattern, convention, standard
    loyalty_kw = ["consistent", "reliable", "pattern", "convention", "standard", "follow", "best practice"]
    attrs["Loyalty"] = min(1.0, sum(0.15 for k in loyalty_kw if k in text))

    # Stealth: hidden, subtle, edge case, race condition, timing
    stealth_kw = ["hidden", "subtle", "edge case", "race", "timing", "intermittent", "heisenbug"]
    attrs["Stealth"] = min(1.0, sum(0.15 for k in stealth_kw if k in text))

    bridge_attributes = [k for k, v in sorted(attrs.items(), key=lambda x: -x[1]) if v > 0][:3]

    # Determine session function
    function = "Analysis"
    if any(k in text for k in ["implement", "create", "build", "add feature"]):
        function = "Implementation"
    elif any(k in text for k in ["debug", "fix", "error", "traceback"]):
        function = "Debugging"
    elif any(k in text for k in ["refactor", "clean", "reorganize"]):
        function = "Refactoring"
    elif any(k in text for k in ["test", "verify", "validate"]):
        function = "Testing"

    return TaxonomyExtractionResult(
        content_type=ContentType.SESSION.value,
        bridge_attributes=bridge_attributes,
        collection_tags=CollectionTags(
            domain=["Agent"],
            thematic_weight=[],
            function=[function],
            perspective=["Operational"],
        ),
        tactical_tags=["Recall", "Model"],
        episodic_associations=[],
        dimensions={},
        confidence=0.5 if bridge_attributes else 0.3,
        raw_matches={"tags": tags},
        participants={},
    )


def _extract_generic_features(
    content_type: ContentType,
    combined_text: str,
) -> TaxonomyExtractionResult:
    """Fallback extractor for unknown content types."""
    bridge_attributes = _check_lore_entities(combined_text)
    episodic = _get_episodic_associations(bridge_attributes, combined_text)

    return TaxonomyExtractionResult(
        content_type=content_type.value if isinstance(content_type, ContentType) else str(content_type),
        bridge_attributes=bridge_attributes[:3],
        collection_tags=CollectionTags(
            domain=[],
            thematic_weight=[],
            function=[],
            perspective=[],
        ),
        tactical_tags=["Recall"],
        episodic_associations=episodic,
        dimensions={},
        confidence=0.3,
        raw_matches={},
        participants={},
    )
