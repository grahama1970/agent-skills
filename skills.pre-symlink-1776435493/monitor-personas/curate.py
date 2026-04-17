"""
Curate step: Proactively discover content relevant to each persona.

Fictional personas get media discovery (movies/books/music) with bridge
weights derived dynamically from current emotional state.

Knowledge personas get domain discovery (arxiv, security alerts, feeds,
dogpile research, YouTube conference talks) with queries augmented by
current knowledge gaps and recent interests.

Personas are NOT static — their interests shift, emotional states change,
knowledge gaps emerge. This step derives discovery targets dynamically
from current persona state, recent memory, and knowledge gaps rather
from loguru import logger
than hardcoded preferences.

Inputs: personas.yaml curate_content, persona state files, memory gaps.
Outputs: curate_state.json with discovered items per persona.
"""

import json
import os
import random
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from monitor_core import (
    PROJECT_ROOT,
    PersonaConfig,
    get_all_personas,
    load_config,
)
from state import get_state_manager, CurateResult

console = Console()

SKILLS_DIR = PROJECT_ROOT / ".pi/skills"
_PERSONA_STATES_DIR = Path(os.environ.get("MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory"))) / "persona" / "states"


# ---------------------------------------------------------------------------
# Bridge derivation (dynamic from persona emotional state)
# ---------------------------------------------------------------------------

