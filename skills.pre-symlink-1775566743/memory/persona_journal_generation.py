"""
Persona Journal - Generation Module

LLM integration, imagined experience generation, journal entry assembly,
and reflection synthesis.
"""

import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from persona_journal_mood import calculate_intensity
from persona_journal_memory import (
    get_current_events,
    get_persona_daily_life,
    get_semantic_memories,
    get_random_old_memory,
    compress_old_entries,
)

# Ensure scillm is importable
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR / "scillm") not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR / "scillm"))


def call_llm(prompt: str, system: str = "") -> str:
    """Call LLM for journal generation via scillm."""
    try:
        from batch import quick_completion
        return quick_completion(
            prompt,
            system=system or None,
            temperature=0.8,
            max_tokens=1500,
            timeout=60,
        )
    except Exception as e:
        return f"[LLM error: {e}]"


def generate_imagined_experiences(
    persona: Dict[str, Any],
    mood_state: Dict[str, Any],
    episodes: List[Dict[str, Any]],
    semantic_memories: str = "",
    random_memory: str = "",
    current_events: str = "",
    daily_life: Dict[str, Any] = None
) -> str:
    """Generate imagined experiences for times when persona wasn't interacting.

    Based on Pennebaker's expressive writing research - entries should be:
    - Variable in length (sometimes 2 sentences, sometimes a paragraph)
    - Sometimes boring/mundane, sometimes emotionally intense
    - Scattered and emotional when mood is low
    - More coherent when mood is good
    - Real human stream-of-consciousness, not polished essays
    - Influenced by past memories (semantic + random)
    - Aware of events from THEIR era (via dogpile)
    - Include personal life (pets, children, spouse, travel, war)

    CRUCIAL: Personas live in THEIR time period, not ours.
    A 1956 persona experiences 1956. Their temporal_setting is their reality.
    """
    if daily_life is None:
        daily_life = {}

    persona_name = persona.get("name", "Unknown")
    role = persona.get("role", "")
    domain = persona.get("domain", "")
    expertise = persona.get("expertise", [])
    goals = persona.get("goals", [])
    quirks = persona.get("quirks", [])

    # Get persona's temporal setting for date context
    temporal_setting = persona.get("temporal_setting", {})
    persona_year = temporal_setting.get("year", datetime.now().year)
    persona_era = temporal_setting.get("era", "AD")
    persona_location = temporal_setting.get("location", "")

    # Build context
    expertise_str = ", ".join(expertise[:3]) if expertise else "general skills"
    goals_str = ", ".join(goals[:2]) if goals else "personal growth"
    quirks_str = ", ".join(quirks[:2]) if quirks else "unique habits"

    # Randomize entry style based on mood and random chance
    entry_styles = [
        "mundane",      # Just boring day stuff
        "scattered",    # Jumping between topics, fragmented
        "intense",      # Deep emotional processing
        "brief",        # Just a few sentences
        "reflective",   # Thoughtful but calm
        "venting",      # Frustrated stream of consciousness
    ]

    # Weight style by mood
    if mood_state["mood"] in ["frustrated", "anxious", "restless"]:
        style_weights = [0.1, 0.3, 0.2, 0.1, 0.1, 0.2]
    elif mood_state["mood"] in ["weary", "melancholic", "depleted"]:
        style_weights = [0.2, 0.2, 0.2, 0.2, 0.1, 0.1]
    elif mood_state["mood"] in ["satisfied", "hopeful", "energized"]:
        style_weights = [0.3, 0.1, 0.1, 0.2, 0.2, 0.1]
    else:
        style_weights = [0.2, 0.2, 0.15, 0.15, 0.2, 0.1]

    style = random.choices(entry_styles, weights=style_weights, k=1)[0]

    style_instructions = {
        "mundane": "Write a BORING entry. Just mundane stuff - what they ate, small tasks, nothing special happened. 2-4 sentences max. Real life is often uneventful.",
        "scattered": "Write SCATTERED, jumping between unfinished thoughts. Use ellipses... trail off mid-sentence sometimes. Fragments okay. Like someone tired writing before bed.",
        "intense": "Write something EMOTIONALLY RAW. A real feeling surfaced - frustration, loneliness, doubt, or unexpected joy. Let it be messy and honest.",
        "brief": "Write VERY SHORT. Just 1-3 sentences. Sometimes you just don't have much to say. That's okay.",
        "reflective": "Write a calm REFLECTION. Something clicked today or they're processing something gently. Not dramatic, just quietly thoughtful.",
        "venting": "Write a VENT. Something annoyed them. Let it ramble a bit. Don't resolve it neatly - real venting doesn't tie up with a bow.",
    }

    # Build memory context (humans recall non-linearly)
    memory_context = ""
    if semantic_memories:
        memory_context += f"\nOLD MEMORIES SURFACING (related to current mood):\n{semantic_memories}\n"
    if random_memory:
        memory_context += f"\nRANDOM MEMORY POPPING UP:{random_memory}\n"
    if current_events:
        memory_context += f"\nEVENTS FROM YOUR WORLD (may or may not mention):\n{current_events}\n"

    # Build personal life context
    personal_context = ""
    if daily_life:
        life_details = []
        if daily_life.get("spouse"):
            life_details.append(f"spouse: {daily_life['spouse']}")
        if daily_life.get("children"):
            kids = daily_life["children"]
            life_details.append(f"children: {', '.join(kids) if isinstance(kids, list) else kids}")
        if daily_life.get("pets"):
            pets = daily_life["pets"]
            life_details.append(f"pets: {', '.join(pets) if isinstance(pets, list) else pets}")
        if daily_life.get("situation"):
            life_details.append(f"current situation: {daily_life['situation']}")
        if daily_life.get("dynamics"):
            life_details.append(f"relationship dynamics: {daily_life['dynamics']}")
        if life_details:
            personal_context = f"\nPERSONAL LIFE (weave naturally if relevant):\n" + "\n".join(f"- {d}" for d in life_details) + "\n"

    # Build date string based on persona's era
    now = datetime.now()
    if persona_year == now.year and persona_era in ["AD", "CE"]:
        date_context = f"{now.strftime('%B %d, %Y')}"
    else:
        era_suffix = f" {persona_era}" if persona_era in ["BC", "BCE"] else ""
        date_context = f"{now.strftime('%B %d')}, {persona_year}{era_suffix}"
        if persona_location:
            date_context += f" in {persona_location}"

    prompt = f"""Write a journal entry for {persona_name}.

STYLE: {style.upper()}
{style_instructions[style]}

PERSONA: {role or 'person'} interested in {domain or 'various things'}
MOOD: {mood_state['mood']} | ENERGY: {mood_state['energy_label']}
TIME: {mood_state['day_of_week']} {mood_state['time_period']}, {mood_state['season']}
DATE IN YOUR WORLD: {date_context}
INTERACTIONS TODAY: {len(episodes)} recorded
{personal_context}{memory_context}
IMPORTANT: This should read like a REAL person's journal:
- Imperfect grammar is fine
- Trailing thoughts...
- Sometimes just lists of what happened
- No need to wrap everything up nicely
- Can mention a flaw or insecurity casually
- Can be boring! Real journals often are
- If old memories surface, weave them in naturally (humans think non-linearly)
- A memory from months ago might connect to something today
- You live in YOUR world ({date_context}) - not some other time
- Personal life (family, pets, travel, work) may naturally appear
- If world events are provided, you may react to them (or ignore them)

Write in first person as {persona_name}."""

    system = """You are writing a private journal entry. NOT for an audience.
This is stream-of-consciousness writing for emotional processing.
Based on Pennebaker's research: expressive writing should be
unpolished, variable, sometimes mundane, sometimes raw.
NEVER write like a blog post for others to read."""

    return call_llm(prompt, system)


