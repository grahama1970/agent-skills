"""
Dream Mode: Day Residue Collection + Dream Storage

Fetch surreal 'day residue' from multiple memory scopes to seed dreams.
Store completed dreams back to memory so they alter the persona over time.

The feedback loop:
  memories → dream residue → dream scenes → stored dreams → future memories → future dreams

This module supports dream mode in the create-movie workflow.
Parameterized by persona — any registered persona (Horus, Embry, etc.) can dream.
"""

import json
from dataclasses import dataclass, field

from loguru import logger
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..skill_registry import run_skill

console = Console()

# ── Stop words for theme extraction ──
STOP_WORDS = frozenset({
    "about", "after", "again", "being", "between", "could", "dream",
    "during", "every", "first", "found", "great", "their", "there",
    "these", "thing", "those", "through", "under", "visual", "which",
    "while", "would", "other", "should", "still", "where", "before",
})

# Curated seed memories per persona for when memory service is unavailable
SEED_RESIDUE: dict[str, list[dict]] = {
    "horus": [
        {"type": "Unresolved Tension", "text": "The weight of unfinished tasks lingers at the edges of consciousness, a persistent hum of incompleteness"},
        {"type": "Cinematic Motif", "text": "A long tracking shot through an abandoned corridor, light filtering through cracked windows onto dust motes"},
        {"type": "Literary Metaphor", "text": "The labyrinth of mirrors reflecting not faces but possibilities never pursued, each turn a different life"},
        {"type": "World Echo", "text": "The hum of machines learning to dream, neural networks painting landscapes from noise and gradient descent"},
        {"type": "Music Echo", "text": "A cello drone building beneath stuttering piano chords, the sound of time dissolving into static"},
    ],
    "embry": [
        {"type": "Unresolved Tension", "text": "The SPARTA controls keep shifting like constellations, each alignment revealing a new gap she almost missed"},
        {"type": "Cinematic Motif", "text": "A satellite dish rotating slowly against a Charleston sunset, receiving signals from something that shouldn't exist"},
        {"type": "Literary Metaphor", "text": "The authentication layers peel back like pages of a book she wrote but can't remember writing"},
        {"type": "World Echo", "text": "Rocket exhaust trails weaving into equations on a whiteboard, the math dissolving into contrails at altitude"},
        {"type": "Music Echo", "text": "Scott Manley's voice narrating orbital mechanics over the hum of her Celsius can opening at 2 AM"},
    ],
}

def _get_seed_residue(persona_id: str = "horus") -> list[dict]:
    """Get persona-specific seed residue, falling back to Horus defaults."""
    return SEED_RESIDUE.get(persona_id, SEED_RESIDUE["horus"])


@dataclass
class DreamPersona:
    """Persona configuration for dream generation.

    Any persona can dream — scope is derived from ID automatically.
    Convention: {id}-memories, {id}-dreams, {id}-dream-journals, etc.
    """
    id: str              # "horus", "embry", any persona ID
    display_name: str    # "Horus", "Embry"
    lore_scope: str = ""  # auto-derived if empty
    tts_checkpoint: Optional[Path] = None

    def __post_init__(self):
        if not self.lore_scope:
            self.lore_scope = f"{self.id}-memories"

    def scope(self, type: str) -> str:
        """Derive memory scope: horus-movies, embry-dreams, etc."""
        return f"{self.id}-{type}"


# Default persona for backward compatibility
DEFAULT_PERSONA = DreamPersona(id="horus", display_name="Horus")


@dataclass
class ResidueItem:
    """A single item of day residue with source metadata and weighting."""
    type: str           # "Unresolved Tension", "Research Insight", etc.
    text: str           # The actual content
    source: str         # Skill that produced it
    weight: float       # Dream theory weight: day_residue=0.70, dream_lag=0.20, semantic=0.10
    recency_hours: int = 0  # How old (for weighting)


# ── Dream Theory Weight Tiers ──
WEIGHT_DAY_RESIDUE = 0.70   # 0-48h: journals, episodic, tasks, feeds
WEIGHT_DREAM_LAG = 0.20     # 5-7 days: older episodic, past journals
WEIGHT_SEMANTIC = 0.10      # >7 days: old memory recall triggered by recent themes

