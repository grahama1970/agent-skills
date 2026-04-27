"""Intent classification helpers for routing ask prompts to OS, health, and knowledge flows."""

#!/usr/bin/env python3
"""
/ask intent classifier — 3-stage classification for routing /ask queries.

Pipeline:
  1. Memory Cache — check if near-identical query was classified before
  2. Rule-Based Heuristics — regex patterns with confidence scoring
  3. LLM Fallback — scillm classification when heuristics are uncertain

Intent Categories:
  OS_QUERY        — Question about embry-os internals, skills, packages
  OS_HEALTH       — Runtime health/status question
  PERSONA_CONSULT — Ask a specific persona
  TOPIC_LEARN     — Learn about an external topic
  TOPIC_QUERY     — Query stored knowledge
  CLARIFY         — Ambiguous, needs follow-up
  OFF_TOPIC       — Not relevant to any /ask mode
"""

import json
import os
import re
import sys
import time

import httpx
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import typer
from loguru import logger as log

from .skills_exec import parse_json_output, run_skill

log.remove()
if os.environ.get("ASK_DEBUG"):
    log.add(sys.stderr, level="DEBUG")
else:
    log.add(sys.stderr, level="WARNING")

SKILLS_DIR = Path(__file__).parent.parent
AGENT_SKILLS_DIR = SKILLS_DIR.parent.parent / ".agent" / "skills"
SCILLM_URL = "http://localhost:4001"

# Confidence threshold: below this, escalate to next stage
HEURISTIC_CONFIDENCE_THRESHOLD = 0.6
LLM_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Intent Result
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    """Classification result from the intent pipeline."""
    intent: str
    confidence: float
    stage: str  # "cache", "heuristic", "llm"
    persona: Optional[str] = None
    subsystem: Optional[str] = None  # For OS_HEALTH: which subsystem
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------------------
# Stage 1: Memory Cache
# ---------------------------------------------------------------------------

def check_cache(query: str) -> Optional[IntentResult]:
    """Check memory for a cached intent classification."""
    cache_query = f"ask-intent: {query}"

    try:
        result = run_skill("memory", ["recall", "-q", cache_query, "--scope", "os", "--k", "1"], timeout=5)
        if result["returncode"] != 0 or not result["stdout"].strip():
            log.error("Intent cache recall failed: %s", result["stderr"][:200])
            return None

        data = parse_json_output(result["stdout"])
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items:
            return None

        solution = items[0].get("solution", "")
        if not solution:
            return None

        cached = json.loads(solution)
        if "intent" in cached and "confidence" in cached:
            log.debug("Cache hit for %r: %s", query, cached["intent"])
            return IntentResult(
                intent=cached["intent"],
                confidence=cached["confidence"],
                stage="cache",
                persona=cached.get("persona"),
                subsystem=cached.get("subsystem"),
            )
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        log.error("Intent cache parse failed: %s", exc)

    return None


def store_cache(query: str, result: IntentResult) -> None:
    """Store a classification result to memory cache."""
    problem = f"ask-intent: {query}"
    solution = json.dumps(result.to_dict())

    cache_result = run_skill(
        "memory",
        ["learn", "--problem", problem, "--solution", solution, "--scope", "os", "--tag", "intent-cache"],
        timeout=10,
    )
    if cache_result["returncode"] != 0:
        log.error("Intent cache store failed: %s", cache_result["stderr"][:200])


# ---------------------------------------------------------------------------
# Stage 2: Rule-Based Heuristics
# ---------------------------------------------------------------------------

# OS internal signals
OS_SIGNALS = [
    (r'/\w+[-\w]*', 0.4),                    # /memory, /ask, /dogpile
    (r'\bskill\b', 0.3),
    (r'\bSKILL\.md\b', 0.5),
    (r'\bcoding-agent\b', 0.5),
    (r'\bswitchboard\b', 0.5),
    (r'\btui\b', 0.3),
    (r'\bpods\b', 0.3),
    (r'\bpackages?\b', 0.2),
    (r'\bembry\b', 0.5),
    (r'\bpi-mono\b', 0.5),
    (r'\bextension\b', 0.3),
    (r'\bhook\b', 0.2),
    (r'\bbridge\b', 0.2),
    (r'\btaxonomy\b', 0.4),
    (r'\bmemory.first\b', 0.5),
    (r'\bmonitor-\w+', 0.4),
    (r'\bops-\w+', 0.4),
    (r'\bscheduler\b', 0.3),
    (r'\bprovides?\b', 0.2),
    (r'\bcomposes?\b', 0.2),
    (r'\brun\.sh\b', 0.4),
    (r'\bsanity\.sh\b', 0.4),
    (r'\bpyproject\.toml\b', 0.4),
]

