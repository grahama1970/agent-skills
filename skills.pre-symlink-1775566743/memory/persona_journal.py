#!/usr/bin/env python3
"""
Persona Journal Generator - Dynamic mood and experience tracking.

Creates nightly journal entries for each persona based on:
1. Real interactions from episodic-archiver
2. Imagined experiences based on persona profile
3. Time/place dependent mood states
4. Accumulated frustrations and satisfactions

The journal influences future response "color" - making personas
feel alive, dynamic, and contextually aware.

This is the assembler module. Implementation is split across:
- persona_journal_mood.py: Constants, time helpers, mood/intensity calculation
- persona_journal_memory.py: DB access, episode queries, storage, taxonomy
- persona_journal_generation.py: LLM calls, imagined experiences, journal assembly
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True))

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SKILLS_DIR.parent

# Re-export all public names from sub-modules for backward compatibility
from persona_journal_mood import (  # noqa: F401, E402
    MOOD_STATES,
    ENERGY_LEVELS,
    TIME_MOOD_MODIFIERS,
    DAY_MOOD_MODIFIERS,
    SEASON_MODIFIERS,
    get_current_season,
    get_time_period,
    calculate_mood_state,
    calculate_intensity,
)

from persona_journal_memory import (  # noqa: F401, E402
    get_db,
    get_persona_profile,
    get_current_events,
    get_persona_daily_life,
    get_all_personas,
    get_daily_episodes,
    get_recent_journal,
    get_semantic_memories,
    get_random_old_memory,
    compress_old_entries,
    extract_taxonomy_tags,
    store_journal,
    get_persona_mood,
)

from persona_journal_generation import (  # noqa: F401, E402
    call_llm,
    generate_imagined_experiences,
    generate_journal_entry,
)

# Memory integration (graceful degradation)
_memory_recall_recent_journals = None
_memory_learn_journal_entry = None
try:
    _journal_skill_dir = SKILLS_DIR / "persona-journal"
    if _journal_skill_dir.exists():
        import importlib.util as _ilu
        _mi_spec = _ilu.spec_from_file_location(
            "persona_journal_memory_integration",
            _journal_skill_dir / "memory_integration.py",
        )
        if _mi_spec and _mi_spec.loader:
            _mi_mod = _ilu.module_from_spec(_mi_spec)
            _mi_spec.loader.exec_module(_mi_mod)
            _memory_recall_recent_journals = getattr(_mi_mod, "recall_recent_journals", None)
            _memory_learn_journal_entry = getattr(_mi_mod, "learn_journal_entry", None)
except Exception as _e:
    pass  # Graceful degradation — memory integration optional


def generate_all_journals(dry_run: bool = False) -> Dict[str, Any]:
    """Generate journal entries for ALL personas."""

    print("=" * 60)
    print("PERSONA JOURNAL GENERATOR - Nightly Run")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Get all personas
    personas = get_all_personas()

    if not personas:
        print("No personas found!")
        return {"success": False, "error": "No personas found"}

    print(f"\nFound {len(personas)} personas to process\n")

    results = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "journals": [],
    }

    for persona in personas:
        persona_name = persona.get("name", "Unknown")
        print(f"Processing: {persona_name}")

        try:
            # Get daily episodes
            episodes = get_daily_episodes(persona_name)
            print(f"  Found {len(episodes)} interactions today")

            # Get recent journals for continuity
            recent = get_recent_journal(persona_name, days=3)
            print(f"  Found {len(recent)} recent journal entries")

            # Memory pre-hook: recall prior journals for cross-session continuity
            if _memory_recall_recent_journals:
                try:
                    prior_context = _memory_recall_recent_journals(persona_name, k=5)
                    if prior_context:
                        print(f"  Recalled {len(prior_context)} chars of prior journal context from memory")
                except Exception as mem_err:
                    print(f"  Memory recall skipped: {mem_err}")

            # Calculate mood
            mood_state = calculate_mood_state(persona, episodes, recent)
            print(f"  Calculated mood: {mood_state['mood']} ({mood_state['energy_label']} energy)")

            # Generate journal
            journal = generate_journal_entry(persona, episodes, recent, mood_state)

            if dry_run:
                print(f"\n--- DRY RUN - Journal Preview for {persona_name} ---")
                print(journal["full_entry"][:1000] + "...\n")
            else:
                # Store to database
                if store_journal(journal):
                    results["success"] += 1

                    # Memory post-hook: learn journal entry for cross-session recall
                    if _memory_learn_journal_entry:
                        try:
                            learned = _memory_learn_journal_entry(
                                persona_id=persona_name,
                                date=journal.get("date", datetime.now().strftime("%Y-%m-%d")),
                                mood=mood_state.get("mood", "neutral"),
                                topics=journal.get("topics", []),
                                key_events=journal.get("key_events", []),
                                reflection=journal.get("reflection", ""),
                                energy_label=mood_state.get("energy_label", ""),
                            )
                            if learned:
                                print(f"  Learned {len(learned)} entries to memory")
                        except Exception as mem_err:
                            print(f"  Memory learn skipped: {mem_err}")
                else:
                    results["failed"] += 1

            results["journals"].append({
                "persona": persona_name,
                "mood": mood_state["mood"],
                "energy": mood_state["energy_label"],
            })
            results["processed"] += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            results["failed"] += 1

        print()

    print("=" * 60)
    print(f"COMPLETE: {results['processed']} processed, {results['success']} success, {results['failed']} failed")
    print("=" * 60)

    return results


def register_nightly_job() -> bool:
    """Register the journal generator as a nightly scheduled job."""
    scheduler_path = SKILLS_DIR / "scheduler"

    if not scheduler_path.exists():
        print(f"Scheduler skill not found at {scheduler_path}")
        return False

    # Journal generation command
    journal_cmd = f"python3 {SCRIPT_DIR / 'persona_journal.py'} generate"

    try:
        result = subprocess.run(
            [
                "./run.sh", "register",
                "--name", "persona-journals-nightly",
                "--cron", "0 3 * * *",  # 3 AM daily
                "--command", journal_cmd,
                "--description", "Generate daily journal entries for all personas",
                "--workdir", str(SCRIPT_DIR),
            ],
            cwd=str(scheduler_path),
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0:
            print("Registered nightly journal job: persona-journals-nightly")
            print("Schedule: 3:00 AM daily")
            return True
        else:
            print(f"Failed to register job: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error registering job: {e}")
        return False


def get_mood_for_response(persona_name: str) -> str:
    """Get mood context string to inject into persona responses.

    Call this BEFORE generating a persona response to get their current
    emotional state based on their journal.
    """
    mood = get_persona_mood(persona_name)

    if not mood:
        return ""

    # Build mood injection string
    mood_str = mood.get("mood", "neutral")
    energy = mood.get("energy_label", "moderate")
    reflection = mood.get("reflection", "")
    date = mood.get("date", "")

    # Only include recent moods (within 2 days)
    if date:
        try:
            journal_date = datetime.strptime(date, "%Y-%m-%d")
            days_old = (datetime.now() - journal_date).days
            if days_old > 2:
                return f"[Mood: {mood_str}, Energy: {energy} - journal is {days_old} days old]"
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    context = f"""[CURRENT EMOTIONAL STATE for {persona_name}]
Mood: {mood_str}
Energy: {energy}
Recent reflection: {reflection[:200] if reflection else 'none recorded'}
[This should subtly color {persona_name}'s responses - not explicitly mentioned, but felt in tone]"""

    return context


import typer

app = typer.Typer(help="Persona Journal Generator")


@app.command()
def generate(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without storing"),
    persona: Optional[str] = typer.Option(None, help="Generate for specific persona only"),
):
    if persona:
        p = get_persona_profile(persona)
        episodes = get_daily_episodes(persona)
        recent = get_recent_journal(persona)
        mood_state = calculate_mood_state(p, episodes, recent)
        journal = generate_journal_entry(p, episodes, recent, mood_state)

        if dry_run:
            print(journal["full_entry"])
        else:
            store_journal(journal)
            print(f"Journal stored for {persona}")
    else:
        generate_all_journals(dry_run=dry_run)


@app.command()
def mood(
    persona: str = typer.Argument(..., help="Persona name"),
    for_response: bool = typer.Option(False, "--for-response", help="Format for response injection"),
):
    if for_response:
        context = get_mood_for_response(persona)
        print(context)
    else:
        m = get_persona_mood(persona)
        if m:
            print(json.dumps(m, indent=2))
        else:
            print(f"No mood data for {persona}")


@app.command("list")
def list_journals(
    persona: Optional[str] = typer.Option(None, help="Filter by persona"),
    days: int = typer.Option(7, help="Number of days"),
):
    try:
        db = get_db()
        query = """
        FOR doc IN persona_journals
            FILTER @persona == null OR doc.persona == @persona
            SORT doc.timestamp DESC
            LIMIT @limit
            RETURN {
                persona: doc.persona,
                date: doc.date,
                mood: doc.mood,
                energy: doc.energy_label
            }
        """
        cursor = db.aql.execute(
            query,
            bind_vars={
                "persona": persona,
                "limit": days * len(get_all_personas()) if not persona else days
            }
        )
        for entry in cursor:
            print(f"{entry['date']} | {entry['persona']:20} | {entry['mood']:15} | {entry['energy']}")
    except Exception as e:
        print(f"Error: {e}")


@app.command()
def schedule():
    register_nightly_job()


if __name__ == "__main__":
    app()
