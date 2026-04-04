"""Harvest skill-chain training data from Claude CLI transcripts.

Scans ~/.claude/projects/ for real user questions that led to skill
invocations. Extracts (question, skill_chain) pairs for training
the /recommend-skill-chain classifier.

Inputs:
    ~/.claude/projects/**/*.jsonl — Claude CLI conversation transcripts

Outputs:
    JSONL with format matching /assistant training pipeline:
    {"input": {"text": "..."}, "output": {"prediction": "skill1,skill2", ...},
     "teacher_grade": "skill1,skill2", "source": "transcript_mining"}

Failures:
    - Skips non-parseable lines
    - Skips system/progress messages
    - Deduplicates by question text hash
"""

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

# Known skill names that are relevant for code/pipeline questions
CODE_SKILLS = frozenset({
    "treesitter", "memory", "review-code", "review-pdf", "analytics",
    "corpus-report", "extractor-quality-check", "create-figure",
    "create-table-classifier", "classifier-lab", "create-classifier",
    "table-lab", "pdf-lab", "debug-pdf", "debug-table", "assess",
    "test", "treesitter", "taxonomy", "learn-datalake", "extractor",
    "review-conversation", "data-audit", "quality-audit", "monitor-pdfs",
    "batch-report", "ingest-doc", "review-pdf",
})

# All known skill names (for general chain extraction)
ALL_SKILLS = frozenset({
    "memory", "treesitter", "review-code", "review-pdf", "analytics",
    "corpus-report", "extractor-quality-check", "create-figure",
    "create-table-classifier", "classifier-lab", "create-classifier",
    "table-lab", "pdf-lab", "debug-pdf", "assess", "test", "taxonomy",
    "learn-datalake", "extractor", "review-conversation", "data-audit",
    "quality-audit", "monitor-pdfs", "batch-report", "ingest-doc",
    "dogpile", "brave-search", "perplexity", "arxiv", "context7",
    "recommend-skill-chain", "assistant", "create-paper", "review-paper",
    "create-persona", "review-persona", "episodic-archiver",
    "mine-transcripts", "skill-lab", "skills-ci", "checkpoint",
    "ops-chutes", "ops-arango", "ops-docker", "ops-workstation",
    "monitor-memory", "monitor-skills", "monitor-codebase",
    "review-design", "create-react-designs", "create-image",
    "formalize-request", "orchestrate", "plan", "interview",
    "review-question", "doc2qra", "ingest-youtube", "consume-book",
})

# Skip these — not real task descriptions
SKIP_PATTERNS = [
    re.compile(r"^proceed\s*$", re.I),
    re.compile(r"^continue\s*$", re.I),
    re.compile(r"^yes\s*$", re.I),
    re.compile(r"^no\s*$", re.I),
    re.compile(r"^ok\s*$", re.I),
    re.compile(r"^y$", re.I),
    re.compile(r"^n$", re.I),
    re.compile(r"^This session is being continued", re.I),
    re.compile(r"^\[Request interrupted", re.I),
    re.compile(r"^```"),
    re.compile(r"^Base directory for this skill:", re.I),  # SKILL.md preamble
    re.compile(r"^# /", re.I),  # SKILL.md heading
]

SKILL_RUN_PATTERN = re.compile(r"/skills/([^/]+)/run\.sh")


