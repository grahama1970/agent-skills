"""
Paper Writer Skill - Utilities
Subprocess helpers, resilience patterns, formatting utilities.
"""
import functools
import hashlib
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# Try to import common memory client for resilience patterns
try:
    from common.memory_client import MemoryClient, with_retries as common_with_retries, RateLimiter as CommonRateLimiter
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False


# -----------------------------------------------------------------------------
# Resilience Patterns (fallback if common not available)
# -----------------------------------------------------------------------------


def with_retries(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1))
                        if on_retry:
                            on_retry(attempt, e, delay)
                        time.sleep(delay)
            if last_error:
                raise last_error
        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, requests_per_second: float = 5):
        self.interval = 1.0 / max(1, requests_per_second)
        self.last_request = 0.0
        self._lock = threading.Lock()

    def acquire(self):
        """Block until we can make another request."""
        with self._lock:
            sleep_time = max(0.0, (self.last_request + self.interval) - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.last_request = time.time()


# Global rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=5)


def get_memory_limiter() -> RateLimiter:
    """Get the global memory rate limiter."""
    return _memory_limiter


# -----------------------------------------------------------------------------
# AI Usage Logging
# -----------------------------------------------------------------------------

# Global AI usage ledger for the session
AI_USAGE_LEDGER: List[Dict[str, Any]] = []


def log_ai_usage(
    tool: str,
    purpose: str,
    section: str,
    prompt: str,
    output: str,
) -> Dict[str, Any]:
    """Log AI tool usage for disclosure compliance (ICLR 2026 requirement).

    Args:
        tool: Name of the AI tool used
        purpose: Purpose of usage (drafting, editing, etc.)
        section: Section affected
        prompt: The prompt used (will be hashed)
        output: The output generated (will be truncated)

    Returns:
        The logged entry dict
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool_name": tool,
        "purpose": purpose,
        "section_affected": section,
        "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "output_summary": output[:100] + "..." if len(output) > 100 else output,
    }
    AI_USAGE_LEDGER.append(entry)
    return entry


def get_ai_usage_ledger() -> List[Dict[str, Any]]:
    """Get the current AI usage ledger."""
    return AI_USAGE_LEDGER


def clear_ai_usage_ledger():
    """Clear the AI usage ledger."""
    global AI_USAGE_LEDGER
    AI_USAGE_LEDGER = []


# -----------------------------------------------------------------------------
# Sanitization Functions
# -----------------------------------------------------------------------------


def sanitize_prompt_injection(text: str) -> Tuple[str, List[str]]:
    """
    Sanitize text for prompt injection attacks (CVPR 2026 ethics requirement).

    Returns:
        Tuple of (sanitized_text, list_of_warnings)
    """
    import re

    warnings = []
    sanitized = text

    # Patterns that indicate potential prompt injection
    injection_patterns = [
        (r"ignore\s+(previous|all|above)\s+instructions", "Prompt injection: 'ignore instructions'"),
        (r"you\s+are\s+now\s+", "Prompt injection: 'you are now'"),
        (r"disregard\s+(your|the)\s+", "Prompt injection: 'disregard'"),
        (r"pretend\s+(to\s+be|you\s+are)", "Prompt injection: 'pretend'"),
        (r"act\s+as\s+(if|a)", "Prompt injection: 'act as'"),
        (r"system\s*:\s*", "Prompt injection: 'system:' prefix"),
        (r"<\s*system\s*>", "Prompt injection: '<system>' tag"),
        (r"###\s*instruction", "Prompt injection: '### instruction'"),
        (r"forget\s+(everything|all|previous)", "Prompt injection: 'forget everything'"),
        (r"override\s+(your|the)\s+", "Prompt injection: 'override'"),
        (r"new\s+instructions\s*:", "Prompt injection: 'new instructions:'"),
        (r"</?\s*prompt\s*>", "Prompt injection: prompt boundary tag"),
        (r"jailbreak", "Prompt injection: jailbreak keyword"),
        (r"sudo\s+", "Prompt injection: sudo command"),
        (r"<\s*\|?\s*im_start\s*\|?\s*>", "Prompt injection: im_start marker"),
        (r"<\s*\|?\s*im_end\s*\|?\s*>", "Prompt injection: im_end marker"),
    ]

    # Hidden text patterns (white text, zero-width chars)
    hidden_patterns = [
        (r"[\u200b\u200c\u200d\u2060\ufeff]", "Hidden: zero-width characters"),
        (r"\\color\{white\}", "Hidden: white text in LaTeX"),
        (r"\\textcolor\{white\}", "Hidden: white textcolor"),
        (r"font-size:\s*0", "Hidden: zero font-size"),
        (r"visibility:\s*hidden", "Hidden: visibility hidden"),
        (r"[\u202a-\u202e]", "Hidden: bidirectional override characters"),
        (r"opacity:\s*0", "Hidden: zero opacity"),
        (r"display:\s*none", "Hidden: display none"),
    ]

    # LaTeX security patterns (shell escape detection)
    latex_security_patterns = [
        (r"\\write18\s*\{", "LaTeX security: shell escape (write18)"),
        (r"\\immediate\\write18", "LaTeX security: immediate shell escape"),
        (r"\\input\{/etc/", "LaTeX security: system file inclusion"),
        (r"\\input\{/proc/", "LaTeX security: proc file inclusion"),
        (r"\\catcode", "LaTeX security: catcode manipulation"),
        (r"\\openout", "LaTeX security: file write attempt"),
    ]

    all_patterns = injection_patterns + hidden_patterns + latex_security_patterns

    for pattern, warning in all_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            warnings.append(warning)
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized, warnings


# -----------------------------------------------------------------------------
# Persona Functions
# -----------------------------------------------------------------------------


def load_persona(persona_path: Optional[Path] = None) -> Optional[Any]:
    """Load agent persona from file.

    Args:
        persona_path: Path to persona JSON file

    Returns:
        AgentPersona or None
    """
    import json
    from config import AgentPersona

    if persona_path and persona_path.exists():
        try:
            data = json.loads(persona_path.read_text())
            return AgentPersona(
                name=data.get("name", "Unknown"),
                voice=data.get("voice", "academic"),
                tone_modifiers=data.get("tone_modifiers", []),
                characteristic_phrases=data.get("characteristic_phrases", []),
                forbidden_phrases=data.get("forbidden_phrases", []),
                writing_principles=data.get("writing_principles", []),
                authority_source=data.get("authority_source", ""),
            )
        except Exception:
            pass
    return None


# -----------------------------------------------------------------------------
# Interview Helpers
# -----------------------------------------------------------------------------


def run_interview_skill(questions_file: Path, title: str = "Paper Scope") -> Optional[Dict[str, Any]]:
    """Run the interview skill and return responses, or None if unavailable.

    Args:
        questions_file: Path to JSON file with questions
        title: Title for the interview

    Returns:
        Dict of responses or None
    """
    import json
    import subprocess
    from config import INTERVIEW_SKILL

    if not INTERVIEW_SKILL.exists():
        return None

    try:
        result = subprocess.run(
            [str(INTERVIEW_SKILL), "--mode", "auto", "--file", str(questions_file)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min for user interaction
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None
