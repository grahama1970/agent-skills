"""
Federated Taxonomy Integration for create-cast skill.

Integrates with .pi/skills/taxonomy for multi-hop graph traversal:
1. Extracting bridge attributes from character traits/descriptions
2. Building taxonomy output for identity packs
3. Integrating with memory for character knowledge persistence

Bridge Attributes (Tier 0):
- Precision: Calculated, methodical, procedural content
- Resilience: Endurance, triumph, survival content
- Fragility: Vulnerable, delicate, emotional content
- Corruption: Dark, compromised, morally complex content
- Loyalty: Honor, duty, familial content
- Stealth: Hidden, subtle, mysterious content

Integration Pattern:
- Uses .pi/skills/taxonomy for bridge extraction
- Uses .pi/skills/common/memory_client for memory integration
"""

import sys
import json
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from .schemas import CharacterSpec, CharacterRole, IdentityPack


# Add common skills to path for memory client
_SKILLS_DIR = Path(__file__).parent.parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

# Try to import common memory client
_memory_client = None
_MemoryScope = None
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _MemoryScope = MemoryScope
    _memory_client = True
except ImportError:
    _memory_client = False

# Load canonical taxonomy module directly by path to avoid name conflicts
import importlib.util
_TAXONOMY_SKILL_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
_canonical_taxonomy = None

if _TAXONOMY_SKILL_PATH.exists():
    _spec = importlib.util.spec_from_file_location("canonical_taxonomy", _TAXONOMY_SKILL_PATH)
    _canonical_taxonomy = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_canonical_taxonomy)


# Use the canonical taxonomy module loaded via importlib
_taxonomy_module = None
if _canonical_taxonomy is not None:
    try:
        _extract_taxonomy = _canonical_taxonomy.extract_taxonomy
        _extract_keywords = _canonical_taxonomy.extract_keywords
        _validate_tags = _canonical_taxonomy.validate_tags
        BRIDGE_TAGS = _canonical_taxonomy.BRIDGE_TAGS
        BRIDGE_KEYWORDS = _canonical_taxonomy.BRIDGE_KEYWORDS
        COLLECTION_VOCABULARIES = _canonical_taxonomy.COLLECTION_VOCABULARIES
        _taxonomy_module = _TAXONOMY_SKILL_PATH.parent
    except AttributeError:
        pass


# Fallback bridge tags if taxonomy skill unavailable
_FALLBACK_BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}


# Character trait keywords mapped to bridge attributes
# This extends the taxonomy skill's BRIDGE_KEYWORDS with character-specific terms
CHARACTER_TRAIT_BRIDGES: Dict[str, List[str]] = {
    # Precision traits
    "Precision": [
        "methodical", "calculated", "precise", "analytical", "strategic",
        "technical", "meticulous", "systematic", "logical", "focused",
        "cold", "detached", "scientific", "clinical", "efficient",
    ],
    # Resilience traits
    "Resilience": [
        "determined", "brave", "courageous", "warrior", "fighter",
        "enduring", "strong", "unstoppable", "survivor", "tough",
        "steadfast", "unwavering", "resolute", "tenacious", "gritty",
    ],
    # Fragility traits
    "Fragility": [
        "vulnerable", "emotional", "sensitive", "gentle", "delicate",
        "tender", "fragile", "innocent", "naive", "soft",
        "wounded", "broken", "tragic", "haunted", "conflicted",
    ],
    # Corruption traits
    "Corruption": [
        "dark", "sinister", "corrupt", "twisted", "evil",
        "menacing", "villainous", "dangerous", "malicious", "wicked",
        "fallen", "compromised", "morally grey", "antihero", "ruthless",
    ],
    # Loyalty traits
    "Loyalty": [
        "loyal", "honorable", "dutiful", "devoted", "faithful",
        "trustworthy", "noble", "protective", "selfless", "traditional",
        "familial", "patriotic", "servant", "oath-bound", "righteous",
    ],
    # Stealth traits
    "Stealth": [
        "mysterious", "secretive", "subtle", "hidden", "covert",
        "shadowy", "enigmatic", "cunning", "deceptive", "quiet",
        "manipulative", "scheming", "infiltrator", "spy", "undercover",
    ],
}

