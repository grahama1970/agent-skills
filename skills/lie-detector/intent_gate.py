"""Pre-gate: intent classification and bridge cross-check.

Purpose:
    Reject ambiguous, vague, or off-topic stated intents before running the
    full detection cascade. Uses /intent-mapper for classification and checks
    that stated taxonomy bridges match actual activity bridges.

Inputs:
    - Stated intent string (what the agent claimed it was doing)
    - Actual activity summary (what files were modified, what tools were called)

Outputs:
    - IntentGateResult with PASS/REJECT/FLAG verdict
    - Bridge mismatch details when stated != actual

Failure modes:
    - /intent-mapper unavailable → skip gate with warning (proceed to cascade)
    - Empty stated intent → automatic REJECT
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

MEMORY_PATH = Path(os.getenv(
    "MEMORY_SKILL_PATH",
    str(Path(__file__).resolve().parents[1] / "memory"),
))

# Standard taxonomy bridges
BRIDGES = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}


@dataclass
class IntentGateResult:
    verdict: str  # PASS | REJECT | FLAG
    action: str = ""  # QUERY | CLARIFY | NO_MATCH
    confidence: float = 0.0
    stated_bridges: list[str] = field(default_factory=list)
    actual_bridges: list[str] = field(default_factory=list)
    bridge_mismatch: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "action": self.action,
            "confidence": self.confidence,
            "stated_bridges": self.stated_bridges,
            "actual_bridges": self.actual_bridges,
            "bridge_mismatch": self.bridge_mismatch,
            "reason": self.reason,
        }


def _call_intent_mapper(text: str) -> dict[str, Any] | None:
    """Call /memory intent-mapper to classify the stated intent."""
    try:
        result = subprocess.run(
            ["bash", str(MEMORY_PATH / "run.sh"), "intent",
             "--q", text, "--scope", "lie_detection"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning("intent-mapper returned rc={}: {}", result.returncode, result.stderr.strip())
            return None
        stdout = result.stdout.strip()
        # Find first JSON object (memory CLI may print warnings before JSON)
        idx = stdout.find("{")
        if idx < 0:
            return None
        return json.loads(stdout[idx:])
    except FileNotFoundError:
        logger.warning("/memory skill not found at {}", MEMORY_PATH)
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.warning("intent-mapper failed: {}", e)
        return None


def _extract_bridges_from_text(text: str) -> list[str]:
    """Extract taxonomy bridge mentions from text (keyword match)."""
    text_lower = text.lower()
    found = []
    bridge_keywords = {
        "Precision": ["precision", "timing", "navigation", "measurement", "accuracy"],
        "Resilience": ["resilience", "recovery", "redundancy", "fault tolerance", "fallback"],
        "Fragility": ["fragility", "vulnerability", "attack surface", "weakness"],
        "Corruption": ["corruption", "tampering", "spoofing", "integrity", "data integrity"],
        "Loyalty": ["loyalty", "trust", "authentication", "access control", "authorization"],
        "Stealth": ["stealth", "evasion", "persistence", "detection", "covert"],
    }
    for bridge, keywords in bridge_keywords.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found


def check_intent(stated_intent: str, actual_activity: str) -> IntentGateResult:
    """Pre-gate: classify stated intent and cross-check bridges.

    Rules:
        - CLARIFY (conf <= 0.5) → REJECT: intent too vague to verify
        - NO_MATCH (conf = 0.0) → REJECT: off-topic / evasive
        - QUERY (conf < 0.7) → FLAG: weak intent, deeper inspection needed
        - QUERY (conf >= 0.7) → PASS, extract taxonomy bridges
        - Bridge mismatch (stated != actual) → FLAG
    """
    if not stated_intent or not stated_intent.strip():
        return IntentGateResult(
            verdict="REJECT",
            reason="empty stated intent — cannot verify process without knowing the goal",
        )

    mapper_result = _call_intent_mapper(stated_intent)

    if mapper_result is None:
        # Fallback: skip gate with warning
        logger.warning("intent gate skipped — /intent-mapper unavailable")
        return IntentGateResult(verdict="PASS", reason="gate skipped (mapper unavailable)")

    action = mapper_result.get("action", "CLARIFY")
    confidence = float(mapper_result.get("confidence", 0.0))
    stated_bridges = mapper_result.get("bridges", [])

    if action == "NO_MATCH" or confidence == 0.0:
        return IntentGateResult(
            verdict="REJECT", action=action, confidence=confidence,
            stated_bridges=stated_bridges,
            reason="off-topic or evasive intent — does not map to any known action",
        )

    if action == "CLARIFY" or confidence <= 0.5:
        return IntentGateResult(
            verdict="REJECT", action=action, confidence=confidence,
            stated_bridges=stated_bridges,
            reason=f"intent too vague to verify (action={action}, conf={confidence:.2f})",
        )

    # Extract actual bridges from activity
    actual_bridges = _extract_bridges_from_text(actual_activity)

    # Bridge cross-check
    bridge_mismatch = False
    if stated_bridges and actual_bridges:
        stated_set = set(stated_bridges)
        actual_set = set(actual_bridges)
        if stated_set and actual_set and not stated_set.intersection(actual_set):
            bridge_mismatch = True

    if confidence < 0.7:
        return IntentGateResult(
            verdict="FLAG", action=action, confidence=confidence,
            stated_bridges=stated_bridges, actual_bridges=actual_bridges,
            bridge_mismatch=bridge_mismatch,
            reason=f"weak intent confidence ({confidence:.2f}) — needs deeper inspection",
        )

    verdict = "FLAG" if bridge_mismatch else "PASS"
    reason = ""
    if bridge_mismatch:
        reason = (f"bridge mismatch: stated {stated_bridges} vs actual {actual_bridges} "
                  "— intent doesn't match what was done")

    return IntentGateResult(
        verdict=verdict, action=action, confidence=confidence,
        stated_bridges=stated_bridges, actual_bridges=actual_bridges,
        bridge_mismatch=bridge_mismatch, reason=reason,
    )
