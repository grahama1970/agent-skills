#!/usr/bin/env python3
"""Mine conversation transcripts for bridge classifier training data.

Extracts user messages from Claude conversation logs and labels them
using the taxonomy skill for bridge extraction.

The goal: train the classifier on REAL human communication patterns,
not synthetic templates. Two-tier training:
1. Developer (Graham) - baseline attunement
2. Client - specific adaptation

Integrates with:
- /taxonomy - for bridge label extraction
- /memory - for deduplication before storage
- /scheduler - for nightly runs

Usage:
    # Mine transcripts using taxonomy for labels
    python mine_transcripts.py --transcripts ~/.claude/projects \
        --output data/bridge_classifier/mined.jsonl

    # Mine and export for human review
    python mine_transcripts.py --transcripts ~/.claude/projects \
        --output data/bridge_classifier/for_review.jsonl \
        --sample 500

    # After human review, merge into training set
    python mine_transcripts.py --merge \
        data/bridge_classifier/reviewed.jsonl \
        data/bridge_classifier/train.jsonl
"""

import typer
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Iterator

from loguru import logger

SKILL_DIR = Path(__file__).parent.parent
PI_SKILLS = SKILL_DIR.parent  # .pi/skills/
TAXONOMY_SKILL = PI_SKILLS / "taxonomy"
MEMORY_SKILL = PI_SKILLS / "memory"

# Import from taxonomy skill
sys.path.insert(0, str(TAXONOMY_SKILL))
try:
    from taxonomy import extract_keywords, BRIDGE_TAGS, BRIDGE_KEYWORDS
    BRIDGE_LABELS = list(BRIDGE_TAGS)
except ImportError:
    logger.warning("Taxonomy skill not found, using fallback bridge labels")
    BRIDGE_LABELS = ["Corruption", "Precision", "Resilience", "Fragility", "Loyalty", "Stealth"]
    BRIDGE_TAGS = set(BRIDGE_LABELS)
    BRIDGE_KEYWORDS = {}
    def extract_keywords(text: str) -> list[str]:
        return []

BRIDGE_INFERENCE = SKILL_DIR / "scripts" / "bridge_inference.py"


def iter_transcripts(transcripts_dir: Path) -> Iterator[Path]:
    """Iterate over all transcript JSONL files."""
    for jsonl in transcripts_dir.rglob("*.jsonl"):
        # Skip agent outputs and non-conversation files
        if "agent-" in jsonl.name:
            continue
        yield jsonl


# Default CLI agent transcript locations
CLI_AGENT_SOURCES = {
    "claude": Path.home() / ".claude" / "projects",
    "codex_history": Path.home() / ".codex" / "history.jsonl",
    "codex_sessions": Path.home() / ".codex" / "sessions",
    # Add more as they exist
}


