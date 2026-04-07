#!/usr/bin/env python3
"""
Core persona model and operations.

Personas are stored in memory with rich metadata for:
- Client/stakeholder modeling
- Expert knowledge profiles
- Multi-hop graph traversal via Federated Taxonomy bridges
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger as log

# Memory CLI for fast operations
MEMORY_AGENT_CLI = Path(os.path.expanduser("~/.local/bin/memory-agent"))

# Skills directory for composing with other skills
SKILLS_DIR = Path(__file__).parent.parent.parent


# =============================================================================
# Persona Model
# =============================================================================

@dataclass
class Persona:
    """Rich persona model for client/stakeholder/expert modeling."""

    # ─────────────────────────────────────────────────────────────────────────
    # Identity
    # ─────────────────────────────────────────────────────────────────────────
    name: str
    aliases: list[str] = field(default_factory=list)
    pen_name: str = ""  # Publication pseudonym for real-person personas
    pen_affiliation: str = ""  # Fictional affiliation for pen name publications
    writing_voice: str = ""  # 1-2 sentence guardrail for publication tone
    role: str = ""  # "CTO", "Product Manager", "Neuroscientist"
    organization: str = ""  # "Acme Corp", "Stanford University"

    # ─────────────────────────────────────────────────────────────────────────
    # Domain & Expertise
    # ─────────────────────────────────────────────────────────────────────────
    domain: str = ""  # "healthcare", "finance", "neuroscience"
    expertise: list[str] = field(default_factory=list)  # ["stress biology", "endocrinology"]

    # ─────────────────────────────────────────────────────────────────────────
    # Communication Style
    # ─────────────────────────────────────────────────────────────────────────
    communication_style: str = ""  # "direct", "diplomatic", "technical", "business"
    preferred_format: str = ""  # "bullet points", "detailed prose", "code examples"

    # ─────────────────────────────────────────────────────────────────────────
    # Goals, Concerns, Constraints
    # ─────────────────────────────────────────────────────────────────────────
    goals: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────────────────────
    # Federated Taxonomy Bridges
    # ─────────────────────────────────────────────────────────────────────────
    # Weights from 0.0-1.0 indicating persona's alignment with each bridge
    bridge_weights: dict[str, float] = field(default_factory=dict)
    # Valid bridges: Precision, Resilience, Fragility, Corruption, Loyalty, Stealth

    # ─────────────────────────────────────────────────────────────────────────
    # Learning Sources (populated by /ask learn)
    # ─────────────────────────────────────────────────────────────────────────
    sources: dict = field(default_factory=dict)  # {youtube: 3, books: 1, dogpile: 5}
    qra_count: int = 0  # Number of QRA pairs extracted

    # ─────────────────────────────────────────────────────────────────────────
    # Voice/TTS (populated by /create-persona voice train)
    # ─────────────────────────────────────────────────────────────────────────
    voice_model_path: str = ""  # Path to trained Qwen3-TTS model
    voice_source_urls: list[str] = field(default_factory=list)  # YouTube URLs used
    voice_status: str = ""  # "pending", "training", "ready", "failed"
    voice_dataset_path: str = ""  # Path to training dataset
    voice_trained_at: str = ""  # ISO timestamp of when voice was trained

    # ─────────────────────────────────────────────────────────────────────────
    # Fictional Character Fields (template: fictional)
    # ─────────────────────────────────────────────────────────────────────────
    # Media consumption - what shapes their personality
    media_consumption: dict = field(default_factory=dict)
    # Structure:
    # {
    #   "movies": {"formative": ["Contact", "Interstellar"], "guilty_pleasure": ["rocket launches"]},
    #   "books": {"nightstand": ["The Right Stuff"], "favorites": []},
    #   "youtube_channels": {"daily": ["Everyday Astronaut"], "occasional": []},
    #   "guilty_pleasures": ["competes with mom at Sudoku"]
    # }

    # Voice references - actors whose voices inform theirs
    voice_references: list[dict] = field(default_factory=list)
    # Structure:
    # [
    #   {"actress": "Hailee Steinfeld", "register": "confident", "weight": 0.6,
    #    "clips_to_find": ["Hawkeye technical scenes"]},
    #   {"actress": "Kristen Stewart", "register": "uncertain", "weight": 0.4,
    #    "clips_to_find": ["awkward interviews"]}
    # ]

    # Accent specification for voice training
    voice_accent: str = ""  # "subtle_southern", "charleston_educated", etc.

    # Character quirks and habits
    quirks: list[str] = field(default_factory=list)
    # ["competes with mom at Sudoku secretly", "drinks too many Celsius"]

    # Path to external character sheet document
    character_sheet_path: str = ""

    # Register switching behavior (for voice and writing)
    register_switching: dict = field(default_factory=dict)
    # {
    #   "confident_triggers": ["SPARTA", "NIST", "technical topics"],
    #   "uncertain_triggers": ["being observed", "Marcus from PM"],
    #   "confident_voice": "Hailee Steinfeld",
    #   "uncertain_voice": "Kristen Stewart"
    # }

    # Simulacrum mode for fictional (validates in-character, not ground truth)
    simulacrum_mode: str = ""  # "character_consistency" for fictional, "" for real

    # ─────────────────────────────────────────────────────────────────────────
    # Historical & Cultural Context (for voice design)
    # ─────────────────────────────────────────────────────────────────────────
    # Family structure and dynamics
    family_structure: dict = field(default_factory=dict)
    # Structure:
    # {
    #   "birth_order": "eldest",  # eldest, middle, youngest, only
    #   "siblings": 2,
    #   "parent_loss_age": 12,  # age when lost parent (if applicable)
    #   "family_size": "large",  # small, medium, large
    #   "socioeconomic_class": "middle",  # lower, middle, upper
    #   "family_stability": "unstable"  # stable, unstable, traumatic
    # }

    # Religious/spiritual context
    religion: dict = field(default_factory=dict)
    # Structure:
    # {
    #   "tradition": "Buddhist",  # Christian, Jewish, Muslim, Buddhist, Hindu, Pagan, Atheist, etc.
    #   "denomination": "Zen",  # Catholic, Protestant, Sunni, Theravada, etc.
    #   "religiosity": 0.7,  # 0.0 = cultural only, 1.0 = devout/practicing
    #   "religious_era": "Victorian",  # Era-specific religious norms
    #   "emotional_expression_norms": "suppressed"  # encouraged, moderate, suppressed
    # }

    # Geographic and cultural origin
    cultural_context: dict = field(default_factory=dict)
    # Structure:
    # {
    #   "birth_region": "Rome, Italy",
    #   "era": "2nd century CE",
    #   "cultural_tradition": "Greco-Roman",
    #   "emotional_display_rules": "Stoic - controlled expression",
    #   "grief_expression_norms": "public mourning rituals but private suffering"
    # }

    # Life events mapped by age (for voice design)
    life_events: dict = field(default_factory=dict)
    # Structure:
    # {
    #   "formative": [  # ages 5-25 - always subtly present in voice
    #     {"age": 12, "event": "father's death", "voice_impact": "underlying grief, guarded"}
    #   ],
    #   "prime": [  # ages 25-50 - defines conscious identity
    #     {"age": 35, "event": "became emperor", "voice_impact": "authoritative weight"}
    #   ],
    #   "later": [  # ages 50+ - most audible layer
    #     {"age": 58, "event": "writing Meditations", "voice_impact": "reflective, philosophical"}
    #   ]
    # }

    # Birth and death years (for age-at-event correlation)
    birth_year: int = 0  # e.g., 121 for Marcus Aurelius (CE), -428 for Plato (BCE)
    death_year: int = 0  # e.g., 180 for Marcus Aurelius
    lifespan_note: str = ""  # "121-180 CE" or "428-348 BCE"

    # ─────────────────────────────────────────────────────────────────────────
    # Metadata
    # ─────────────────────────────────────────────────────────────────────────
    scope: str = "personas"
    tags: list[str] = field(default_factory=list)
    template: str = ""  # "client", "expert", "stakeholder", "adversary"
    created_at: str = ""
    last_updated: str = ""

    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.last_updated:
            self.last_updated = now

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        """Create Persona from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "Persona":
        """Create Persona from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def get_publication_name(self) -> str:
        """Return pen_name if set, otherwise name. Use for paper authorship."""
        return self.pen_name or self.name

    def get_memory_problem(self) -> str:
        """Generate the 'problem' field for memory storage."""
        return f"Persona: {self.name}"

    def get_memory_tags(self) -> list[str]:
        """Generate tags for memory storage."""
        tags = ["persona", self.template or "custom"]
        tags.append(self.name.lower().replace(" ", "_"))

        if self.organization:
            tags.append(f"org:{self.organization.lower().replace(' ', '_')}")
        if self.domain:
            tags.append(f"domain:{self.domain.lower().replace(' ', '_')}")
        for bridge in self.bridge_weights:
            tags.append(f"bridge:{bridge}")

        tags.extend(self.tags)
        return list(set(tags))  # Deduplicate

    def update_timestamp(self):
        """Update last_updated to now."""
        self.last_updated = datetime.now().isoformat()


@dataclass
class PersonaRelationship:
    """Relationship edge between two personas for graph traversal."""

    from_persona: str
    to_persona: str
    relationship: str  # "colleague", "mentor", "reports_to", "manages", "collaborator"
    bridges: list[str] = field(default_factory=list)  # Shared taxonomy bridges
    context: str = ""  # Additional context about the relationship
    bidirectional: bool = True  # If True, relationship works both ways
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def get_memory_problem(self) -> str:
        """Generate the 'problem' field for memory storage."""
        return f"Relationship: {self.from_persona} → {self.to_persona} ({self.relationship})"

    def get_memory_tags(self) -> list[str]:
        """Generate tags for memory storage and traversal."""
        tags = [
            "persona_relationship",
            self.relationship,
            f"from:{self.from_persona.lower().replace(' ', '_')}",
            f"to:{self.to_persona.lower().replace(' ', '_')}",
            f"colleague:{self.from_persona.lower().replace(' ', '_')}",
            f"colleague:{self.to_persona.lower().replace(' ', '_')}",
        ]
        for bridge in self.bridges:
            tags.append(f"bridge:{bridge}")
        return tags


# =============================================================================
# Memory Operations
# =============================================================================

def run_skill(name: str, args: list[str], timeout: int = 30) -> dict:
    """Run a skill via its run.sh and capture output."""
    candidates = [
        SKILLS_DIR / name / "run.sh",
        SKILLS_DIR.parent / ".agent" / "skills" / name / "run.sh",
    ]

    script = None
    for candidate in candidates:
        if candidate.exists():
            script = candidate
            break

    if not script:
        log.warning("Skill '%s' not found in any location", name)
        return {"returncode": -1, "stdout": "", "stderr": f"Skill {name} not found", "skipped": True}

    log.debug("Running skill '%s': %s %s", name, script, args)

    try:
        result = subprocess.run(
            [str(script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script.parent),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "skipped": False,
        }
    except subprocess.TimeoutExpired:
        log.error("Skill '%s' timed out after %ds", name, timeout)
        return {"returncode": -2, "stdout": "", "stderr": f"Skill {name} timed out", "skipped": False}
    except Exception as e:
        log.error("Skill '%s' failed: %s", name, e)
        return {"returncode": -3, "stdout": "", "stderr": str(e), "skipped": False}


def store_to_memory(
    problem: str,
    solution: str,
    scope: str,
    tags: list[str],
    timeout: int = 30,
) -> bool:
    """Store item to memory using memory-agent CLI or run.sh."""
    if MEMORY_AGENT_CLI.exists():
        cmd = [
            str(MEMORY_AGENT_CLI), "learn",
            "-p", problem,
            "-s", solution,
            "--scope", scope,
        ]
        for tag in tags:
            cmd.extend(["-t", tag])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return result.returncode == 0
        except Exception as e:
            log.error("Memory store failed: %s", e)

    # Fallback to run_skill
    args = ["learn", "--problem", problem, "--solution", solution, "--scope", scope]
    for tag in tags:
        args.extend(["--tag", tag])

    result = run_skill("memory", args, timeout=timeout)
    return result["returncode"] == 0


def recall_from_memory(
    query: str,
    scope: str,
    k: int = 5,
    tags: Optional[list[str]] = None,
    timeout: int = 15,
) -> list[dict]:
    """Recall items from memory."""
    if MEMORY_AGENT_CLI.exists():
        cmd = [
            str(MEMORY_AGENT_CLI), "recall",
            "-q", query,
            "--scope", scope,
            "--k", str(k),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                    )
                    # Handle both raw list and wrapped response formats
                    if isinstance(data, dict) and "items" in data:
                        return data["items"]
                    elif isinstance(data, list):
                        return data
                    return []
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            log.error("Memory recall failed: %s", e)

    # Fallback to run_skill
    args = ["recall", "-q", query, "--scope", scope, "--k", str(k)]
    if tags:
        for tag in tags:
            args.extend(["--tags", tag])

    result = run_skill("memory", args, timeout=timeout)
    if result["returncode"] == 0:
        try:
            data = json.loads(result["stdout"])
            # Handle both raw list and wrapped response formats
            if isinstance(data, dict) and "items" in data:
                return data["items"]
            elif isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            pass

    return []


# =============================================================================
# Persona CRUD Operations
# =============================================================================

def create_persona(
    persona: Persona,
    store: bool = True,
) -> bool:
    """Create and optionally store a persona to memory.

    Args:
        persona: Persona object to create
        store: If True, store to memory

    Returns:
        True if successful
    """
    if not store:
        return True

    problem = persona.get_memory_problem()
    solution = persona.to_json()
    tags = persona.get_memory_tags()

    success = store_to_memory(problem, solution, persona.scope, tags)

    if success:
        log.info("Created persona '%s' in scope '%s'", persona.name, persona.scope)
    else:
        log.error("Failed to create persona '%s'", persona.name)

    return success


def get_persona(
    name: str,
    scope: str = "personas",
) -> Optional[Persona]:
    """Retrieve a persona from memory.

    Args:
        name: Persona name to find
        scope: Memory scope to search

    Returns:
        Persona if found, None otherwise
    """
    items = recall_from_memory(f"Persona: {name}", scope, k=3)

    for item in items:
        problem = item.get("problem", "")
        solution = item.get("solution", "")

        if name.lower() in problem.lower() and "persona" in problem.lower():
            try:
                data = json.loads(solution)
                return Persona.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                continue

    return None


def list_personas(
    scope: Optional[str] = None,
    template: Optional[str] = None,
    tag: Optional[str] = None,
) -> list[Persona]:
    """List personas from memory.

    Args:
        scope: Filter by scope (None = search common scopes)
        template: Filter by template type
        tag: Filter by tag

    Returns:
        List of Persona objects
    """
    scopes_to_search = [scope] if scope else ["personas", "clients", "behavioral", "stakeholders", "threat-models"]

    personas = []
    seen_names = set()

    for search_scope in scopes_to_search:
        query = "Persona:"
        if template:
            query += f" {template}"

        items = recall_from_memory(query, search_scope, k=50)

        for item in items:
            problem = item.get("problem", "")
            solution = item.get("solution", "")

            if "persona" not in problem.lower():
                continue

            try:
                data = json.loads(solution)
                persona = Persona.from_dict(data)

                # Apply filters
                if template and persona.template != template:
                    continue
                if tag and tag not in persona.tags:
                    continue
                if persona.name.lower() in seen_names:
                    continue

                seen_names.add(persona.name.lower())
                personas.append(persona)

            except (json.JSONDecodeError, TypeError):
                continue

    return personas


def update_persona(
    name: str,
    scope: str = "personas",
    **updates,
) -> Optional[Persona]:
    """Update an existing persona.

    Args:
        name: Persona name to update
        scope: Memory scope
        **updates: Fields to update

    Returns:
        Updated Persona if successful, None otherwise
    """
    persona = get_persona(name, scope)
    if not persona:
        log.warning("Persona '%s' not found in scope '%s'", name, scope)
        return None

    # Apply updates
    for key, value in updates.items():
        if hasattr(persona, key):
            if key in ("goals", "concerns", "constraints", "expertise", "aliases", "tags"):
                # Append to lists
                current = getattr(persona, key)
                if isinstance(value, list):
                    current.extend(value)
                else:
                    current.append(value)
                setattr(persona, key, list(set(current)))  # Deduplicate
            elif key == "bridge_weights":
                # Merge dicts
                current = getattr(persona, key)
                current.update(value)
            else:
                setattr(persona, key, value)

    persona.update_timestamp()

    # Re-store
    if create_persona(persona, store=True):
        return persona

    return None


def delete_persona(
    name: str,
    scope: str = "personas",
) -> bool:
    """Delete a persona from memory.

    Note: This marks the persona as deleted but doesn't remove from storage.
    Memory doesn't support true deletion.

    Args:
        name: Persona name to delete
        scope: Memory scope

    Returns:
        True if marked as deleted
    """
    persona = get_persona(name, scope)
    if not persona:
        return False

    # Store a deletion marker
    problem = f"Persona DELETED: {name}"
    solution = json.dumps({"name": name, "deleted": True, "deleted_at": datetime.now().isoformat()})
    tags = ["persona", "deleted", name.lower().replace(" ", "_")]

    return store_to_memory(problem, solution, scope, tags)


# =============================================================================
# Relationship Operations
# =============================================================================

def create_relationship(
    relationship: PersonaRelationship,
    scope: str = "personas",
) -> bool:
    """Create a relationship edge between personas.

    Args:
        relationship: PersonaRelationship to store
        scope: Memory scope for the relationship

    Returns:
        True if successful
    """
    problem = relationship.get_memory_problem()
    solution = json.dumps(relationship.to_dict(), indent=2)
    tags = relationship.get_memory_tags()

    success = store_to_memory(problem, solution, scope, tags)

    if success:
        log.info("Created relationship: %s → %s (%s)",
                 relationship.from_persona, relationship.to_persona, relationship.relationship)

        # If bidirectional, store reverse relationship too
        if relationship.bidirectional:
            reverse = PersonaRelationship(
                from_persona=relationship.to_persona,
                to_persona=relationship.from_persona,
                relationship=_reverse_relationship(relationship.relationship),
                bridges=relationship.bridges,
                context=relationship.context,
                bidirectional=False,  # Don't recurse
            )
            reverse_problem = reverse.get_memory_problem()
            reverse_solution = json.dumps(reverse.to_dict(), indent=2)
            reverse_tags = reverse.get_memory_tags()
            store_to_memory(reverse_problem, reverse_solution, scope, reverse_tags)

    return success


def _reverse_relationship(rel_type: str) -> str:
    """Get the reverse relationship type."""
    reverses = {
        "reports_to": "manages",
        "manages": "reports_to",
        "mentors": "mentored_by",
        "mentored_by": "mentors",
    }
    return reverses.get(rel_type, rel_type)  # colleague, collaborator are symmetric


def get_relationships(
    persona_name: str,
    scope: str = "personas",
    relationship_type: Optional[str] = None,
) -> list[PersonaRelationship]:
    """Get relationships for a persona.

    Args:
        persona_name: Name to find relationships for
        scope: Memory scope
        relationship_type: Filter by type (colleague, mentor, etc.)

    Returns:
        List of PersonaRelationship objects
    """
    tag = f"from:{persona_name.lower().replace(' ', '_')}"
    items = recall_from_memory(f"Relationship: {persona_name}", scope, k=20, tags=[tag])

    relationships = []
    for item in items:
        solution = item.get("solution", "")
        try:
            data = json.loads(solution)
            rel = PersonaRelationship(**data)
            if relationship_type and rel.relationship != relationship_type:
                continue
            relationships.append(rel)
        except (json.JSONDecodeError, TypeError):
            continue

    return relationships


def get_colleagues(
    persona_name: str,
    scope: str = "personas",
    via_bridges: Optional[list[str]] = None,
) -> list[str]:
    """Get colleague names for multi-hop traversal.

    Args:
        persona_name: Persona to find colleagues for
        scope: Memory scope
        via_bridges: Only return colleagues sharing these bridges

    Returns:
        List of colleague names
    """
    relationships = get_relationships(persona_name, scope)
    colleagues = []

    for rel in relationships:
        if rel.relationship in ("colleague", "collaborator", "mentor", "mentored_by"):
            if via_bridges:
                # Filter by shared bridges
                shared = set(rel.bridges) & set(via_bridges)
                if not shared:
                    continue
            colleagues.append(rel.to_persona)

    return colleagues
