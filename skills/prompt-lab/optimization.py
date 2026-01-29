"""
Prompt Lab Skill - Optimization
Analysis, optimization suggestions, and prompt improvement functionality.
"""
import asyncio
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import (
    SKILL_DIR,
    TIER0_CONCEPTUAL,
    TIER1_TACTICAL,
)


def analyze_results(
    results_files: List[Path],
    prompt_name: str,
) -> Dict[str, Any]:
    """
    Analyze evaluation results for error patterns.

    Args:
        results_files: List of result JSON files
        prompt_name: Name of the prompt

    Returns:
        Analysis dict with patterns, trends, and suggestions
    """
    all_cases = []
    all_rejected = []
    all_corrections = []
    metrics_over_time = []

    for rf in results_files:
        data = json.loads(rf.read_text())

        metrics_over_time.append({
            "timestamp": data.get("timestamp", ""),
            "model": data.get("model", ""),
            "avg_f1": data.get("metrics", {}).get("avg_f1", 0),
            "correction_rounds": data.get("metrics", {}).get("correction_rounds", 0),
        })

        for case in data.get("cases", []):
            all_cases.append(case)
            if case.get("rejected"):
                all_rejected.extend(case["rejected"])
            if case.get("correction_rounds", 0) > 0:
                all_corrections.append(case)

    # Error pattern analysis
    rejected_counts = Counter(all_rejected)

    return {
        "prompt": prompt_name,
        "total_cases": len(all_cases),
        "total_rejected": len(all_rejected),
        "rejected_counts": dict(rejected_counts),
        "corrections_needed": len(all_corrections),
        "metrics_trend": metrics_over_time,
        "most_common_errors": rejected_counts.most_common(10),
    }


def generate_improvement_suggestions(
    rejected_counts: Counter,
) -> List[str]:
    """
    Generate improvement suggestions based on error patterns.

    Args:
        rejected_counts: Counter of rejected tag occurrences

    Returns:
        List of suggestion strings
    """
    suggestions = []
    common_errors = rejected_counts.most_common(5)

    for error_tag, count in common_errors:
        # Check if it's a near-miss (close to valid tag)
        for valid in TIER0_CONCEPTUAL | TIER1_TACTICAL:
            if error_tag.lower() in valid.lower() or valid.lower() in error_tag.lower():
                suggestions.append(
                    f"Add explicit mapping: '{error_tag}' -> '{valid}' in prompt"
                )
                break
        else:
            suggestions.append(
                f"Consider adding explicit instruction: 'Do NOT use \"{error_tag}\" - use the closest valid tag instead'"
            )

    return suggestions[:5]


def save_analysis_report(
    analysis: Dict[str, Any],
    skill_dir: Path = SKILL_DIR,
) -> Path:
    """
    Save analysis report to JSON file.

    Args:
        analysis: Analysis dict
        skill_dir: Skill directory

    Returns:
        Path to saved analysis file
    """
    results_dir = skill_dir / "results"
    results_dir.mkdir(exist_ok=True)

    analysis_file = results_dir / f"analysis_{analysis['prompt']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    analysis_file.write_text(json.dumps(analysis, indent=2))

    return analysis_file


def collect_error_cases(
    results_files: List[Path],
    max_files: int = 5,
) -> List[Dict[str, Any]]:
    """
    Collect error cases from result files.

    Args:
        results_files: List of result file paths
        max_files: Maximum files to process

    Returns:
        List of error case dicts
    """
    error_cases = []

    for rf in results_files[:max_files]:
        data = json.loads(rf.read_text())
        for case in data.get("cases", []):
            if case.get("rejected") or case.get("f1", 1.0) < 0.8:
                error_cases.append(case)

    return error_cases


def build_optimization_prompt(
    system_prompt: str,
    error_cases: List[Dict[str, Any]],
) -> str:
    """
    Build prompt for LLM-based optimization suggestions.

    Args:
        system_prompt: Current system prompt
        error_cases: List of error cases

    Returns:
        Optimization prompt string
    """
    prompt = f"""Analyze this taxonomy extraction prompt and suggest improvements based on the error cases below.

CURRENT PROMPT:
{system_prompt}

ERROR CASES (showing expected vs predicted):
"""
    for i, case in enumerate(error_cases[:10], 1):
        prompt += f"""
Case {i}: ID={case['id']}
  Expected: {case.get('expected', {})}
  Got: {case.get('predicted', {})}
  Rejected tags: {case.get('rejected', [])}
"""

    prompt += """

Based on these errors, suggest specific improvements to the prompt. Focus on:
1. Clarifying ambiguous tag definitions
2. Adding examples for commonly confused tags
3. Strengthening instructions to prevent hallucinated tags

Return your suggestions as a JSON object:
{"improvements": ["suggestion 1", "suggestion 2", ...], "revised_prompt_section": "..."}"""

    return prompt


def apply_prompt_improvement(
    prompt_file: Path,
    add_text: str,
) -> bool:
    """
    Apply improvement text to a prompt file.

    Args:
        prompt_file: Path to prompt file
        add_text: Text to add to prompt

    Returns:
        True if applied successfully
    """
    if not prompt_file.exists():
        return False

    current_content = prompt_file.read_text()

    # Insert improvement after the vocabulary section, before [USER]
    if "Valid tactical tags" in current_content:
        insert_point = current_content.find("[USER]")
        if insert_point > 0:
            new_content = (
                current_content[:insert_point] +
                f"\n{add_text}\n\n" +
                current_content[insert_point:]
            )
            prompt_file.write_text(new_content)
            return True

    return False


def save_optimization_report(
    prompt_name: str,
    error_cases_count: int,
    suggestions: Dict[str, Any],
    skill_dir: Path = SKILL_DIR,
) -> Path:
    """
    Save optimization suggestions to file.

    Args:
        prompt_name: Name of the prompt
        error_cases_count: Number of error cases analyzed
        suggestions: Suggestions dict from LLM
        skill_dir: Skill directory

    Returns:
        Path to saved optimization file
    """
    results_dir = skill_dir / "results"
    results_dir.mkdir(exist_ok=True)

    opt_file = results_dir / f"optimization_{prompt_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    opt_file.write_text(json.dumps({
        "prompt": prompt_name,
        "timestamp": datetime.now().isoformat(),
        "error_cases_analyzed": error_cases_count,
        "suggestions": suggestions,
    }, indent=2))

    return opt_file


def save_auto_iterate_report(
    prompt_name: str,
    model: str,
    ground_truth: str,
    target_f1: float,
    final_f1: float,
    iteration_history: List[Dict[str, Any]],
    skill_dir: Path = SKILL_DIR,
) -> Path:
    """
    Save auto-iterate optimization report.

    Args:
        prompt_name: Name of the prompt
        model: Model used
        ground_truth: Ground truth name
        target_f1: Target F1 score
        final_f1: Final achieved F1 score
        iteration_history: List of iteration results
        skill_dir: Skill directory

    Returns:
        Path to saved report file
    """
    results_dir = skill_dir / "results"
    results_dir.mkdir(exist_ok=True)

    report_file = results_dir / f"optimization_{prompt_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.write_text(json.dumps({
        "prompt": prompt_name,
        "model": model,
        "ground_truth": ground_truth,
        "timestamp": datetime.now().isoformat(),
        "target_f1": target_f1,
        "final_f1": final_f1,
        "total_rounds": len(iteration_history),
        "history": iteration_history,
    }, indent=2))

    return report_file