# Role-based default bridges
ROLE_DEFAULT_BRIDGES: Dict[CharacterRole, List[str]] = {
    CharacterRole.PROTAGONIST: ["Resilience", "Loyalty"],
    CharacterRole.ANTAGONIST: ["Corruption", "Stealth"],
    CharacterRole.SUPPORTING: ["Loyalty"],
    CharacterRole.MINOR: [],
    CharacterRole.NARRATOR: ["Precision"],
}


def extract_bridges_from_character(spec: CharacterSpec) -> List[str]:
    """
    Extract bridge attributes from a character specification.

    Uses both taxonomy skill's extraction and character-specific trait analysis.

    Analyzes:
    - Personality traits
    - Physical description features
    - Role-based defaults
    - Explicit bridge attributes

    Args:
        spec: Character specification

    Returns:
        List of bridge attribute names
    """
    bridges: Set[str] = set()

    # 1. Check explicit bridges first
    if spec.bridge_attributes:
        bridges.update(spec.bridge_attributes)

    # 2. Build text corpus from character data
    text_parts = [
        " ".join(spec.personality),
        " ".join(spec.physical.distinguishing_features),
        spec.voice_type or "",
    ]
    if spec.physical.build:
        text_parts.append(spec.physical.build)
    text_corpus = " ".join(text_parts)

    # 3. Use taxonomy skill's extraction if available
    if _taxonomy_module:
        taxonomy_result = _extract_taxonomy(text_corpus, collection="lore", fast=True)
        bridges.update(taxonomy_result.get("bridge_tags", []))

    # 4. Analyze personality traits with character-specific keywords
    for trait in spec.personality:
        trait_lower = trait.lower()
        for bridge, keywords in CHARACTER_TRAIT_BRIDGES.items():
            if any(kw in trait_lower for kw in keywords):
                bridges.add(bridge)

    # 5. Analyze distinguishing features
    features_text = " ".join(spec.physical.distinguishing_features).lower()
    for bridge, keywords in CHARACTER_TRAIT_BRIDGES.items():
        if any(kw in features_text for kw in keywords):
            bridges.add(bridge)

    # 6. Apply role-based defaults if no bridges found
    if not bridges:
        bridges.update(ROLE_DEFAULT_BRIDGES.get(spec.role, []))

    # 7. Validate bridges against known vocabulary
    valid_bridges = BRIDGE_TAGS if _taxonomy_module else _FALLBACK_BRIDGE_TAGS
    validated = [b for b in bridges if b in valid_bridges]

    return validated


