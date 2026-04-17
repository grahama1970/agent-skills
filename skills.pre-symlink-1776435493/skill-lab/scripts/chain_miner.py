#!/usr/bin/env python3
"""
Mine real conversation transcripts for skill-chain training data.

Extracts (user_request, skill_chain) pairs from Claude Code and Codex session
transcripts. These pairs are the ground truth for training a classifier that
routes natural language requests to skill compositions.

Pipeline:
  transcripts → extract_sessions → label_chains → export_training_data

Training data feeds into:
  - /create-classifier (train a request→chain classifier)
  - /create-gpt (train a rationale model: WHY these skills compose)
  - skill-lab bond_predictor (validate chain predictions)

Usage:
    python chain_miner.py extract --skills-root /path/to/skills
    python chain_miner.py stats
    python chain_miner.py export --format jsonl --output chains.jsonl
    python chain_miner.py export --format csv --output chains.csv
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(help="Mine transcripts for skill-chain training data")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path(__file__).parent.parent / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CHAINS_FILE = STATE_DIR / "skill_chains.jsonl"

# Transcript source directories
TRANSCRIPT_SOURCES = [
    Path.home() / ".claude" / "projects",
    Path.home() / ".codex" / "sessions",
]

# Patterns to detect skill usage in transcript content
RUN_SH_PATTERN = re.compile(r'([a-z][a-z0-9-]+)/run\.sh')
SKILL_TOOL_PATTERN = re.compile(r'"skill"\s*:\s*"([^"]+)"')
SLASH_CMD_PATTERN = re.compile(r'(?:^|\s)/([a-z][a-z0-9-]+)(?:\s|$)', re.MULTILINE)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def discover_known_skills(skills_root: Path) -> set[str]:
    """Get set of valid skill names from skills directory."""
    if not skills_root.exists():
        return set()
    return {
        d.name for d in skills_root.iterdir()
        if d.is_dir() and not d.name.startswith('.') and (d / "SKILL.md").exists()
    }


def extract_user_request(session_content: str) -> Optional[str]:
    """Extract the first substantive user message from a session transcript."""
    lines = session_content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Claude Code format
        msg = obj.get("message", {})
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and len(text) > 10 and not text.startswith("{"):
                            return text[:500]  # Truncate long messages
            elif isinstance(content, str) and len(content) > 10:
                return content[:500]

        # Codex format
        if obj.get("type") == "message" and obj.get("role") == "user":
            content = obj.get("content", "")
            if isinstance(content, str) and len(content) > 10:
                return content[:500]

    return None


def extract_skills_used(session_content: str, known_skills: set[str]) -> list[str]:
    """Extract ordered list of skills used in a session."""
    skills_seen = []
    skills_set = set()

    # Find run.sh invocations
    for m in RUN_SH_PATTERN.finditer(session_content):
        skill = m.group(1)
        if skill in known_skills and skill not in skills_set:
            skills_seen.append(skill)
            skills_set.add(skill)

    # Find Skill tool invocations
    for m in SKILL_TOOL_PATTERN.finditer(session_content):
        skill = m.group(1)
        if skill in known_skills and skill not in skills_set:
            skills_seen.append(skill)
            skills_set.add(skill)

    return skills_seen


def mine_sessions(
    skills_root: Path,
    min_skills: int = 2,
    max_sessions: int = 0,
) -> list[dict]:
    """Mine transcript sessions for skill-chain training data."""
    known_skills = discover_known_skills(skills_root)
    if not known_skills:
        logger.error(f"No skills found at {skills_root}")
        return []

    logger.info(f"Known skills: {len(known_skills)}")

    chains = []
    processed = 0

    for source_dir in TRANSCRIPT_SOURCES:
        if not source_dir.exists():
            logger.info(f"Skipping {source_dir} (not found)")
            continue

        for jsonl_path in sorted(source_dir.rglob("*.jsonl")):
            try:
                content = jsonl_path.read_text(errors="replace")
            except OSError:
                continue

            processed += 1
            if processed % 2000 == 0:
                logger.info(f"Processed {processed} files, found {len(chains)} chains...")

            # Extract skills used
            skills = extract_skills_used(content, known_skills)
            if len(skills) < min_skills:
                continue

            # Extract user's initial request
            user_request = extract_user_request(content)
            if not user_request:
                continue

            chains.append({
                "request": user_request,
                "skills": skills,
                "skill_count": len(skills),
                "session_file": str(jsonl_path.name),
                "source": "claude" if ".claude" in str(jsonl_path) else "codex",
            })

            if max_sessions and len(chains) >= max_sessions:
                break
        if max_sessions and len(chains) >= max_sessions:
            break

    logger.info(f"Processed {processed} files, extracted {len(chains)} chains")
    return chains


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def compute_stats(chains: list[dict]) -> dict:
    """Compute statistics from extracted chains."""
    if not chains:
        return {"total_chains": 0}

    skill_freq = Counter()
    chain_lengths = []
    pair_freq = Counter()

    for chain in chains:
        skills = chain.get("skills") or chain.get("output", [])
        chain_lengths.append(len(skills))
        for s in skills:
            skill_freq[s] += 1
        # Count consecutive pairs (chain order)
        for i in range(len(skills) - 1):
            pair_freq[(skills[i], skills[i + 1])] += 1

    return {
        "total_chains": len(chains),
        "avg_chain_length": round(sum(chain_lengths) / len(chain_lengths), 1),
        "max_chain_length": max(chain_lengths),
        "unique_skills": len(skill_freq),
        "top_skills": skill_freq.most_common(20),
        "top_pairs": [(f"{a}→{b}", c) for (a, b), c in pair_freq.most_common(20)],
        "length_distribution": dict(Counter(chain_lengths).most_common(10)),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_training_data(
    chains: list[dict],
    output: Path,
    fmt: str = "jsonl",
    include_rationale_prompt: bool = False,
) -> int:
    """Export chains as training data for classifier or GPT."""
    count = 0
    with open(output, "w") as f:
        for chain in chains:
            # Support both raw format (request/skills) and exported format (input/output)
            request = chain.get("request") or chain.get("input", "")
            skills = chain.get("skills") or chain.get("output", [])
            skill_count = chain.get("skill_count", len(skills))

            if fmt == "jsonl":
                record = {
                    "input": request,
                    "output": skills,
                    "skill_count": skill_count,
                }
                if include_rationale_prompt:
                    record["rationale_prompt"] = (
                        f"Given the user request: \"{request[:200]}\"\n"
                        f"The following skills were composed: {', '.join(skills)}\n"
                        f"Explain WHY these skills work together for this task."
                    )
                f.write(json.dumps(record) + "\n")
            elif fmt == "csv":
                skills_str = "|".join(skills)
                request_clean = request.replace('"', '""')
                f.write(f'"{request_clean}","{skills_str}",{skill_count}\n')
            count += 1
    return count


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@app.command()
def extract(
    skills_root: Path = typer.Option(..., help="Path to skills directory"),
    min_skills: int = typer.Option(2, help="Minimum skills in chain"),
    max_sessions: int = typer.Option(0, help="Max sessions to process (0=all)"),
    output: Optional[Path] = typer.Option(None, help="Output file (default: state/skill_chains.jsonl)"),
):
    """Extract skill chains from conversation transcripts."""
    chains = mine_sessions(skills_root, min_skills, max_sessions)

    out_path = output or CHAINS_FILE
    count = export_training_data(chains, out_path, fmt="jsonl")
    logger.info(f"Wrote {count} chains to {out_path}")

    # Print summary stats
    stats = compute_stats(chains)
    print(f"\n=== Skill Chain Mining Results ===")
    print(f"Total chains:       {stats['total_chains']}")
    print(f"Avg chain length:   {stats.get('avg_chain_length', 0)}")
    print(f"Unique skills:      {stats.get('unique_skills', 0)}")
    print(f"\nTop skills in chains:")
    for skill, count in stats.get("top_skills", [])[:10]:
        print(f"  {count:>4}  {skill}")
    print(f"\nTop sequential pairs:")
    for pair, count in stats.get("top_pairs", [])[:10]:
        print(f"  {count:>4}  {pair}")


@app.command()
def stats():
    """Show statistics from previously extracted chains."""
    if not CHAINS_FILE.exists():
        print("No chains file found. Run 'extract' first.")
        raise typer.Exit(1)

    chains = []
    with open(CHAINS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chains.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    s = compute_stats(chains)
    print(f"=== Skill Chain Stats ===")
    print(f"Total chains:       {s['total_chains']}")
    print(f"Avg chain length:   {s.get('avg_chain_length', 0)}")
    print(f"Max chain length:   {s.get('max_chain_length', 0)}")
    print(f"Unique skills:      {s.get('unique_skills', 0)}")
    print(f"\nTop skills:")
    for skill, c in s.get("top_skills", []):
        print(f"  {c:>4}  {skill}")
    print(f"\nTop pairs:")
    for pair, c in s.get("top_pairs", []):
        print(f"  {c:>4}  {pair}")
    print(f"\nChain length distribution:")
    for length, c in sorted(s.get("length_distribution", {}).items()):
        print(f"  {length} skills: {c} chains")


@app.command()
def export(
    output: Path = typer.Option(..., help="Output file path"),
    fmt: str = typer.Option("jsonl", help="Format: jsonl or csv"),
    with_rationale: bool = typer.Option(False, help="Include rationale prompts for GPT training"),
):
    """Export extracted chains for classifier/GPT training."""
    if not CHAINS_FILE.exists():
        print("No chains file found. Run 'extract' first.")
        raise typer.Exit(1)

    chains = []
    with open(CHAINS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chains.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    count = export_training_data(chains, output, fmt, with_rationale)
    print(f"Exported {count} chains to {output} ({fmt})")


@app.command()
def prepare(
    output_dir: Path = typer.Option(
        STATE_DIR / "training", help="Output directory for training data"
    ),
    min_request_len: int = typer.Option(20, help="Min request length to include"),
    top_skills: int = typer.Option(50, help="Top N skills for classifier labels"),
):
    """Prepare training data for /create-classifier and /create-gpt."""
    if not CHAINS_FILE.exists():
        print("No chains file found. Run 'extract' first.")
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    chains = []
    with open(CHAINS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chains.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not chains:
        print("No chains loaded.")
        raise typer.Exit(1)

    # Filter quality chains
    quality_chains = []
    for c in chains:
        request = c.get("input") or c.get("request", "")
        skills = c.get("output") or c.get("skills", [])
        if len(request) >= min_request_len and 2 <= len(skills) <= 20:
            quality_chains.append({"request": request, "skills": skills})

    logger.info(f"Quality chains: {len(quality_chains)} / {len(chains)}")

    # Find top skills for labels
    skill_freq = Counter()
    for c in quality_chains:
        for s in c["skills"]:
            skill_freq[s] += 1
    top_skill_set = {s for s, _ in skill_freq.most_common(top_skills)}

    # --- Format for /create-classifier (multi-label) ---
    classifier_path = output_dir / "classifier_multilabel.jsonl"
    clf_count = 0
    with open(classifier_path, "w") as f:
        for i, c in enumerate(quality_chains):
            # Multi-label: each skill present in chain is a positive label
            labels = [s for s in c["skills"] if s in top_skill_set]
            if not labels:
                continue
            record = {
                "id": f"chain_{i:05d}",
                "task": "skill_chain_classifier",
                "input": {"text": c["request"][:500]},
                "label": "|".join(labels),  # pipe-separated multi-label
                "labels": labels,
                "confidence": 1.0,
                "source": "transcript_mining",
            }
            f.write(json.dumps(record) + "\n")
            clf_count += 1

    # --- Format for /create-gpt (rationale generation) ---
    gpt_path = output_dir / "gpt_rationale.jsonl"
    gpt_count = 0
    with open(gpt_path, "w") as f:
        for i, c in enumerate(quality_chains):
            record = {
                "input": {
                    "request": c["request"][:500],
                    "available_skills": sorted(top_skill_set),
                },
                "output": {
                    "skills": c["skills"],
                    "skill_count": len(c["skills"]),
                    "rationale_prompt": (
                        f"The user requested: \"{c['request'][:200]}\"\n"
                        f"Skills composed: {', '.join(c['skills'])}\n"
                        f"Explain WHY these skills work together."
                    ),
                },
            }
            f.write(json.dumps(record) + "\n")
            gpt_count += 1

    # --- Create task YAML for /create-gpt ---
    task_yaml_path = output_dir / "chain_rationale_task.yaml"
    task_yaml = f"""name: chain-rationale