# Health/status signals
HEALTH_SIGNALS = [
    (r'\bhealthy?\b', 0.4),
    (r'\bstatus\b', 0.4),
    (r'\brunning\b', 0.3),
    (r'\bbroken\b', 0.4),
    (r'how.?s .* doing', 0.5),
    (r'is .* working', 0.4),
    (r'\buptime\b', 0.5),
    (r'\berrors?\b', 0.3),
    (r'\bfailing\b', 0.4),
    (r'\bdown\b', 0.2),
    (r'\bcheck\b', 0.2),
    (r'\bdiagnos', 0.4),
]

# Persona consult signals
PERSONA_CONSULT_PATTERNS = [
    (r'(?:what does|ask)\s+(\w+)\s+(?:think|say)', 0.8),
    (r'consult\s+(\w+)', 0.9),
    (r'^as\s+(\w+)\s*[,:]', 0.8),
    (r'(?:from|through)\s+(\w+)(?:\'s)?\s+(?:perspective|lens|view)', 0.8),
]

# Known persona names (common ones for fast matching)
KNOWN_PERSONAS = {
    "brandon", "margaret", "horus", "embry",
    "paula", "jodorowsky", "sapolsky", "barrett",
}

# Health subsystem keywords
HEALTH_SUBSYSTEMS = {
    "memory": ["memory", "arango", "arangodb", "recall", "learn"],
    "skills": ["skill", "skills"],
    "skill-health": ["skill-health", "sanity"],
    "security": ["security", "hack", "vuln"],
    "sparta": ["sparta", "knowledge graph", "d3fend", "att&ck"],
    "personas": ["persona", "personas", "character"],
    "taxonomy": ["taxonomy", "bridge", "bridges"],
    "workstation": ["workstation", "disk", "nvme", "storage", "cache"],
    "arango": ["arango", "arangodb", "database", "db"],
    "docker": ["docker", "container"],
    "llm": ["llm", "ollama", "model", "inference"],
    "chutes": ["chutes", "chutes.ai", "scillm", "deepseek"],
}


def _score_signals(query: str, signals: list[tuple[str, float]]) -> float:
    """Score a query against a list of (regex, weight) signals."""
    total = 0.0
    for pattern, weight in signals:
        if re.search(pattern, query, re.IGNORECASE):
            total += weight
    return min(total, 1.0)


def _extract_persona(query: str) -> Optional[str]:
    """Extract persona name from consult-style queries."""
    for pattern, _ in PERSONA_CONSULT_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            name = match.group(1)
            return name

    # Check for known persona names
    query_lower = query.lower()
    for name in KNOWN_PERSONAS:
        if name in query_lower:
            return name.capitalize()

    return None


def _detect_health_subsystem(query: str) -> Optional[str]:
    """Detect which subsystem a health query targets."""
    query_lower = query.lower()
    best_match = None
    best_count = 0

    for subsystem, keywords in HEALTH_SUBSYSTEMS.items():
        count = sum(1 for kw in keywords if kw in query_lower)
        if count > best_count:
            best_count = count
            best_match = subsystem

    return best_match


def classify_heuristic(query: str) -> IntentResult:
    """Classify query using rule-based heuristics."""
    os_score = _score_signals(query, OS_SIGNALS)
    health_score = _score_signals(query, HEALTH_SIGNALS)

    # Check persona consult patterns
    persona = _extract_persona(query)
    consult_score = 0.0
    if persona:
        for pattern, weight in PERSONA_CONSULT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                consult_score = max(consult_score, weight)
                break
        if consult_score == 0.0:
            consult_score = 0.5  # Known persona name but no consult pattern

    # Learn signals
    learn_score = 0.0
    learn_patterns = [
        (r'\b(?:learn|teach|study)\b', 0.5),
        (r'\b(?:discover|research|ingest)\b', 0.4),
        (r'\blearn about\b', 0.7),
        (r'\bteach me\b', 0.7),
    ]
    learn_score = _score_signals(query, learn_patterns)

    # Compute combined scores
    scores = {
        "OS_HEALTH": min(os_score + health_score, 1.0) if health_score > 0.3 else health_score,
        "OS_QUERY": os_score if health_score < 0.3 else os_score * 0.5,
        "PERSONA_CONSULT": consult_score,
        "TOPIC_LEARN": learn_score if os_score < 0.3 else learn_score * 0.3,
        "TOPIC_QUERY": 0.3,  # Default fallback
    }

    # Pick highest scoring intent
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    # If OS_HEALTH wins, detect subsystem
    subsystem = None
    if best_intent == "OS_HEALTH":
        subsystem = _detect_health_subsystem(query)

    # If nothing scored high, it's ambiguous
    if best_score < 0.3:
        best_intent = "TOPIC_QUERY"
        best_score = 0.3

    log.debug("Heuristic scores: %s → %s (%.2f)", scores, best_intent, best_score)

    return IntentResult(
        intent=best_intent,
        confidence=best_score,
        stage="heuristic",
        persona=persona if best_intent == "PERSONA_CONSULT" else None,
        subsystem=subsystem,
    )