def generate_journal_entry(
    persona: Dict[str, Any],
    episodes: List[Dict[str, Any]],
    recent_journals: List[Dict[str, Any]],
    mood_state: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate complete daily journal entry.

    Memory retrieval follows human patterns:
    1. Recent entries (rolling 7-day window) for continuity
    2. Semantic memories from older entries related to current mood
    3. Random old memories that surface unpredictably
    """

    persona_name = persona.get("name", "Unknown")

    # Summarize real interactions
    interaction_summary = ""
    if episodes:
        ep_summaries = []
        for ep in episodes[:10]:  # Limit to 10
            content = ep.get("content", "")[:200]
            category = ep.get("category", "unknown")
            ep_summaries.append(f"- [{category}] {content}...")
        interaction_summary = "\n".join(ep_summaries)
    else:
        interaction_summary = "No recorded interactions today."

    # Get semantic memories from the past (related to current mood)
    semantic_memories = get_semantic_memories(persona_name, mood_state["mood"])
    semantic_summary = compress_old_entries(semantic_memories) if semantic_memories else ""

    # Randomly surface an old memory (like humans do)
    random_memory = get_random_old_memory(persona_name)
    random_memory_text = ""
    if random_memory:
        random_memory_text = f"\n[Random memory surfaced: {random_memory.get('how_long_ago', 'long ago')} - {random_memory.get('snippet', '')}]"

    # Calculate emotional intensity for taxonomy tagging
    intensity_data = calculate_intensity(mood_state, episodes)

    # Get current events from dogpile (date-specific for persona's era)
    current_events = get_current_events(persona)
    if current_events:
        print(f"  Found events for {persona_name}'s world")

    # Get personal life context (pets, children, spouse, travel, war)
    daily_life = get_persona_daily_life(persona)
    if daily_life.get("has_family") or daily_life.get("has_pets"):
        print(f"  Personal life context: {len(daily_life.get('relationships', []))} relationships")

    # Get imagined experiences - with memory, world events, AND personal life
    imagined = generate_imagined_experiences(
        persona, mood_state, episodes,
        semantic_memories=semantic_summary,
        random_memory=random_memory_text,
        current_events=current_events,
        daily_life=daily_life
    )

    # Generate reflective synthesis - keep it SHORT and human
    # Sometimes skip reflection entirely (like real people do)
    skip_reflection = random.random() < 0.2  # 20% chance of no reflection

    if skip_reflection:
        reflection = random.choice([
            "too tired to write more",
            "...",
            "whatever. bed.",
            "that's it for today",
            "",
            "done",
        ])
    else:
        synthesis_prompt = f"""Write a VERY BRIEF end-of-day thought for {persona_name}.

MOOD: {mood_state['mood']} | ENERGY: {mood_state['energy_label']}
SATISFYING: {mood_state['satisfying_interactions']} | FRUSTRATING: {mood_state['frustrating_interactions']}

1-3 sentences MAX. Like a real person jotting a final thought before sleep.
Can be:
- A worry that won't go away
- Something they're looking forward to (or dreading) tomorrow
- A random observation
- Just "going to try to sleep"
- A question with no answer

NOT a summary of the day. Just a final thought. Messy is fine."""

        reflection = call_llm(synthesis_prompt)

    # Build full journal entry
    now = datetime.now()
    journal = {
        "persona": persona_name,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.isoformat(),
        "mood": mood_state["mood"],
        "energy": mood_state["energy"],
        "energy_label": mood_state["energy_label"],
        "time_context": {
            "time_period": mood_state["time_period"],
            "day_of_week": mood_state["day_of_week"],
            "season": mood_state["season"],
        },
        "interaction_count": len(episodes),
        "satisfying_count": mood_state["satisfying_interactions"],
        "frustrating_count": mood_state["frustrating_interactions"],
        "imagined_experiences": imagined,
        "reflection": reflection,
        "mood_continuity": mood_state.get("mood_continuity", []),
        # Intensity data for taxonomy tagging (affects weight in multi-hop traversal)
        "intensity_data": intensity_data,
        "emotional_intensity": intensity_data.get("intensity_label", "moderate"),
        # Memories that influenced this entry (non-sequential recall)
        "semantic_memories_used": len(semantic_memories) if semantic_memories else 0,
        "random_memory_surfaced": random_memory is not None,
        # Real-world context (persona exists in present day)
        "current_events_fetched": bool(current_events),
        "full_entry": f"""# {persona_name}'s Journal - {now.strftime('%A, %B %d, %Y')}

**Mood:** {mood_state['mood']} | **Energy:** {mood_state['energy_label']}
**Context:** {mood_state['time_period']} on {mood_state['day_of_week']}, {mood_state['season']}

## What Happened Today

{imagined}

## Real Interactions

{interaction_summary if episodes else "_Quiet day - no recorded conversations_"}

## Evening Reflection

{reflection}

---
_Satisfying moments: {mood_state['satisfying_interactions']} | Frustrating moments: {mood_state['frustrating_interactions']}_
""",
    }

    return journal
