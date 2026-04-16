#!/usr/bin/env python3
"""
Memory Quality Scorer with Contradiction Reachability.

Scores a memory on four axes:
  1. content_quality  — Is the text event-grounded with sensory detail?
  2. taxonomy_quality — Are bridge attributes accurate?
  3. contradiction_reachable — Can an opposing memory be found via graph traversal?
  4. bridge_distribution — Does the memory add diversity to the persona's bridge mix?

Key output: _conflict_ref metadata for every memory that has a reachable contradiction.

Note: contradiction checks call memory recall and can take up to ~30s per bridge; use --no-contradiction to skip.

Usage (as library):
    from memory_quality_scorer import score_memory, MemoryQualityResult

Usage (CLI):
    python memory_quality_scorer.py score --text "..." --scope horus-lore
    python memory_quality_scorer.py batch --input data/memory_quality_labels.jsonl
"""

import os
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Add common skills to path
SKILLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILLS_DIR))
sys.path.insert(0, str(SKILLS_DIR / "common"))

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)

# Bridge opposition map — canonical
BRIDGE_OPPOSITIONS = {
    "Fragility": "Resilience",
    "Resilience": "Fragility",
    "Corruption": "Loyalty",
    "Loyalty": "Corruption",
    "Stealth": "Precision",
    "Precision": "Stealth",
    "Intimacy": "Stealth",
}


@dataclass
class ConflictRef:
    """Reference to a contradicting memory found via graph traversal."""
    key: str                    # ArangoDB _key of opposing memory
    bridge: str                 # Opposing bridge attribute
    text: str                   # First 120 chars of opposing memory text
    tension_score: float        # 0.0-1.0 strength of opposition


@dataclass
class MemoryQualityResult:
    """Full quality assessment of a memory."""
    # Content grounding
    content_quality: str = ""       # grounded | thin | ambiguous
    has_event_anchor: bool = False
    has_sensory: bool = False
    sensory_modalities: list = field(default_factory=list)
    text_length: int = 0

    # Taxonomy accuracy
    taxonomy_quality: str = ""      # correct | vague | missing | wrong
    bridges_extracted: list = field(default_factory=list)
    bridges_stored: list = field(default_factory=list)
    has_literal_bridge: bool = False

    # Contradiction reachability
    contradiction_reachable: bool = False
    conflict_ref: Optional[ConflictRef] = None

    # Bridge distribution (populated by batch scorer)
    bridge_distribution_score: float = 0.0

    # Deficits
    deficits: list = field(default_factory=list)

    # Overall score 0.0-1.0
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["conflict_ref"] is None:
            d["conflict_ref"] = None
        return d

    def to_metadata(self) -> dict:
        """Return just the _conflict_ref fields for memory metadata."""
        if self.conflict_ref:
            return {
                "_conflict_ref": self.conflict_ref.key,
                "_conflict_bridge": self.conflict_ref.bridge,
                "_conflict_text": self.conflict_ref.text[:120],
                "_quality_score": round(self.overall_score, 3),
            }
        return {
            "_conflict_ref": None,
            "_conflict_bridge": None,
            "_conflict_text": None,
            "_quality_score": round(self.overall_score, 3),
        }


def _has_event_anchor(text: str) -> bool:
    """Check if text references a specific event, entity, or temporal marker."""
    patterns = [
        r"\b[A-Z][a-z]{2,}\b",  # Proper nouns
        r"\b(yesterday|today|last\s+\w+|during|when|after|before)\b",
        r"\b(at\s+the|in\s+the|on\s+the)\b",
        r"\b(watched|built|destroyed|held|broke|completed|deployed|ran|fought|burned|shattered)\b",
    ]
    matches = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
    return matches >= 2


