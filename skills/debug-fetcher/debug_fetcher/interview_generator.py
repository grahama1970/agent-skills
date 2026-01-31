"""Interview generator for human-in-the-loop collaboration.

Generates /interview-compatible JSON for unrecoverable URLs,
allowing humans to provide credentials, mirror URLs, or other help.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlparse

from .batch_analyzer import analyze_batch
from .strategy_engine import StrategyResult


def generate_interview(
    failures: List[StrategyResult],
    max_questions: int = 20,
    group_by_domain: bool = True,
) -> Dict[str, Any]:
    """Generate /interview-compatible JSON for failed URLs.

    Creates questions for each unrecoverable URL with options:
    - I have credentials (login/password)
    - Try this mirror URL
    - I'll download manually
    - Skip this URL
    - Retry later

    Args:
        failures: List of failed StrategyResult
        max_questions: Maximum number of questions to generate
        group_by_domain: If True, group URLs by domain into fewer questions

    Returns:
        Dict compatible with /interview skill
    """
    # Filter to only truly unrecoverable
    unrecoverable = [f for f in failures if f.winning_strategy == "all_failed"]

    if not unrecoverable:
        return {
            "title": "No Failures Requiring Attention",
            "context": "All URLs were either fetched successfully or had partial success.",
            "questions": [],
        }

    # Analyze to get patterns
    analysis = analyze_batch(failures)

    # Build context message
    context_parts = [
        f"I tried all automated strategies but couldn't fetch {len(unrecoverable)} URLs.",
        f"Total attempts: {sum(len(f.attempts) for f in unrecoverable)}",
    ]
    if analysis.patterns:
        context_parts.append("Detected patterns:")
        for pattern in analysis.patterns[:3]:
            context_parts.append(f"  - {pattern}")

    context = "\n".join(context_parts)

    # Generate questions
    if group_by_domain:
        questions = _generate_domain_grouped_questions(unrecoverable, max_questions)
    else:
        questions = _generate_per_url_questions(unrecoverable, max_questions)

    return {
        "title": "Fetcher Needs Help",
        "context": context,
        "questions": questions,
    }


def _generate_per_url_questions(
    failures: List[StrategyResult],
    max_questions: int,
) -> List[Dict[str, Any]]:
    """Generate one question per URL."""
    questions = []

    for result in failures[:max_questions]:
        url = result.url

        # Get error info
        error_info = "All strategies failed"
        if result.final_attempt:
            if result.final_attempt.status_code:
                error_info = f"HTTP {result.final_attempt.status_code}"
            if result.final_attempt.content_verdict:
                error_info += f" ({result.final_attempt.content_verdict})"
            if result.final_attempt.error:
                error_info = result.final_attempt.error

        # Parse domain for header
        try:
            domain = urlparse(url).hostname or "unknown"
        except Exception:
            domain = "unknown"

        questions.append({
            "id": f"url_{hash(url) % 10000:04x}",
            "header": domain[:12],  # Max 12 chars for header
            "text": f"Failed to fetch:\n{url}\n\nError: {error_info}\nAttempts: {len(result.attempts)}",
            "options": [
                {
                    "label": "I have credentials",
                    "description": "I can provide login credentials for this site",
                },
                {
                    "label": "Try this mirror",
                    "description": "I know an alternate URL or archive link",
                },
                {
                    "label": "I'll download manually",
                    "description": "I'll get the file and provide the path",
                },
                {
                    "label": "Skip it",
                    "description": "Not critical, move on without this URL",
                },
            ],
            "multi_select": False,
        })

    return questions


def _generate_domain_grouped_questions(
    failures: List[StrategyResult],
    max_questions: int,
) -> List[Dict[str, Any]]:
    """Generate questions grouped by domain."""
    # Group by domain
    by_domain: Dict[str, List[StrategyResult]] = {}
    for result in failures:
        try:
            domain = urlparse(result.url).hostname or "unknown"
        except Exception:
            domain = "unknown"

        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(result)

    # Sort domains by failure count
    sorted_domains = sorted(by_domain.items(), key=lambda x: len(x[1]), reverse=True)

    questions = []

    for domain, results in sorted_domains[:max_questions]:
        # Sample URLs for this domain
        sample_urls = [r.url for r in results[:3]]
        url_list = "\n".join(f"  - {u}" for u in sample_urls)
        if len(results) > 3:
            url_list += f"\n  ... and {len(results) - 3} more"

        # Common error
        errors = [r.final_attempt.error or r.final_attempt.content_verdict
                  for r in results if r.final_attempt]
        common_error = errors[0] if errors else "Unknown"

        questions.append({
            "id": f"domain_{hash(domain) % 10000:04x}",
            "header": domain[:12],
            "text": f"Failed {len(results)} URLs from {domain}:\n{url_list}\n\nCommon error: {common_error}",
            "options": [
                {
                    "label": "I have credentials",
                    "description": f"Login credentials for {domain}",
                },
                {
                    "label": "Try different strategy",
                    "description": "Suggest a specific approach (proxy, VPN, etc.)",
                },
                {
                    "label": "Skip all",
                    "description": f"Skip all {len(results)} URLs from this domain",
                },
                {
                    "label": "Handle individually",
                    "description": "Show me each URL separately",
                },
            ],
            "multi_select": False,
        })

    return questions


def generate_interview_file(
    failures: List[StrategyResult],
    output_path: str,
    **kwargs,
) -> str:
    """Generate interview JSON and write to file.

    Args:
        failures: List of failed StrategyResult
        output_path: Path to write JSON file
        **kwargs: Passed to generate_interview

    Returns:
        Path to generated file
    """
    interview_data = generate_interview(failures, **kwargs)

    with open(output_path, "w") as f:
        json.dump(interview_data, f, indent=2)

    return output_path
