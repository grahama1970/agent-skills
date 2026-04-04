"""
Persona Journal - Memory & Storage Module

Database access, episode queries, memory retrieval, journal storage,
taxonomy extraction, and graph edge creation.
"""

import json
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from loguru import logger

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SKILLS_DIR.parent


def get_db():
    """Get ArangoDB connection."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from db import get_db as _get_db
        return _get_db()
    except ImportError:
        # Fallback to graph_memory
        from graph_memory.arango_client import get_db as _get_db
        return _get_db()


def get_persona_profile(persona_name: str) -> Dict[str, Any]:
    """Get persona profile from create-persona skill."""
    create_persona_path = SKILLS_DIR.parent.parent / "streamdeck" / ".claude" / "skills" / "create-persona"
    if not create_persona_path.exists():
        create_persona_path = SKILLS_DIR / "create-persona"

    try:
        result = subprocess.run(
            ["./run.sh", "show", persona_name, "--json"],
            cwd=str(create_persona_path),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        logger.debug("JSON parse failed: {}", e)

    return {"name": persona_name, "role": "unknown", "domain": "general"}


def get_current_events(persona: Dict[str, Any]) -> str:
    """Query dogpile for events on THIS SPECIFIC DAY in the persona's era.

    CRUCIAL: A persona lives in THEIR time period, not ours.
    - A 1956 persona on February 10th experiences February 10, 1956
    - A 2026 persona experiences February 10, 2026
    - A 667 BC persona experiences their equivalent calendar date

    The persona's temporal_setting is their REALITY.
    Events may not always be available for historical dates.
    """
    domain = persona.get("domain", "")
    expertise = persona.get("expertise", [])
    role = persona.get("role", "")

    # Get persona's temporal setting (default to present if not specified)
    temporal_setting = persona.get("temporal_setting", {})
    persona_year = temporal_setting.get("year", datetime.now().year)
    persona_era = temporal_setting.get("era", "AD")  # AD, BC, CE, BCE
    persona_location = temporal_setting.get("location", "")

    # Get today's date in the PERSONA's time
    now = datetime.now()
    persona_month = now.strftime("%B")  # February
    persona_day = now.day  # 10

    # Build search query based on persona's interests
    search_terms = []
    if domain:
        search_terms.append(domain)
    if expertise:
        search_terms.extend(expertise[:2])
    if role:
        search_terms.append(role)

    # Build date-specific query for THEIR era
    if persona_year == now.year and persona_era in ["AD", "CE"]:
        # Contemporary persona - use today's exact date
        query = f"news {now.strftime('%B %d %Y')} {' '.join(search_terms[:3])}"
    else:
        # Historical persona - search for events ON THIS DAY in their year
        era_suffix = f" {persona_era}" if persona_era in ["BC", "BCE"] else ""
        location_context = f" in {persona_location}" if persona_location else ""

        # Try date-specific first (most relevant for recent history)
        if persona_year > 1800:
            # "What happened on February 10, 1956"
            query = f"what happened on {persona_month} {persona_day} {persona_year}{era_suffix}{location_context}"
        else:
            # For ancient history, broader search by year (exact dates less documented)
            query = f"events in {persona_year}{era_suffix}{location_context} {' '.join(search_terms[:2])}"

    dogpile_path = SKILLS_DIR / "dogpile"
    if not dogpile_path.exists():
        return ""

    try:
        # Quick dogpile search (no deep research, just headlines)
        result = subprocess.run(
            ["./run.sh", "search", query, "--no-interactive", "--no-tailor"],
            cwd=str(dogpile_path),
            capture_output=True,
            text=True,
            timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0 and result.stdout:
            # Extract just headlines/summaries (first 500 chars)
            output = result.stdout[:500]

            # Format based on era
            if persona_year == now.year:
                return f"[Today's news ({persona_month} {persona_day}, {persona_year}): {output[:300]}...]"
            else:
                return f"[Events from {persona_month} {persona_day}, {persona_year}{' ' + persona_era if persona_era in ['BC', 'BCE'] else ''}: {output[:300]}...]"

    except Exception as e:
        print(f"  Note: Could not fetch events for {persona_month} {persona_day}, {persona_year}: {e}")

    # Return empty - historical events not always available
    return ""


def get_persona_daily_life(persona: Dict[str, Any]) -> Dict[str, Any]:
    """Get persona's personal life context for journal entries."""
    personal_life = persona.get("personal_life", {})

    # Get relationships
    relationships = []
    spouse = personal_life.get("spouse") or personal_life.get("partner")
    if spouse:
        relationships.append(f"spouse: {spouse}")

    children = personal_life.get("children", [])
    if children:
        relationships.append(f"children: {', '.join(children) if isinstance(children, list) else children}")

    pets = personal_life.get("pets", [])
    if pets:
        relationships.append(f"pets: {', '.join(pets) if isinstance(pets, list) else pets}")

    # Get current situation
    situation = personal_life.get("current_situation", "")
    activities = personal_life.get("typical_activities", [])
    dynamics = personal_life.get("relationship_dynamics", "")

    return {
        "relationships": relationships,
        "spouse": spouse,
        "children": children,
        "pets": pets,
        "situation": situation,
        "activities": activities,
        "dynamics": dynamics,
        "has_family": bool(spouse or children),
        "has_pets": bool(pets),
    }