def _has_literal_bridge_name(text: str, bridges: list) -> bool:
    """Check if text uses literal bridge names as descriptors (bad signal)."""
    text_lower = text.lower()
    for bridge in bridges:
        bl = bridge.lower()
        if bl in text_lower:
            patterns = [
                rf"\bfeel\s+{bl}\b",
                rf"\bfelt\s+{bl}\b",
                rf"\bis\s+{bl}\b",
                rf"\bwas\s+{bl}\b",
                rf"\bseems?\s+{bl}\b",
                rf"\b{bl}\s+today\b",
            ]
            if any(re.search(p, text_lower) for p in patterns):
                return True
    return False


def _recall_opposing(text: str, bridges: list, scope: str) -> Optional[ConflictRef]:
    """Search for an opposing memory via memory recall (triggers graph BFS).

    For each bridge, looks for a memory tagged with its opposite.
    Returns the strongest contradiction found.
    """
    if not bridges or not MEMORY_RUN_SH.exists():
        return None

    best = None
    best_score = 0.0

    for bridge in bridges[:2]:  # Check top 2 bridges max
        opposite = BRIDGE_OPPOSITIONS.get(bridge)
        if not opposite:
            continue

        # Build query with opposing bridge keywords
        query = f"{opposite.lower()} {text[:80]}"
        cmd = [
            "bash", str(MEMORY_RUN_SH),
            "recall",
            "--q", query,
            "--scope", scope,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(MEMORY_RUN_SH.parent),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            stdout = result.stdout.strip()
            if not stdout:
                continue

            data = None
            for line in stdout.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            if not data:
                try:
                    data = json.loads(stdout)
                except json.JSONDecodeError:
                    continue

            items = data.get("items", [])
            for item in items:
                item_bridges = item.get("bridge_attributes", [])
                item_text = f"{item.get('problem', '')} {item.get('solution', '')}".strip()

                # Check if this item has the opposing bridge
                if opposite in item_bridges:
                    score = 0.8  # Strong: stored bridge matches
                elif any(b in BRIDGE_OPPOSITIONS.get(bridge, "") for b in item_bridges):
                    score = 0.5  # Moderate: related opposition
                else:
                    # Re-extract bridges from text
                    try:
                        from taxonomy_core import get_bridge_attributes
                        reextracted = get_bridge_attributes(item_text)
                        if opposite in reextracted:
                            score = 0.6
                        else:
                            continue
                    except ImportError:
                        continue

                if score > best_score:
                    best_score = score
                    best = ConflictRef(
                        key=item.get("_key", "unknown"),
                        bridge=opposite,
                        text=item_text[:120],
                        tension_score=score,
                    )

        except Exception:
            continue

    return best


def score_memory(
    text: str,
    scope: str = "",
    bridges_stored: list | None = None,
    check_contradiction: bool = True,
) -> MemoryQualityResult:
    """Score a single memory on all quality axes.

    Args:
        text: The memory text (problem + solution concatenated).
        scope: Memory scope for contradiction recall.
        bridges_stored: Bridge attributes already stored with the memory.
        check_contradiction: Whether to do graph recall (slower).

    Returns:
        MemoryQualityResult with all scores and _conflict_ref if found.
    """
    if bridges_stored is None:
        bridges_stored = []

    # Import taxonomy
    try:
        from taxonomy_core import get_bridge_attributes, extract_sensory_modalities
        bridges_extracted = get_bridge_attributes(text)
        sensory = extract_sensory_modalities(text)
    except ImportError:
        bridges_extracted = []
        sensory = []

    # ── Content Quality ──
    has_event = _has_event_anchor(text)
    has_sensory = len(sensory) > 0
    has_bridges = len(bridges_extracted) > 0
    text_length = len(text)

    if has_event and has_sensory and has_bridges and text_length > 80:
        content_quality = "grounded"
    elif has_bridges and (has_event or has_sensory) and text_length > 40:
        content_quality = "thin"
    else:
        content_quality = "ambiguous"

    # ── Taxonomy Quality ──
    literal_bridge = _has_literal_bridge_name(text, bridges_stored or bridges_extracted)

    if not bridges_stored and not bridges_extracted:
        taxonomy_quality = "missing"
    elif literal_bridge:
        taxonomy_quality = "vague"
    elif bridges_stored:
        if bridges_extracted and set(bridges_extracted) & set(bridges_stored):
            taxonomy_quality = "correct"
        elif bridges_extracted and not (set(bridges_extracted) & set(bridges_stored)):
            taxonomy_quality = "wrong"
        else:
            taxonomy_quality = "correct"
    else:
        taxonomy_quality = "vague"

    # ── Deficits ──
    deficits = []
    if not has_event:
        deficits.append("no_event_anchor")
    if not has_sensory:
        deficits.append("no_sensory")
    if not has_bridges:
        deficits.append("no_bridges")
    if literal_bridge:
        deficits.append("literal_bridge_name")
    if text_length < 40:
        deficits.append("too_short")

    # ── Contradiction Reachability ──
    conflict_ref = None
    contradiction_reachable = False
    if check_contradiction and scope and bridges_extracted:
        conflict_ref = _recall_opposing(text, bridges_extracted, scope)
        contradiction_reachable = conflict_ref is not None

    if not contradiction_reachable:
        deficits.append("no_contradiction_reachable")

    # ── Overall Score ──
    score = 0.0
    # Content grounding: 0.35
    if content_quality == "grounded":
        score += 0.35
    elif content_quality == "thin":
        score += 0.15

    # Taxonomy accuracy: 0.25
    if taxonomy_quality == "correct":
        score += 0.25
    elif taxonomy_quality == "vague":
        score += 0.10

    # Contradiction reachable: 0.25
    if contradiction_reachable:
        score += 0.25 * (conflict_ref.tension_score if conflict_ref else 0.5)

    # Sensory richness: 0.15
    sensory_score = min(1.0, len(sensory) / 3.0)  # 3+ modalities = max
    score += 0.15 * sensory_score

    return MemoryQualityResult(
        content_quality=content_quality,
        has_event_anchor=has_event,
        has_sensory=has_sensory,
        sensory_modalities=sensory,
        text_length=text_length,
        taxonomy_quality=taxonomy_quality,
        bridges_extracted=bridges_extracted,
        bridges_stored=bridges_stored,
        has_literal_bridge=literal_bridge,
        contradiction_reachable=contradiction_reachable,
        conflict_ref=conflict_ref,
        deficits=deficits,
        overall_score=round(score, 3),
    )


import typer
import httpx

app = typer.Typer(help="Memory Quality Scorer")


@app.command()
def score(
    text: str = typer.Option(..., help="Memory text to score"),
    scope: str = typer.Option("", help="Memory scope for contradiction check"),
    bridges: Optional[list[str]] = typer.Option(None, help="Stored bridge attributes"),
    no_contradiction: bool = typer.Option(False, "--no-contradiction", help="Skip contradiction check"),
):
    result = score_memory(
        text=text,
        scope=scope,
        bridges_stored=bridges or [],
        check_contradiction=not no_contradiction,
    )
    print(json.dumps(result.to_dict(), indent=2))


@app.command()
def batch(
    input: str = typer.Option(..., "--input", help="Input JSONL file"),
    output: Optional[str] = typer.Option(None, "--output", help="Output JSONL file (default: stdout)"),
    no_contradiction: bool = typer.Option(False, "--no-contradiction", help="Skip contradiction checks"),
):
    results = []
    with open(input) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            text = item.get("text", "")
            scope = item.get("scope", "")
            bridges_list = item.get("bridges_stored", [])

            result = score_memory(
                text=text,
                scope=scope,
                bridges_stored=bridges_list,
                check_contradiction=not no_contradiction,
            )
            out = {**item, **result.to_dict()}
            results.append(out)

    if output:
        with open(output, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"Wrote {len(results)} scored memories to {output}")
    else:
        for r in results:
            print(json.dumps(r))


if __name__ == "__main__":
    app()