# ---------------------------------------------------------------------------
# Stage 3: LLM Fallback
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = """You are an intent classifier for Embry-OS, an AI operating system with 130+ skills.

Classify this query into ONE intent:
- OS_QUERY: Question about embry-os internals, skills, packages, architecture, configuration
- OS_HEALTH: Runtime health or status question about a subsystem
- PERSONA_CONSULT: User wants a specific persona to answer (e.g., "ask Brandon about...")
- TOPIC_LEARN: User wants to learn about an external topic (not about the OS itself)
- TOPIC_QUERY: User wants to query already-stored knowledge about an external topic
- CLARIFY: Query is too ambiguous to classify
- OFF_TOPIC: Not relevant to any /ask mode

Examples:
- "how does the memory skill work?" → OS_QUERY
- "is memory healthy?" → OS_HEALTH
- "what does Sapolsky say about stress?" → TOPIC_QUERY
- "ask Brandon about security" → PERSONA_CONSULT
- "learn about quantum computing" → TOPIC_LEARN
- "what?" → CLARIFY

Query: "{query}"

Respond ONLY with JSON: {{"intent": "...", "confidence": 0.0-1.0, "persona": "name or null", "subsystem": "name or null"}}"""


def classify_llm(query: str) -> IntentResult:
    """Classify query using LLM via scillm HTTP proxy."""
    prompt = CLASSIFY_PROMPT.format(query=query.replace('"', '\\"'))

    try:
        payload = {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            timeout=float(LLM_TIMEOUT),
        )
        resp.raise_for_status()
        stdout = resp.json()["choices"][0]["message"]["content"].strip()

        # Find JSON in output
        json_start = stdout.find("{")
        json_end = stdout.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(stdout[json_start:json_end])
            intent = data.get("intent", "TOPIC_QUERY")
            confidence = float(data.get("confidence", 0.5))

            valid_intents = {
                "OS_QUERY", "OS_HEALTH", "PERSONA_CONSULT",
                "TOPIC_LEARN", "TOPIC_QUERY", "CLARIFY", "OFF_TOPIC",
            }
            if intent not in valid_intents:
                intent = "TOPIC_QUERY"
                confidence = 0.4

            return IntentResult(
                intent=intent,
                confidence=confidence,
                stage="llm",
                persona=data.get("persona"),
                subsystem=data.get("subsystem"),
            )

    except httpx.HTTPStatusError as e:
        log.warning("scillm classification HTTP error: %s", e.response.status_code)
    except (httpx.TimeoutException, json.JSONDecodeError, ValueError, OSError) as e:
        log.warning("LLM classification error: %s", e)

    return IntentResult(intent="TOPIC_QUERY", confidence=0.4, stage="llm")


# ---------------------------------------------------------------------------
# Main Classification Pipeline
# ---------------------------------------------------------------------------

def classify_intent(query: str, scope: Optional[str] = None) -> IntentResult:
    """Classify a query through the 3-stage pipeline.

    Args:
        query: The user's question
        scope: Optional scope hint (e.g., "os" forces OS routing)

    Returns:
        IntentResult with intent, confidence, and metadata
    """
    start = time.monotonic()

    # Scope override: if scope is "os", skip classification
    if scope == "os":
        return IntentResult(intent="OS_QUERY", confidence=1.0, stage="scope_override")

    # Stage 1: Memory cache
    cached = check_cache(query)
    if cached and cached.confidence >= HEURISTIC_CONFIDENCE_THRESHOLD:
        log.info("Intent (cache, %.0fms): %s [%.2f]",
                 (time.monotonic() - start) * 1000, cached.intent, cached.confidence)
        return cached

    # Stage 2: Rule-based heuristics
    heuristic = classify_heuristic(query)
    if heuristic.confidence >= HEURISTIC_CONFIDENCE_THRESHOLD:
        # Cache the result
        store_cache(query, heuristic)
        log.info("Intent (heuristic, %.0fms): %s [%.2f]",
                 (time.monotonic() - start) * 1000, heuristic.intent, heuristic.confidence)
        return heuristic

    # Stage 3: LLM fallback
    llm_result = classify_llm(query)
    # Cache the LLM result
    store_cache(query, llm_result)
    log.info("Intent (llm, %.0fms): %s [%.2f]",
             (time.monotonic() - start) * 1000, llm_result.intent, llm_result.confidence)
    return llm_result


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

app = typer.Typer(help="/ask intent classifier")


@app.command()
def main(
    query: str = typer.Argument(help="Query to classify"),
    scope: Optional[str] = typer.Option(None, help="Scope hint"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Classify a query into an intent category."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    result = classify_intent(query, scope)

    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    app()
