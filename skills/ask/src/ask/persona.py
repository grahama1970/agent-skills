"""
Persona-aware learning for /ask learn.

Handles persona detection, profile management, interview-based depth
selection, colleague discovery, and sparse persona enrichment.
"""

import json
import re
from datetime import datetime
from typing import Optional

from loguru import logger as log

from .skills_exec import run_skill, parse_json_output, parse_memory_output


# -------------------------------------------------------------------------
# Learning Depth Configurations
# -------------------------------------------------------------------------

LEARNING_DEPTHS = {
    "quick": {
        "description": "Quick overview (5-10 min)",
        "max_videos": 3,
        "max_books": 0,
        "download_books": False,
        "arxiv_papers": 0,
        "estimated_time": "5-10 minutes",
    },
    "standard": {
        "description": "Standard learning (30-60 min)",
        "max_videos": 5,
        "max_books": 3,
        "download_books": False,
        "arxiv_papers": 3,
        "estimated_time": "30-60 minutes",
    },
    "deep": {
        "description": "Deep dive (hours)",
        "max_videos": 10,
        "max_books": 5,
        "download_books": True,
        "arxiv_papers": 10,
        "estimated_time": "2-6 hours",
    },
}


# -------------------------------------------------------------------------
# Persona Detection
# -------------------------------------------------------------------------

def detect_persona(topic: str) -> bool:
    """Detect if topic is likely a person (for persona learning mode).

    Uses simple heuristics: capitalized words, common name patterns.
    """
    words = topic.strip().split()

    # Check for "Dr.", "Professor", etc.
    titles = {"dr", "dr.", "professor", "prof", "prof."}
    if words and words[0].lower() in titles:
        return True

    # Check if looks like "Firstname Lastname" (2-4 capitalized words)
    if 2 <= len(words) <= 4:
        capitalized = sum(1 for w in words if w[0].isupper())
        if capitalized >= 2:
            return True

    return False


# -------------------------------------------------------------------------
# Persona Profiles
# -------------------------------------------------------------------------

def get_persona_profile(name: str, scope: str) -> Optional[dict]:
    """Retrieve existing persona profile from memory."""
    # Check for persona profile in memory
    result = run_memory_recall(f"persona profile {name}", scope, k=1, timeout=10)
    if result["returncode"] == 0:
        items = parse_memory_output(result["stdout"])
        for item in items:
            if "persona_profile" in item.get("problem", "").lower():
                return item
    return None


def store_persona_profile(
    name: str,
    scope: str,
    sources: dict,
    stats: dict,
) -> bool:
    """Store persona profile to memory for future retrieval.

    The profile includes:
    - Name and aliases
    - Sources ingested (books, videos, papers)
    - Learning stats (QRA count, last updated)
    - Tags for easy retrieval
    """
    profile = {
        "name": name,
        "scope": scope,
        "sources": sources,
        "stats": stats,
        "last_updated": datetime.now().isoformat(),
    }

    problem = f"Persona profile: {name}"
    solution = json.dumps(profile, indent=2)
    tags = ["persona", "profile", name.lower().replace(" ", "_")]

    args = ["learn", "-p", problem, "-s", solution, "--scope", scope]
    for tag in tags:
        args.extend(["-t", tag])

    result = run_skill("memory", args, timeout=30)
    if result["returncode"] != 0:
        log.error("Failed to store persona profile: %s", result["stderr"][:200])
        return False
    return True


# -------------------------------------------------------------------------
# Interview-Based Depth Selection
# -------------------------------------------------------------------------

def run_interview(questions: list[dict], title: str = "Learning Preferences") -> dict:
    """Run /interview skill to ask user questions.

    Args:
        questions: List of question dicts with id, text, header, options
        title: Title for the interview form

    Returns:
        Dict mapping question id to selected answer(s)
    """
    import tempfile

    interview_data = {
        "title": title,
        "context": "The /ask skill needs your input to proceed.",
        "questions": questions,
    }

    # Write questions to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(interview_data, f, indent=2)
        questions_file = f.name

    try:
        # Run interview skill
        result = run_skill("interview", ["--mode", "tui", "--file", questions_file], timeout=300)

        if result["returncode"] == 0:
            # Parse response
            response = parse_json_output(result["stdout"])
            if response and "answers" in response:
                return response["answers"]

        log.warning("Interview failed or timed out: %s", result.get("stderr", "")[:100])
        return {}

    finally:
        Path(questions_file).unlink(missing_ok=True)


