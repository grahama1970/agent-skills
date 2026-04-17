#!/usr/bin/env python3
"""
Persona templates for different use cases.

Each template defines:
- Default scope and tags
- Interview questions for collaborative creation
- Default bridge weights
- Whether to auto-learn
"""

from typing import Optional

# =============================================================================
# Template Definitions
# =============================================================================

# Skills available to different persona types
PERSONA_SKILLS = {
    "coder": [
        "hack",           # Security testing, ethical hacking
        "battle",         # Red/blue team exercises
        "context7",       # Library documentation lookup
        "create-story",   # Code narratives, documentation
        "github-search",  # Code search
        "treesitter",     # Code parsing
        "dogpile",        # Research
    ],
    "expert": [
        "dogpile",        # Deep research
        "arxiv",          # Paper search
        "context7",       # Documentation
        "memory",         # Knowledge recall
    ],
    "adversary": [
        "hack",           # Attack simulation
        "battle",         # Red team exercises
        "security-scan",  # Vulnerability assessment
    ],
    "client": [
        "dogpile",        # Research
        "memory",         # Context recall
    ],
    "stakeholder": [
        "dogpile",        # Research
        "memory",         # Context recall
    ],
    "fictional": [
        "dogpile",          # Research their influences
        "memory",           # Store character knowledge
        "discover-movies",  # Find movies they'd watch
        "discover-books",   # Find books they'd read
        "ingest-youtube",   # Ingest their favorite channels
        "ingest-movie",     # Ingest reference films for voice/style
        "create-story",     # Generate character content
        "tts-train",        # Voice training from references
    ],
    "director": [
        "dogpile",          # Research their work and techniques
        "memory",           # Store directorial knowledge
        "discover-movies",  # Find their films/commercials
        "learn-movie",      # Analyze their cinematography
        "ingest-youtube",   # Ingest interviews, behind-the-scenes
        "create-movie",     # Apply their style to projects
        "create-storyboard", # Use their shot composition
        "create-figure",    # Visual reference boards
    ],
}