description: >
  Given a user request, predict which skills should be composed and explain why.
  Trained on {gpt_count} real conversation transcripts from embry-os sessions.
base_model: Qwen/Qwen2.5-1.5B-Instruct
max_seq_length: 512
system_prompt: |
  You are a skill-chain routing assistant for embry-os. Given a user request,
  predict which skills should be composed to fulfill it. Output JSON with the
  selected skills and a brief rationale explaining why they work together.

  Available skills include: {', '.join(sorted(list(top_skill_set)[:30]))}
  (and {len(top_skill_set) - 30} more)

input_schema:
  type: object
  required: [request]
  properties:
    request:
      type: string
      description: The user's natural language request

output_schema:
  type: object
  required: [skills, rationale_prompt]
  properties:
    skills:
      type: array
      items:
        type: string
      description: Ordered list of skills to compose
    skill_count:
      type: integer
    rationale_prompt:
      type: string
      description: Explanation of why these skills compose

reward_weights:
  format: 0.2
  accuracy: 0.6
  grounding: 0.2

eval_thresholds:
  accuracy: 0.70
  format_valid: 0.90
  latency_p50_ms: 1000

training:
  lora_r: 16
  lora_alpha: 32
  sft_epochs: 3
  quality_threshold: 0.70
  max_iterations: 3
  hp_trials: 5