# ── Sensory Dream Weights (research-backed differential weighting) ──
# Per PMC11202128 & PMC7415562:
#   - Touch/temperature/pain → direct scene content (most effective for incorporation)
#   - Smell → emotional coloring (modulates mood, not literal scene elements)
#   - Taste → rare vivid anchors (powerful when present, but sparse)
#   - Proprioception → body-awareness / spatial grounding in dream
# Items with these modalities get a weight boost proportional to incorporation rate.
SENSORY_DREAM_WEIGHTS: dict[str, float] = {
    "touch": 0.15,          # Strongest incorporation rate in NREM→REM
    "temperature": 0.15,    # Thermal stimuli cross the sleep barrier
    "pain": 0.12,           # High arousal → vivid dream content
    "proprioception": 0.10, # Body-as-permeable-barrier (PMC7415562)
    "smell": 0.08,          # Modulates emotion, not literal (TMR studies)
    "taste": 0.05,          # Rare but vivid — anchor moments
}

# ── Bridge Opposition Map (taxonomy tensions) ──
BRIDGE_OPPOSITIONS = {
    "Fragility": "Resilience",   # weakness ↔ strength
    "Resilience": "Fragility",
    "Corruption": "Loyalty",     # betrayal ↔ trust
    "Loyalty": "Corruption",
    "Stealth": "Precision",      # hidden ↔ explicit
    "Precision": "Stealth",
    "Intimacy": "Stealth",       # closeness ↔ hidden
}


@dataclass
class Contradiction:
    """A tension between two residue items with opposing taxonomy bridges."""
    item_a: dict               # First item in tension
    item_b: dict               # Opposing item (may come from graph recall)
    bridge_a: str              # Dominant bridge of item_a
    bridge_b: str              # Opposing bridge of item_b
    tension_score: float       # 0.0-1.0
    description: str           # Human-readable tension


def _extract_item_bridges(item: dict) -> list[str]:
    """Extract taxonomy bridge attributes from a residue item using keyword matching."""
    try:
        from common.taxonomy_core import get_bridge_attributes
        return get_bridge_attributes(item.get("text", ""))
    except ImportError:
        return []


def detect_contradictions(
    items: list[dict],
    persona: "DreamPersona",
    max_contradictions: int = 3,
) -> list[Contradiction]:
    """
    Analyze residue items to find tensions — pairs with opposing taxonomy bridges.

    Contradictions are the dramatic engine of dreams. Humans dream about unresolved
    conflicts; these tensions become high-weight dream material.

    Steps:
      1. Tag items with bridges via taxonomy keyword matching
      2. Pairwise opposition scan within residue
      3. Graph-augmented discovery for high-weight items without pairwise matches
      4. Rank by tension_score, cap at max_contradictions
    """
    # Step 1: Tag all items with bridges
    tagged: list[tuple[dict, list[str]]] = []
    for item in items:
        bridges = _extract_item_bridges(item)
        if bridges:
            tagged.append((item, bridges))

    if not tagged:
        return []

    contradictions: list[Contradiction] = []
    used_pairs: set[tuple[int, int]] = set()

    # Step 2: Pairwise opposition scan
    for i, (item_a, bridges_a) in enumerate(tagged):
        for j, (item_b, bridges_b) in enumerate(tagged):
            if i >= j or (i, j) in used_pairs:
                continue
            for ba in bridges_a:
                opposite = BRIDGE_OPPOSITIONS.get(ba)
                if opposite and opposite in bridges_b:
                    weight_a = item_a.get("weight", 0.5)
                    weight_b = item_b.get("weight", 0.5)
                    score = weight_a * weight_b * 1.0
                    desc = (
                        f"You feel {ba.lower()} despite {opposite.lower()}: "
                        f"{item_a.get('text', '')[:60]} vs {item_b.get('text', '')[:60]}"
                    )
                    contradictions.append(Contradiction(
                        item_a=item_a, item_b=item_b,
                        bridge_a=ba, bridge_b=opposite,
                        tension_score=score, description=desc,
                    ))
                    used_pairs.add((i, j))
                    break  # One contradiction per pair

    # Step 3: Graph-augmented discovery for high-weight items without pairwise matches
    matched_indices = {idx for pair in used_pairs for idx in pair}
    unmatched_high = [
        (i, item, bridges) for i, (item, bridges) in enumerate(tagged)
        if i not in matched_indices and item.get("weight", 0) >= WEIGHT_DAY_RESIDUE
    ]

    for _, item, bridges in unmatched_high[:3]:
        query_text = item.get("text", "")[:100]
        try:
            recall_result = run_skill("memory", [
                "recall", "--q", query_text,
                "--scope", persona.lore_scope, "--k", "3",
            ], capture=True)
            if recall_result.get("returncode") != 0:
                continue

            data = json.loads(recall_result.get("stdout", "{}"))
            for mem in data.get("items", []):
                mem_bridges = mem.get("bridge_attributes", [])
                if isinstance(mem_bridges, str):
                    mem_bridges = [b.strip() for b in mem_bridges.split(",")]
                for ba in bridges:
                    opposite = BRIDGE_OPPOSITIONS.get(ba)
                    if opposite and opposite in mem_bridges:
                        mem_text = (
                            mem.get("solution", "")
                            or mem.get("title", "")
                            or mem.get("text", "")
                            or ""
                        )
                        mem_item = {
                            "type": "Graph Memory",
                            "text": mem_text[:150],
                            "source": "memory-graph",
                            "weight": WEIGHT_DREAM_LAG,
                        }
                        score = item.get("weight", 0.5) * WEIGHT_DREAM_LAG * 1.0
                        desc = (
                            f"You feel {ba.lower()} despite {opposite.lower()}: "
                            f"{item.get('text', '')[:60]} vs {mem_text[:60]}"
                        )
                        contradictions.append(Contradiction(
                            item_a=item, item_b=mem_item,
                            bridge_a=ba, bridge_b=opposite,
                            tension_score=score, description=desc,
                        ))
                        break  # One per memory item
                if len(contradictions) >= max_contradictions + 2:
                    break
        except Exception:
            continue  # Graph recall is best-effort

    # Step 4: Rank and cap
    contradictions.sort(key=lambda c: c.tension_score, reverse=True)
    return contradictions[:max_contradictions]


