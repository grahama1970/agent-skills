"""
Movie Ingest Skill - Agent Integrations
Dogpile search, agent-inbox messaging, and book recommendation logic.
Split from agent.py to keep modules under 800 lines.
"""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from config import (
    VALID_EMOTIONS,
    HORUS_ARCHETYPE_MAP,
    DOGPILE_DIR,
)
from loguru import logger

console = Console()


# -----------------------------------------------------------------------------
# Dogpile Integration
# -----------------------------------------------------------------------------
def run_dogpile(query: str, preset: str = "movie_scenes", timeout_sec: int = 300) -> Dict[str, Any]:
    """
    Run dogpile search and return results.

    Args:
        query: Search query string
        preset: Dogpile preset to use (default: movie_scenes)
        timeout_sec: Timeout in seconds (default: 300)

    Returns:
        Dict with either results or error information
    """
    dogpile_script = DOGPILE_DIR / "dogpile.py"

    if not dogpile_script.exists():
        return {"error": f"Dogpile not found at {dogpile_script}", "status": "not_found"}

    cmd = [
        sys.executable, str(dogpile_script),
        "search", query,
        "--preset", preset,
        "--json"
    ]

    proc = None
    try:
        # Use Popen for better process control
        # start_new_session=True ensures child process is in its own session
        # so it can be cleanly killed without affecting parent
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(DOGPILE_DIR),
            start_new_session=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            # Attempt graceful termination of the process group, then force kill if needed
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception as e:
                    logger.debug("proc failed: {}", e)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
            return {
                "error": f"Dogpile search timed out after {timeout_sec}s",
                "status": "timeout",
                "query": query
            }

        if proc.returncode == 0:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"raw_output": stdout, "status": "success", "query": query}
        else:
            return {
                "error": stderr or "Unknown error",
                "status": "failed",
                "returncode": proc.returncode,
                "query": query
            }
    except FileNotFoundError:
        return {"error": f"Python interpreter not found: {sys.executable}", "status": "exception"}
    except Exception as e:
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception as e:
                    logger.debug("proc failed: {}", e)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
        return {"error": str(e), "status": "exception", "query": query}