def build_taxonomy_output(
    spec: CharacterSpec,
    pack: Optional[IdentityPack] = None,
    collection: str = "lore"
) -> dict:
    """
    Build taxonomy metadata for graph integration.

    Uses taxonomy skill for proper multi-hop traversal support.

    This output format enables multi-hop traversal in the Federated Taxonomy:
    - bridge_tags: Enable cross-collection queries
    - collection_tags: Domain and function classification
    - confidence: Reliability score
    - worth_remembering: Flag for memory integration

    Args:
        spec: Character specification
        pack: Optional identity pack
        collection: Taxonomy collection (lore, operational, sparta)

    Returns:
        Taxonomy dict with graph metadata
    """
    # Extract bridges from character
    bridge_tags = extract_bridges_from_character(spec)

    # Build character description for taxonomy extraction
    description = build_character_description(spec)

    # Use taxonomy skill for collection tags if available
    collection_tags = {}
    confidence = 0.4

    if _taxonomy_module:
        taxonomy_result = _extract_taxonomy(description, collection=collection, fast=True)
        collection_tags = taxonomy_result.get("collection_tags", {})
        confidence = taxonomy_result.get("confidence", 0.4)
        # Merge any additional bridges from full description
        for tag in taxonomy_result.get("bridge_tags", []):
            if tag not in bridge_tags:
                bridge_tags.append(tag)

    # Override/set character-specific collection tags
    # Function based on character role (using lore vocabulary)
    function_map = {
        CharacterRole.PROTAGONIST: "Catalyst",  # Drives the story
        CharacterRole.ANTAGONIST: "Confrontation",  # Creates conflict
        CharacterRole.SUPPORTING: "Preservation",  # Maintains narrative
        CharacterRole.MINOR: "Revelation",  # Provides info
        CharacterRole.NARRATOR: "Revelation",  # Reveals story
    }
    collection_tags["function"] = function_map.get(spec.role, "Revelation")

    # Domain based on character's thematic alignment
    if any(b in ["Corruption", "Fragility"] for b in bridge_tags):
        collection_tags["domain"] = "Chaos"
    elif any(b in ["Resilience", "Loyalty", "Precision"] for b in bridge_tags):
        collection_tags["domain"] = "Imperium"
    else:
        collection_tags["domain"] = "World"

    # Boost confidence if we have bridges
    if bridge_tags:
        confidence = max(confidence, 0.7)

    return {
        "bridge_tags": bridge_tags,
        "collection_tags": collection_tags,
        "character_metadata": {
            "name": spec.name,
            "role": spec.role.value,
            "screen_time": spec.screen_time_estimate,
            "dialogue_count": spec.dialogue_count,
        },
        "confidence": confidence,
        "worth_remembering": spec.role in [CharacterRole.PROTAGONIST, CharacterRole.ANTAGONIST],
    }


def enrich_character_with_bridges(spec: CharacterSpec) -> CharacterSpec:
    """
    Enrich a character specification with extracted bridge attributes.

    Args:
        spec: Character specification

    Returns:
        Updated CharacterSpec with bridge_attributes populated
    """
    if not spec.bridge_attributes:
        spec.bridge_attributes = extract_bridges_from_character(spec)
    return spec


def build_character_graph_node(
    spec: CharacterSpec,
    pack: Optional[IdentityPack] = None
) -> dict:
    """
    Build a graph node for memory integration.

    This node can be stored in ArangoDB for federated traversal.

    Args:
        spec: Character specification
        pack: Optional identity pack

    Returns:
        Graph node dict ready for memory storage
    """
    taxonomy = build_taxonomy_output(spec, pack)

    node = {
        "_key": f"character_{spec.name.lower().replace(' ', '_')}",
        "type": "character",
        "name": spec.name,
        "full_text": build_character_description(spec),
        "role": spec.role.value,
        "bridge_tags": taxonomy["bridge_tags"],
        "collection": "lore",  # Characters are lore entities
        "domain": taxonomy["collection_tags"].get("domain", "World"),
        "function": taxonomy["collection_tags"].get("function", "Revelation"),
        "metadata": {
            "screen_time": spec.screen_time_estimate,
            "dialogue_count": spec.dialogue_count,
            "scenes": spec.scenes,
            "reference_actors": spec.reference_actors,
            "voice_type": spec.voice_type,
        },
        "taxonomy": taxonomy,
    }

    if pack and pack.images:
        node["identity_pack"] = {
            "images": pack.images,
            "prompt_descriptors": pack.prompt_descriptors,
        }

    return node


