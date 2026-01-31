"""
HMT (Horus Music Taxonomy) Bridge Attribute Mapper.

Maps audio features to Bridge Attributes for Horus persona integration.

IMPORTANT: This module imports from the CANONICAL HMT at:
    /home/graham/workspace/experiments/memory/persona/bridge/horus_music_taxonomy.py

This ensures multi-hop graph traversal works across ALL collections (music, lore,
operational, sparta, episodic) via shared Bridge Attributes.
"""
from typing import Dict, List, Optional, Tuple
import sys
from pathlib import Path

import numpy as np

# Import canonical HMT from memory persona
# This is the authoritative source for the Federated Taxonomy
_MEMORY_PERSONA_PATH = Path("/home/graham/workspace/experiments/memory/persona")
if str(_MEMORY_PERSONA_PATH) not in sys.path:
    sys.path.insert(0, str(_MEMORY_PERSONA_PATH))

try:
    from bridge.horus_music_taxonomy import (
        MUSIC_BRIDGE_INDICATORS,
        EPISODIC_ASSOCIATIONS,
        HMT_VOCABULARY,
        MUSIC_TACTICAL_TAGS,
        MusicDimension,
        MathematicalMusicFeatures,
        HorusMusicTaxonomyVerifier,
        create_music_verifier,
    )
    _HMT_AVAILABLE = True
except ImportError as e:
    # Fallback: define local versions if canonical not available
    _HMT_AVAILABLE = False
    import warnings
    warnings.warn(f"Cannot import canonical HMT: {e}. Using fallback definitions.")

# Re-export canonical definitions for use in this module
if _HMT_AVAILABLE:
    BRIDGE_INDICATORS = MUSIC_BRIDGE_INDICATORS
else:
    # Fallback Bridge Attribute definitions (simplified)
    BRIDGE_INDICATORS = {
        "Precision": {
            "indicators": ["polyrhythm", "complex", "technical", "algorithmic"],
            "artists": ["Tool", "Meshuggah", "Animals as Leaders", "Dream Theater"],
            "lore_resonance": "Iron Warriors, Perturabo's calculated siege craft",
        },
        "Resilience": {
            "indicators": ["crescendo", "building", "triumphant", "anthemic"],
            "artists": ["Sabaton", "Two Steps From Hell", "Audiomachine", "Hans Zimmer"],
            "lore_resonance": "Imperial Fists, Siege of Terra, Dorn's defense",
        },
        "Fragility": {
            "indicators": ["fragile", "delicate", "sparse", "acoustic"],
            "artists": ["Daughter", "Phoebe Bridgers", "Billie Marten", "Chelsea Wolfe"],
            "lore_resonance": "Webway, Magnus's Folly, shattered dreams",
        },
        "Corruption": {
            "indicators": ["distorted", "corrupted", "industrial", "harsh"],
            "artists": ["Nine Inch Nails", "Ministry", "Godflesh", "Author & Punisher"],
            "lore_resonance": "Warp, Chaos, Davin transformation",
        },
        "Loyalty": {
            "indicators": ["ceremonial", "ritual", "choral", "solemn"],
            "artists": ["Wardruna", "Heilung", "Dead Can Dance", "Gregorian chant"],
            "lore_resonance": "Oaths of Moment, Loken's loyalty, Luna Wolves",
        },
        "Stealth": {
            "indicators": ["ambient", "subtle", "drone", "minimalist"],
            "artists": ["Sunn O)))", "Stars of the Lid", "Tim Hecker", "Brian Eno"],
            "lore_resonance": "Alpha Legion, Alpharius, infiltration",
        },
    }