def _load_persona_state(persona_id: str) -> Optional[Dict[str, float]]:
    """Load persona emotional state from state files."""
    try:
        candidates = list(_PERSONA_STATES_DIR.glob(f"{persona_id}_persona_*.json"))
        if not candidates:
            # Try horus-specific naming
            candidates = list(_PERSONA_STATES_DIR.glob(f"{persona_id}_*.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return json.loads(latest.read_text())
    except Exception:
        return None


def _persona_bridge_weights(state: Dict[str, float]) -> Dict[str, float]:
    """Derive per-bridge weights from persona emotional state.

    Replicates common/discovery.py:persona_bridge_weights() to avoid
    cross-skill import dependency.
    """
    resentment = state.get("resentment", 0.5)
    arrogance = state.get("arrogance", 0.5)
    grandiosity = state.get("grandiosity", 0.5)
    weariness = state.get("weariness", 0.5)
    suspicion = state.get("suspicion", 0.5)
    honor = state.get("honor_sense", 0.2)
    protective = state.get("protective_instinct", 0.1)

    weights = {
        "Precision": 0.5 + 0.3 * arrogance + 0.2 * grandiosity,
        "Resilience": 0.5 + 0.3 * (1.0 - weariness) + 0.2 * honor,
        "Fragility": 0.5 + 0.4 * weariness + 0.1 * (1.0 - arrogance),
        "Corruption": 0.5 + 0.3 * resentment + 0.2 * suspicion,
        "Loyalty": 0.5 + 0.4 * honor + 0.1 * protective,
        "Stealth": 0.5 + 0.4 * suspicion + 0.1 * weariness,
    }
    max_w = max(weights.values()) or 1.0
    return {k: round(v / max_w, 3) for k, v in weights.items()}


def _derive_bridges(persona: PersonaConfig) -> List[str]:
    """Derive top bridges from current persona emotional state."""
    state = _load_persona_state(persona.id)
    if state:
        weights = _persona_bridge_weights(state)
        ranked = sorted(weights.items(), key=lambda x: -x[1])
        return [bridge for bridge, _ in ranked[:3]]
    # Fallback: use taxonomy_hints from personas.yaml
    return persona.taxonomy_hints[:3] if persona.taxonomy_hints else ["Resilience", "Precision"]


# ---------------------------------------------------------------------------
# Query derivation (dynamic from gaps + journal + memory)
# ---------------------------------------------------------------------------

def _derive_queries(persona: PersonaConfig, base_queries: List[str]) -> List[str]:
    """Augment base queries with knowledge gaps and recent interests.

    Personas are NOT static — their queries evolve with:
    1. Knowledge gaps from gap_tracker.json
    2. Recent memory recall terms
    3. Base interests rotated by tier (primary always, cross_domain rotated,
       guilty_pleasure weekly)
    """
    queries = list(base_queries)

    # 1. Check knowledge gaps for this persona
    try:
        state_mgr = get_state_manager()
        gaps = state_mgr.get_pending_gaps()
        persona_gaps = [g for g in gaps if g.persona_id == persona.id]
        for gap in persona_gaps[:2]:
            queries.append(gap.description)
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    return queries[:8]  # Cap at 8 queries


def _get_interest_queries(persona: PersonaConfig) -> List[str]:
    """Extract interest queries from curate_content config, respecting tiers.

    primary: always searched
    cross_domain: rotated (2 per run)
    guilty_pleasure: weekly (1/week)
    """
    cc = _get_curate_content(persona)
    interests = cc.get("interests", {})
    queries = []

    # Primary — always
    queries.extend(interests.get("primary", []))

    # Cross-domain — rotate 2 per run
    cross = interests.get("cross_domain", [])
    if cross:
        random.shuffle(cross)
        queries.extend(cross[:2])

    # Guilty pleasure — weekly (check day of week)
    guilty = interests.get("guilty_pleasure", [])
    if guilty and date.today().weekday() == 0:  # Monday
        queries.extend(guilty[:1])

    return queries


def _get_curate_content(persona: PersonaConfig) -> Dict[str, Any]:
    """Get curate_content dict from persona config (raw yaml)."""
    config = load_config()
    for category, persona_list in config.items():
        if category == "settings" or not isinstance(persona_list, list):
            continue
        for p in persona_list:
            if isinstance(p, dict) and p.get("id") == persona.id:
                return p.get("curate_content", {})
    return {}


# ---------------------------------------------------------------------------
# Skill subprocess runner
# ---------------------------------------------------------------------------

def _run_skill(skill: str, command: str, args: Optional[List[str]] = None,
               timeout: int = 120) -> Optional[str]:
    """Run a sibling skill via its run.sh and return stdout."""
    run_sh = SKILLS_DIR / skill / "run.sh"
    if not run_sh.exists():
        console.print(f"  [dim]Skill {skill} not available[/]")
        return None

    cmd = [str(run_sh), command]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SKILLS_DIR / skill,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            console.print(f"  [dim]{skill} {command}: {result.stderr[:100]}[/]")
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        console.print(f"  [dim]{skill} {command}: timeout[/]")
        return None
    except Exception as e:
        console.print(f"  [dim]{skill} {command}: {e}[/]")
        return None


# ---------------------------------------------------------------------------
# Result extraction helpers
# ---------------------------------------------------------------------------

def _extract_scored(raw: Optional[str], content_type: str, bridge: str,
                    persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from discover-* JSON output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("results", data.get("items", []))
        for item in items:
            title = item.get("title", item.get("name", ""))
            if not title:
                continue
            score = item.get("final_score", item.get("score", item.get("popularity", 0)))
            if isinstance(score, str):
                try:
                    score = float(score)
                except ValueError:
                    score = 0.0
            results.append(CurateResult(
                title=title,
                content_type=content_type,
                bridge=bridge,
                score=float(score),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k not in ("title", "name") and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        pass
    return results


def _extract_papers(raw: Optional[str], persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from arxiv search JSON output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("results", data.get("papers", []))
        for item in items:
            title = item.get("title", "")
            if not title:
                continue
            results.append(CurateResult(
                title=title,
                content_type="arxiv",
                bridge=item.get("query", "arxiv"),
                score=float(item.get("relevance", item.get("score", 0.5))),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k != "title" and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        pass
    return results


def _extract_alerts(raw: Optional[str], persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from social-bridge check output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("alerts", data.get("items", []))
        for item in items:
            title = item.get("title", item.get("summary", ""))
            if not title:
                continue
            results.append(CurateResult(
                title=title,
                content_type="security",
                bridge="social-bridge",
                score=float(item.get("severity", item.get("score", 0.5))),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k not in ("title", "summary") and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        pass
    return results


def _extract_feed_items(raw: Optional[str], persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from consume-feed run output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        for item in items:
            title = item.get("title", item.get("name", ""))
            if not title:
                continue
            results.append(CurateResult(
                title=title,
                content_type="feed",
                bridge="consume-feed",
                score=float(item.get("score", 0.5)),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k != "title" and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        pass
    return results


def _extract_dogpile(raw: Optional[str], query: str,
                     persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from dogpile search output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("results", data.get("sources", []))
        for item in items:
            title = item.get("title", item.get("name", ""))
            if not title:
                continue
            results.append(CurateResult(
                title=title,
                content_type="dogpile",
                bridge=query[:60],
                score=float(item.get("relevance", item.get("score", 0.5))),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k != "title" and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        # Dogpile may return markdown/text, not JSON — log as single result
        if raw and len(raw) > 50:
            results.append(CurateResult(
                title=f"Dogpile research: {query[:50]}",
                content_type="dogpile",
                bridge=query[:60],
                score=0.5,
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={"raw_length": len(raw)},
            ))
    return results


def _extract_youtube_results(raw: Optional[str], persona_id: str) -> List[CurateResult]:
    """Extract CurateResults from ingest-youtube search output."""
    if not raw:
        return []
    results = []
    try:
        data = json.loads(raw)
        items = data if isinstance(data, list) else data.get("results", data.get("videos", []))
        for item in items:
            title = item.get("title", item.get("name", ""))
            if not title:
                continue
            results.append(CurateResult(
                title=title,
                content_type="youtube",
                bridge="conference-talk",
                score=float(item.get("score", item.get("view_count", 0.5))),
                persona_id=persona_id,
                discovered_at=datetime.now().isoformat(),
                metadata={
                    k: v for k, v in item.items()
                    if k != "title" and isinstance(v, (str, int, float, bool))
                },
            ))
    except (json.JSONDecodeError, TypeError):
        pass
    return results


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedupe(results: List[CurateResult]) -> List[CurateResult]:
    """Deduplicate results by title (case-insensitive)."""
    seen = set()
    deduped = []
    for r in results:
        key = r.title.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


# ---------------------------------------------------------------------------
# Media curate (fictional personas)
# ---------------------------------------------------------------------------

def _curate_media(persona: PersonaConfig, types: List[str],
                  limit: int, dry_run: bool) -> List[CurateResult]:
    """Discover movies/books/music via discover-* skills with dynamic bridges."""
    bridges = _derive_bridges(persona)
    console.print(f"  Bridges (dynamic): {', '.join(bridges)}")

    if dry_run:
        console.print(f"  [yellow][DRY RUN] Would search {types} via {len(bridges)} bridges[/]")
        return []

    discoveries = []
    for bridge in bridges:
        if "movies" in types:
            console.print(f"  Searching movies for bridge: {bridge}...")
            raw = _run_skill("discover-movies", "bridge", [bridge, "--limit", str(limit), "--json"])
            discoveries.extend(_extract_scored(raw, "movie", bridge, persona.id))

        if "books" in types:
            console.print(f"  Searching books for bridge: {bridge}...")
            raw = _run_skill("discover-books", "bridge", [bridge, "--limit", str(limit), "--json"])
            discoveries.extend(_extract_scored(raw, "book", bridge, persona.id))

        if "music" in types:
            console.print(f"  Searching music for bridge: {bridge}...")
            raw = _run_skill("discover-music", "bridge", [bridge, "--limit", str(limit), "--json"])
            discoveries.extend(_extract_scored(raw, "music", bridge, persona.id))

    # Music taste-profile recommendations
    if "music" in types:
        profile = Path.home() / ".pi/ingest-yt-history/profile.json"
        if profile.exists():
            console.print("  Searching music via taste-profile...")
            raw = _run_skill("discover-music", "recommend", [
                "--profile", str(profile), "--limit", "10", "--json"
            ])
            discoveries.extend(_extract_scored(raw, "music", "taste-profile", persona.id))

    return _dedupe(discoveries)


# ---------------------------------------------------------------------------
# Knowledge curate (real/knowledge personas)
# ---------------------------------------------------------------------------

def _curate_knowledge(persona: PersonaConfig, dry_run: bool) -> List[CurateResult]:
    """Discover arxiv papers, security alerts, feeds, dogpile research,
    and YouTube conference content for knowledge personas.

    Personas are NOT static — queries are derived dynamically from interests,
    knowledge gaps, and recent journal topics.
    """
    cc = _get_curate_content(persona)
    types = cc.get("types", [])
    limit = cc.get("limit", 5)
    base_queries = _get_interest_queries(persona)
    queries = _derive_queries(persona, base_queries)

    console.print(f"  Types: {', '.join(types)}")
    console.print(f"  Queries ({len(queries)}): {', '.join(q[:40] for q in queries[:3])}...")

    if dry_run:
        console.print(f"  [yellow][DRY RUN] Would search {len(queries)} queries across {types}[/]")
        return []

    discoveries = []

    # Arxiv papers
    if "arxiv" in types:
        for query in queries[:5]:
            console.print(f"  arxiv: {query[:50]}...")
            raw = _run_skill("arxiv", "search", [query, "--limit", str(limit), "--json"])
            discoveries.extend(_extract_papers(raw, persona.id))

    # Security alerts via social-bridge
    if "security" in types:
        feeds = cc.get("security_feeds", [])
        if "social-bridge" in feeds:
            console.print("  Checking social-bridge for security alerts...")
            raw = _run_skill("social-bridge", "fetch", ["--json", "--hours", "24", "--limit", "20"])
            discoveries.extend(_extract_alerts(raw, persona.id))

    # RSS/NVD exploit feeds via consume-feed
    if "feeds" in types:
        feed_sources = cc.get("feed_sources", [])
        if "consume-feed" in feed_sources:
            console.print("  Checking consume-feed for new exploit/advisory items...")
            raw = _run_skill("consume-feed", "run", [
                "--mode", "manual", "--dry-run", "--limit", str(limit)
            ])
            discoveries.extend(_extract_feed_items(raw, persona.id))

    # Deep research via dogpile
    if "dogpile" in types:
        dogpile_queries = cc.get("dogpile_queries", [])
        # Also augment with dynamic queries from gaps
        augmented = list(dogpile_queries)
        gap_queries = [q for q in queries if q not in base_queries]
        augmented.extend(gap_queries[:2])
        for query in augmented[:3]:  # Cap dogpile at 3 (expensive)
            console.print(f"  dogpile: {query[:50]}...")
            raw = _run_skill("dogpile", "search", [query, "--json"], timeout=180)
            discoveries.extend(_extract_dogpile(raw, query, persona.id))

    # YouTube conference talks and colleague content
    if "youtube" in types:
        yt_config = cc.get("youtube_search", {})
        search_terms = yt_config.get("search_terms", [])
        # Augment search terms dynamically from interests
        dynamic_terms = [q for q in queries[:2] if q not in search_terms]
        all_terms = search_terms + dynamic_terms
        for term in all_terms[:5]:  # Cap at 5 YouTube searches
            console.print(f"  youtube search: {term[:50]}...")
            raw = _run_skill("ingest-youtube", "search", [term, "--limit", "5", "--json"])
            discoveries.extend(_extract_youtube_results(raw, persona.id))

    # Books (for knowledge personas with book interests)
    if "books" in types:
        book_queries = base_queries[:3]
        for query in book_queries:
            console.print(f"  books: {query[:50]}...")
            raw = _run_skill("discover-books", "search-subject", [query, "--limit", "5", "--json"])
            discoveries.extend(_extract_scored(raw, "book", query, persona.id))

    return _dedupe(discoveries)


# ---------------------------------------------------------------------------
# Per-persona dispatch
# ---------------------------------------------------------------------------

def _curate_persona(persona: PersonaConfig, content_types: Optional[List[str]],
                    dry_run: bool) -> List[CurateResult]:
    """Dispatch curate for a single persona."""
    cc = _get_curate_content(persona)
    if not cc:
        console.print(f"  [dim]No curate_content defined, skipping[/]")
        return []

    configured_types = cc.get("types", [])
    if content_types:
        # Filter to requested types that this persona supports
        types = [t for t in content_types if t in configured_types]
        if not types:
            console.print(f"  [dim]No matching types (has: {configured_types})[/]")
            return []
    else:
        types = configured_types

    # Dispatch: media types use bridge-based discovery, knowledge types use query-based
    # Personas are NOT one-dimensional — a fictional warmaster can also want arxiv papers
    media_types = [t for t in types if t in ("movies", "books", "music")]
    knowledge_types = [t for t in types if t in ("arxiv", "security", "feeds", "dogpile", "youtube")]

    discoveries = []

    if media_types and persona.fictional:
        limit = cc.get("limit_per_bridge", 5)
        discoveries.extend(_curate_media(persona, media_types, limit, dry_run))

    if knowledge_types:
        # Any persona with knowledge types gets the knowledge path
        discoveries.extend(_curate_knowledge(persona, dry_run))
    elif media_types and not persona.fictional:
        # Non-fictional personas with only media types still use knowledge path
        discoveries.extend(_curate_knowledge(persona, dry_run))

    return discoveries


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def cmd_curate(
    persona_ids: Optional[List[str]] = None,
    content_types: Optional[List[str]] = None,
    dry_run: bool = False,
    json_output: bool = False,
):
    """Discover new content aligned to persona tastes.

    For each persona with curate_content defined:
    1. Dynamically derive current interests from state + gaps + journal
    2. Pick top bridges by current weight (fictional) or build queries (knowledge)
    3. Search via discover-*/arxiv/social-bridge/consume-feed/dogpile/youtube
    4. Deduplicate and append to curate_state.json queue
    5. Log summary per persona
    """
    personas = get_all_personas()
    state_mgr = get_state_manager()

    all_discoveries = []
    persona_summaries = []

    for persona in personas:
        if persona_ids and persona.id not in persona_ids:
            continue

        cc = _get_curate_content(persona)
        if not cc:
            continue

        console.print(f"\n[bold cyan]=== {persona.name} ({persona.id}) ===[/]")

        discoveries = _curate_persona(persona, content_types, dry_run)
        all_discoveries.extend(discoveries)

        if discoveries:
            added = state_mgr.add_curate_results(discoveries)
            console.print(f"  [green]Discovered {len(discoveries)} items, {added} new to queue[/]")
        else:
            added = 0
            if not dry_run:
                console.print("  [dim]No new discoveries[/]")

        persona_summaries.append({
            "persona_id": persona.id,
            "persona_name": persona.name,
            "discovered": len(discoveries),
            "added_to_queue": added,
            "types": [d.content_type for d in discoveries],
        })

    # Summary
    if json_output:
        import sys
        summary = {
            "curated_at": datetime.now().isoformat(),
            "dry_run": dry_run,
            "total_discovered": len(all_discoveries),
            "personas": persona_summaries,
            "queue": state_mgr.get_curate_summary(),
        }
        sys.stdout.write(json.dumps(summary, indent=2, default=str) + "\n")
    else:
        console.print(f"\n[bold]=== Curate Summary ===[/]")
        console.print(f"  Total discovered: {len(all_discoveries)}")

        if persona_summaries:
            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("Persona", width=20)
            table.add_column("Discovered", justify="right", width=12)
            table.add_column("New", justify="right", width=6)

            for ps in persona_summaries:
                disc = ps["discovered"]
                added = ps["added_to_queue"]
                disc_str = f"[green]{disc}[/]" if disc > 0 else "[dim]0[/]"
                add_str = f"[green]{added}[/]" if added > 0 else "[dim]0[/]"
                table.add_row(ps["persona_name"], disc_str, add_str)

            console.print(table)

        queue_summary = state_mgr.get_curate_summary()
        console.print(f"\n  Queue: {queue_summary['total']} total, {queue_summary['unconsumed']} unconsumed")