def build_character_description(spec: CharacterSpec) -> str:
    """
    Build a searchable text description for embedding.

    Args:
        spec: Character specification

    Returns:
        Full text description for semantic search
    """
    parts = [
        f"{spec.name} is a {spec.role.value} character.",
    ]

    if spec.physical.to_prompt():
        parts.append(f"Physical: {spec.physical.to_prompt()}.")

    if spec.personality:
        parts.append(f"Personality: {', '.join(spec.personality)}.")

    if spec.voice_type:
        parts.append(f"Voice: {spec.voice_type}.")

    if spec.reference_actors:
        parts.append(f"Visual reference: {', '.join(spec.reference_actors)}.")

    if spec.bridge_attributes:
        parts.append(f"Thematic bridges: {', '.join(spec.bridge_attributes)}.")

    return " ".join(parts)


def store_character_in_memory(
    spec: CharacterSpec,
    pack: Optional[IdentityPack] = None,
    scope: str = "horus_lore"
) -> bool:
    """
    Store character in memory for future retrieval.

    Uses the common memory client from .pi/skills/common/memory_client.py
    for consistent integration with the memory skill.

    Args:
        spec: Character specification
        pack: Optional identity pack
        scope: Memory scope (default: horus_lore for character lore)

    Returns:
        True if stored successfully
    """
    if not _memory_client:
        print("Memory client not available - common/memory_client.py not found")
        return False

    # Build graph node with taxonomy
    node = build_character_graph_node(spec, pack)

    try:
        # Use common memory client
        client = MemoryClient(scope=scope)

        # Store as a lesson with character data as solution
        result = client.learn(
            problem=f"Character: {spec.name} ({spec.role.value})",
            solution=json.dumps(node, indent=2),
            tags=["character", spec.role.value] + node["bridge_tags"],
        )

        return result.success
    except Exception as e:
        print(f"Memory storage error: {e}")
        return False


def query_related_characters(
    bridge: str,
    limit: int = 5,
    scope: str = "horus_lore"
) -> List[dict]:
    """
    Query characters with the same bridge attribute.

    Uses the common memory client from .pi/skills/common/memory_client.py
    for multi-hop traversal: find all characters sharing a thematic bridge.

    Args:
        bridge: Bridge attribute to search
        limit: Max results
        scope: Memory scope (default: horus_lore for character lore)

    Returns:
        List of character nodes
    """
    # Validate bridge
    valid_bridges = BRIDGE_TAGS if _taxonomy_module else _FALLBACK_BRIDGE_TAGS
    if bridge not in valid_bridges:
        return []

    if not _memory_client:
        return []

    try:
        # Use common memory client
        client = MemoryClient(scope=scope)

        # Query for characters with this bridge
        result = client.recall(
            query=f"character bridge:{bridge} type:character",
            k=limit,
        )

        if result.found:
            # Parse character nodes from results
            characters = []
            for item in result.items:
                # Try to parse solution as JSON (character node)
                solution = item.get("solution", "")
                if solution:
                    try:
                        node = json.loads(solution)
                        if isinstance(node, dict) and node.get("type") == "character":
                            characters.append(node)
                    except json.JSONDecodeError:
                        # Not JSON, include as-is
                        characters.append(item)
                else:
                    characters.append(item)
            return characters[:limit]

    except Exception as e:
        print(f"Memory query error: {e}")

    return []


def get_taxonomy_skill_status() -> Dict[str, Any]:
    """
    Get status of taxonomy and memory skill integration.

    Returns:
        Dict with integration status and available features
    """
    return {
        "taxonomy_integrated": _taxonomy_module is not None,
        "taxonomy_skill_path": str(_taxonomy_module) if _taxonomy_module else None,
        "memory_integrated": _memory_client is not None,
        "available_bridges": list(BRIDGE_TAGS) if _taxonomy_module else list(_FALLBACK_BRIDGE_TAGS),
        "features": {
            "llm_extraction": _taxonomy_module is not None,
            "keyword_extraction": True,
            "validation": _taxonomy_module is not None,
            "collection_vocabularies": _taxonomy_module is not None,
            "memory_storage": _memory_client is not None,
            "memory_recall": _memory_client is not None,
        }
    }