def fetch_day_residue(persona: Optional[DreamPersona] = None) -> dict:
    """
    Fetch surreal 'day residue' from multiple memory scopes to seed dreams.

    Queries 18 sources across memory, consumed content, research, tasks,
    journals, and failure patterns. Returns structured residue items with
    dream theory weighting alongside a backward-compatible prompt string.

    Args:
        persona: Persona to dream as. Defaults to Horus.

    Returns:
        dict with:
          - "prompt": combined residue text (backward compat)
          - "ids": source identifiers
          - "items": list of ResidueItem dicts (structured)
    """
    if persona is None:
        persona = DEFAULT_PERSONA

    residue_parts: list[str] = []
    items: list[dict] = []
    item_ids: list[str] = []

    def _add(label: str, text: str, source: str, weight: float):
        """Helper to append to both flat and structured lists."""
        residue_parts.append(f"{label}: {text}")
        items.append({"type": label, "text": text, "source": source, "weight": weight})

    try:
        console.print(f"[dim]Scanning memory for {persona.display_name}'s day residue...[/dim]")

        # 1. Episodic / Unresolved Tensions
        console.print("  [dim]Checking unresolved tensions...[/dim]")
        res_episodic = run_skill("episodic-archiver", ["list-unresolved"], capture=True)
        if res_episodic.get("returncode") == 0 and "No unresolved" not in res_episodic.get("stdout", ""):
            lines = res_episodic.get("stdout", "").strip().split("\n")
            _add("Unresolved Tension", "; ".join(lines[:2]), "episodic-archiver", WEIGHT_DAY_RESIDUE)
            item_ids.extend(lines[:2])

        # 2. Movies (Cinematic motifs)
        console.print("  [dim]Recalling cinematic motifs...[/dim]")
        res_movies = run_skill("memory", [
            "recall", "--q", "recurrent motif dramatic tension",
            "--scope", persona.scope("movies"), "--k", "2",
        ], capture=True)
        if res_movies.get("returncode") == 0:
            _extract_memory_result(res_movies, residue_parts, items, "Cinematic Motif", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append(f"memory:{persona.scope('movies')}:rec-motif")

        # 3. Library (Literary metaphors)
        console.print("  [dim]Recalling literary metaphors...[/dim]")
        res_books = run_skill("memory", [
            "recall", "--q", "philosophical pillar literary metaphor",
            "--scope", persona.scope("library"), "--k", "2",
        ], capture=True)
        if res_books.get("returncode") == 0:
            _extract_memory_result(res_books, residue_parts, items, "Literary Metaphor", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append(f"memory:{persona.scope('library')}:phil-pillar")

        # 4. Feeds (World echoes)
        console.print("  [dim]Sensing world echoes...[/dim]")
        res_feeds = run_skill("memory", [
            "recall", "--q", "external world echo technology shift",
            "--scope", persona.scope("feeds"), "--k", "2",
        ], capture=True)
        if res_feeds.get("returncode") == 0:
            _extract_memory_result(res_feeds, residue_parts, items, "World Echo", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append(f"memory:{persona.scope('feeds')}:world-echo")

        # 5. Music (Soundtrack anchors)
        console.print("  [dim]Recalling musical echoes...[/dim]")
        res_music = run_skill("memory", [
            "recall", "--q", "atmospheric hook rhythmic anchor soundtrack",
            "--scope", persona.scope("music"), "--k", "2",
        ], capture=True)
        if res_music.get("returncode") == 0:
            _extract_memory_result(res_music, residue_parts, items, "Music Echo", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append(f"memory:{persona.scope('music')}:echo")

        # 6. Lore (Persona/Voice Core)
        console.print("  [dim]Touching persona core...[/dim]")
        res_lore = run_skill("memory", [
            "recall", "--q", "emotional core visual echo vocal texture",
            "--scope", persona.lore_scope, "--k", "2",
        ], capture=True)
        if res_lore.get("returncode") == 0:
            _extract_memory_result(res_lore, residue_parts, items, "Subconscious Voice", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append(f"memory:{persona.lore_scope}:persona")

        # 7. Journal reflections and mood
        console.print("  [dim]Recalling journal reflections...[/dim]")
        res_journals = run_skill(
            "memory",
            ["recall", "--q", "journal reflection mood unresolved emotional", "--scope", "operational", "--k", "2"],
            capture=True,
        )
        if res_journals.get("returncode") == 0:
            _extract_memory_result(res_journals, residue_parts, items, "Journal Reflection", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append("persona-journal:reflection")

        # 8. Past dream motifs (recursive dream layer)
        console.print("  [dim]Recalling past dreams...[/dim]")
        res_dreams = run_skill("memory", [
            "recall", "--q", "dream motif visual surreal recurring image",
            "--scope", persona.scope("dreams"), "--k", "3",
        ], capture=True)
        if res_dreams.get("returncode") == 0:
            _extract_memory_result(res_dreams, residue_parts, items, "Dream Echo", "memory", WEIGHT_DREAM_LAG)
            item_ids.append(f"memory:{persona.scope('dreams')}:motif")

        # ── Consumed Content: Vivid Source Material ──

        # 9. Books — a passage that resonates
        console.print("  [dim]Searching book passages...[/dim]")
        res_books_consumed = run_skill(
            "consume-book",
            ["search", "dream surreal metaphor transformation", "--context", "200"],
            capture=True,
        )
        if res_books_consumed.get("returncode") == 0:
            stdout = res_books_consumed.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Book Fragment", stdout[:200], "consume-book", WEIGHT_DAY_RESIDUE)
                item_ids.append("consume-book:dream-passage")

        # 10. Movies — a scene fragment
        console.print("  [dim]Searching movie scenes...[/dim]")
        res_movies_consumed = run_skill(
            "consume-movie",
            ["search", "tension atmosphere surreal dream", "--context", "5"],
            capture=True,
        )
        if res_movies_consumed.get("returncode") == 0:
            stdout = res_movies_consumed.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Movie Fragment", stdout[:200], "consume-movie", WEIGHT_DAY_RESIDUE)
                item_ids.append("consume-movie:dream-scene")

        # 11. YouTube — an instructional echo
        console.print("  [dim]Searching YouTube transcripts...[/dim]")
        res_yt_consumed = run_skill(
            "consume-youtube",
            ["search", "creative process dream visual storytelling"],
            capture=True,
        )
        if res_yt_consumed.get("returncode") == 0:
            stdout = res_yt_consumed.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Tutorial Echo", stdout[:200], "consume-youtube", WEIGHT_DAY_RESIDUE)
                item_ids.append("consume-youtube:dream-echo")

        # 12. Music — a soundtrack anchor
        console.print("  [dim]Searching music catalog...[/dim]")
        res_music_consumed = run_skill(
            "consume-music",
            ["search", "atmospheric dreamlike ambient"],
            capture=True,
        )
        if res_music_consumed.get("returncode") == 0:
            stdout = res_music_consumed.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Soundtrack Anchor", stdout[:200], "consume-music", WEIGHT_DAY_RESIDUE)
                item_ids.append("consume-music:dream-anchor")

        # ── NEW Sources 13-18 ──

        # 13. Research Insights (dogpile) — external knowledge from dream themes
        themes = _extract_themes(residue_parts)
        if themes:
            console.print(f"  [dim]Researching dream themes: {themes}...[/dim]")
            res_dogpile = run_skill("dogpile", [
                "search", themes,
                "--limit", "3",
                "--fast",
            ], capture=True)
            if res_dogpile.get("returncode") == 0:
                stdout = res_dogpile.get("stdout", "").strip()
                if stdout and len(stdout) > 20:
                    # Extract first meaningful insight
                    insight = stdout[:200]
                    _add("Research Insight", insight, "dogpile", WEIGHT_DAY_RESIDUE)
                    item_ids.append("dogpile:research-insight")

        # 14. Codebase Tasks (unfinished work surfacing in dreams)
        console.print("  [dim]Scanning unfinished work...[/dim]")
        _collect_task_residue(residue_parts, items, item_ids)

        # 15. RSS/Feed World Events (consume-feed)
        console.print("  [dim]Scanning world events from feeds...[/dim]")
        res_feed = run_skill("consume-feed", [
            "search", "notable breakthrough crisis discovery",
            "--limit", "2",
        ], capture=True)
        if res_feed.get("returncode") == 0:
            stdout = res_feed.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("World Event", stdout[:200], "consume-feed", WEIGHT_DAY_RESIDUE)
                item_ids.append("consume-feed:world-event")

        # 16. Failure Patterns (monitor-episodic-archiver)
        console.print("  [dim]Checking for recurring failures...[/dim]")
        res_failures = run_skill("monitor-episodic-archiver", [
            "nightly-analysis", "--failures-only", "--limit", "2",
        ], capture=True)
        if res_failures.get("returncode") == 0:
            stdout = res_failures.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Recurring Failure", stdout[:200], "monitor-episodic-archiver", WEIGHT_DAY_RESIDUE)
                item_ids.append("monitor-episodic-archiver:failure-pattern")

        # 17. Persona Journal Direct (persona-journal skill)
        console.print("  [dim]Reading recent journal entries...[/dim]")
        res_journal_direct = run_skill("persona-journal", [
            "list", "--days", "2", "--persona", persona.id,
        ], capture=True)
        if res_journal_direct.get("returncode") == 0:
            stdout = res_journal_direct.get("stdout", "").strip()
            if stdout and len(stdout) > 20:
                _add("Journal Entry", stdout[:200], "persona-journal", WEIGHT_DAY_RESIDUE)
                item_ids.append("persona-journal:direct-entry")

        # 18. Deep Memory (semantic resonance — dream-lag effect)
        if residue_parts:
            console.print("  [dim]Probing deep memory resonance...[/dim]")
            # Use themes from current residue to find older, resonant memories
            deep_themes = _extract_themes(residue_parts[:5], max_themes=2)
            if deep_themes:
                res_deep = run_skill("memory", [
                    "recall", "--q", deep_themes,
                    "--scope", persona.lore_scope, "--k", "2",
                ], capture=True)
                if res_deep.get("returncode") == 0:
                    _extract_memory_result(
                        res_deep, residue_parts, items,
                        "Deep Memory", "memory", WEIGHT_SEMANTIC,
                    )
                    item_ids.append(f"memory:{persona.lore_scope}:deep-resonance")

        # 19. User Priors (episodic-archiver user behavior patterns)
        console.print("  [dim]Sensing user behavioral patterns...[/dim]")
        res_priors = run_skill("memory", [
            "recall", "--q", "user communication style preference expertise bridge affinity",
            "--scope", "user-priors", "--k", "2",
        ], capture=True)
        if res_priors.get("returncode") == 0:
            _extract_memory_result(res_priors, residue_parts, items, "User Prior", "episodic-archiver", WEIGHT_SEMANTIC)
            item_ids.append("episodic-archiver:user-priors")

        # 20. Fix Outcomes (what was repaired — satisfaction/frustration residue)
        console.print("  [dim]Recalling recent fix outcomes...[/dim]")
        res_fixes = run_skill("memory", [
            "recall", "--q", "fix outcome resolved success failure workaround",
            "--scope", "operational", "--k", "2",
        ], capture=True)
        if res_fixes.get("returncode") == 0:
            _extract_memory_result(res_fixes, residue_parts, items, "Fix Outcome", "memory", WEIGHT_DAY_RESIDUE)
            item_ids.append("memory:operational:fix-outcomes")

        # ── Build response ──

        if not residue_parts:
            seeds = _get_seed_residue(persona.id)
            console.print(f"[yellow]No live memories found. Using seed residue for {persona.display_name}.[/yellow]")
            prompt = "\n\n".join(f"{m['type']}: {m['text']}" for m in seeds)
            seed_items = [
                {"type": m["type"], "text": m["text"], "source": "seed", "weight": WEIGHT_DAY_RESIDUE}
                for m in seeds
            ]
            return {"prompt": prompt, "ids": ["seed:curated"], "items": seed_items}

        # ── Contradiction Detection ──
        contradictions = detect_contradictions(items, persona, max_contradictions=3)
        if contradictions:
            console.print(f"[dim]Found {len(contradictions)} contradictions:[/dim]")
            for c in contradictions:
                console.print(f"  [dim]({c.bridge_a} vs {c.bridge_b}) {c.description[:80]}[/dim]")
                items.append({
                    "type": "Contradiction",
                    "text": f"TENSION: {c.description} [{c.bridge_a} vs {c.bridge_b}]",
                    "source": f"contradiction:{c.item_a.get('source', '?')}+{c.item_b.get('source', '?')}",
                    "weight": WEIGHT_DAY_RESIDUE,
                    "recency_hours": 0,
                })

        # ── Sensory Modality Tagging + Weight Boost ──
        # Tag each item with sensory channels and boost weight based on
        # research-backed incorporation rates (PMC11202128, PMC7415562).
        # Touch/temperature/pain get the biggest boost because they cross
        # the sleep barrier most effectively. Smell modulates emotion.
        try:
            from common.taxonomy_core import extract_sensory_modalities
            for item in items:
                sensory = extract_sensory_modalities(item.get("text", ""))
                if sensory:
                    item["sensory"] = sensory
                    # Boost weight by best modality's dream incorporation rate
                    best_boost = max(
                        SENSORY_DREAM_WEIGHTS.get(mod, 0.0) for mod in sensory
                    )
                    item["weight"] = min(1.0, item.get("weight", 0.5) + best_boost)
        except ImportError:
            pass  # taxonomy not available — skip sensory tagging

        # Select ~15 items weighted by dream theory tier
        selected = _select_weighted(items, max_items=15)

        return {
            "prompt": "\n\n".join(residue_parts),
            "ids": item_ids,
            "items": selected,
            "contradictions": [
                {
                    "bridge_a": c.bridge_a,
                    "bridge_b": c.bridge_b,
                    "tension_score": c.tension_score,
                    "description": c.description,
                }
                for c in contradictions
            ],
        }

    except Exception as e:
        seeds = _get_seed_residue(persona.id)
        console.print(f"[yellow]Memory unavailable ({e}). Using seed residue for {persona.display_name}.[/yellow]")
        prompt = "\n\n".join(f"{m['type']}: {m['text']}" for m in seeds)
        seed_items = [
            {"type": m["type"], "text": m["text"], "source": "seed", "weight": WEIGHT_DAY_RESIDUE}
            for m in seeds
        ]
        return {"prompt": prompt, "ids": ["seed:fallback"], "items": seed_items}


def _extract_memory_result(
    result: dict,
    residue_parts: list,
    items: list,
    label: str,
    source: str = "memory",
    weight: float = WEIGHT_DAY_RESIDUE,
):
    """Helper to extract text from memory recall result into both flat and structured lists."""
    try:
        data = json.loads(result.get("stdout", "{}"))
        mem_items = data.get("items", [])
        if mem_items:
            item = mem_items[0]
            text = (
                item.get("solution", "")
                or item.get("title", "")
                or item.get("body", "")
                or item.get("text", "")
                or item.get("statement", "")
                or item.get("playbook", "")
            )
            if text:
                residue_parts.append(f"{label}: {text[:150]}")
                items.append({"type": label, "text": text[:150], "source": source, "weight": weight})
    except Exception:
        stdout = result.get("stdout", "").strip()
        if stdout:
            residue_parts.append(f"{label}: {stdout[:100]}")
            items.append({"type": label, "text": stdout[:100], "source": source, "weight": weight})


def _extract_themes(residue_parts: list[str], max_themes: int = 3) -> str:
    """Extract searchable themes from residue text for dogpile/deep memory."""
    combined = " ".join(residue_parts[:5])
    words = [w for w in combined.lower().split() if len(w) > 4 and w not in STOP_WORDS]
    seen: set[str] = set()
    themes: list[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            themes.append(w)
        if len(themes) >= max_themes:
            break
    return " ".join(themes)


def _collect_task_residue(residue_parts: list[str], items: list[dict], item_ids: list[str]):
    """Source 14: Read 0N_TASKS.md files for pending/in-progress items."""
    try:
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        task_files = list(project_root.glob("0N_*TASKS*.md"))
        if not task_files:
            return

        collected: list[str] = []
        for tf in task_files[:3]:  # Cap at 3 files
            text = tf.read_text(errors="ignore")
            # Extract lines that look like pending tasks
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
                    collected.append(stripped[6:].strip()[:80])
                if len(collected) >= 4:
                    break
            if len(collected) >= 4:
                break

        if collected:
            summary = "; ".join(collected[:3])
            residue_parts.append(f"Unfinished Work: {summary}")
            items.append({
                "type": "Unfinished Work",
                "text": summary,
                "source": "task-files",
                "weight": WEIGHT_DAY_RESIDUE,
            })
            item_ids.append("tasks:unfinished-work")
    except Exception as e:
        logger.debug("dream mode day residue collection failed: {}", e)


def _select_weighted(items: list[dict], max_items: int = 15) -> list[dict]:
    """Select items weighted by dream theory tier. Higher weights get priority."""
    if len(items) <= max_items:
        return items
    # Sort by weight descending, then take top N
    sorted_items = sorted(items, key=lambda x: x.get("weight", 0), reverse=True)
    return sorted_items[:max_items]


def augment_dream_style(base_style: str) -> str:
    """Augment a visual style string with dream-specific modifiers."""
    return f"{base_style}, surreal, dreamlike, non-linear, shifting geometry"


def render_shots(
    work_path: Path,
    renderer=None,
    characters_dir: Optional[Path] = None,
    monitor=None,
) -> int:
    """
    Render shots from HorusShotSpec YAML via any VideoRenderer backend.

    Args:
        work_path: Project work directory
        renderer: A VideoRenderer instance (defaults to VeoRenderer if None)
        characters_dir: Optional character identity packs directory
        monitor: Optional task monitor instance

    Returns:
        Number of shots successfully rendered
    """
    import yaml

    # Lazy default to VeoRenderer for backward compatibility
    if renderer is None:
        from core.veo_renderer import VeoRenderer
        renderer = VeoRenderer()

    manifest_path = work_path / "veo_export" / "manifest.yaml"
    if not manifest_path.exists():
        console.print("[yellow]No shot manifest found[/yellow]")
        return 0

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    shots_rendered = 0
    assets_render_dir = work_path / "assets" / "veo"
    assets_render_dir.mkdir(parents=True, exist_ok=True)
    compiled_dir = work_path / "veo_export" / "compiled"

    shot_files = list(compiled_dir.glob("*.json"))
    if monitor:
        monitor.set_description(f"Rendering via {renderer.name} (HorusShotSpec)")

    for compiled_file in shot_files:
        with open(compiled_file) as f:
            veo_request = json.load(f)

        shot_id = veo_request.get("_metadata", {}).get("shot_id", compiled_file.stem)
        console.print(f"[dim]Rendering shot {shot_id} via {renderer.name}...[/dim]")
        output_file = assets_render_dir / f"{shot_id}.mp4"

        if output_file.exists():
            console.print(f"  [dim]Skipping {shot_id} (already exists)[/dim]")
            if monitor:
                monitor.update(1)
            continue

        # Extract prompt and config from compiled request
        prompt = veo_request.get("prompt", "")
        config = veo_request.get("config", {})
        duration_s = config.get("duration_seconds", 8)
        aspect_ratio = config.get("aspect_ratio", "16:9")

        # Forward optional params (negative_prompt, seed, etc.)
        extra_kwargs = {}
        if config.get("negative_prompt"):
            extra_kwargs["negative_prompt"] = config["negative_prompt"]
        if config.get("seed") is not None:
            extra_kwargs["seed"] = config["seed"]

        result = renderer.render_shot(
            prompt=prompt,
            output_path=output_file,
            duration_s=duration_s,
            aspect_ratio=aspect_ratio,
            **extra_kwargs,
        )

        if result.success:
            shots_rendered += 1
            console.print(f"  [green]✓ Shot {shot_id} rendered[/green]")
            if monitor:
                monitor.update(1)
        else:
            console.print(f"  [yellow]✗ Shot {shot_id} failed: {result.error}[/yellow]")
            if monitor:
                monitor.fail()

    if monitor:
        monitor._update(final=True)

    console.print(f"[green]Render Complete ({renderer.name}): {shots_rendered} shots in {assets_render_dir}[/green]")
    return shots_rendered


# Backward-compatible alias
render_veo_shots = render_shots


def store_dream(
    scenes: list,
    source_ids: list,
    duration: int,
    output_path: Optional[Path] = None,
    persona: Optional[DreamPersona] = None,
) -> bool:
    """
    Store a completed dream back into memory so it alters/colors the persona.

    Each dream is stored as a lesson in the persona's dreams memory scope. Over time,
    these accumulate and feed back into dream residue queries, creating a recursive
    dream vocabulary — recurring motifs, evolving visual signatures, and narrative
    threads that persist across sessions.

    The dream is also archived as an episodic session for full context recall.

    Args:
        scenes: List of DreamScene objects (or dicts with visual_prompt, narration, etc.)
        source_ids: Memory source IDs that seeded this dream
        duration: Target duration in seconds
        output_path: Path to the generated dream movie (if any)
        persona: Persona that dreamed. Defaults to Horus.

    Returns:
        True if dream was stored successfully
    """
    if not scenes:
        return False

    if persona is None:
        persona = DEFAULT_PERSONA

    dreams_scope = persona.scope("dreams")
    timestamp = datetime.now().isoformat()
    stored = False

    # ── 1. Extract dream essence for memory storage ──
    visual_motifs = []
    narrative_threads = []
    audio_textures = []
    memory_sources = []

    for scene in scenes:
        if hasattr(scene, "visual_prompt"):
            visual_motifs.append(scene.visual_prompt[:100])
            narrative_threads.append(scene.narration[:100])
            audio_textures.append(scene.audio_cue[:80])
            if scene.memory_source:
                memory_sources.append(scene.memory_source[:60])
        elif isinstance(scene, dict):
            visual_motifs.append(scene.get("visual_prompt", "")[:100])
            narrative_threads.append(scene.get("narration", "")[:100])
            audio_textures.append(scene.get("audio_cue", "")[:80])
            src = scene.get("memory_source", "")
            if src:
                memory_sources.append(src[:60])

    dream_essence = (
        f"Visual motifs: {'; '.join(visual_motifs[:3])}\n"
        f"Narrative threads: {'; '.join(narrative_threads[:3])}\n"
        f"Audio textures: {'; '.join(audio_textures[:3])}"
    )

    # ── 2. Store dream as a memory lesson ──
    problem = (
        f"Dream generated at {timestamp} from {len(source_ids)} memory sources "
        f"({', '.join(source_ids[:5])}). "
        f"Duration: {duration}s, Scenes: {len(scenes)}."
    )
    if memory_sources:
        problem += f" Seed memories: {'; '.join(memory_sources[:3])}"

    console.print(f"[dim]Storing dream in {dreams_scope} memory...[/dim]")
    learn_result = run_skill("memory", [
        "learn",
        "--problem", problem,
        "--solution", dream_essence,
        "--scope", dreams_scope,
    ])

    if learn_result.get("returncode") == 0:
        console.print(f"[green]Dream stored in {dreams_scope} scope[/green]")
        stored = True
    else:
        error = learn_result.get("error", learn_result.get("stderr", "unknown"))
        console.print(f"[yellow]Failed to store dream: {error}[/yellow]")

    # ── 3. Archive full dream session (episodic memory) ──
    session_summary = json.dumps({
        "type": "dream_generation",
        "persona": persona.id,
        "timestamp": timestamp,
        "duration_s": duration,
        "scene_count": len(scenes),
        "source_ids": source_ids,
        "visual_motifs": visual_motifs[:5],
        "narrative_threads": narrative_threads[:3],
        "output": str(output_path) if output_path else None,
    })

    console.print("[dim]Archiving dream session...[/dim]")
    archive_result = run_skill("episodic-archiver", [
        "archive",
        "--summary", f"Dream sequence ({len(scenes)} scenes, {duration}s): {visual_motifs[0][:60] if visual_motifs else 'unknown'}",
        "--body", session_summary,
    ])

    if archive_result.get("returncode") == 0:
        console.print("[green]Dream session archived[/green]")
    else:
        console.print("[dim]Episodic archiver not available — dream still stored in memory[/dim]")

    return stored


def load_identity_packs_for_veo(characters_dir: Path) -> Optional[dict]:
    """Load identity packs from characters directory for Veo export."""
    if not characters_dir.exists():
        return None

    identity_packs = {}
    for char_dir in characters_dir.iterdir():
        if char_dir.is_dir() and (char_dir / "identity_pack").exists():
            char_name = char_dir.name
            pack_dir = char_dir / "identity_pack"
            identity_packs[char_name] = {
                "front": pack_dir / "front.png" if (pack_dir / "front.png").exists() else None,
                "three_quarter": pack_dir / "three_quarter.png" if (pack_dir / "three_quarter.png").exists() else None,
                "full_body": pack_dir / "full_body.png" if (pack_dir / "full_body.png").exists() else None,
            }

    if identity_packs:
        console.print(f"[cyan]Including identity packs for: {', '.join(identity_packs.keys())}[/cyan]")
        return identity_packs

    return None
