#!/usr/bin/env python3
"""
Research integration for personas.

Enables personas to:
- Quote colleagues' ArXiv papers
- Reference colleagues' books
- Cite colleagues' YouTube transcripts
- Use /dogpile for deep research

This is critical for multi-hop traversal where a persona
can automatically quote colleagues when helpful/necessary.
"""

import json
from pathlib import Path
from typing import Optional

from .persona import (
    Persona,
    PersonaRelationship,
    get_persona,
    get_colleagues,
    get_relationships,
    run_skill,
)

from loguru import logger as log


def research_colleague_work(
    colleague_name: str,
    topic: Optional[str] = None,
    sources: list[str] = None,
    max_results: int = 5,
    timeout: int = 60,
) -> dict:
    """Research a colleague's published work via /dogpile.

    Args:
        colleague_name: Name of the colleague to research
        topic: Optional topic to focus on
        sources: Dogpile sources to use (default: arxiv, brave, youtube)
        max_results: Max results per source
        timeout: Timeout for dogpile

    Returns:
        Dict with papers, books, videos found
    """
    if sources is None:
        sources = ["arxiv", "brave", "youtube"]

    query = f'"{colleague_name}"'
    if topic:
        query += f" {topic}"

    log.info("Researching colleague '%s' work on topic '%s'", colleague_name, topic or "(general)")

    result = run_skill("dogpile", [
        "--query", query,
        "--sources", ",".join(sources),
        "--max-results", str(max_results),
        "--no-interactive",
    ], timeout=timeout)

    if result["returncode"] != 0:
        log.warning("Dogpile research failed: %s", result["stderr"][:100])
        return {"papers": [], "books": [], "videos": [], "error": result["stderr"][:200]}

    # Parse dogpile output for structured references
    output = result["stdout"]
    references = {
        "papers": _extract_arxiv_refs(output, colleague_name),
        "books": _extract_book_refs(output, colleague_name),
        "videos": _extract_youtube_refs(output, colleague_name),
        "raw_content": output[:2000],  # First 2K chars for context
    }

    log.info("Found %d papers, %d books, %d videos for '%s'",
             len(references["papers"]), len(references["books"]),
             len(references["videos"]), colleague_name)

    return references


def _extract_arxiv_refs(content: str, author: str) -> list[dict]:
    """Extract ArXiv paper references from dogpile output."""
    import re
    papers = []

    # Look for ArXiv IDs
    arxiv_pattern = r'arXiv:(\d+\.\d+)'
    arxiv_ids = re.findall(arxiv_pattern, content)

    for arxiv_id in arxiv_ids[:5]:  # Limit to 5
        papers.append({
            "type": "arxiv",
            "id": arxiv_id,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "author": author,
        })

    # Also look for paper titles near author name
    title_pattern = rf'{author}.*?["\']([^"\']+)["\']'
    titles = re.findall(title_pattern, content, re.IGNORECASE)

    for title in titles[:3]:
        if len(title) > 10 and len(title) < 200:
            papers.append({
                "type": "paper",
                "title": title,
                "author": author,
            })

    return papers


def _extract_book_refs(content: str, author: str) -> list[dict]:
    """Extract book references from dogpile output."""
    import re
    books = []

    # Look for book patterns
    book_patterns = [
        rf'{author}.*?book[:\s]+["\']?([^"\',.]+)["\']?',
        rf'["\']([^"\']+)["\'].*?by\s+{author}',
        rf'{author}.*?authored?\s+["\']?([^"\',.]+)["\']?',
    ]

    for pattern in book_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for title in matches[:3]:
            if len(title) > 5 and len(title) < 150:
                books.append({
                    "type": "book",
                    "title": title.strip(),
                    "author": author,
                })

    return books


def _extract_youtube_refs(content: str, author: str) -> list[dict]:
    """Extract YouTube references from dogpile output."""
    import re
    videos = []

    # Look for YouTube URLs
    yt_pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
    video_ids = re.findall(yt_pattern, content)

    for vid_id in video_ids[:5]:
        videos.append({
            "type": "youtube",
            "video_id": vid_id,
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "speaker": author,
        })

    return videos