# Audio feature thresholds for bridge detection
AUDIO_BRIDGE_THRESHOLDS = {
    "Precision": {
        "tempo_variance": ("high", 0.15),
        "time_signature": ["5/4", "7/8", "6/8"],
        "harmonic_complexity": ("high", 0.7),
        "spectral_flatness": ("high", 0.3),
    },
    "Resilience": {
        "mode": "major",
        "dynamic_range": ("high", 12),
        "brightness": "bright",
        "texture": "dense",
    },
    "Fragility": {
        "mode": "minor",
        "dynamics": ("soft", -20),
        "brightness": "dark",
        "texture": "sparse",
    },
    "Corruption": {
        "spectral_flatness": ("high", 0.4),
        "zero_crossing_rate": ("high", 0.2),
        "brightness": "bright",
    },
    "Loyalty": {
        "texture": "layered",
        "harmonic_complexity": ("low", 0.3),
        "spectral_contrast": ("high", 50),
    },
    "Stealth": {
        "beat_strength": ("low", 0.3),
        "brightness": "dark",
        "spectral_centroid": ("low", 1000),
    },
}

# Use canonical HMT vocabulary for domains if available
if _HMT_AVAILABLE:
    # Extract from MusicDimension.DOMAIN vocabulary
    DOMAINS = {
        domain: []  # Will be populated from canonical vocab
        for domain in HMT_VOCABULARY.get(MusicDimension.DOMAIN, [])
    }
    THEMATIC_WEIGHTS = {
        weight: []
        for weight in HMT_VOCABULARY.get(MusicDimension.THEMATIC_WEIGHT, [])
    }
    TACTICAL_TAGS = MUSIC_TACTICAL_TAGS
else:
    # Fallback domain definitions
    DOMAINS = {
        "Dark_Folk": ["acoustic", "folk", "haunting", "minor", "sparse"],
        "Doom_Metal": ["heavy", "slow", "distorted", "dark", "minor"],
        "Progressive_Metal": ["technical", "complex", "polyrhythmic"],
        "Power_Metal": ["major", "fast", "triumphant", "epic"],
        "Orchestral_Epic": ["orchestral", "cinematic", "building", "major"],
        "Industrial": ["electronic", "distorted", "mechanical", "harsh"],
        "Atmospheric_Ambient": ["atmospheric", "drone", "minimal", "slow"],
        "Neo_Classical": ["neo-classical", "modern", "orchestra"],
        "Post_Rock": ["crescendo", "dynamics", "instrumental"],
        "Synthwave_Dark": ["synthwave", "retro", "electronic"],
    }

    # Fallback thematic weights
    THEMATIC_WEIGHTS = {
        "Melancholic": ["minor", "soft", "sparse", "slow"],
        "Epic": ["building", "triumphant", "major", "loud"],
        "Ominous": ["dark", "minor", "slow", "dissonant"],
        "Transcendent": ["ethereal", "divine", "otherworldly"],
        "Brutal": ["heavy", "harsh", "aggressive"],
        "Ethereal": ["ambient", "sparse", "soft", "atmospheric"],
        "Defiant": ["resistant", "rebellious", "strong"],
        "Tragic": ["doom", "fate", "sorrow"],
        "Wrathful": ["rage", "fury", "aggressive"],
        "Serene": ["calm", "peaceful", "quiet"],
    }

    # Fallback tactical tags
    TACTICAL_TAGS = {
        "Score": "Use for movie/story soundtrack",
        "Recall": "Trigger memory/association",
        "Amplify": "Intensify existing emotion",
        "Contrast": "Provide emotional counterpoint",
        "Immerse": "Create atmosphere/environment",
        "Signal": "Mark narrative transition",
        "Invoke": "Summon specific thematic element",
        "Endure": "Support long work sessions",
    }