"""
    task_yaml_path.write_text(task_yaml)

    # --- Summary ---
    print(f"\n=== Training Data Prepared ===")
    print(f"Quality chains:   {len(quality_chains)} / {len(chains)}")
    print(f"Top skills:       {len(top_skill_set)}")
    print(f"")
    print(f"Classifier data:  {classifier_path} ({clf_count} records)")
    print(f"GPT data:         {gpt_path} ({gpt_count} records)")
    print(f"Task YAML:        {task_yaml_path}")
    print(f"")
    print(f"Next steps:")
    print(f"  1. Train classifier:")
    print(f"     .pi/skills/create-classifier/run.sh train-text \\")
    print(f"       --task skill_chain_classifier \\")
    print(f"       --labels {classifier_path}")
    print(f"  2. Train GPT:")
    print(f"     .pi/skills/create-gpt/run.sh define \\")
    print(f"       --name chain-rationale \\")
    print(f"       --from-yaml {task_yaml_path}")
    print(f"     .pi/skills/create-gpt/run.sh prepare \\")
    print(f"       --task chain-rationale \\")
    print(f"       --input {gpt_path}")
    print(f"     .pi/skills/create-gpt/run.sh train \\")
    print(f"       --task chain-rationale --sft-only")


if __name__ == "__main__":
    app()