# -----------------------------------------------------------------------------
# Agent Inbox Integration
# -----------------------------------------------------------------------------
def send_to_inbox(
    to_project: str,
    message: str,
    message_type: str = "request",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Send a message via agent-inbox."""
    skills_dir = Path(__file__).resolve().parents[1]
    inbox_script = skills_dir / "agent-inbox" / "inbox.py"

    if not inbox_script.exists():
        console.print(f"[yellow]Agent inbox not found at {inbox_script}[/yellow]")
        return False

    full_message = message
    if metadata:
        full_message = f"{message}\n\n---\nMetadata: {json.dumps(metadata)}"

    cmd = [
        sys.executable, str(inbox_script),
        "send",
        "--to", to_project,
        "--type", message_type,
        full_message
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except Exception as e:
        console.print(f"[red]Failed to send to inbox: {e}[/red]")
        return False


# -----------------------------------------------------------------------------
# Book-Movie Mappings (static data)
# -----------------------------------------------------------------------------
BOOK_MOVIE_MAP: Dict[str, List[str]] = {
    "dune": ["Dune - Frank Herbert", "Dune Messiah - Frank Herbert"],
    "there will be blood": ["Oil! - Upton Sinclair"],
    "the godfather": ["The Godfather - Mario Puzo"],
    "apocalypse now": ["Heart of Darkness - Joseph Conrad"],
    "gladiator": ["Those About to Die - Daniel Mannix"],
    "blade runner": ["Do Androids Dream of Electric Sheep? - Philip K. Dick"],
    "no country for old men": ["No Country for Old Men - Cormac McCarthy", "Blood Meridian - Cormac McCarthy"],
    "the road": ["The Road - Cormac McCarthy"],
    "sicario": ["Sicario: A True Story - Barry Seal"],
    "fury": ["Death Traps - Belton Y. Cooper", "With the Old Breed - Eugene Sledge"],
    "saving private ryan": ["Citizen Soldiers - Stephen Ambrose", "Band of Brothers - Stephen Ambrose"],
    "band of brothers": ["Band of Brothers - Stephen Ambrose"],
    "the last samurai": ["The Last Samurai - Helen DeWitt", "Shogun - James Clavell"],
}

EMOTION_BOOKS: Dict[str, List[str]] = {
    "rage": [
        "Blood Meridian - Cormac McCarthy",
        "American Psycho - Bret Easton Ellis",
        "The Iliad - Homer",
    ],
    "anger": [
        "The Godfather - Mario Puzo",
        "Crime and Punishment - Fyodor Dostoevsky",
        "The Count of Monte Cristo - Alexandre Dumas",
    ],
    "sorrow": [
        "All Quiet on the Western Front - Erich Maria Remarque",
        "A Farewell to Arms - Ernest Hemingway",
        "The Things They Carried - Tim O'Brien",
    ],
    "regret": [
        "The Great Gatsby - F. Scott Fitzgerald",
        "Atonement - Ian McEwan",
        "Never Let Me Go - Kazuo Ishiguro",
    ],
    "camaraderie": [
        "Band of Brothers - Stephen Ambrose",
        "The Three Musketeers - Alexandre Dumas",
        "Dune - Frank Herbert",
    ],
    "command": [
        "Gates of Fire - Steven Pressfield",
        "The Art of War - Sun Tzu",
        "Ender's Game - Orson Scott Card",
    ],
}


def recommend_books(
    movie: Optional[str] = None,
    emotion: Optional[str] = None,
    library_path: Optional[Path] = None,
    output_json: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Recommend books to read before processing a movie for emotion extraction.

    Searches for source material, related reading, and thematic companions
    that would provide better context for persona training.

    Args:
        movie: Movie title to find source material for
        emotion: Target emotion to find thematically related books
        library_path: Path to local book library to check availability
        output_json: Save recommendations to JSON

    Returns:
        Recommendations dict with dogpile results and reading suggestions
    """
    if not movie and not emotion:
        raise ValueError("Must specify --movie or --emotion")

    # Build search query
    query_parts = []

    if movie:
        query_parts.extend([
            f'"{movie}" book novel source material',
            "adaptation original work",
        ])

    if emotion:
        emotion = emotion.lower()
        if emotion not in VALID_EMOTIONS:
            raise ValueError(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

        # Add emotion-specific book queries
        emotion_book_queries = {
            "rage": "war novels fury vengeance blood meridian violence",
            "anger": "mafia crime family betrayal cold revenge novels",
            "sorrow": "loss grief mourning war memorial novels",
            "regret": "redemption guilt conscience psychological novels",
            "camaraderie": "brotherhood military band of brothers loyalty novels",
            "command": "leadership military strategy command novels",
        }
        query_parts.append(emotion_book_queries.get(emotion, f"{emotion} novels themes"))

    query = " ".join(query_parts)

    console.print(f"[cyan]Researching books for pre-movie reading[/cyan]")
    if movie:
        console.print(f"[dim]Movie: {movie}[/dim]")
    if emotion:
        console.print(f"[dim]Emotion: {emotion}[/dim]")

    # Run dogpile search for books
    console.print("[cyan]Running dogpile search (book research)...[/cyan]")
    dogpile_results = run_dogpile(query, preset="general")

    if "error" in dogpile_results:
        console.print(f"[yellow]Dogpile warning: {dogpile_results.get('error')}[/yellow]")

    # Check local book library if specified
    local_books: Dict[str, Path] = {}
    if library_path and library_path.exists():
        console.print(f"[cyan]Scanning local book library: {library_path}[/cyan]")
        for ext in [".epub", ".pdf", ".mobi", ".txt", ".md"]:
            for book_file in library_path.rglob(f"*{ext}"):
                book_name = book_file.stem
                local_books[book_name.lower()] = book_file

    recommendations: Dict[str, Any] = {
        "movie": movie,
        "emotion": emotion,
        "query": query,
        "dogpile_results": dogpile_results,
        "local_books_found": len(local_books),
        "known_source_material": [],
        "thematic_recommendations": [],
        "local_available": [],
    }

    # Add known source material
    if movie:
        movie_lower = movie.lower()
        for key, books in BOOK_MOVIE_MAP.items():
            if key in movie_lower or movie_lower in key:
                recommendations["known_source_material"].extend(books)

    # Add emotion-based recommendations
    if emotion:
        recommendations["thematic_recommendations"] = EMOTION_BOOKS.get(emotion, [])

    # Check local availability
    all_recommended = recommendations["known_source_material"] + recommendations["thematic_recommendations"]
    for book in all_recommended:
        book_title = book.split(" - ")[0].lower()
        for local_name, local_path in local_books.items():
            if book_title in local_name or local_name in book_title:
                recommendations["local_available"].append({
                    "title": book,
                    "path": str(local_path),
                })
                break

    # Build instructions
    recommendations["instructions_for_horus"] = f"""
## Pre-Movie Reading Recommendations

{f'Before processing **{movie}** for emotion extraction:' if movie else f'For **{emotion}** emotional training:'}

### Source Material (Read First)
{chr(10).join(f'- [ ] {b}' for b in recommendations["known_source_material"]) or '- No known source material'}

### Thematic Companions
{chr(10).join(f'- [ ] {b}' for b in recommendations["thematic_recommendations"]) or '- No thematic recommendations'}

### Already Available Locally
{chr(10).join(f'- [x] {b["title"]} ({b["path"]})' for b in recommendations["local_available"]) or '- None found locally'}

### Next Steps

1. **Acquire missing books:**
   ```bash
   cd .pi/skills/ingest-book
   ./run.sh search "BOOK_TITLE"
   ./run.sh add "BOOK_TITLE"
   ```

2. **Read and annotate:**
   ```bash
   cd .pi/skills/consume-book
   ./run.sh sync --books-dir ~/library/books
   ./run.sh search "KEY_CHARACTER" --book BOOK_ID
   ./run.sh note --book BOOK_ID --char-position N --note "Insight for persona"
   ```

3. **Then extract movie scenes:**
   ```bash
   cd .pi/skills/ingest-movie
   ./run.sh agent recommend {emotion or 'EMOTION'} --library /path/to/movies
   ```
"""

    # Display recommendations
    console.print("\n" + "=" * 70)
    console.print(f"[bold green]BOOK RECOMMENDATIONS{' FOR ' + movie.upper() if movie else ''}[/bold green]")
    console.print("=" * 70)

    if recommendations["known_source_material"]:
        console.print("\n[bold]Source Material:[/bold]")
        for book in recommendations["known_source_material"]:
            avail = "LOCAL" if any(book in b["title"] for b in recommendations["local_available"]) else ""
            console.print(f"  - {book} {avail}")

    if recommendations["thematic_recommendations"]:
        console.print("\n[bold]Thematic Companions:[/bold]")
        for book in recommendations["thematic_recommendations"]:
            avail = "LOCAL" if any(book in b["title"] for b in recommendations["local_available"]) else ""
            console.print(f"  - {book} {avail}")

    console.print(f"\n[dim]Local library: {len(local_books)} books indexed[/dim]")
    console.print("\n" + "-" * 70)
    console.print(recommendations["instructions_for_horus"])

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(recommendations, f, indent=2, default=str)
        console.print(f"\n[green]Recommendations saved to {output_json}[/green]")

    return recommendations