def _extract_user_text(msg: dict) -> str:
    """Extract plain text from a user message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c["text"])
        return " ".join(parts)
    return str(content) if content else ""


def _extract_skills_from_assistant(msg: dict) -> list[str]:
    """Extract skill names invoked in an assistant message."""
    skills = []
    content = msg.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return skills

    for c in content:
        if not isinstance(c, dict):
            continue
        if c.get("type") != "tool_use":
            continue

        name = c.get("name", "")
        inp = c.get("input", {})

        if name == "Bash":
            cmd = inp.get("command", "")
            for m in SKILL_RUN_PATTERN.finditer(cmd):
                skill = m.group(1)
                # Clean up skill name (sometimes captured with && or spaces)
                skill = skill.split("&&")[0].split(";")[0].strip()
                if skill in ALL_SKILLS:
                    skills.append(skill)

        elif name == "Skill":
            skill = inp.get("skill", "")
            if skill in ALL_SKILLS:
                skills.append(skill)

    return skills


def _is_task_or_question(text: str) -> bool:
    """Check if text is a real task/question (not a confirmation or system prompt).

    Deliberately permissive — we want to capture task descriptions,
    not just questions. A human saying "fix the auth bug" or
    "deploy to staging" is valid training data.
    """
    text = text.strip()
    if len(text) < 15:
        return False
    for pat in SKIP_PATTERNS:
        if pat.search(text):
            return False
    # Accept anything that isn't filtered above — the user said something
    # meaningful before the agent invoked a skill.
    return True


def _categorize_chain(skills: list[str]) -> str:
    """Determine the category for a skill chain."""
    code_skills = {"treesitter", "review-code", "test"}
    pipeline_skills = {
        "extractor-quality-check", "review-pdf", "learn-datalake",
        "corpus-report", "batch-report", "monitor-pdfs",
    }
    analytics_skills = {"analytics", "create-figure", "data-audit", "quality-audit"}
    research_skills = {"dogpile", "brave-search", "perplexity", "arxiv", "context7"}

    skill_set = set(skills)
    if skill_set & code_skills:
        return "code_trace"
    if skill_set & pipeline_skills:
        return "pipeline_analytics"
    if skill_set & analytics_skills:
        return "analytics"
    if skill_set & research_skills:
        return "research"
    return "general"


def harvest_transcript(fpath: str) -> list[dict]:
    """Harvest (question, skill_chain) pairs from a single transcript."""
    pairs = []
    last_user_text = ""

    try:
        with open(fpath) as f:
            for line in f:
                try:
                    d = json.loads(line.strip())
                except (json.JSONDecodeError, ValueError):
                    continue

                msg_type = d.get("type", "")

                if msg_type == "user":
                    text = _extract_user_text(d)
                    if text and len(text) > 10:
                        # Use first 300 chars — captures the task, not system prompts
                        last_user_text = text[:300]

                elif msg_type == "assistant" and last_user_text:
                    skills = _extract_skills_from_assistant(d)
                    if skills and _is_task_or_question(last_user_text):
                        # Deduplicate skills while preserving order
                        seen = set()
                        unique_skills = []
                        for s in skills:
                            if s not in seen:
                                seen.add(s)
                                unique_skills.append(s)

                        chain_str = ",".join(unique_skills)
                        category = _categorize_chain(unique_skills)

                        pairs.append({
                            "input": {"text": last_user_text[:300]},
                            "output": {
                                "prediction": chain_str,
                                "confidence": 0.95,
                                "domain": "code" if category in ("code_trace", "pipeline_analytics") else "general",
                                "category": category,
                            },
                            "teacher_grade": chain_str,
                            "source": "transcript_mining",
                            "source_file": os.path.basename(fpath),
                        })
    except Exception as e:
        logger.debug(f"Error reading {fpath}: {e}")

    return pairs


def harvest_all(
    projects_dir: str = None,
    max_files: int = 0,
    code_only: bool = True,
) -> list[dict]:
    """Harvest from all Claude CLI transcripts."""
    if projects_dir is None:
        projects_dir = os.path.expanduser("~/.claude/projects")

    all_files = sorted(
        Path(projects_dir).rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if max_files:
        all_files = all_files[:max_files]

    logger.info(f"Scanning {len(all_files)} transcript files...")

    all_pairs = []
    seen_hashes = set()

    for i, fpath in enumerate(all_files):
        if i % 500 == 0 and i > 0:
            logger.info(f"  ...scanned {i}/{len(all_files)} files, {len(all_pairs)} pairs so far")

        pairs = harvest_transcript(str(fpath))

        for pair in pairs:
            # Deduplicate by question text hash
            text = pair["input"]["text"]
            h = hashlib.sha256(text.encode()).hexdigest()[:16]
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            # Optional: filter to code/pipeline skills only
            if code_only:
                skills = set(pair["output"]["prediction"].split(","))
                if not skills & CODE_SKILLS:
                    continue

            all_pairs.append(pair)

    logger.info(f"Harvested {len(all_pairs)} unique pairs from {len(all_files)} files")
    return all_pairs


def main(
    max_files: int = typer.Option(0, "--max-files", help="Limit number of transcript files (0=all)"),
    all_skills: bool = typer.Option(False, "--all-skills", help="Include non-code skills too"),
    output: Optional[str] = typer.Option(None, "--output", help="Output JSONL path"),
    stats: bool = typer.Option(False, "--stats", help="Print stats only, don't write"),
) -> None:
    """Harvest skill-chain training data from transcripts."""
    pairs = harvest_all(
        max_files=max_files,
        code_only=not all_skills,
    )

    # Stats
    chain_counts = Counter(p["output"]["prediction"] for p in pairs)
    category_counts = Counter(p["output"]["category"] for p in pairs)

    print(f"\n=== HARVEST STATS ===")
    print(f"Total unique pairs: {len(pairs)}")
    print(f"\nTop 20 chains:")
    for chain, count in chain_counts.most_common(20):
        print(f"  {count:4d}x  {chain}")
    print(f"\nCategories:")
    for cat, count in category_counts.most_common():
        print(f"  {count:4d}x  {cat}")

    if stats:
        return

    # Write output
    output_path = output or os.path.expanduser(
        "~/.pi/assistant/training_data/skill-chain-router/labels_mined_v1.jsonl"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        for pair in pairs:
            f.write(json.dumps(pair, default=str) + "\n")

    print(f"\nWrote {len(pairs)} pairs to {output_path}")


if __name__ == "__main__":
    typer.run(main)
