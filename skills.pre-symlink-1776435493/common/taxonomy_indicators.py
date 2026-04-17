#!/usr/bin/env python3
"""Bridge indicators and lore mappings for taxonomy extraction.

Contains content-specific bridge indicators (movie, book, lore) that map
thematic elements to the seven Bridge Attributes:
Precision, Resilience, Fragility, Corruption, Loyalty, Stealth, Intimacy.
"""

from typing import Dict, List

# ==============================================================================
# CONTENT-SPECIFIC BRIDGE INDICATORS
# ==============================================================================

# Movie/Film Bridge Indicators (maps visual/emotional to bridges)
MOVIE_BRIDGE_INDICATORS: Dict[str, Dict] = {
    "Precision": {
        "themes": ["strategy", "planning", "calculated", "methodical"],
        "emotions": ["focused", "determined"],
        "genres": ["thriller", "heist", "war"],
        "lore_resonance": "Iron Warriors, siege craft, calculated warfare",
    },
    "Resilience": {
        "themes": ["survival", "endurance", "triumph", "last stand", "defense"],
        "emotions": ["triumphant", "defiant", "hopeful"],
        "genres": ["war", "survival", "sports", "epic"],
        "lore_resonance": "Imperial Fists, Siege of Terra, Dorn's defense",
    },
    "Fragility": {
        "themes": ["loss", "broken", "vulnerable", "shattered"],
        "emotions": ["sorrow", "melancholy", "despair"],
        "genres": ["drama", "tragedy", "romance"],
        "lore_resonance": "Webway collapse, Magnus's Folly, shattered dreams",
    },
    "Corruption": {
        "themes": ["betrayal", "fall", "darkness", "possession", "influence"],
        "emotions": ["dread", "horror", "fear"],
        "genres": ["horror", "psychological", "thriller"],
        "lore_resonance": "Davin corruption, Chaos influence, Warp taint",
    },
    "Loyalty": {
        "themes": ["oath", "duty", "honor", "brotherhood", "sacrifice"],
        "emotions": ["devotion", "pride", "camaraderie"],
        "genres": ["war", "drama", "action"],
        "lore_resonance": "Oaths of Moment, Loken's loyalty, Luna Wolves",
    },
    "Stealth": {
        "themes": ["infiltration", "deception", "hidden", "covert"],
        "emotions": ["tension", "suspense"],
        "genres": ["spy", "thriller", "noir"],
        "lore_resonance": "Alpha Legion, Alpharius, hidden agendas",
    },
    "Intimacy": {
        "themes": ["love", "connection", "touch", "body", "closeness", "tenderness", "desire", "longing", "sensuality"],
        "emotions": ["desire", "warmth", "ache", "yearning", "comfort", "vulnerability"],
        "genres": ["romance", "erotic", "drama", "coming-of-age"],
        "lore_resonance": "Sanguinius bonds, Legion brotherhood, Emperor's love for humanity",
    },
}

# Book Bridge Indicators (maps literary elements to bridges)
BOOK_BRIDGE_INDICATORS: Dict[str, Dict] = {
    "Precision": {
        "themes": ["strategy", "tactics", "logic", "systems", "engineering"],
        "genres": ["military sci-fi", "hard sci-fi", "technical thriller"],
        "authors": ["Andy Weir", "Isaac Asimov", "Michael Crichton"],
        "lore_resonance": "Iron Warriors, Perturabo's calculated siege craft",
    },
    "Resilience": {
        "themes": ["survival", "perseverance", "hope", "rebuilding"],
        "genres": ["post-apocalyptic", "survival", "epic fantasy"],
        "authors": ["Brandon Sanderson", "Cormac McCarthy"],
        "lore_resonance": "Imperial Fists, Siege of Terra, endurance",
    },
    "Fragility": {
        "themes": ["loss", "mortality", "memory", "grief", "vulnerability"],
        "genres": ["literary fiction", "tragedy", "memoir"],
        "authors": ["Kazuo Ishiguro", "Donna Tartt"],
        "lore_resonance": "Webway, shattered plans, irreversible loss",
    },
    "Corruption": {
        "themes": ["fall", "power", "temptation", "darkness", "descent"],
        "genres": ["dark fantasy", "horror", "psychological thriller"],
        "authors": ["H.P. Lovecraft", "Joe Abercrombie"],
        "lore_resonance": "Chaos corruption, Davin, moral descent",
    },
    "Loyalty": {
        "themes": ["duty", "honor", "oaths", "brotherhood", "service"],
        "genres": ["military fiction", "samurai", "knight fiction"],
        "authors": ["Dan Abnett", "Bernard Cornwell"],
        "lore_resonance": "Oaths of Moment, Luna Wolves, sworn duty",
    },
    "Stealth": {
        "themes": ["secrets", "espionage", "hidden", "subterfuge"],
        "genres": ["spy thriller", "mystery", "noir"],
        "authors": ["John le Carré", "Ian Fleming"],
        "lore_resonance": "Alpha Legion, hidden identities, deception",
    },
    "Intimacy": {
        "themes": ["love", "desire", "body", "touch", "closeness", "sensuality", "tenderness", "heartbreak"],
        "genres": ["romance", "literary fiction", "erotic fiction", "memoir"],
        "authors": ["Sally Rooney", "Anaïs Nin", "Ocean Vuong", "Garth Greenwell"],
        "lore_resonance": "Sanguinius bonds, primarch kinship, Emperor's love",
    },
}

