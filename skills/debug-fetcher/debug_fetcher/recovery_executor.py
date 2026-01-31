"""Recovery executor for human-provided actions.

Executes recovery actions based on human input from /interview,
such as trying mirror URLs, using provided credentials, or
processing manually downloaded files.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .memory_bridge import learn_strategy
from .memory_schema import RecoveryAction
from .strategy_engine import StrategyEngine, StrategyResult, FetchAttempt


def execute_recovery(
    actions: List[RecoveryAction],
    output_dir: Optional[Path] = None,
) -> List[StrategyResult]:
    """Execute recovery actions from human input.

    Args:
        actions: List of RecoveryAction from interview processor
        output_dir: Directory to store recovered files

    Returns:
        List of StrategyResult for each action
    """
    results = []

    for action in actions:
        result = _execute_single_action(action, output_dir)
        results.append(result)

        # Store successful recoveries in /memory
        if result.success and action.action_type != "skip":
            _store_recovery_learning(action, result)

    return results


def _execute_single_action(
    action: RecoveryAction,
    output_dir: Optional[Path] = None,
) -> StrategyResult:
    """Execute a single recovery action.

    Args:
        action: RecoveryAction to execute
        output_dir: Directory for output files

    Returns:
        StrategyResult
    """
    if action.action_type == "skip":
        return StrategyResult(
            url=action.url,
            success=True,  # Skip is "successful" in that we handled it
            winning_strategy="skipped",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="skip",
                success=True,
                metadata={"skipped": True, "reason": action.notes},
            ),
        )

    elif action.action_type == "mirror":
        return _try_mirror_url(action)

    elif action.action_type == "manual_file":
        return _process_manual_file(action, output_dir)

    elif action.action_type == "credentials":
        return _try_with_credentials(action)

    elif action.action_type == "retry":
        return _schedule_retry(action)

    elif action.action_type == "custom_strategy":
        return _try_custom_strategy(action)

    else:
        # Unknown action type
        return StrategyResult(
            url=action.url,
            success=False,
            winning_strategy="unknown_action",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="unknown",
                success=False,
                error=f"Unknown action type: {action.action_type}",
            ),
        )


def _try_mirror_url(action: RecoveryAction) -> StrategyResult:
    """Try fetching from a mirror URL.

    Args:
        action: RecoveryAction with mirror_url

    Returns:
        StrategyResult
    """
    if not action.mirror_url:
        return StrategyResult(
            url=action.url,
            success=False,
            winning_strategy="mirror_failed",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="mirror",
                success=False,
                error="No mirror URL provided",
            ),
        )

    # Fetch the mirror URL
    engine = StrategyEngine(enable_memory=False)  # Don't learn from mirror
    result = engine.exhaust_strategies(action.mirror_url)

    # Update result to reference original URL
    if result.success:
        result.winning_strategy = "mirror"
        if result.final_attempt:
            result.final_attempt.metadata["original_url"] = action.url
            result.final_attempt.metadata["mirror_url"] = action.mirror_url

    # Keep original URL for tracking
    result.url = action.url

    return result


def _process_manual_file(
    action: RecoveryAction,
    output_dir: Optional[Path] = None,
) -> StrategyResult:
    """Process a manually downloaded file.

    Args:
        action: RecoveryAction with file_path
        output_dir: Directory to copy file to

    Returns:
        StrategyResult
    """
    if not action.file_path:
        return StrategyResult(
            url=action.url,
            success=False,
            winning_strategy="manual_failed",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="manual",
                success=False,
                error="No file path provided",
            ),
        )

    file_path = Path(action.file_path).expanduser()

    if not file_path.exists():
        return StrategyResult(
            url=action.url,
            success=False,
            winning_strategy="manual_failed",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="manual",
                success=False,
                error=f"File not found: {file_path}",
            ),
        )

    # Copy to output directory if specified
    final_path = file_path
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / file_path.name
        shutil.copy2(file_path, final_path)

    return StrategyResult(
        url=action.url,
        success=True,
        winning_strategy="manual",
        final_attempt=FetchAttempt(
            url=action.url,
            strategy="manual",
            success=True,
            content_length=file_path.stat().st_size,
            file_path=str(final_path),
            metadata={
                "source": "manual_download",
                "original_path": str(file_path),
            },
        ),
    )


def _try_with_credentials(action: RecoveryAction) -> StrategyResult:
    """Try fetching with provided credentials.

    Note: This is a placeholder. Full credential handling
    would require integration with authenticated fetch.

    Args:
        action: RecoveryAction with credentials

    Returns:
        StrategyResult
    """
    # For now, just record that credentials were provided
    # Full implementation would use Playwright with login flow
    return StrategyResult(
        url=action.url,
        success=False,
        winning_strategy="credentials_pending",
        final_attempt=FetchAttempt(
            url=action.url,
            strategy="credentials",
            success=False,
            error="Credential-based fetch not yet implemented",
            metadata={
                "credentials_provided": bool(action.credentials),
                "hint": action.credentials.get("hint") if action.credentials else None,
            },
        ),
    )


def _schedule_retry(action: RecoveryAction) -> StrategyResult:
    """Schedule a URL for retry later.

    Args:
        action: RecoveryAction with retry_after

    Returns:
        StrategyResult marking URL as pending
    """
    return StrategyResult(
        url=action.url,
        success=False,  # Not yet successful
        winning_strategy="retry_scheduled",
        final_attempt=FetchAttempt(
            url=action.url,
            strategy="retry",
            success=False,
            error="Scheduled for retry",
            metadata={
                "retry_after_seconds": action.retry_after or 3600,
                "reason": action.notes,
            },
        ),
    )


def _try_custom_strategy(action: RecoveryAction) -> StrategyResult:
    """Try a user-suggested custom strategy.

    Args:
        action: RecoveryAction with notes describing strategy

    Returns:
        StrategyResult
    """
    # Parse user notes for strategy hints
    notes = (action.notes or "").lower()

    strategies_to_try = []

    if "proxy" in notes or "vpn" in notes:
        strategies_to_try.append("proxy")
    if "playwright" in notes or "browser" in notes or "js" in notes:
        strategies_to_try.append("playwright")
    if "wayback" in notes or "archive" in notes:
        strategies_to_try.append("wayback")
    if "jina" in notes:
        strategies_to_try.append("jina")

    if not strategies_to_try:
        return StrategyResult(
            url=action.url,
            success=False,
            winning_strategy="custom_failed",
            final_attempt=FetchAttempt(
                url=action.url,
                strategy="custom",
                success=False,
                error=f"Could not parse strategy from: {action.notes}",
            ),
        )

    # Try suggested strategies
    engine = StrategyEngine(strategies=strategies_to_try, enable_memory=True)
    return engine.exhaust_strategies(action.url)


def _store_recovery_learning(action: RecoveryAction, result: StrategyResult) -> None:
    """Store successful recovery in /memory for future reference.

    Args:
        action: The recovery action that worked
        result: The successful result
    """
    strategy_name = result.winning_strategy

    # Map action types to strategy names for memory
    if action.action_type == "mirror" and action.mirror_url:
        # Store that this URL has a known mirror
        learn_strategy(
            url=action.url,
            strategy_used="mirror",
            human_provided=True,
            human_notes=f"Mirror: {action.mirror_url}",
            tags=["human_provided", "mirror"],
        )

    elif action.action_type == "manual":
        # Store that this URL required manual download
        learn_strategy(
            url=action.url,
            strategy_used="manual_required",
            human_provided=True,
            human_notes=action.notes,
            tags=["human_provided", "manual"],
        )

    elif action.action_type == "custom_strategy":
        # Store the custom strategy that worked
        timing = result.final_attempt.timing_ms if result.final_attempt else 0
        learn_strategy(
            url=action.url,
            strategy_used=strategy_name,
            timing_ms=timing,
            human_provided=True,
            human_notes=action.notes,
            tags=["human_provided", "custom"],
        )