def get_all_personas() -> List[Dict[str, Any]]:
    """Get all personas from create-persona skill."""
    create_persona_path = Path(os.environ.get("CREATE_PERSONA_SKILL", str(Path.home() / "workspace/streamdeck/.claude/skills/create-persona")))

    try:
        result = subprocess.run(
            ["./run.sh", "list", "--json"],
            cwd=str(create_persona_path),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Error listing personas: {e}")

    return []


def get_daily_episodes(persona_name: str, date: datetime = None) -> List[Dict[str, Any]]:
    """Query episodic-archiver for persona's interactions on a given day."""
    if date is None:
        date = datetime.now()

    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    try:
        db = get_db()
        query = """
        FOR doc IN agent_conversations
            FILTER doc.timestamp >= @start AND doc.timestamp < @end
            FILTER CONTAINS(LOWER(doc.content), LOWER(@persona))
                OR doc.persona == @persona
                OR doc.agent == @persona
            SORT doc.timestamp ASC
            RETURN doc
        """

        cursor = db.aql.execute(
            query,
            bind_vars={
                "start": start_of_day.isoformat(),
                "end": end_of_day.isoformat(),
                "persona": persona_name.lower()
            }
        )
        return list(cursor)
    except Exception as e:
        print(f"Error querying episodes: {e}")
        return []


def get_recent_journal(persona_name: str, days: int = 7) -> List[Dict[str, Any]]:
    """Get recent journal entries for short-term continuity (rolling window)."""
    try:
        db = get_db()

        query = """
        FOR doc IN persona_journals
            FILTER doc.persona == @persona
            SORT doc.date DESC
            LIMIT @limit
            RETURN doc
        """

        cursor = db.aql.execute(
            query,
            bind_vars={"persona": persona_name, "limit": days}
        )
        return list(cursor)
    except Exception:
        return []


def get_semantic_memories(persona_name: str, current_mood: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Get older journal entries that are thematically related to current mood.

    Humans don't experience reality sequentially - an event from years ago
    can influence today's journal entry.
    """
    try:
        db = get_db()

        # Find entries with similar mood or bridge attributes
        mood_to_bridges = {
            "frustrated": ["Fragility", "Corruption"],
            "anxious": ["Fragility", "Stealth"],
            "weary": ["Fragility", "Resilience"],
            "melancholic": ["Fragility", "Corruption"],
            "restless": ["Stealth", "Fragility"],
            "energized": ["Resilience", "Precision"],
            "satisfied": ["Resilience", "Loyalty"],
            "hopeful": ["Resilience", "Loyalty"],
            "focused": ["Precision", "Resilience"],
        }

        related_bridges = mood_to_bridges.get(current_mood, ["Resilience"])

        # Query for older entries (skip recent 14 days) with similar bridges
        query = """
        FOR doc IN persona_journals
            FILTER doc.persona == @persona
            FILTER DATE_DIFF(doc.date, DATE_ISO8601(DATE_NOW()), "day") > 14
            FILTER doc.mood == @mood
                OR @bridge1 IN ATTRIBUTES(doc.bridges)
                OR @bridge2 IN ATTRIBUTES(doc.bridges)
            SORT RAND()
            LIMIT @limit
            RETURN {
                date: doc.date,
                mood: doc.mood,
                reflection: doc.reflection,
                imagined_experiences: SUBSTRING(doc.imagined_experiences, 0, 300)
            }
        """

        cursor = db.aql.execute(
            query,
            bind_vars={
                "persona": persona_name,
                "mood": current_mood,
                "bridge1": related_bridges[0] if related_bridges else "Resilience",
                "bridge2": related_bridges[1] if len(related_bridges) > 1 else related_bridges[0],
                "limit": limit
            }
        )
        return list(cursor)
    except Exception:
        return []


def get_random_old_memory(persona_name: str) -> Optional[Dict[str, Any]]:
    """Randomly surface an old memory - like humans do unpredictably.

    Sometimes a random old experience just pops into your head.
    """
    # 30% chance of surfacing a random old memory
    if random.random() > 0.3:
        return None

    try:
        db = get_db()

        query = """
        FOR doc IN persona_journals
            FILTER doc.persona == @persona
            FILTER DATE_DIFF(doc.date, DATE_ISO8601(DATE_NOW()), "day") > 30
            SORT RAND()
            LIMIT 1
            RETURN {
                date: doc.date,
                mood: doc.mood,
                snippet: SUBSTRING(doc.imagined_experiences, 0, 200),
                how_long_ago: CONCAT(
                    FLOOR(DATE_DIFF(doc.date, DATE_ISO8601(DATE_NOW()), "day") / 30),
                    " months ago"
                )
            }
        """

        cursor = db.aql.execute(query, bind_vars={"persona": persona_name})
        results = list(cursor)
        return results[0] if results else None
    except Exception:
        return None


def compress_old_entries(entries: List[Dict[str, Any]]) -> str:
    """Create compressed summaries of older entries.

    Older memories are fuzzier - we don't remember every detail,
    just the emotional essence.
    """
    if not entries:
        return ""

    summaries = []
    for entry in entries:
        date = entry.get("date", "unknown date")
        mood = entry.get("mood", "unknown")
        snippet = entry.get("reflection", entry.get("snippet", ""))[:100]

        # Fuzzy time descriptions like humans use
        try:
            entry_date = datetime.strptime(date, "%Y-%m-%d")
            days_ago = (datetime.now() - entry_date).days

            if days_ago < 30:
                time_desc = "a few weeks ago"
            elif days_ago < 90:
                time_desc = "a couple months back"
            elif days_ago < 180:
                time_desc = "earlier this year" if datetime.now().month > 6 else "last year sometime"
            else:
                time_desc = "a while back"
        except Exception:
            time_desc = "sometime before"

        summaries.append(f"- {time_desc}: felt {mood}... {snippet}...")

    return "\n".join(summaries)


def extract_taxonomy_tags(journal: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Federated Taxonomy tags from journal for multi-hop recall.

    Uses Behavioral collection vocabulary since journals are about
    psychology, mood, and emotional states.

    Includes intensity calculation for weighted recall.
    """

    mood = journal.get("mood", "neutral")
    energy = journal.get("energy_label", "moderate")
    intensity_data = journal.get("intensity_data", {})

    # Bridge attributes based on mood/content
    # Scale by intensity so high-intensity entries have stronger bridges
    intensity = intensity_data.get("intensity", 0.5)

    # Map moods to bridge attributes
    mood_to_bridges = {
        "frustrated": {"Fragility": 0.7, "Corruption": 0.3},
        "anxious": {"Fragility": 0.8, "Stealth": 0.2},
        "weary": {"Fragility": 0.6, "Resilience": 0.3},
        "melancholic": {"Fragility": 0.7, "Corruption": 0.2},
        "restless": {"Stealth": 0.4, "Fragility": 0.4},
        "energized": {"Resilience": 0.7, "Precision": 0.4},
        "satisfied": {"Resilience": 0.6, "Loyalty": 0.4},
        "hopeful": {"Resilience": 0.7, "Loyalty": 0.3},
        "focused": {"Precision": 0.8, "Resilience": 0.3},
        "playful": {"Stealth": 0.3, "Resilience": 0.4},
        "curious": {"Precision": 0.5, "Resilience": 0.4},
        "contemplative": {"Precision": 0.4, "Fragility": 0.3},
    }

    base_bridges = mood_to_bridges.get(mood, {"Resilience": 0.5})

    # Scale bridges by intensity
    bridges = {k: v * intensity for k, v in base_bridges.items()}

    # Map intensity to taxonomy vocabulary
    intensity_to_taxonomy = {
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
    }
    if intensity >= 0.9:
        emotional_intensity = "Extreme"
    else:
        emotional_intensity = intensity_to_taxonomy.get(
            intensity_data.get("intensity_label", "moderate"),
            "Moderate"
        )

    # Behavioral taxonomy dimensions
    behavioral_tags = {
        "function": "Regulation",  # Journals are emotional regulation
        "domain": "Clinical" if mood in ["anxious", "melancholic"] else "Social",
        "thematic_weight": intensity_data.get("thematic_weight", _map_mood_to_theme(mood)),
        "perspective": "Individual",
        "emotional_intensity": emotional_intensity,  # New intensity field
    }

    # Keywords for search
    keywords = [
        journal.get("persona", ""),
        mood,
        energy,
        intensity_data.get("intensity_label", "moderate"),
        journal.get("time_context", {}).get("day_of_week", ""),
        journal.get("time_context", {}).get("season", ""),
    ]

    return {
        "bridges": bridges,
        "collection": "behavioral",
        "behavioral_tags": behavioral_tags,
        "intensity": intensity,
        "intensity_label": intensity_data.get("intensity_label", "moderate"),
        "keywords": [k for k in keywords if k],
        "document_type": "persona_journal",
    }


def _map_mood_to_theme(mood: str) -> str:
    """Map mood to behavioral thematic weight."""
    mood_themes = {
        "frustrated": "Aggression",
        "anxious": "Stress",
        "weary": "Stress",
        "melancholic": "Emotion",
        "restless": "Stress",
        "energized": "Cognition",
        "satisfied": "Cooperation",
        "hopeful": "Emotion",
        "focused": "Cognition",
        "playful": "Cooperation",
        "curious": "Cognition",
        "contemplative": "Emotion",
    }
    return mood_themes.get(mood, "Emotion")


def store_journal(journal: Dict[str, Any]) -> bool:
    """Store journal entry to ArangoDB with taxonomy tags for multi-hop recall."""
    try:
        db = get_db()

        # Ensure collection exists
        if not db.has_collection("persona_journals"):
            db.create_collection("persona_journals")

        collection = db.collection("persona_journals")

        # Extract and add taxonomy tags
        taxonomy = extract_taxonomy_tags(journal)
        journal["taxonomy"] = taxonomy
        journal["bridges"] = taxonomy["bridges"]
        journal["keywords"] = taxonomy["keywords"]

        # Check for existing entry today
        existing = list(db.aql.execute(
            """
            FOR doc IN persona_journals
                FILTER doc.persona == @persona AND doc.date == @date
                RETURN doc
            """,
            bind_vars={"persona": journal["persona"], "date": journal["date"]}
        ))

        if existing:
            # Update existing
            collection.update({"_key": existing[0]["_key"]}, journal)
            print(f"  Updated existing journal for {journal['persona']} (bridges: {list(taxonomy['bridges'].keys())})")
        else:
            # Insert new
            collection.insert(journal)
            print(f"  Created new journal for {journal['persona']} (bridges: {list(taxonomy['bridges'].keys())})")

        # Create graph edges for multi-hop traversal
        _create_taxonomy_edges(db, journal)

        return True
    except Exception as e:
        print(f"  Error storing journal: {e}")
        return False


def _create_taxonomy_edges(db, journal: Dict[str, Any]) -> None:
    """Create graph edges linking journal to taxonomy nodes for multi-hop traversal."""
    try:
        # Ensure edge collection exists
        if not db.has_collection("taxonomy_edges"):
            db.create_collection("taxonomy_edges", edge=True)

        edges = db.collection("taxonomy_edges")
        journal_key = f"persona_journals/{journal['persona']}_{journal['date']}"

        # Create edges for each bridge attribute
        for bridge, weight in journal.get("bridges", {}).items():
            edge = {
                "_from": journal_key,
                "_to": f"taxonomy_bridges/{bridge}",
                "weight": weight,
                "type": "has_bridge",
                "source": "persona_journal",
                "persona": journal["persona"],
                "date": journal["date"],
            }

            # Upsert edge
            try:
                edges.insert(edge)
            except Exception as e:
                logger.debug("journal edge insert skipped (may already exist): {}", e)

        # Create edge to persona node
        persona_edge = {
            "_from": journal_key,
            "_to": f"personas/{journal['persona']}",
            "type": "journal_of",
            "date": journal["date"],
            "mood": journal.get("mood", "unknown"),
        }
        try:
            edges.insert(persona_edge)
        except Exception as e:
            logger.debug("edges failed: {}", e)

    except Exception as e:
        print(f"  Warning: Could not create taxonomy edges: {e}")


def get_persona_mood(persona_name: str) -> Optional[Dict[str, Any]]:
    """Get current mood state for a persona (for query-time injection)."""
    try:
        db = get_db()

        # Get most recent journal
        cursor = db.aql.execute(
            """
            FOR doc IN persona_journals
                FILTER doc.persona == @persona
                SORT doc.timestamp DESC
                LIMIT 1
                RETURN {
                    mood: doc.mood,
                    energy: doc.energy,
                    energy_label: doc.energy_label,
                    date: doc.date,
                    reflection: doc.reflection,
                    time_context: doc.time_context
                }
            """,
            bind_vars={"persona": persona_name}
        )
        results = list(cursor)
        return results[0] if results else None
    except Exception:
        return None