# ==============================================================================
# SENSORY MODALITY INDICATORS
# ==============================================================================
# Orthogonal to bridges — describes HOW a memory is encoded, not WHAT it means.
# Used by the dream pipeline to render vivid scenes and find sensory contradictions.

SENSORY_INDICATORS: Dict[str, Dict[str, List[str]]] = {
    "smell": {
        "indicators": [
            "smell", "smelled", "scent", "fragrance", "aroma", "stench", "odor",
            "whiff", "perfume", "musk", "reek", "nose", "nostrils", "inhale",
            "sniff", "pungent", "acrid", "musty", "earthy", "floral",
        ],
        "substances": [
            "smoke", "coffee", "salt", "sweat", "blood", "flowers", "rain",
            "gasoline", "diesel", "chlorine", "sulfur", "linden", "thyme",
            "chicory", "plumeria", "jasmine", "cedar", "pine", "mildew",
            "algae", "seaweed", "fish", "rust", "gunpowder", "incense",
            "ozone", "petrichor", "sunscreen", "soap", "leather", "oil",
        ],
    },
    "taste": {
        "indicators": [
            "taste", "tasted", "flavor", "tongue", "mouth", "swallow",
            "bitter", "sweet", "sour", "salty", "umami", "savory",
            "ate", "eaten", "drank", "drink", "sip", "chew", "bite",
        ],
        "substances": [
            "coffee", "blood", "salt", "iron", "copper", "lemon", "sugar",
            "alcohol", "beer", "wine", "whiskey", "tea", "honey", "char",
            "smoke", "poke", "soy", "sesame", "pizza", "bread", "fish",
            "chocolate", "cinnamon", "ginger", "pepper", "vinegar", "lime",
        ],
    },
    "touch": {
        "indicators": [
            "touch", "touched", "feel", "felt", "skin", "hands", "fingers",
            "palm", "grip", "grasp", "press", "pressed", "stroke", "caress",
            "rough", "smooth", "soft", "hard", "wet", "dry", "sticky",
            "slippery", "sharp", "dull", "texture", "surface",
        ],
        "substances": [
            "wood", "metal", "stone", "concrete", "fabric", "leather",
            "sand", "mud", "ice", "water", "glass", "paper", "rust",
            "bark", "moss", "fur", "hair", "bone", "iron", "silk",
        ],
    },
    "temperature": {
        "indicators": [
            "hot", "cold", "warm", "cool", "freezing", "burning", "scalding",
            "icy", "frozen", "numb", "chilled", "heated", "sweltering",
            "shiver", "sweat", "goosebumps", "flush", "flushed",
        ],
        "contexts": [
            "winter", "summer", "fire", "ice", "snow", "sun", "shade",
            "radiator", "wind", "breeze", "fever", "hypothermia",
        ],
    },
    "pain": {
        "indicators": [
            "pain", "hurt", "ache", "sting", "burn", "throb", "stab",
            "sharp", "dull", "sore", "tender", "raw", "bruise", "bleed",
            "bleeding", "blood", "scar", "wound", "cut", "scrape", "tear",
            "cramp", "spasm", "numb", "tingle",
        ],
        "contexts": [
            "injury", "reef", "coral", "broken", "fracture", "stitch",
            "surgery", "headache", "migraine", "sunburn",
        ],
    },
    "proprioception": {
        "indicators": [
            "balance", "dizzy", "vertigo", "falling", "floating", "weightless",
            "heavy", "light", "spinning", "sway", "steady", "unsteady",
            "heartbeat", "pulse", "breath", "breathing", "chest tight",
            "stomach drop", "gut", "adrenaline", "shaking", "trembling",
        ],
        "contexts": [
            "running", "surfing", "climbing", "swimming", "flying",
            "driving", "standing", "sitting", "lying", "waking",
        ],
    },
}