def map_features_to_bridges(features: Dict, title: str = "", artist: str = "") -> Dict:
    """
    Map extracted audio features to Bridge Attributes.

    Uses canonical HMT when available for proper multi-hop graph traversal.
    The output structure matches the edge scoring formula:
        (dimension_overlap * 0.5) + min(bridge_bonus, 0.5) + min(tactical_bonus, 0.2)

    Args:
        features: Feature dictionary from extract_all_features()
        title: Track title for text-based matching
        artist: Artist name for text-based matching

    Returns:
        Dictionary with:
        - bridge_attributes: List of matching bridges (for edge creation)
        - collection_tags: Domain, thematic_weight, function (Tier 3)
        - tactical_tags: Suggested tactical uses (Tier 1)
        - episodic_associations: Lore event links (for Music→Lore edges)
        - dimensions: Full 6-dimension HMT structure
        - confidence: Overall confidence score
    """
    rhythm = features.get("rhythm", {})
    harmony = features.get("harmony", {})
    timbre = features.get("timbre", {})
    dynamics = features.get("dynamics", {})

    # Try canonical HMT verifier first for text-based extraction
    if _HMT_AVAILABLE and (title or artist):
        verifier = create_music_verifier()
        music_entry = {
            "title": title,
            "artist": artist,
            "channel": artist,
        }
        hmt_features = verifier.extract_features(music_entry)
        text_bridges = hmt_features.get("bridge_attributes", [])
        text_confidence = hmt_features.get("confidence", 0.3)
    else:
        text_bridges = []
        text_confidence = 0.0

    # Score each bridge
    bridge_scores = {}

    for bridge_name, bridge_def in BRIDGE_INDICATORS.items():
        score = calculate_bridge_score(
            bridge_name,
            bridge_def,
            rhythm,
            harmony,
            timbre,
            dynamics,
        )
        if score > 0:
            bridge_scores[bridge_name] = score

    # Get top bridges (those with significant scores)
    threshold = 0.3
    bridge_attributes = [
        name for name, score in sorted(bridge_scores.items(), key=lambda x: -x[1])
        if score >= threshold
    ][:3]  # Top 3 max

    # If no strong matches, use best guess
    if not bridge_attributes and bridge_scores:
        bridge_attributes = [max(bridge_scores, key=bridge_scores.get)]

    # Extract collection tags
    collection_tags = extract_collection_tags(features, bridge_attributes)

    # Extract tactical tags
    tactical_tags = extract_tactical_tags(features, bridge_attributes)

    # Calculate overall confidence
    confidence = max(bridge_scores.values()) if bridge_scores else 0.3

    # Get episodic associations for Music→Lore edge creation
    episodic_associations = get_episodic_associations(
        bridge_attributes,
        features={"metadata": {"title": title, "artist": artist}}
    )

    # Build dimensions structure for full HMT compliance
    dimensions = {}
    if _HMT_AVAILABLE:
        dimensions = {
            MusicDimension.DOMAIN.value: collection_tags.get("domain", []),
            MusicDimension.THEMATIC_WEIGHT.value: [collection_tags.get("thematic_weight", "Neutral")],
            MusicDimension.FUNCTION.value: [collection_tags.get("function", "Contemplation")],
        }

    return {
        "bridge_attributes": bridge_attributes,
        "collection_tags": collection_tags,
        "tactical_tags": tactical_tags,
        "episodic_associations": episodic_associations,
        "dimensions": dimensions,
        "confidence": min(confidence, 1.0),
        "bridge_scores": bridge_scores,
    }