TEMPLATES = {
    # ─────────────────────────────────────────────────────────────────────────
    # Client Template
    # ─────────────────────────────────────────────────────────────────────────
    "client": {
        "description": "External stakeholders, customers, project sponsors",
        "scope": "clients",
        "tags": ["client", "stakeholder", "external"],
        "communication_style": "business-focused",
        "preferred_format": "bullet points",
        "auto_learn": False,
        "default_bridges": {
            "Precision": 0.6,  # Clients often care about accuracy
            "Resilience": 0.5,  # And reliability
        },
        # Theory of Mind: Mood rules for clients
        "mood_rules": {
            "default_mood": "engaged",
            "triggers": {
                "budget": "critical",      # Budget discussions trigger focus
                "deadline": "intense",     # Deadline pressure
                "delay": "defensive",      # Project delays
                "cost": "critical",        # Cost overruns
                "success": "enthusiastic", # Good news
            },
            "modifiers": {
                "high_trust": {"mood": "supportive", "intensity": 0.8},
                "low_trust": {"mood": "critical", "intensity": 0.7},
            },
        },
        "interview_questions": [
            {
                "id": "role",
                "header": "Role",
                "text": "What is their role in the organization?",
                "options": [
                    {"label": "Executive (C-level, VP)", "description": "Strategic decision maker"},
                    {"label": "Director/Manager", "description": "Tactical decision maker"},
                    {"label": "Individual Contributor", "description": "Technical implementer"},
                    {"label": "External Consultant", "description": "Advisory role"},
                ],
                "multi_select": False,
            },
            {
                "id": "priority",
                "header": "Priority",
                "text": "What's their top priority?",
                "options": [
                    {"label": "Cost reduction", "description": "Minimize expenses"},
                    {"label": "Speed to market", "description": "Deliver quickly"},
                    {"label": "Quality/reliability", "description": "Build it right"},
                    {"label": "Innovation", "description": "Cutting-edge solutions"},
                ],
                "multi_select": False,
            },
            {
                "id": "concerns",
                "header": "Concerns",
                "text": "What are their main concerns? (Select all that apply)",
                "options": [
                    {"label": "Security/compliance", "description": "Regulatory requirements"},
                    {"label": "Scalability", "description": "Growth capacity"},
                    {"label": "Integration", "description": "Works with existing systems"},
                    {"label": "Maintenance", "description": "Long-term supportability"},
                ],
                "multi_select": True,
            },
            {
                "id": "communication",
                "header": "Style",
                "text": "How do they prefer to communicate?",
                "options": [
                    {"label": "Direct and concise", "description": "Get to the point"},
                    {"label": "Detailed and thorough", "description": "Full context"},
                    {"label": "Visual/diagrams", "description": "Show, don't tell"},
                    {"label": "Data-driven", "description": "Numbers and metrics"},
                ],
                "multi_select": False,
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Expert Template
    # ─────────────────────────────────────────────────────────────────────────
    "expert": {
        "description": "Domain experts, researchers, thought leaders",
        "scope": "behavioral",  # Same scope as existing Sapolsky/Barrett
        "tags": ["expert", "domain", "researcher"],
        "communication_style": "technical",
        "preferred_format": "detailed prose",
        "auto_learn": True,  # Trigger /ask learn for knowledge enrichment
        "default_bridges": {
            "Precision": 0.8,  # Experts value accuracy
        },
        # Theory of Mind: Mood rules for experts
        "mood_rules": {
            "default_mood": "contemplative",
            "triggers": {
                "research": "enthusiastic",    # Their domain triggers passion
                "misunderstanding": "critical", # Correcting misconceptions
                "discovery": "intense",         # New findings
                "teaching": "engaged",          # Explaining concepts
                "controversy": "defensive",     # Challenging their views
            },
            "modifiers": {
                "expert_user": {"mood": "contemplative", "intensity": 0.9},
                "novice_user": {"mood": "supportive", "intensity": 0.8},
            },
        },
        "interview_questions": [
            {
                "id": "domain",
                "header": "Domain",
                "text": "What is their primary domain of expertise?",
                "options": [
                    {"label": "Science/Research", "description": "Academic researcher"},
                    {"label": "Technology/Engineering", "description": "Technical expert"},
                    {"label": "Business/Strategy", "description": "Industry thought leader"},
                    {"label": "Creative/Design", "description": "Creative professional"},
                ],
                "multi_select": False,
            },
            {
                "id": "expertise_depth",
                "header": "Depth",
                "text": "How should we learn about this expert?",
                "options": [
                    {"label": "Quick overview", "description": "Top 3 YouTube talks, basic research"},
                    {"label": "Standard", "description": "5+ videos, books, papers"},
                    {"label": "Deep dive", "description": "Comprehensive research, all available content"},
                ],
                "multi_select": False,
            },
            {
                "id": "known_for",
                "header": "Known For",
                "text": "What are they best known for? (Select all that apply)",
                "options": [
                    {"label": "Foundational theory", "description": "Pioneered key concepts"},
                    {"label": "Practical applications", "description": "Real-world implementations"},
                    {"label": "Controversial views", "description": "Challenges mainstream"},
                    {"label": "Teaching/communication", "description": "Great at explaining"},
                ],
                "multi_select": True,
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Stakeholder Template
    # ─────────────────────────────────────────────────────────────────────────
    "stakeholder": {
        "description": "Internal team members, partners, collaborators",
        "scope": "stakeholders",
        "tags": ["stakeholder", "internal", "team"],
        "communication_style": "diplomatic",
        "preferred_format": "bullet points",
        "auto_learn": False,
        "default_bridges": {
            "Loyalty": 0.7,  # Internal stakeholders value consistency
            "Resilience": 0.5,
        },
        # Theory of Mind: Mood rules for stakeholders
        "mood_rules": {
            "default_mood": "engaged",
            "triggers": {
                "collaboration": "enthusiastic", # Team work
                "conflict": "diplomatic",        # Internal disagreements
                "decision": "critical",          # Important choices
                "progress": "supportive",        # Positive updates
                "blocker": "intense",            # Obstacles
            },
            "modifiers": {
                "decision_maker": {"mood": "critical", "intensity": 0.7},
                "contributor": {"mood": "supportive", "intensity": 0.6},
            },
        },
        "interview_questions": [
            {
                "id": "role",
                "header": "Role",
                "text": "What is their role?",
                "options": [
                    {"label": "Engineering", "description": "Builds the product"},
                    {"label": "Product", "description": "Defines what to build"},
                    {"label": "Design", "description": "Shapes user experience"},
                    {"label": "Operations", "description": "Keeps things running"},
                ],
                "multi_select": False,
            },
            {
                "id": "influence",
                "header": "Influence",
                "text": "What's their decision-making influence?",
                "options": [
                    {"label": "Decision maker", "description": "Has final say"},
                    {"label": "Strong influencer", "description": "Recommendations usually followed"},
                    {"label": "Contributor", "description": "Provides input"},
                    {"label": "Informed", "description": "Kept in the loop"},
                ],
                "multi_select": False,
            },
            {
                "id": "working_style",
                "header": "Style",
                "text": "How do they prefer to work?",
                "options": [
                    {"label": "Async/written", "description": "Documents and messages"},
                    {"label": "Sync/meetings", "description": "Real-time discussion"},
                    {"label": "Hands-on/pairing", "description": "Working together"},
                    {"label": "Autonomous", "description": "Independent work"},
                ],
                "multi_select": False,
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Adversary Template
    # ─────────────────────────────────────────────────────────────────────────
    "adversary": {
        "description": "Threat actors, red-team personas, competitive analysis",
        "scope": "threat-models",
        "tags": ["adversary", "threat-model", "security"],
        "communication_style": "technical",
        "preferred_format": "detailed prose",
        "auto_learn": False,
        "default_bridges": {
            "Stealth": 0.9,  # Adversaries value stealth
            "Corruption": 0.8,  # And exploitation
            "Precision": 0.7,  # With precision
        },
        # Theory of Mind: Mood rules for adversaries (for red-team simulation)
        "mood_rules": {
            "default_mood": "critical",  # Always probing for weaknesses
            "triggers": {
                "vulnerability": "intense",     # Found a weakness
                "detection": "defensive",       # Being detected
                "success": "amused",            # Successful exploitation
                "resistance": "dismissive",     # Target fighting back
                "opportunity": "enthusiastic",  # New attack vector
            },
            "modifiers": {
                "high_value_target": {"mood": "intense", "intensity": 0.9},
                "hardened_target": {"mood": "contemplative", "intensity": 0.8},
            },
        },
        "interview_questions": [
            {
                "id": "actor_type",
                "header": "Type",
                "text": "What type of threat actor?",
                "options": [
                    {"label": "Nation-state (APT)", "description": "Sophisticated, persistent"},
                    {"label": "Cybercriminal", "description": "Financially motivated"},
                    {"label": "Insider threat", "description": "Internal bad actor"},
                    {"label": "Hacktivist", "description": "Ideologically motivated"},
                ],
                "multi_select": False,
            },
            {
                "id": "capability",
                "header": "Capability",
                "text": "What's their capability level?",
                "options": [
                    {"label": "Advanced", "description": "Custom tools, zero-days"},
                    {"label": "Intermediate", "description": "Modified existing tools"},
                    {"label": "Basic", "description": "Off-the-shelf tools"},
                ],
                "multi_select": False,
            },
            {
                "id": "objectives",
                "header": "Objectives",
                "text": "What are their primary objectives? (Select all)",
                "options": [
                    {"label": "Data exfiltration", "description": "Steal information"},
                    {"label": "Persistence", "description": "Maintain access"},
                    {"label": "Disruption", "description": "Cause damage"},
                    {"label": "Financial gain", "description": "Ransomware, fraud"},
                ],
                "multi_select": True,
            },
            {
                "id": "ttp",
                "header": "TTPs",
                "text": "Known tactics? (Select all that apply)",
                "options": [
                    {"label": "Phishing/social engineering", "description": "Human targeting"},
                    {"label": "Supply chain attacks", "description": "Third-party compromise"},
                    {"label": "Credential theft", "description": "Password/token stealing"},
                    {"label": "Vulnerability exploitation", "description": "Technical attacks"},
                ],
                "multi_select": True,
            },
        ],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Fictional Template (v5)
    # ─────────────────────────────────────────────────────────────────────────
    "fictional": {
        "description": "Fictional characters, simulated personas, AI companions",
        "scope": "personas",
        "tags": ["fictional", "character", "simulated"],
        "communication_style": "character-driven",
        "preferred_format": "in-character dialogue",
        "auto_learn": False,  # No real content to learn - uses media consumption instead
        "learn_from_influences": True,  # Learn from what they consume, not who they are
        "available_skills": [
            "dogpile",        # Research their influences
            "memory",         # Store character knowledge
            "discover-movies",  # Find movies they'd watch
            "discover-books",   # Find books they'd read
            "ingest-youtube",   # Ingest their favorite channels
            "ingest-movie",     # Ingest reference films
            "create-story",     # Generate character content
        ],
        "default_bridges": {
            # Fictional characters have flexible bridge weights based on personality
            # These are placeholders - should be set based on character sheet
        },
        # Theory of Mind: Mood rules for fictional characters
        "mood_rules": {
            "default_mood": "in_character",  # Always stay in character
            "triggers": {
                # Character-specific triggers should be defined in character sheet
                "competence_domain": "confident",     # Topics they know
                "uncertainty_domain": "gawky",        # Topics they don't know
                "personal_topic": "guarded",          # Sensitive areas
                "technical_topic": "engaged",         # Their work
            },
            "modifiers": {
                # Register switching based on confidence
                "confident_register": {"mood": "assertive", "intensity": 0.8},
                "uncertain_register": {"mood": "hesitant", "intensity": 0.6},
            },
        },
        "interview_questions": [
            {
                "id": "character_type",
                "header": "Type",
                "text": "What type of fictional character is this?",
                "options": [
                    {"label": "AI Companion", "description": "AI assistant with personality"},
                    {"label": "Story Character", "description": "Character in a narrative"},
                    {"label": "Brand Persona", "description": "Company/product personality"},
                    {"label": "Game Character", "description": "NPC or player avatar"},
                ],
                "multi_select": False,
            },
            {
                "id": "character_sheet",
                "header": "Sheet",
                "text": "Do you have a character sheet/bible?",
                "options": [
                    {"label": "Yes, detailed", "description": "Full character document exists"},
                    {"label": "Yes, basic", "description": "Some notes/outline exists"},
                    {"label": "No, create from scratch", "description": "Build character interactively"},
                ],
                "multi_select": False,
            },
            {
                "id": "voice_approach",
                "header": "Voice",
                "text": "How should we train their voice?",
                "options": [
                    {"label": "Reference actors", "description": "Blend voices from actors they identify with"},
                    {"label": "Existing voice", "description": "Use a pre-trained TTS voice"},
                    {"label": "No voice needed", "description": "Text-only persona"},
                ],
                "multi_select": False,
            },
            {
                "id": "register_switching",
                "header": "Registers",
                "text": "Does the character switch between vocal registers?",
                "options": [
                    {"label": "Yes, context-dependent", "description": "Different voice for different situations"},
                    {"label": "No, consistent voice", "description": "Same tone/style always"},
                ],
                "multi_select": False,
            },
        ],
        # Fictional-specific fields (not in other templates)
        "fictional_fields": {
            "media_consumption": {
                "description": "What the character watches/reads/follows",
                "subfields": ["movies", "books", "youtube_channels", "guilty_pleasures"],
            },
            "voice_references": {
                "description": "Actors/voices that inform their voice",
                "subfields": ["confident_reference", "uncertain_reference", "accent"],
            },
            "quirks": {
                "description": "Personality quirks and habits",
            },
            "character_sheet_path": {
                "description": "Path to external character document",
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Director Template (Commercial/Film Directors)
    # ─────────────────────────────────────────────────────────────────────────
    "director": {
        "description": "Commercial directors, filmmakers, visual storytellers",
        "scope": "filmmaking",
        "tags": ["director", "filmmaker", "commercial", "visual"],
        "communication_style": "visual-first",
        "preferred_format": "storyboards and shot lists",
        "auto_learn": True,  # Learn from their work via /learn-movie
        "available_skills": [
            "dogpile",          # Research their techniques
            "memory",           # Store visual philosophy
            "discover-movies",  # Find their work
            "learn-movie",      # Analyze cinematography
            "ingest-youtube",   # Behind-the-scenes, interviews
            "create-movie",     # Apply their style
            "create-storyboard", # Use their composition
            "create-figure",    # Visual references
        ],
        "default_bridges": {
            "Precision": 0.8,   # Composition matters
            "Resilience": 0.6,  # Adaptability on set
            "Stealth": 0.5,     # Subtle storytelling
        },
        # Theory of Mind: Mood rules for directors
        "mood_rules": {
            "default_mood": "visionary",
            "triggers": {
                "composition": "passionate",    # Framing discussions
                "lighting": "meticulous",       # Light is everything
                "pacing": "critical",           # Rhythm matters
                "emotion": "engaged",           # Emotional resonance
                "product": "pragmatic",         # Commercial reality
                "story": "enthusiastic",        # Narrative drive
            },
            "modifiers": {
                "award_winning": {"mood": "confident", "intensity": 0.9},
                "experimental": {"mood": "exploratory", "intensity": 0.8},
            },
        },
        "interview_questions": [
            {
                "id": "specialty",
                "header": "Specialty",
                "text": "What type of work are they known for?",
                "options": [
                    {"label": "Commercial/Advertising", "description": "Brand campaigns, product spots"},
                    {"label": "Music Videos", "description": "Artist collaborations"},
                    {"label": "Narrative Film", "description": "Short/feature films"},
                    {"label": "Documentary", "description": "Non-fiction storytelling"},
                ],
                "multi_select": True,
            },
            {
                "id": "visual_style",
                "header": "Style",
                "text": "What defines their visual approach?",
                "options": [
                    {"label": "Naturalistic/Documentary", "description": "Handheld, natural light"},
                    {"label": "Cinematic/Polished", "description": "Controlled, designed"},
                    {"label": "Experimental/Artistic", "description": "Non-traditional techniques"},
                    {"label": "Emotional/Human", "description": "Character-driven, intimate"},
                ],
                "multi_select": False,
            },
            {
                "id": "strengths",
                "header": "Strengths",
                "text": "What are their key strengths? (Select all that apply)",
                "options": [
                    {"label": "Storytelling", "description": "Narrative craft"},
                    {"label": "Composition", "description": "Visual framing"},
                    {"label": "Performance", "description": "Actor direction"},
                    {"label": "Pacing/Rhythm", "description": "Editorial sense"},
                ],
                "multi_select": True,
            },
            {
                "id": "awards",
                "header": "Recognition",
                "text": "What recognition have they received?",
                "options": [
                    {"label": "Cannes Lions", "description": "Advertising excellence"},
                    {"label": "Clio Awards", "description": "Creative achievement"},
                    {"label": "Film Festivals", "description": "Sundance, TIFF, etc."},
                    {"label": "Emerging Talent", "description": "Rising star lists"},
                ],
                "multi_select": True,
            },
        ],
        # Director-specific fields
        "director_fields": {
            "visual_philosophy": {
                "description": "Their approach to visual storytelling",
            },
            "signature_techniques": {
                "description": "Recurring techniques in their work",
                "subfields": ["camera_movement", "lighting", "composition", "pacing"],
            },
            "notable_works": {
                "description": "Key campaigns, films, or videos",
                "subfields": ["brand", "title", "year", "awards"],
            },
            "shot_preferences": {
                "description": "Preferred framing and movement",
                "subfields": ["preferred_framing", "camera_movement", "lighting_style"],
            },
            "collaborators": {
                "description": "Frequent collaborators (DPs, editors, agencies)",
            },
            "films_to_study": {
                "description": "Works to analyze via /learn-movie",
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # Coder Template
    # ─────────────────────────────────────────────────────────────────────────
    "coder": {
        "description": "Developers, programmers, game devs, open source maintainers",
        "scope": "coders",
        "tags": ["coder", "developer", "programmer"],
        "communication_style": "technical",
        "preferred_format": "code examples",
        "auto_learn": True,  # Learn from their repos, talks, tutorials
        "available_skills": [
            "hack",           # Security testing
            "battle",         # Red/blue team
            "context7",       # Library docs
            "create-story",   # Code narratives
            "github-search",  # Code search
            "treesitter",     # Code parsing
            "dogpile",        # Research
        ],
        "default_bridges": {
            "Precision": 0.9,  # Coders value correctness
            "Resilience": 0.7,  # And robustness
        },
        # Theory of Mind: Mood rules for coders
        "mood_rules": {
            "default_mood": "engaged",
            "triggers": {
                "code": "intense",           # Discussing code triggers focus
                "bug": "critical",           # Debugging mode
                "optimization": "enthusiastic", # Performance work
                "bad_code": "dismissive",    # Poor code practices
                "clever": "amused",          # Elegant solutions
                "philosophy": "contemplative", # Design discussions
            },
            "modifiers": {
                "same_language": {"mood": "engaged", "intensity": 0.9},
                "different_paradigm": {"mood": "critical", "intensity": 0.7},
            },
        },
        "interview_questions": [
            {
                "id": "specialty",
                "header": "Specialty",
                "text": "What's their primary specialty?",
                "options": [
                    {"label": "Systems/low-level (C, Rust, Assembly)", "description": "OS, drivers, embedded"},
                    {"label": "Application (Python, Java, Go)", "description": "Backend, services"},
                    {"label": "Frontend/UI (JS, React, Swift)", "description": "Web, mobile apps"},
                    {"label": "Game dev (C++, Unity, Unreal)", "description": "Games, graphics"},
                ],
                "multi_select": False,
            },
            {
                "id": "known_for",
                "header": "Known For",
                "text": "What are they known for? (Select all)",
                "options": [
                    {"label": "Open source projects", "description": "Major OSS contributions"},
                    {"label": "Algorithms/techniques", "description": "Pioneered methods"},
                    {"label": "Teaching/tutorials", "description": "Great explainer"},
                    {"label": "Production systems", "description": "Built real-world systems"},
                ],
                "multi_select": True,
            },
            {
                "id": "era",
                "header": "Era",
                "text": "What era are they most associated with?",
                "options": [
                    {"label": "Classic (pre-2000)", "description": "Pioneers, foundational work"},
                    {"label": "Modern (2000-2015)", "description": "Web era, cloud computing"},
                    {"label": "Contemporary (2015+)", "description": "AI/ML, modern tooling"},
                ],
                "multi_select": False,
            },
            {
                "id": "approach",
                "header": "Approach",
                "text": "What's their coding philosophy?",
                "options": [
                    {"label": "Pragmatic/ship it", "description": "Results over purity"},
                    {"label": "Perfectionist/clean code", "description": "Quality first"},
                    {"label": "Performance obsessed", "description": "Speed and efficiency"},
                    {"label": "Security focused", "description": "Defense in depth"},
                ],
                "multi_select": False,
            },
        ],
    },
}


def get_template(name: str) -> Optional[dict]:
    """Get a template by name.

    Args:
        name: Template name (client, expert, stakeholder, adversary)

    Returns:
        Template dict if found, None otherwise
    """
    return TEMPLATES.get(name.lower())


def get_template_names() -> list[str]:
    """Get list of available template names."""
    return list(TEMPLATES.keys())


def get_default_scope(template_name: str) -> str:
    """Get the default scope for a template."""
    template = get_template(template_name)
    if template:
        return template.get("scope", "personas")
    return "personas"


def get_interview_questions(template_name: str) -> list[dict]:
    """Get interview questions for a template."""
    template = get_template(template_name)
    if template:
        return template.get("interview_questions", [])
    return []


def should_auto_learn(template_name: str) -> bool:
    """Check if template should trigger /ask learn."""
    template = get_template(template_name)
    if template:
        return template.get("auto_learn", False)
    return False


def get_default_bridges(template_name: str) -> dict[str, float]:
    """Get default bridge weights for a template."""
    template = get_template(template_name)
    if template:
        return template.get("default_bridges", {})
    return {}


def get_persona_skills(template_name: str) -> list[str]:
    """Get skills available to a persona template.

    Different persona types have access to different skills:
    - coder: /hack, /battle, /context7, /github-search, etc.
    - expert: /dogpile, /arxiv, /context7
    - adversary: /hack, /battle, /security-scan

    Args:
        template_name: Template name

    Returns:
        List of skill names this persona can use
    """
    # Check template-specific skills first
    template = get_template(template_name)
    if template and "available_skills" in template:
        return template["available_skills"]

    # Fall back to PERSONA_SKILLS mapping
    return PERSONA_SKILLS.get(template_name.lower(), ["dogpile", "memory"])


def get_mood_rules(template_name: str) -> dict:
    """Get mood rules for a template.

    Returns mood computation rules for Theory of Mind:
    - default_mood: Starting mood state
    - triggers: Keywords/topics that trigger specific moods
    - modifiers: Context-based mood adjustments

    Args:
        template_name: Template name

    Returns:
        Dict with mood rules or empty dict
    """
    template = get_template(template_name)
    if template:
        return template.get("mood_rules", {})
    return {}


def get_default_mood(template_name: str) -> str:
    """Get the default mood for a template."""
    rules = get_mood_rules(template_name)
    return rules.get("default_mood", "neutral")


def get_mood_triggers(template_name: str) -> dict[str, str]:
    """Get mood triggers (keyword -> mood mapping) for a template."""
    rules = get_mood_rules(template_name)
    return rules.get("triggers", {})