def ask_learning_depth(topic: str, is_persona: bool = False) -> str:
    """Ask user about learning depth via /interview.

    Returns: 'quick', 'standard', or 'deep'
    """
    questions = [{
        "id": "depth",
        "header": "Depth",
        "text": f"How deeply should I learn about {topic}?",
        "options": [
            {
                "label": "Quick overview (Recommended)",
                "description": "Dogpile research + top 3 YouTube videos. ~5-10 minutes."
            },
            {
                "label": "Standard",
                "description": "+ Book discovery + 5 videos + ArXiv papers. ~30-60 minutes."
            },
            {
                "label": "Deep dive",
                "description": "+ Download books + 10+ videos + extensive research. 2-6 hours."
            },
        ],
        "multi_select": False,
    }]

    answers = run_interview(questions, title=f"Learning about {topic}")

    depth_answer = answers.get("depth", "Quick overview")

    if "deep" in depth_answer.lower():
        return "deep"
    elif "standard" in depth_answer.lower():
        return "standard"
    else:
        return "quick"


# -------------------------------------------------------------------------
# Memory Recall
# -------------------------------------------------------------------------

def run_memory_recall(query: str, scope: str, k: int = 5, timeout: int = 15) -> dict:
    """Run memory recall through the memory skill."""
    return run_skill("memory", ["recall", "--q", query, "--scope", scope, "--k", str(k)], timeout=timeout)


# -------------------------------------------------------------------------
# Colleague Discovery for Sparse Personas
# -------------------------------------------------------------------------

SPARSE_THRESHOLD = 3  # If fewer QRAs than this, consider the persona data sparse


def discover_colleagues(
    persona_name: str,
    max_colleagues: int = 3,
    timeout: int = 60,
) -> list[dict]:
    """Discover academic/professional colleagues of a persona.

    Uses dogpile research to identify people who:
    - Collaborate with the persona
    - Work in the same field
    - Are frequently mentioned together

    Args:
        persona_name: Name of the persona (e.g., "Robert Sapolsky")
        max_colleagues: Maximum colleagues to return
        timeout: Timeout for dogpile research

    Returns:
        List of colleague dicts with name, relationship, field
    """
    query = f'"{persona_name}" colleagues collaborators co-authors research partners'
    log.info("Discovering colleagues for '%s'", persona_name)

    # Run dogpile to find colleague mentions
    result = run_skill("dogpile", [
        "--query", query,
        "--sources", "brave,perplexity",
        "--max-results", "10",
        "--no-interactive",
    ], timeout=timeout)

    if result["returncode"] != 0:
        log.warning("Dogpile colleague search failed: %s", result["stderr"][:100])
        return []

    # Parse output for person names
    output = result["stdout"]
    colleagues = []
    seen_names = {persona_name.lower()}

    # Look for capitalized name patterns near keywords
    colleague_patterns = [
        # "works with <Name>", "collaborated with <Name>"
        r"(?:work(?:s|ed)?|collaborat(?:es?|ed|ing))\s+with\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        # "co-authored with <Name>"
        r"co-author(?:ed|s)?\s+(?:by|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        # "<Name>, a colleague" or "<Name>, who also"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}),\s+(?:a\s+colleague|who\s+also|another)",
        # "alongside <Name>"
        r"alongside\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        # "Dr. <Name>" or "Professor <Name>" (not the original persona)
        r"(?:Dr\.?|Prof(?:essor)?\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
    ]

    for pattern in colleague_patterns:
        matches = re.findall(pattern, output, re.IGNORECASE)
        for match in matches:
            name = match.strip()
            # Filter: must be capitalized (actual name)
            words = name.split()
            words = [w for w in words if w and w[0].isupper()]
            if not words:
                continue
            name = " ".join(words)

            # Skip the original persona and duplicates
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            # Add colleague
            colleagues.append({
                "name": name,
                "relationship": "colleague",
                "discovered_via": "dogpile",
            })

            if len(colleagues) >= max_colleagues:
                break
        if len(colleagues) >= max_colleagues:
            break

    log.info("Discovered %d colleagues for '%s': %s",
             len(colleagues), persona_name, [c["name"] for c in colleagues])
    return colleagues


def is_persona_sparse(stats: dict) -> bool:
    """Check if the learned persona data is sparse and needs enrichment.

    Args:
        stats: Learning stats dict from learn()

    Returns:
        True if data is sparse and should discover colleagues
    """
    qra_count = stats.get("qra_extracted", 0)
    books_count = stats.get("books_downloaded", 0)

    # Sparse if few QRAs and not many sources
    if qra_count < SPARSE_THRESHOLD:
        # But only if we didn't get books (books often have lots of content)
        if books_count == 0:
            return True

    return False