def calculate_bridge_score(
    bridge_name: str,
    bridge_def: Dict,
    rhythm: Dict,
    harmony: Dict,
    timbre: Dict,
    dynamics: Dict,
) -> float:
    """Calculate how well features match a bridge definition."""
    score = 0.0
    matches = 0
    total_checks = 0

    indicators = bridge_def.get("indicators", {})
    audio_patterns = bridge_def.get("audio_patterns", {})

    # Check rhythm indicators
    if "tempo_variance" in indicators:
        direction, threshold = indicators["tempo_variance"]
        variance = rhythm.get("tempo_variance", 0)
        total_checks += 1
        if direction == "high" and variance > threshold:
            score += 1.0
            matches += 1
        elif direction == "low" and variance < threshold:
            score += 1.0
            matches += 1

    if "time_signature" in indicators:
        ts = rhythm.get("time_signature", "4/4")
        total_checks += 1
        if ts in indicators["time_signature"]:
            score += 1.0
            matches += 1

    if "beat_strength" in indicators:
        direction, threshold = indicators["beat_strength"]
        strength = rhythm.get("beat_strength", 0.5)
        total_checks += 1
        if direction == "low" and strength < threshold:
            score += 1.0
            matches += 1
        elif direction == "high" and strength > threshold:
            score += 1.0
            matches += 1

    # Check harmony indicators
    if "mode" in indicators:
        mode = harmony.get("mode", "major")
        total_checks += 1
        if mode == indicators["mode"]:
            score += 1.0
            matches += 1

    if "harmonic_complexity" in indicators:
        direction, threshold = indicators["harmonic_complexity"]
        complexity = harmony.get("harmonic_complexity", 0.5)
        total_checks += 1
        if direction == "high" and complexity > threshold:
            score += 1.0
            matches += 1
        elif direction == "low" and complexity < threshold:
            score += 1.0
            matches += 1

    # Check timbre patterns
    if "brightness" in audio_patterns:
        expected = audio_patterns["brightness"]
        actual = timbre.get("brightness", "neutral")
        total_checks += 1
        if actual == expected:
            score += 1.0
            matches += 1

    if "texture" in audio_patterns:
        expected = audio_patterns["texture"]
        actual = timbre.get("texture", "layered")
        total_checks += 1
        if actual == expected:
            score += 1.0
            matches += 1

    if "spectral_flatness" in audio_patterns:
        direction, threshold = audio_patterns["spectral_flatness"]
        flatness = timbre.get("spectral_flatness", 0)
        total_checks += 1
        if direction == "high" and flatness > threshold:
            score += 1.0
            matches += 1
        elif direction == "low" and flatness < threshold:
            score += 1.0
            matches += 1

    # Check dynamics patterns
    if "dynamic_range" in indicators:
        direction, threshold = indicators["dynamic_range"]
        dr = dynamics.get("dynamic_range", 10)
        total_checks += 1
        if direction == "high" and dr > threshold:
            score += 1.0
            matches += 1
        elif direction == "medium" and abs(dr - threshold) < 4:
            score += 0.7
            matches += 0.7

    # Normalize score
    if total_checks > 0:
        return score / total_checks
    return 0.0


def extract_collection_tags(features: Dict, bridges: List[str]) -> Dict:
    """Extract collection tags (domain, thematic_weight, function)."""
    timbre = features.get("timbre", {})
    harmony = features.get("harmony", {})
    dynamics = features.get("dynamics", {})
    rhythm = features.get("rhythm", {})

    # Build feature keywords
    keywords = []

    if timbre.get("brightness") == "dark":
        keywords.append("dark")
    elif timbre.get("brightness") == "bright":
        keywords.append("bright")

    if harmony.get("mode") == "minor":
        keywords.append("minor")
    else:
        keywords.append("major")

    if timbre.get("texture") == "sparse":
        keywords.append("sparse")
    elif timbre.get("texture") == "dense":
        keywords.append("dense")

    if dynamics.get("loudness_integrated", -20) > -14:
        keywords.append("loud")
    else:
        keywords.append("soft")

    if rhythm.get("bpm", 100) < 80:
        keywords.append("slow")
    elif rhythm.get("bpm", 100) > 140:
        keywords.append("fast")

    # Match domains
    domain_scores = {}
    for domain, domain_keywords in DOMAINS.items():
        score = sum(1 for kw in keywords if kw in domain_keywords)
        if score > 0:
            domain_scores[domain] = score

    domains = sorted(domain_scores.keys(), key=lambda d: -domain_scores[d])[:2]

    # Match thematic weights
    thematic_scores = {}
    for thematic, thematic_keywords in THEMATIC_WEIGHTS.items():
        score = sum(1 for kw in keywords if kw in thematic_keywords)
        if score > 0:
            thematic_scores[thematic] = score

    thematic = sorted(thematic_scores.keys(), key=lambda t: -thematic_scores[t])[:1]

    # Determine function based on bridges
    function = "Contemplation"  # Default
    if "Resilience" in bridges:
        function = "Battle"
    elif "Fragility" in bridges:
        function = "Mourning"
    elif "Corruption" in bridges:
        function = "Dread"
    elif "Stealth" in bridges:
        function = "Ambush"
    elif "Loyalty" in bridges:
        function = "Oath"

    return {
        "domain": domains,
        "thematic_weight": thematic[0] if thematic else "Neutral",
        "function": function,
    }