# Sensory dimension values for CollectionTags
SENSORY_MODALITIES = ["smell", "taste", "touch", "temperature", "pain", "proprioception"]

# ==============================================================================
# LORE-SPECIFIC SENSORY INDICATORS
# ==============================================================================
# Extend the universal sensory indicators with persona-specific substances.
# These are merged at extraction time so lore memories trigger the right modalities.

LORE_SENSORY_INDICATORS: Dict[str, List[str]] = {
    "smell": [
        "ceramite", "promethium", "incense", "sacred oils", "cordite",
        "ozone", "warp", "brimstone", "myrrh", "lapping powder",
        "gene-seed", "recaff", "amasec", "tanna", "counterseptic",
        "bolt propellant", "plasma discharge", "burnt ceramite",
    ],
    "taste": [
        "recaff", "amasec", "tanna", "blood", "iron", "copper",
        "gene-seed", "sacred wine", "combat stims", "nutrient paste",
    ],
    "touch": [
        "ceramite", "power armour", "chainsword", "bolt pistol",
        "parchment", "wax seal", "oath paper", "gene-seed",
        "thunder hammer", "lightning claw", "storm bolter",
        "black carapace", "interface port", "sus-an membrane",
    ],
    "temperature": [
        "plasma", "melta", "promethium", "void cold", "warp fire",
        "ceramite heat", "void exposure", "cryo", "magma",
    ],
    "pain": [
        "nails", "butcher's nails", "black carapace", "gene-seed implant",
        "sus-an membrane", "betcher's gland", "larraman cells",
        "bolt wound", "chainsword wound", "power sword",
    ],
    "proprioception": [
        "warp jump", "gellar field", "void walk", "jump pack",
        "drop pod", "thunderhawk", "teleportation", "webway",
        "sus-an membrane", "catalepsean node",
    ],
}


# ==============================================================================
# LORE-SPECIFIC MAPPINGS
# ==============================================================================

# Warhammer 40K/Horus Heresy specific mappings
LORE_BRIDGE_MAPPINGS: Dict[str, List[str]] = {
    # Primarchs
    "Horus": ["Corruption"],
    "Perturabo": ["Precision"],
    "Dorn": ["Resilience"],
    "Rogal Dorn": ["Resilience"],
    "Magnus": ["Fragility"],
    "Alpharius": ["Stealth"],
    "Omegon": ["Stealth"],
    "Lorgar": ["Corruption"],
    "Sanguinius": ["Loyalty"],
    "Fulgrim": ["Corruption"],
    "Mortarion": ["Corruption"],
    "Angron": ["Fragility"],  # broken by the Nails

    # Legions
    "Iron Warriors": ["Precision"],
    "Imperial Fists": ["Resilience"],
    "Alpha Legion": ["Stealth"],
    "Luna Wolves": ["Loyalty"],
    "Sons of Horus": ["Corruption"],
    "Word Bearers": ["Corruption"],
    "Death Guard": ["Resilience", "Corruption"],
    "Thousand Sons": ["Fragility"],
    "Blood Angels": ["Loyalty"],
    "Ultramarines": ["Resilience"],

    # Events
    "Siege of Terra": ["Resilience"],
    "Davin": ["Corruption"],
    "Isstvan": ["Corruption", "Fragility"],
    "Prospero": ["Fragility"],
    "Webway": ["Fragility"],
    "Iron Cage": ["Precision", "Resilience"],
}