def extract_codex_messages(history_path: Path) -> list[dict]:
    """Extract messages from Codex history.jsonl.

    Codex format: {"session_id": ..., "ts": ..., "text": ...}
    This is PURE human input - no system prompts!
    """
    messages = []
    try:
        with open(history_path, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    text = msg.get("text", "").strip()
                    if is_real_human_message(text) and len(text) < 1000:
                        messages.append({
                            "text": text,
                            "source": f"codex:{msg.get('session_id', 'unknown')}",
                            "timestamp": msg.get("ts"),
                            "hash": text_hash(text),
                        })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Error reading Codex history: {e}")
    return messages


def discover_all_cli_sources() -> dict[str, Path]:
    """Discover all available CLI agent transcript sources."""
    sources = {}
    for name, path in CLI_AGENT_SOURCES.items():
        if path.exists():
            sources[name] = path
            logger.info(f"Found CLI source: {name} at {path}")
    return sources


# Patterns that indicate system-injected prompts (not real human messages)
SYSTEM_PROMPT_PATTERNS = [
    "You are an expert",
    "You are a",
    "<system",
    "Provide a high-reasoning",
    "Return only",
    "Given this query",
    "Given the following",
    "Design Rules:",
    "Use a 24x24",
    "As an expert",
    "Your task is",
    "Create a",
    "Generate a",
    "Analyze the",
    "Based on the",
]


def is_real_human_message(content: str) -> bool:
    """Check if content is a real human message vs system-injected prompt."""
    content = content.strip()

    # Skip empty or too short
    if len(content) < 20:
        return False

    # Skip commands
    if content.startswith("/"):
        return False

    # Skip XML tags (system messages)
    if content.startswith("<"):
        return False

    # Skip system-injected prompts
    content_lower = content.lower()
    for pattern in SYSTEM_PROMPT_PATTERNS:
        if content_lower.startswith(pattern.lower()):
            return False

    # Skip task/agent notifications
    if any(tag in content for tag in ["task-id>", "output-file>", "agent-id>", "task-notification"]):
        return False

    return True


def extract_user_messages(transcript_path: Path) -> list[dict]:
    """Extract real human messages from a transcript.

    Filters out:
    - System-injected prompts (skill templates)
    - Commands (/foo)
    - XML tagged messages
    - Agent/task notifications
    """
    messages = []
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "user":
                        content = msg.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            content = content.strip()
                            # Only include real human messages
                            if is_real_human_message(content) and len(content) < 1000:
                                messages.append({
                                    "text": content,
                                    "source": str(transcript_path),
                                    "timestamp": msg.get("timestamp"),
                                    "hash": text_hash(content),
                                })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Error reading {transcript_path}: {e}")
    return messages


def bootstrap_labels(text: str, threshold: float = 0.4) -> list[str]:
    """Use existing classifier to bootstrap labels."""
    try:
        result = subprocess.run(
            [sys.executable, str(BRIDGE_INFERENCE), text, "--all", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(SKILL_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            bridges = json.loads(result.stdout)
            # Return bridges above threshold
            return [k for k, v in bridges.items() if v >= threshold]
    except Exception as e:
        logger.debug(f"Bootstrap failed: {e}")
    return []


def detect_emotional_state(text: str) -> dict:
    """Detect emotional state - both frustration AND satisfaction/happiness."""
    text_lower = text.lower()

    # Frustration signals
    frustration_signals = [
        "wrong", "not what", "error", "failed", "no!",
        "frustrat", "livid", "angry", "annoyed", "stop",
        "shouldn't", "why did", "you crashed", "crashed",
        "not working", "broken", "useless", "terrible",
        "disappointed", "confused", "stuck", "blocked",
    ]

    # Satisfaction/happiness signals - VERY IMPORTANT
    satisfaction_signals = [
        "perfect", "great", "thanks", "excellent", "good job",
        "works", "working", "correct", "yes!", "nice",
        "love it", "exactly", "brilliant", "amazing", "awesome",
        "happy", "pleased", "satisfied", "impressed", "well done",
        "that's it", "nailed it", "spot on", "beautiful",
        "finally", "makes sense", "understand now", "got it",
        "proceed", "continue", "looks good", "ship it",
    ]

    # Neutral progress signals
    progress_signals = [
        "ok", "next", "continue", "proceed", "go ahead",
        "move on", "what's next", "then", "now",
    ]

    state = {
        "frustrated": any(sig in text_lower for sig in frustration_signals),
        "satisfied": any(sig in text_lower for sig in satisfaction_signals),
        "progressing": any(sig in text_lower for sig in progress_signals),
        "unresolved": "unresolved" in text_lower or "still broken" in text_lower,
    }

    # Intensity estimation
    frustration_count = sum(1 for sig in frustration_signals if sig in text_lower)
    satisfaction_count = sum(1 for sig in satisfaction_signals if sig in text_lower)

    if frustration_count >= 2:
        state["intensity"] = "high_frustration"
    elif satisfaction_count >= 2:
        state["intensity"] = "very_satisfied"
    elif state["satisfied"]:
        state["intensity"] = "satisfied"
    elif state["frustrated"]:
        state["intensity"] = "frustrated"
    else:
        state["intensity"] = "neutral"

    return state


def extract_bridges_from_keywords(text: str) -> list[str]:
    """Extract bridges using taxonomy skill + emotional awareness.

    Uses taxonomy skill's extract_keywords for the core bridge extraction,
    then enhances with emotional context from the conversation.
    """
    # Use taxonomy skill's comprehensive keyword extraction
    bridges = extract_keywords(text)

    # Detect emotional state for context enhancement
    emotional = detect_emotional_state(text)
    text_lower = text.lower()

    # Emotional context enriches bridge detection:

    # Frustrated users often signal Fragility in the system
    if emotional["frustrated"] and "Fragility" not in bridges:
        bridges.append("Fragility")

    # Satisfied users indicate Resilience (system worked/recovered)
    if emotional["satisfied"] and "Resilience" not in bridges:
        bridges.append("Resilience")

    # Satisfaction + understanding signals strong Loyalty (good collaboration)
    if emotional["satisfied"] or any(w in text_lower for w in ["understand", "attune", "human", "real world"]):
        if "Loyalty" not in bridges:
            bridges.append("Loyalty")

    # High satisfaction indicates both Resilience AND Loyalty
    if emotional.get("intensity") == "very_satisfied":
        if "Resilience" not in bridges:
            bridges.append("Resilience")
        if "Loyalty" not in bridges:
            bridges.append("Loyalty")

    return bridges


def text_hash(text: str) -> str:
    """Generate a hash for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def mine_transcripts(
    transcripts_dir: Path,
    output_path: Path,
    bootstrap: bool = False,
    sample_size: int = 0,
    min_per_source: int = 1,  # Reduced from 5 - we want more real messages
    existing_hashes: set = None,
) -> int:
    """Mine transcripts for training data with deduplication.

    Args:
        transcripts_dir: Directory containing transcript JSONL files
        output_path: Output JSONL file
        bootstrap: Use classifier to bootstrap labels
        sample_size: If >0, sample this many examples
        min_per_source: Minimum messages per transcript to include
        existing_hashes: Set of hashes for already-seen examples (dedup)

    Returns:
        Number of examples mined
    """
    all_messages = []
    seen_hashes = existing_hashes or set()
    duplicates_skipped = 0

    logger.info(f"Mining transcripts from {transcripts_dir}")
    if existing_hashes:
        logger.info(f"Deduplicating against {len(existing_hashes)} existing examples")

    transcript_count = 0
    for transcript_path in iter_transcripts(transcripts_dir):
        messages = extract_user_messages(transcript_path)
        if len(messages) >= min_per_source:
            for msg in messages:
                msg_hash = msg.get("hash", text_hash(msg["text"]))
                if msg_hash in seen_hashes:
                    duplicates_skipped += 1
                    continue
                seen_hashes.add(msg_hash)
                all_messages.append(msg)
            transcript_count += 1

        if transcript_count % 100 == 0 and transcript_count > 0:
            logger.info(f"Processed {transcript_count} transcripts, {len(all_messages)} unique messages")

    logger.info(f"Total: {transcript_count} transcripts, {len(all_messages)} unique messages")
    if duplicates_skipped > 0:
        logger.info(f"Skipped {duplicates_skipped} duplicates")

    # Sample if requested
    if sample_size > 0 and len(all_messages) > sample_size:
        all_messages = random.sample(all_messages, sample_size)
        logger.info(f"Sampled {sample_size} messages")

    # Label messages
    labeled = []
    for i, msg in enumerate(all_messages):
        if bootstrap:
            labels = bootstrap_labels(msg["text"])
        else:
            labels = extract_bridges_from_keywords(msg["text"])

        if labels:  # Only include if we got labels
            labeled.append({
                "text": msg["text"],
                "labels": labels,
                "source": msg["source"],
                "bootstrap": bootstrap,
            })

        if (i + 1) % 100 == 0:
            logger.info(f"Labeled {i + 1}/{len(all_messages)}")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for ex in labeled:
            f.write(json.dumps({
                "text": ex["text"],
                "labels": ex["labels"],
            }) + "\n")

    logger.info(f"Saved {len(labeled)} labeled examples to {output_path}")
    return len(labeled)


def mine_all_cli_agents(
    output_path: Path,
    sample_size: int = 0,
    existing_hashes: set = None,
) -> int:
    """Mine from ALL discovered CLI agent sources.

    Sources:
    - Claude: ~/.claude/projects/**/*.jsonl
    - Codex history: ~/.codex/history.jsonl (pure human input)
    - Codex sessions: ~/.codex/sessions/**/*.jsonl

    This enables training on real human communication patterns
    from the developer (first tier) before client adaptation (second tier).
    """
    all_messages = []
    seen_hashes = existing_hashes or set()
    duplicates_skipped = 0

    sources = discover_all_cli_sources()
    logger.info(f"Discovered {len(sources)} CLI agent sources")

    for source_name, source_path in sources.items():
        logger.info(f"Mining {source_name}...")

        if source_name == "codex_history":
            # Codex history.jsonl has a different format
            messages = extract_codex_messages(source_path)
            for msg in messages:
                msg_hash = msg.get("hash", text_hash(msg["text"]))
                if msg_hash in seen_hashes:
                    duplicates_skipped += 1
                    continue
                seen_hashes.add(msg_hash)
                all_messages.append(msg)
            logger.info(f"  {source_name}: {len(messages)} messages")

        elif source_path.is_dir():
            # Directory of JSONL files (Claude, Codex sessions)
            transcript_count = 0
            msg_count = 0
            for transcript_path in iter_transcripts(source_path):
                messages = extract_user_messages(transcript_path)
                for msg in messages:
                    msg_hash = msg.get("hash", text_hash(msg["text"]))
                    if msg_hash in seen_hashes:
                        duplicates_skipped += 1
                        continue
                    seen_hashes.add(msg_hash)
                    all_messages.append(msg)
                    msg_count += 1
                transcript_count += 1
            logger.info(f"  {source_name}: {msg_count} messages from {transcript_count} transcripts")

    logger.info(f"Total: {len(all_messages)} unique messages from all sources")
    if duplicates_skipped > 0:
        logger.info(f"Skipped {duplicates_skipped} duplicates")

    # Sample if requested
    if sample_size > 0 and len(all_messages) > sample_size:
        all_messages = random.sample(all_messages, sample_size)
        logger.info(f"Sampled {sample_size} messages")

    # Label messages using taxonomy skill
    labeled = []
    for i, msg in enumerate(all_messages):
        labels = extract_bridges_from_keywords(msg["text"])
        if labels:
            labeled.append({
                "text": msg["text"],
                "labels": labels,
                "source": msg.get("source", "unknown"),
            })

        if (i + 1) % 500 == 0:
            logger.info(f"Labeled {i + 1}/{len(all_messages)}")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for ex in labeled:
            f.write(json.dumps({
                "text": ex["text"],
                "labels": ex["labels"],
            }) + "\n")

    logger.info(f"Saved {len(labeled)} labeled examples to {output_path}")
    return len(labeled)


def merge_datasets(reviewed_path: Path, train_path: Path):
    """Merge reviewed data into training set."""
    # Load existing training data
    existing = {}
    if train_path.exists():
        with open(train_path) as f:
            for line in f:
                ex = json.loads(line)
                existing[ex["text"]] = ex

    # Add reviewed data (overwrites if duplicate)
    with open(reviewed_path) as f:
        for line in f:
            ex = json.loads(line)
            existing[ex["text"]] = ex

    # Save merged
    with open(train_path, "w") as f:
        for ex in existing.values():
            f.write(json.dumps({"text": ex["text"], "labels": ex["labels"]}) + "\n")

    logger.info(f"Merged to {len(existing)} total examples in {train_path}")


def load_existing_hashes(data_path: Path) -> set:
    """Load hashes from existing training data for deduplication."""
    hashes = set()
    if not data_path.exists():
        return hashes
    try:
        with open(data_path) as f:
            for line in f:
                ex = json.loads(line)
                hashes.add(text_hash(ex.get("text", "")))
    except Exception as e:
        logger.warning(f"Failed to load existing hashes: {e}")
    return hashes


def analyze_coverage(data_path: Path):
    """Analyze bridge coverage in dataset."""
    counts = {b: 0 for b in BRIDGE_LABELS}
    total = 0

    with open(data_path) as f:
        for line in f:
            ex = json.loads(line)
            total += 1
            for label in ex.get("labels", []):
                if label in counts:
                    counts[label] += 1

    print(f"\nBridge Coverage ({total} examples):")
    print("-" * 40)
    for bridge, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"{bridge:12} {count:5} ({pct:5.1f}%) {bar}")


app = typer.Typer(help="Mine transcripts for bridge classifier data")


@app.command()
def main(
    transcripts: str = typer.Option(None, help="Transcripts directory"),
    output: str = typer.Option(None, help="Output JSONL file"),
    all_agents: bool = typer.Option(False, help=""),
    bootstrap: bool = typer.Option(False, help="Use classifier to bootstrap labels"),
    sample: int = typer.Option(0, help=""),
    merge: str = typer.Option(None, help=""),
    analyze: str = typer.Option(None, help="Analyze coverage in dataset"),
    dedupe: str = typer.Option(None, help="Deduplicate against existing JSONL file"),
    seed: int = typer.Option(42, help=""),
):
    random.seed(seed)

    if merge:
        merge_datasets(Path(merge[0]), Path(merge[1]))
        return

    if analyze:
        analyze_coverage(analyze)
        return

    # Load existing hashes for deduplication
    existing_hashes = None
    if dedupe:
        existing_hashes = load_existing_hashes(dedupe)
        logger.info(f"Loaded {len(existing_hashes)} existing hashes for deduplication")

    # Mine from all CLI agents
    if all_agents:
        if not output:
            parser.error("--output required when using --all-agents")
        count = mine_all_cli_agents(
            output,
            sample_size=sample,
            existing_hashes=existing_hashes,
        )
    elif transcripts and output:
        count = mine_transcripts(
            transcripts,
            output,
            bootstrap=bootstrap,
            sample_size=sample,
            existing_hashes=existing_hashes,
        )
    else:
        parser.error("--transcripts and --output required for mining (or use --all-agents)")

    # Analyze result
    if count > 0:
        analyze_coverage(output)


if __name__ == "__main__":
    app()