def extract_tactical_tags(features: Dict, bridges: List[str]) -> List[str]:
    """Extract tactical tags for Horus persona use."""
    tags = []

    # Score - background scoring
    tags.append("Score")

    # Based on dynamics
    dynamics = features.get("dynamics", {})
    if dynamics.get("loudness_range", 0) > 15:
        tags.append("Contrast")  # Good for contrast scenes

    # Based on rhythm
    rhythm = features.get("rhythm", {})
    if rhythm.get("bpm", 100) > 120:
        tags.append("Amplify")  # Good for action

    # Based on bridges
    if "Fragility" in bridges or "Stealth" in bridges:
        tags.append("Immerse")  # Atmospheric
    if "Resilience" in bridges:
        tags.append("Endure")  # Triumphant moments
    if "Corruption" in bridges:
        tags.append("Signal")  # Warning/tension

    # Based on lyrics
    lyrics = features.get("lyrics", {})
    if not lyrics.get("is_instrumental", True):
        tags.append("Invoke")  # Has meaningful lyrics

    # Recall is always included for persona memory
    tags.append("Recall")

    return list(set(tags))  # Remove duplicates


def get_bridge_indicators() -> Dict:
    """Return the bridge indicator definitions for reference."""
    return BRIDGE_INDICATORS


def get_episodic_associations(bridges: List[str], features: Optional[Dict] = None) -> List[str]:
    """
    Get episodic (lore) associations for bridges.

    Uses EPISODIC_ASSOCIATIONS from canonical HMT for full multi-hop traversal.
    Returns list of Warhammer 40K lore events/episodes.

    Args:
        bridges: List of Bridge Attribute names
        features: Optional feature dict for deeper matching

    Returns:
        List of episode names (e.g., "Siege_of_Terra", "Davin_Corruption")
    """
    associations = []

    if _HMT_AVAILABLE:
        # Use canonical EPISODIC_ASSOCIATIONS for full lore integration
        for episode_name, episode_data in EPISODIC_ASSOCIATIONS.items():
            episode_bridge = episode_data.get("bridge", "")

            # Match by bridge attribute
            if episode_bridge in bridges:
                if episode_name not in associations:
                    associations.append(episode_name)
                continue

            # Match by music indicators if features provided
            if features:
                title = features.get("metadata", {}).get("title", "").lower()
                for indicator in episode_data.get("music_indicators", []):
                    if indicator.lower() in title:
                        if episode_name not in associations:
                            associations.append(episode_name)
                        break
    else:
        # Fallback episode map
        episode_map = {
            "Precision": ["Iron_Cage", "Horus_Primarch"],
            "Resilience": ["Siege_of_Terra", "Emperor_Throne"],
            "Fragility": ["Webway_Collapse", "Sanguinius_Fall"],
            "Corruption": ["Davin_Corruption", "Isstvan_Betrayal"],
            "Loyalty": ["Mournival_Oath"],
            "Stealth": ["Alpharius_Deception"],
        }

        for bridge in bridges:
            if bridge in episode_map:
                for ep in episode_map[bridge]:
                    if ep not in associations:
                        associations.append(ep)

    return associations


def get_episode_details(episode_name: str) -> Optional[Dict]:
    """
    Get full details of an episodic association.

    Returns lore_moment, mood, artists, bridge for multi-hop traversal.
    """
    if _HMT_AVAILABLE and episode_name in EPISODIC_ASSOCIATIONS:
        return EPISODIC_ASSOCIATIONS[episode_name]
    return None


def create_verifier() -> Optional["HorusMusicTaxonomyVerifier"]:
    """
    Create a HorusMusicTaxonomyVerifier for cross-collection edge verification.

    Returns None if canonical HMT not available.
    """
    if _HMT_AVAILABLE:
        return create_music_verifier()
    return None
