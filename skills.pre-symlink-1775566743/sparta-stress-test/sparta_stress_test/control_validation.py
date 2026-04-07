"""SPARTA control ID validation and lightweight intent classification.

Loads valid control prefixes and max IDs from ArangoDB via /memory skill,
falling back to a minimal hardcoded set only if /memory is unreachable.

Extracted from runner.py to:
  1. Eliminate hardcoded domain knowledge (no-regex-silo rule)
  2. Keep runner.py under 800 lines (best-practices-python)
"""

import json
import os
import re
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from loguru import logger

# Always use HTTP — urllib can't handle unix:// sockets
_env_url = os.environ.get("MEMORY_SERVICE_URL", "")
MEMORY_SERVICE_URL = _env_url if _env_url.startswith("http") else "http://127.0.0.1:8601"

# Pattern matches SV-XX-N format — regex is OK here (tokenization, not classification)
CONTROL_PATTERN = re.compile(r'SV-[A-Z]{2}-\d+')

# Loaded once from ArangoDB, cached for session
_valid_prefixes: Optional[frozenset] = None
_max_control_num: Optional[dict] = None


def _memory_recall(q: str, scope: str, k: int = 50, timeout: int = 30) -> dict:
    """Call /memory recall via HTTP service — the sanctioned DB path."""
    payload = json.dumps({"q": q, "scope": scope, "k": k}).encode()
    req = Request(
        f"{MEMORY_SERVICE_URL}/recall",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _load_control_prefixes():
    """Load valid SPARTA control prefixes from ArangoDB via /memory recall."""
    global _valid_prefixes, _max_control_num
    if _valid_prefixes is not None:
        return

    try:
        result = _memory_recall(
            q="SPARTA control family prefixes SV-AC SV-IT SV-CF",
            scope="sparta_controls", k=50,
        )
        items = result.get("items", [])
        prefixes = set()
        max_nums = {}
        for item in items:
            # Scan ALL string fields for control IDs
            text = " ".join(str(v) for v in item.values() if isinstance(v, str))
            for match in CONTROL_PATTERN.findall(text):
                prefix = match.rsplit("-", 1)[0]
                num = int(match.rsplit("-", 1)[1])
                prefixes.add(prefix)
                max_nums[prefix] = max(max_nums.get(prefix, 0), num)

        if prefixes:
            _valid_prefixes = frozenset(prefixes)
            _max_control_num = max_nums
            logger.info(f"Loaded {len(prefixes)} SPARTA prefixes from ArangoDB: {sorted(prefixes)}")
            return
    except (URLError, OSError) as e:
        raise RuntimeError(
            f"Cannot load SPARTA control prefixes from memory service at {MEMORY_SERVICE_URL}: {e}. "
            "Memory service must be running (./run.sh serve --host 0.0.0.0 --port 8601)."
        ) from e


def get_valid_prefixes() -> frozenset:
    """Get valid SPARTA control prefixes (loads from ArangoDB on first call)."""
    _load_control_prefixes()
    return _valid_prefixes


def get_max_control_num() -> dict:
    """Get max control numbers per family (loads from ArangoDB on first call)."""
    _load_control_prefixes()
    return _max_control_num


def edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein for short strings."""
    if len(a) < len(b):
        return edit_distance(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def find_closest_control(ctrl_id: str) -> str:
    """Find closest valid control ID by prefix match."""
    prefixes = get_valid_prefixes()
    prefix = ctrl_id.rsplit("-", 1)[0] if "-" in ctrl_id else ctrl_id
    if prefix in prefixes:
        return f"{prefix}-1"
    closest = min(prefixes, key=lambda p: edit_distance(prefix, p))
    return f"{closest}-1"


def validate_control_id(ctrl: str) -> dict | None:
    """Return a NO_MATCH intent if ctrl is not a valid SPARTA control. None if valid."""
    if not ctrl:
        return None
    prefixes = get_valid_prefixes()
    max_nums = get_max_control_num()

    match = CONTROL_PATTERN.match(ctrl)
    if not match:
        closest = find_closest_control(ctrl)
        return {
            "action": "NO_MATCH", "scope": "sparta",
            "persona_guidance": (
                f"'{ctrl}' is not a recognized SPARTA control ID. "
                f"SPARTA controls use the format SV-XX-N. Did you mean {closest}?"
            ),
        }
    prefix = ctrl.rsplit("-", 1)[0]
    num = int(ctrl.rsplit("-", 1)[1])
    max_num = max_nums.get(prefix, 0)
    if prefix not in prefixes or (max_num and num > max_num):
        closest = find_closest_control(ctrl)
        return {
            "action": "NO_MATCH", "scope": "sparta",
            "persona_guidance": (
                f"'{ctrl}' does not exist in the SPARTA framework. "
                f"The {prefix} family has controls up to {prefix}-{max_num}. "
                f"Did you mean {closest}?"
            ) if max_num else (
                f"'{ctrl}' is not a valid SPARTA control. Did you mean {closest}?"
            ),
        }
    return None


def classify_without_mapper(question: dict) -> dict:
    """Lightweight intent classification when IntentMapper is unavailable.

    Detects three cases:
    - NO_MATCH: question references an invalid/fake control ID
    - CLARIFY: question is too vague (no control ID, no SPARTA terms)
    - QUERY: default for answerable questions
    """
    prefixes = get_valid_prefixes()
    q_text = question.get("question", "")
    target = question.get("target_control") or ""

    # Check for invalid control IDs (flawed questions)
    control_ids = CONTROL_PATTERN.findall(q_text + " " + target)
    if control_ids:
        for cid in control_ids:
            prefix = cid.rsplit("-", 1)[0]
            if prefix not in prefixes:
                closest = min(prefixes, key=lambda p: edit_distance(prefix, p))
                return {
                    "action": "NO_MATCH",
                    "scope": "sparta",
                    "persona_guidance": (
                        f"I don't recognize the control ID '{cid}'. "
                        f"Did you mean a control under {closest}? "
                        f"Valid families include: {', '.join(sorted(prefixes))}."
                    ),
                }

    # Check for ambiguous queries (no control ID, no specific SPARTA terms)
    sparta_terms = {
        "satellite", "spacecraft", "ground station", "uplink", "control",
        "telemetry", "firmware", "cyber", "jamming", "spoofing", "command",
        "cwe", "threat", "attack", "vulnerability", "countermeasure",
        "technique", "sv-", "nist", "do-178", "mil-std",
    }
    q_lower = q_text.lower()
    has_control = bool(control_ids) or bool(target)
    has_domain = any(t in q_lower for t in sparta_terms)

    if not has_control and not has_domain:
        return {
            "action": "CLARIFY",
            "scope": "sparta",
            "suggested_questions": [
                "Which SPARTA control family are you asking about? (e.g. SV-IT, SV-AC, SV-CF)",
                "Are you asking about a specific spacecraft subsystem or threat category?",
            ],
            "persona_guidance": (
                "I'd like to help, but could you be more specific? "
                "For example, are you asking about a particular SPARTA control, "
                "a threat technique, or a countermeasure?"
            ),
        }

    return {"action": "QUERY", "scope": "sparta"}