def get_quotable_colleagues(
    persona_name: str,
    topic: str,
    scope: str = "personas",
    max_colleagues: int = 3,
) -> list[dict]:
    """Find colleagues who can be quoted on a topic.

    Uses Federated Taxonomy bridges to find relevant colleagues,
    then researches their work via /dogpile.

    Args:
        persona_name: Name of the persona asking
        topic: Topic to find quotes for
        scope: Memory scope
        max_colleagues: Max colleagues to research

    Returns:
        List of colleague dicts with their relevant work
    """
    # Get relationships with bridges
    relationships = get_relationships(persona_name, scope)

    if not relationships:
        log.info("No relationships found for '%s'", persona_name)
        return []

    # Score colleagues by topic relevance
    scored = []
    for rel in relationships:
        # Simple topic matching for now
        # Could enhance with embedding similarity
        score = 0.5  # Base score for being a colleague

        # Boost if relationship context mentions topic
        if rel.context and topic.lower() in rel.context.lower():
            score += 0.3

        # Boost based on bridges (could match topic to bridge attributes)
        if rel.bridges:
            score += 0.1 * len(rel.bridges)

        scored.append({
            "name": rel.to_persona,
            "relationship": rel.relationship,
            "bridges": rel.bridges,
            "context": rel.context,
            "score": score,
        })

    # Sort by score and take top N
    scored.sort(key=lambda x: -x["score"])
    top_colleagues = scored[:max_colleagues]

    # Research each colleague's work on the topic
    results = []
    for colleague in top_colleagues:
        references = research_colleague_work(
            colleague["name"],
            topic=topic,
            sources=["arxiv", "brave"],  # Fast sources
            max_results=3,
            timeout=30,
        )

        if references.get("papers") or references.get("books"):
            results.append({
                **colleague,
                "references": references,
            })

    return results


def format_colleague_quote(
    colleague: dict,
    include_source: bool = True,
) -> str:
    """Format a colleague's work as a quotable reference.

    Args:
        colleague: Colleague dict from get_quotable_colleagues
        include_source: Whether to include source citation

    Returns:
        Formatted quote string
    """
    name = colleague["name"]
    relationship = colleague.get("relationship", "colleague")
    refs = colleague.get("references", {})

    parts = [f"According to {name}"]

    if relationship == "mentor":
        parts = [f"As my mentor {name} has shown"]
    elif relationship == "collaborator":
        parts = [f"In collaboration with {name}"]

    # Add paper reference if available
    papers = refs.get("papers", [])
    if papers and include_source:
        paper = papers[0]
        if paper.get("title"):
            parts.append(f'(in "{paper["title"]}")')
        elif paper.get("id"):
            parts.append(f"(arXiv:{paper['id']})")

    return " ".join(parts)


def enrich_persona_with_colleagues(
    persona: Persona,
    scope: str = "personas",
    max_colleagues: int = 3,
) -> list[dict]:
    """Discover and research colleagues for a persona.

    Combines colleague discovery with /dogpile research
    to build a rich network of quotable references.

    Args:
        persona: Persona to enrich
        scope: Memory scope
        max_colleagues: Max colleagues to discover

    Returns:
        List of discovered colleagues with their work
    """
    # First discover colleagues via dogpile
    log.info("Discovering colleagues for '%s'", persona.name)

    # Import discover_colleagues from ask skill
    try:
        import sys
        ask_dir = Path(__file__).parent.parent.parent.parent / ".agent" / "skills" / "ask"
        sys.path.insert(0, str(ask_dir))
        from learn import discover_colleagues
    except ImportError:
        log.warning("Could not import discover_colleagues from /ask")
        return []

    colleagues = discover_colleagues(persona.name, max_colleagues=max_colleagues)

    # Research each colleague
    enriched = []
    for colleague in colleagues:
        name = colleague["name"]

        # Research their work
        references = research_colleague_work(
            name,
            topic=persona.domain,
            sources=["arxiv", "brave", "youtube"],
            max_results=5,
        )

        enriched.append({
            **colleague,
            "references": references,
        })

    return enriched
