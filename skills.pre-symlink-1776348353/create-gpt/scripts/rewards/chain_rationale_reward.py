"""Chain-rationale task reward for GRPO training.

Combines three signals per the chain-rationale task YAML reward_weights:
  - format: 0.2 (valid JSON with skills array, skill_count, rationale_prompt)
  - accuracy: 0.6 (Jaccard similarity against ground truth skills)
  - grounding: 0.2 (rationale mentions at least one skill name)

Ground truth is loaded from the query file at init time.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


# Global ground truth lookup: query text -> list of skills
_GT_LOOKUP: dict[str, list[str]] = {}
_KNOWN_SKILLS: set[str] = set()


def init_ground_truth(query_file: Path) -> None:
    """Load ground truth from GRPO query JSONL file."""
    global _GT_LOOKUP, _KNOWN_SKILLS
    with open(query_file) as f:
        for line in f:
            rec = json.loads(line.strip())
            key = rec["input"][:200]  # truncate for matching
            _GT_LOOKUP[key] = rec["ground_truth_skills"]
            _KNOWN_SKILLS.update(rec["ground_truth_skills"])
    logger.info(f"Loaded {len(_GT_LOOKUP)} ground truth entries, {len(_KNOWN_SKILLS)} known skills")


def compute_reward(output: dict, input_dict: dict, reference: dict = None) -> float:
    """Compute chain-rationale reward combining format + accuracy + grounding.

    Args:
        output: Parsed JSON output from model (or {"raw": ...} if parse failed)
        input_dict: Input context (has "text" key with original request)
        reference: Optional reference (unused, GT comes from _GT_LOOKUP)

    Returns:
        Reward score in [0, 1]
    """
    # Check if parse failed
    if "raw" in output and len(output) == 1:
        return 0.0

    # --- Format score (weight: 0.2) ---
    skills = output.get("skills", [])
    rationale = output.get("rationale_prompt", "")
    skill_count = output.get("skill_count")

    format_score = 0.0
    if isinstance(skills, list) and len(skills) > 0:
        format_score += 0.4
        if all(isinstance(s, str) for s in skills):
            format_score += 0.2
    if isinstance(rationale, str) and len(rationale) > 10:
        format_score += 0.2
    if isinstance(skill_count, int) and skill_count == len(skills):
        format_score += 0.2

    # --- Accuracy score (weight: 0.6) ---
    accuracy_score = 0.0
    request_text = input_dict.get("text", "")
    gt_key = request_text[:200]
    gt_skills = _GT_LOOKUP.get(gt_key, [])

    if gt_skills and isinstance(skills, list):
        pred_set = set(s.lower().strip() for s in skills if isinstance(s, str))
        gt_set = set(s.lower().strip() for s in gt_skills)
        if pred_set or gt_set:
            jaccard = len(pred_set & gt_set) / len(pred_set | gt_set) if (pred_set | gt_set) else 0.0
            accuracy_score = jaccard

    # --- Grounding score (weight: 0.2) ---
    grounding_score = 0.0
    if isinstance(rationale, str) and isinstance(skills, list):
        rationale_lower = rationale.lower()
        mentioned = sum(1 for s in skills if isinstance(s, str) and s.lower() in rationale_lower)
        if len(skills) > 0:
            grounding_score = min(1.0, mentioned / max(1, len(skills)))

    # Combine with task YAML weights
    combined = 0.2 * format_score + 0.6 * accuracy_score + 0.2 * grounding_score
    return combined
