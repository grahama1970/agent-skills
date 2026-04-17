#!/usr/bin/env python3
"""Core taxonomy logic: imports, bridge extraction, LLM extraction, utilities.

This module handles:
- Canonical taxonomy imports from the persona bridge
- Bridge attribute extraction from text
- Lore entity checking
- Episodic association lookup
- LLM-based taxonomy extraction
- Verifier creation
- Public utility functions
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common.taxonomy_types import (
    CollectionTags,
    ContentType,
    EXTRACTION_PROMPT,
    TaxonomyExtractionResult,
)
from common.taxonomy_indicators import (
    BOOK_BRIDGE_INDICATORS,
    LORE_BRIDGE_MAPPINGS,
    LORE_SENSORY_INDICATORS,
    MOVIE_BRIDGE_INDICATORS,
    SENSORY_INDICATORS,
    SENSORY_MODALITIES,
)
from loguru import logger

# ==============================================================================
# CANONICAL TAXONOMY IMPORTS
# ==============================================================================

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
_MEMORY_PERSONA_PATH = Path(
    os.environ.get(
        "MEMORY_PERSONA_PATH",
        str(_PROJECT_ROOT / "memory" / "persona"),
    )
)
if str(_MEMORY_PERSONA_PATH) not in sys.path:
    sys.path.insert(0, str(_MEMORY_PERSONA_PATH))

# Import canonical HMT (for music)
_HMT_AVAILABLE = False
MUSIC_BRIDGE_INDICATORS = {}
EPISODIC_ASSOCIATIONS = {}
HMT_VOCABULARY = {}
MUSIC_TACTICAL_TAGS = {}
MusicDimension = None
MathematicalMusicFeatures = None
HorusMusicTaxonomyVerifier = None
create_music_verifier = None

try:
    from bridge.horus_music_taxonomy import (
        MUSIC_BRIDGE_INDICATORS as _MBI,
        EPISODIC_ASSOCIATIONS as _EA,
        HMT_VOCABULARY as _HV,
        MUSIC_TACTICAL_TAGS as _MTT,
        MusicDimension as _MD,
        MathematicalMusicFeatures as _MMF,
        HorusMusicTaxonomyVerifier as _HMTV,
        create_music_verifier as _cmv,
    )
    MUSIC_BRIDGE_INDICATORS = _MBI
    EPISODIC_ASSOCIATIONS = _EA
    HMT_VOCABULARY = _HV
    MUSIC_TACTICAL_TAGS = _MTT
    MusicDimension = _MD
    MathematicalMusicFeatures = _MMF
    HorusMusicTaxonomyVerifier = _HMTV
    create_music_verifier = _cmv
    _HMT_AVAILABLE = True
except ImportError:
    pass  # canonical HMT not available in this project — use built-in fallbacks

# Import main verifier (Persona-agnostic Core)
_VERIFIER_AVAILABLE = False
BRIDGE_ATTRIBUTES = {}
HLT_VOCABULARY = {}
OPERATIONAL_VOCABULARY = {}
SPARTA_VOCABULARY = {}
TACTICAL_TO_CONCEPTUAL = {}
Dimension = None
LORE_ANCHORS = {}
LORE_BRIDGE_INDICATORS = {}
FederatedTaxonomyVerifier = None
CORE_BRIDGE_INDICATORS = {}

try:
    from bridge.federated_taxonomy_verifier import (
        FederatedTaxonomyVerifier as _FTV,
        CORE_BRIDGE_INDICATORS as _CBI,
        OPERATIONAL_VOCABULARY as _OV,
        SPARTA_VOCABULARY as _SV,
        TACTICAL_TO_CONCEPTUAL as _TTC,
        Dimension as _Dim,
        TaxonomyFeatures,
    )
    FederatedTaxonomyVerifier = _FTV
    CORE_BRIDGE_INDICATORS = _CBI
    OPERATIONAL_VOCABULARY = _OV
    SPARTA_VOCABULARY = _SV
    TACTICAL_TO_CONCEPTUAL = _TTC
    Dimension = _Dim

    # Dynamic Persona Loading
    import os as _os
    import importlib
    _persona_name = _os.getenv("PERSONA", "horus").lower()

    try:
        _persona_mod = importlib.import_module(f"bridge.{_persona_name}_persona")
        HLT_VOCABULARY = getattr(_persona_mod, "VOCABULARY", {})
        LORE_ANCHORS = getattr(_persona_mod, "ANCHORS", {})
        LORE_BRIDGE_INDICATORS = getattr(_persona_mod, "BRIDGE_INDICATORS", {})

        # Build unified Bridge Attributes
        BRIDGE_ATTRIBUTES = CORE_BRIDGE_INDICATORS.copy()
        for bridge, indicators in LORE_BRIDGE_INDICATORS.items():
            if bridge not in BRIDGE_ATTRIBUTES:
                BRIDGE_ATTRIBUTES[bridge] = {"lore": indicators}
            else:
                # Merge lore indicators into bridge
                BRIDGE_ATTRIBUTES[bridge] = BRIDGE_ATTRIBUTES[bridge].copy()
                BRIDGE_ATTRIBUTES[bridge]["lore"] = indicators
    except (ImportError, AttributeError) as e:
        import warnings
        warnings.warn(f"Cannot load persona config for '{_persona_name}': {e}")
        HLT_VOCABULARY = {}
        LORE_ANCHORS = {}
        BRIDGE_ATTRIBUTES = CORE_BRIDGE_INDICATORS

    _VERIFIER_AVAILABLE = True
except ImportError:
    pass  # canonical taxonomy verifier not available — use built-in fallbacks


# ==============================================================================
# BRIDGE EXTRACTION FUNCTIONS
# ==============================================================================

def _build_combined_text(*args) -> str:
    """Build combined text from all inputs for pattern matching."""
    parts = []
    for arg in args:
        if isinstance(arg, str) and arg:
            parts.append(arg.lower())
        elif isinstance(arg, list):
            parts.extend(t.lower() for t in arg if t)
    return " ".join(parts)


def _extract_bridges_from_text(text: str, indicators: Dict[str, Dict]) -> Tuple[List[str], Dict[str, float]]:
    """Extract bridge attributes from text using indicators."""
    scores = {}
    text_lower = text.lower()

    for bridge, bridge_def in indicators.items():
        score = 0.0
        matches = 0

        # Check various indicator fields
        for field_name in ["indicators", "themes", "artists", "authors", "genres", "emotions"]:
            field_values = bridge_def.get(field_name, [])
            if isinstance(field_values, dict):
                field_values = list(field_values.keys())
            for indicator in field_values:
                if isinstance(indicator, str) and indicator.lower() in text_lower:
                    score += 1.0
                    matches += 1

        if matches > 0:
            scores[bridge] = score / max(len(indicators.get(bridge, {})), 1)

    # Get top bridges with significant scores
    threshold = 0.2
    bridges = [name for name, score in sorted(scores.items(), key=lambda x: -x[1]) if score >= threshold][:3]

    # If no strong matches, use best guess
    if not bridges and scores:
        bridges = [max(scores, key=scores.get)]

    return bridges, scores


def _check_lore_entities(text: str) -> List[str]:
    """Check for persona-specific lore entities in text."""
    bridges = set()
    text_lower = text.lower()

    # Use dynamic lore anchors from persona config if available
    if _VERIFIER_AVAILABLE and LORE_ANCHORS:
        for entity, mapping in LORE_ANCHORS.items():
            if entity.lower() in text_lower:
                if "bridge" in mapping:
                    bridges.add(mapping["bridge"])

    # Fallback to hardcoded mappings if persona loading failed or found nothing
    if not bridges:
        for entity, entity_bridges in LORE_BRIDGE_MAPPINGS.items():
            if entity.lower() in text_lower:
                bridges.update(entity_bridges)

    return list(bridges)


def _get_episodic_associations(bridges: List[str], text: str = "") -> List[str]:
    """Get episodic associations for bridges."""
    associations = []

    if _HMT_AVAILABLE:
        for episode_name, episode_data in EPISODIC_ASSOCIATIONS.items():
            episode_bridge = episode_data.get("bridge", "")
            if episode_bridge in bridges:
                if episode_name not in associations:
                    associations.append(episode_name)
                continue

            # Match by music indicators in text
            for indicator in episode_data.get("music_indicators", []):
                if indicator.lower() in text.lower():
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
            "Intimacy": ["Sanguinius_Bond", "Emperor_Love"],
        }
        for bridge in bridges:
            associations.extend(episode_map.get(bridge, []))

    return list(set(associations))


# ==============================================================================
# SENSORY MODALITY EXTRACTION
# ==============================================================================

def _sensory_match(indicator: str, text: str) -> bool:
    """Check if indicator appears in text with word-boundary awareness.

    Short indicators (<=3 chars like 'ate', 'cut', 'dry') use word boundary
    matching to avoid false positives ('strategy' matching 'ate'). Longer
    indicators use simple substring matching for speed.
    """
    ind = indicator.lower()
    if len(ind) <= 3:
        import re
        return bool(re.search(r'\b' + re.escape(ind) + r'\b', text))
    return ind in text


def extract_sensory_modalities(text: str) -> List[str]:
    """Extract sensory modalities present in text.

    Scans for smell, taste, touch, temperature, pain, and proprioception
    indicators — both universal (reef, coffee, sweat) and lore-specific
    (ceramite, promethium, gene-seed). Returns the modality names that are
    detected. These describe HOW a memory is encoded, orthogonal to bridge
    attributes (WHAT it means).

    Args:
        text: Text to scan for sensory content.

    Returns:
        List of modality names (e.g. ["smell", "touch", "pain"]).
    """
    text_lower = text.lower()
    detected: List[str] = []

    for modality in SENSORY_MODALITIES:
        # Check universal indicators
        modality_def = SENSORY_INDICATORS.get(modality, {})
        found = False

        for field in modality_def.values():
            if isinstance(field, list):
                for indicator in field:
                    if _sensory_match(indicator, text_lower):
                        found = True
                        break
            if found:
                break

        # Check lore-specific indicators (ceramite, promethium, etc.)
        if not found:
            lore_terms = LORE_SENSORY_INDICATORS.get(modality, [])
            for term in lore_terms:
                if _sensory_match(term, text_lower):
                    found = True
                    break

        if found:
            detected.append(modality)

    return detected


# ==============================================================================
# LLM EXTRACTION (HIGH FIDELITY)
# ==============================================================================

def _extract_llm_taxonomy(combined_text: str, content_type: ContentType) -> Optional[Dict[str, Any]]:
    """Use scillm/chutes to extract high-fidelity taxonomy."""
    # Map ContentType to taxonomy collection strings
    collection_map = {
        ContentType.LORE: "lore",
        ContentType.OPERATIONAL: "operational",
        ContentType.SECURITY: "sparta",
        ContentType.BOOK: "lore",
        ContentType.AUDIOBOOK: "lore",
        ContentType.MOVIE: "lore",
        ContentType.YOUTUBE: "lore",
        ContentType.MUSIC: "lore",
        ContentType.SESSION: "operational",
    }
    collection = collection_map.get(content_type, "operational")

    # Get vocabulary for the collection
    vocab = {}
    if collection == "lore":
        # Convert Enum keys to strings for JSON serialization
        vocab = {k.value if hasattr(k, "value") else str(k): list(v) for k, v in HLT_VOCABULARY.items()}
    elif collection == "operational":
        vocab = {k.value if hasattr(k, "value") else str(k): list(v) for k, v in OPERATIONAL_VOCABULARY.items()}
    elif collection == "sparta":
        vocab = {k.value if hasattr(k, "value") else str(k): list(v) for k, v in SPARTA_VOCABULARY.items()}

    prompt = EXTRACTION_PROMPT.format(
        text=combined_text[:4000],
        collection=collection,
        vocab=json.dumps(vocab, indent=2)
    )

    # Locate scillm batch script
    scillm_path = _PROJECT_ROOT / "memory" / ".agents" / "skills" / "scillm" / "batch.py"
    if not scillm_path.exists():
        return None

    try:
        import sys as _sys
        # Detect model
        import os as _os
        model = _os.getenv("CHUTES_MODEL_ID") or _os.getenv("CHUTES_MODEL") or _os.getenv("CHUTES_TEXT_MODEL")

        # Use uv run with --directory to ensure it uses the scillm skill's own environment
        cmd = ["uv", "run", "--directory", str(scillm_path.parent), "python", "batch.py", "single", prompt, "--json", "--timeout", "90"]
        if model:
            cmd += ["--model", model]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=100,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.strip().startswith("{"):
                    raw = json.loads(line)
                    if raw.get("ok") and raw.get("content"):
                        # The content itself is the JSON string
                        extracted = json.loads(raw["content"])
                        return extracted
        else:
            print(f"DEBUG: scillm failed with code {res.returncode}: {res.stderr}", file=_sys.stderr)
    except Exception as e:
        import sys as _sys
        print(f"DEBUG: scillm exception: {e}", file=_sys.stderr)
        pass
    return None


# ==============================================================================
# VERIFIER CREATION
# ==============================================================================

def create_verifier(content_type: ContentType = ContentType.LORE):
    """
    Create appropriate taxonomy verifier for content type.

    Args:
        content_type: Type of content to verify

    Returns:
        Verifier instance or None if not available
    """
    if content_type == ContentType.MUSIC and _HMT_AVAILABLE:
        return create_music_verifier()
    elif _VERIFIER_AVAILABLE:
        # Load persona config for lore
        lore_config = {
            "anchors": LORE_ANCHORS,
            "vocabulary": HLT_VOCABULARY,
            "bridge_indicators": LORE_BRIDGE_INDICATORS
        }
        return FederatedTaxonomyVerifier(lore_config=lore_config)
    return None


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def get_bridge_attributes(text: str, content_type: Optional[ContentType] = None) -> List[str]:
    """
    Quick utility to get just bridge attributes from text.

    Args:
        text: Text to analyze
        content_type: Optional content type for specialized extraction

    Returns:
        List of Bridge Attribute names
    """
    # Avoid circular import by importing here
    if content_type:
        from common.taxonomy_extractors import (
            _extract_music_features,
            _extract_movie_features,
            _extract_book_features,
            _extract_youtube_features,
            _extract_lore_features,
            _extract_operational_features,
            _extract_security_features,
            _extract_session_features,
            _extract_generic_features,
        )
        result = extract_taxonomy_features(content_type, title=text)
        return result["bridge_attributes"]

    # Check for lore entities first
    bridges = _check_lore_entities(text)

    # Try all indicator sets
    for indicators in [MOVIE_BRIDGE_INDICATORS, BOOK_BRIDGE_INDICATORS]:
        found, _ = _extract_bridges_from_text(text, indicators)
        bridges.extend(found)

    if _HMT_AVAILABLE:
        found, _ = _extract_bridges_from_text(text, MUSIC_BRIDGE_INDICATORS)
        bridges.extend(found)

    return list(set(bridges))[:3]


def get_episodic_associations(bridges: List[str], text: str = "") -> List[str]:
    """
    Get episodic associations for given bridges.

    Args:
        bridges: List of Bridge Attribute names
        text: Optional text for additional matching

    Returns:
        List of episode names (e.g., "Siege_of_Terra", "Davin_Corruption")
    """
    return _get_episodic_associations(bridges, text)


def is_taxonomy_available() -> Dict[str, bool]:
    """Check which taxonomy components are available."""
    return {
        "hmt": _HMT_AVAILABLE,
        "verifier": _VERIFIER_AVAILABLE,
        "music_indicators": bool(MUSIC_BRIDGE_INDICATORS),
        "episodic_associations": bool(EPISODIC_ASSOCIATIONS),
        "bridge_attributes": bool(BRIDGE_ATTRIBUTES),
    }


# ==============================================================================
# CLASSIFIER-BASED EXTRACTION (TIER 1.5)
# ==============================================================================

_bridge_classifier = None
_tactical_classifier = None
_classifier_load_attempted = False


def _load_classifiers():
    """Lazy-load trained classifiers. Only attempts once."""
    global _bridge_classifier, _tactical_classifier, _classifier_load_attempted
    if _classifier_load_attempted:
        return
    _classifier_load_attempted = True

    def _load_multilabel_model(paths):
        """Load a multi-label HuggingFace or joblib model."""
        for p in paths:
            if p.exists():
                try:
                    if p.suffix == ".joblib":
                        import joblib
                        return joblib.load(p)
                    else:
                        from transformers import AutoTokenizer, AutoModelForSequenceClassification
                        tokenizer = AutoTokenizer.from_pretrained(str(p))
                        model = AutoModelForSequenceClassification.from_pretrained(str(p))
                        model.eval()
                        # Read label mapping
                        config = model.config
                        id2label = config.id2label if hasattr(config, "id2label") else {}
                        labels = [id2label.get(i, f"LABEL_{i}") for i in range(config.num_labels)]
                        # Read label_map.json if present (maps index → actual class name)
                        label_map_file = p / "label_map.json"
                        if label_map_file.exists():
                            import json
                            with open(label_map_file) as f:
                                label_map = json.load(f)
                            # label_map keys may be "0","1",... or "LABEL_0","LABEL_1",...
                            labels = [label_map.get(str(i), label_map.get(l, l)) for i, l in enumerate(labels)]
                        # Read per-class thresholds if present
                        thresholds = {}
                        thresholds_file = p / "thresholds.json"
                        if thresholds_file.exists():
                            import json
                            with open(thresholds_file) as f:
                                thresholds = json.load(f)
                        return {"tokenizer": tokenizer, "model": model, "labels": labels, "thresholds": thresholds}
                except Exception as e:
                    logger.debug("value lookup failed: {}", e)
        return None

    # Bridge classifier (Tier 0 conceptual tags) — DistilBERT multi-label (macro_f1=0.9997)
    _bridge_classifier = _load_multilabel_model([
        Path.home() / ".pi/skills/assistant/models/taxonomy-bridge-v5",
        Path.home() / ".pi/models/classifiers/bridge_text_classifier.joblib",
        _EMBRY_STORAGE / "media/agents/shared/create-classifier/models/bridge_classifier/best_model",
    ])

    # Tactical classifier (Tier 1 tactical tags) — DistilBERT multi-label (macro_f1=0.9644)
    _tactical_classifier = _load_multilabel_model([
        Path.home() / ".pi/skills/assistant/models/taxonomy-tactical-v7",
        Path.home() / ".pi/models/classifiers/tactical_text_classifier.joblib",
        _EMBRY_STORAGE / "media/agents/shared/create-classifier/models/tactical_classifier/best_model",
    ])


def _run_multilabel_classifier(classifier, text: str, threshold: float, per_class_thresholds: Optional[Dict[str, float]] = None) -> List[str]:
    """Run inference on a multi-label classifier (joblib or HuggingFace)."""
    if classifier is None:
        return []
    try:
        if hasattr(classifier, "predict_proba"):
            # scikit-learn / joblib model
            probs = classifier.predict_proba([text[:512]])[0]
            classes = classifier.classes_
            return [classes[i] for i, p in enumerate(probs) if p >= (per_class_thresholds or {}).get(classes[i], threshold)]
        elif isinstance(classifier, dict):
            # HuggingFace model dict {tokenizer, model, labels, thresholds}
            import torch
            tokenizer = classifier["tokenizer"]
            model = classifier["model"]
            labels = classifier["labels"]
            cls_thresholds = classifier.get("thresholds", per_class_thresholds or {})
            inputs = tokenizer(text[:512], return_tensors="pt", truncation=True, max_length=256)
            inputs.pop("token_type_ids", None)  # DistilBERT doesn't use these
            with torch.no_grad():
                logits = model(**inputs).logits
            probs = torch.sigmoid(logits)[0]
            return [labels[i] for i, p in enumerate(probs) if p.item() >= cls_thresholds.get(labels[i], threshold)]
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return []


def _classify_bridges(text: str, threshold: float = 0.5) -> List[str]:
    """Use trained bridge classifier for Tier 0 tags. Returns empty list if unavailable."""
    _load_classifiers()
    return _run_multilabel_classifier(_bridge_classifier, text, threshold)


def _classify_tactical(text: str, threshold: float = 0.45) -> List[str]:
    """Use trained tactical classifier for Tier 1 tags. Returns empty list if unavailable."""
    _load_classifiers()
    return _run_multilabel_classifier(_tactical_classifier, text, threshold)


def extract_taxonomy_features(
    content_type: ContentType,
    title: str = "",
    artist: str = "",
    author: str = "",
    genre: str = "",
    tags: Optional[List[str]] = None,
    emotion: str = "",
    description: str = "",
    audio_features: Optional[Dict[str, Any]] = None,
    high_fidelity: bool = False,
    user_id: str = "",
    persona_id: str = "",
    participants: Optional[List[str]] = None,
) -> TaxonomyExtractionResult:
    """
    Extract taxonomy features from any content type.

    This is the unified entry point for all content types. It routes to the
    appropriate extractor based on content_type.

    Args:
        content_type: Type of content (music, movie, book, etc.)
        title: Content title
        artist: Artist/performer name (for music/video)
        author: Author name (for books)
        genre: Genre or category
        tags: Additional tags/keywords
        emotion: Primary emotion/mood
        description: Extended description or synopsis
        audio_features: Audio feature dict (for music with MIR analysis)
        high_fidelity: Use LLM for extraction (slower, higher confidence)
        user_id: User who created/participated in the content
        persona_id: Persona involved in the content (for sessions)
        participants: All participant IDs (users + personas in the conversation)

    Returns:
        TaxonomyExtractionResult with bridge_attributes, collection_tags,
        tactical_tags, episodic_associations, dimensions, participants, and confidence.
    """
    from common.taxonomy_extractors import (
        _extract_music_features,
        _extract_movie_features,
        _extract_book_features,
        _extract_youtube_features,
        _extract_lore_features,
        _extract_operational_features,
        _extract_security_features,
        _extract_session_features,
        _extract_generic_features,
    )

    tags = tags or []
    combined_text = _build_combined_text(title, artist, author, genre, tags, emotion, description)

    # Tier 1.5: Try trained classifiers first (instant, free)
    classifier_bridges = _classify_bridges(combined_text)
    classifier_tactical = _classify_tactical(combined_text)

    llm_features = None
    if high_fidelity:
        llm_features = _extract_llm_taxonomy(combined_text, content_type)

    if content_type == ContentType.MUSIC:
        res = _extract_music_features(title, artist, tags, audio_features, combined_text)
    elif content_type == ContentType.MOVIE:
        res = _extract_movie_features(title, tags, emotion, combined_text)
    elif content_type in (ContentType.BOOK, ContentType.AUDIOBOOK):
        res = _extract_book_features(title, author, genre, tags, combined_text)
    elif content_type == ContentType.YOUTUBE:
        res = _extract_youtube_features(title, artist, tags, combined_text)
    elif content_type == ContentType.LORE:
        res = _extract_lore_features(title, tags, combined_text)
    elif content_type == ContentType.OPERATIONAL:
        res = _extract_operational_features(title, tags, combined_text)
    elif content_type == ContentType.SECURITY:
        res = _extract_security_features(title, tags, combined_text)
    elif content_type == ContentType.SESSION:
        res = _extract_session_features(title, tags, combined_text)
    else:
        # Default fallback
        res = _extract_generic_features(content_type, combined_text)

    # Inject participants into result
    all_participants = list(participants or [])
    if user_id and user_id not in all_participants:
        all_participants.insert(0, user_id)
    if persona_id and persona_id not in all_participants:
        all_participants.append(persona_id)
    res["participants"] = {
        "user_id": user_id or "",
        "persona_id": persona_id or "",
        "participants": all_participants,
    }

    # Merge classifier results (Tier 1.5 — trained models, instant inference)
    if classifier_bridges or classifier_tactical:
        valid_bridges = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
        clf_bridges = [b for b in classifier_bridges if b in valid_bridges]
        res["bridge_attributes"] = list(set(res["bridge_attributes"] + clf_bridges))

        valid_tactical = {"Detect", "Harden", "Model", "Isolate", "Restore", "Evade", "Exploit", "Persist"}
        clf_tactical = [t for t in classifier_tactical if t in valid_tactical]
        res["tactical_tags"] = list(set(res.get("tactical_tags", []) + clf_tactical))

        res["method"] = "classifier_hybrid"
        # Boost confidence when classifier agrees with heuristic
        res["confidence"] = min(res["confidence"] + 0.15, 0.95)

    # Merge LLM results if available (Tier 2 — Enforcement Pattern)
    if llm_features:
        # Use LLM bridge tags as primary, but keep any heuristic hits that are high-confidence
        llm_bridges = llm_features.get("bridge_tags", [])

        # Valid bridge attributes only
        valid_bridges = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth", "Intimacy"}
        llm_bridges = [b for b in llm_bridges if b in valid_bridges]

        # Combine: LLM provides candidates, heuristics (res) provide enforcement
        res["bridge_attributes"] = list(set(res["bridge_attributes"] + llm_bridges))

        # Merge collection tags (LLM often better at these dimensions)
        llm_col_tags = llm_features.get("collection_tags", {})
        for dim, val in llm_col_tags.items():
            if val and dim in res["collection_tags"]:
                if not res["collection_tags"][dim]:
                    res["collection_tags"][dim] = [val]
                elif val not in res["collection_tags"][dim]:
                    res["collection_tags"][dim].append(val)

        res["confidence"] = (res["confidence"] + llm_features.get("confidence", 0.5)) / 2
        res["method"] = "llm_hybrid"
    elif not classifier_bridges and not classifier_tactical:
        res["method"] = "heuristic"

    # Sensory modality extraction (orthogonal to bridges — describes encoding channel)
    sensory = extract_sensory_modalities(combined_text)
    if sensory:
        existing = res["collection_tags"].get("sensory", [])
        res["collection_tags"]["sensory"] = list(set(existing + sensory))

    return res
