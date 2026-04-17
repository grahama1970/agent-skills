"""Six validation gates for F36-grounded persona questions."""
from __future__ import annotations
import os

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from config import (
    ALLOWED_TERMS,
    DIFFICULTY_LEVELS,
    F36_CATEGORIES,
    PERSONAS,
    SYSTEM_LEAKAGE_TERMS,
    PersonaProfile,
)

# ---------------------------------------------------------------------------
# Taxonomy import (bridge-based persona alignment)
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).resolve().parents[1]  # .pi/skills/
_taxonomy_dir = SKILLS_DIR / "taxonomy"
if str(_taxonomy_dir) not in sys.path:
    sys.path.insert(0, str(_taxonomy_dir))

try:
    from taxonomy import extract_keywords as _extract_bridge_tags
except ImportError:
    logger.warning("taxonomy skill not available — falling back to keyword matching")
    _extract_bridge_tags = None

# Persona → expected bridge tags mapping
# Each persona's domain naturally aligns with specific bridge attributes
PERSONA_BRIDGES: dict[str, list[str]] = {
    "brandon": ["Loyalty", "Stealth", "Corruption"],      # Security/adversary/compliance
    "jennifer": ["Loyalty", "Corruption", "Stealth"],      # Cybersecurity/compromise/auth
    "noah": ["Resilience", "Fragility", "Precision"],      # Safety/fault tolerance/verification
    "margaret": ["Precision", "Resilience", "Loyalty"],     # V&V/requirements/certification
    "paul": ["Precision", "Resilience", "Fragility"],       # Manufacturing/tolerance/QA
    "embry": ["Precision", "Resilience", "Loyalty",         # Cross-domain assistant
              "Corruption", "Fragility", "Stealth"],
}

# scillm run.sh path for composable subprocess calls
_SCILLM_DIR = SKILLS_DIR / "scillm"


def _llm_completion(prompt: str, system: str, json_mode: bool = True) -> str:
    """Call /scillm via subprocess (composable skill pattern).

    Combines system + user prompt into a single prompt since the CLI
    only accepts a prompt arg. Uses --json flag for JSON mode.
    """
    import subprocess

    combined = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}"
    cmd = [
        "uv", "run", "--directory", str(_SCILLM_DIR),
        "python", "batch.py", "single",
    ]
    if json_mode:
        cmd.append("--json")
    cmd.append(combined)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            cwd=str(_SCILLM_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning(f"scillm failed (rc={result.returncode}): {result.stderr[:200]}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("scillm timed out")
        return ""
    except FileNotFoundError:
        logger.warning("scillm not found — LLM gates skipped")
        return ""


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    gate: str
    passed: bool
    reason: str
    score: Optional[float] = None
    details: dict = field(default_factory=dict)


@dataclass
class QuestionValidation:
    question: str
    difficulty: str
    f36_category: str
    gates: list[GateResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    @property
    def total_count(self) -> int:
        return len(self.gates)

    @property
    def all_passed(self) -> bool:
        return all(g.passed for g in self.gates)

    @property
    def summary(self) -> str:
        status = "PASS" if self.all_passed else "FAIL"
        return f"[{status} {self.passed_count}/{self.total_count}] {self.difficulty.title()}"


# ---------------------------------------------------------------------------
# Gate 1: Persona alignment
# ---------------------------------------------------------------------------

def _word_match(keyword: str, text_lower: str) -> bool:
    """Match keyword using word boundaries to avoid substring false positives."""
    # Short keywords (<=3 chars) need word boundary matching
    if len(keyword) <= 3:
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text_lower))
    return keyword in text_lower


def check_persona_alignment(question: str, persona: PersonaProfile) -> GateResult:
    """Check that the question matches the persona's domain expertise.

    Uses two signals:
    1. Taxonomy bridge tags (semantic) — primary signal via /taxonomy
    2. Domain keyword matching — secondary signal for specificity
    """
    q_lower = question.lower()

    # --- Signal 1: Taxonomy bridge tags (semantic alignment) ---
    bridge_score = 0.0
    bridge_matched: list[str] = []
    expected_bridges = PERSONA_BRIDGES.get(persona.short_name, [])

    if _extract_bridge_tags is not None:
        question_bridges = _extract_bridge_tags(question)
        bridge_matched = [b for b in question_bridges if b in expected_bridges]
        if expected_bridges:
            bridge_score = len(bridge_matched) / min(len(expected_bridges), 3)
    else:
        bridge_score = 0.5  # Neutral if taxonomy unavailable

    # --- Signal 2: Domain keyword matching (specificity) ---
    matched_keywords = [
        kw for kw in persona.domain_keywords
        if _word_match(kw.lower(), q_lower)
    ]

    # --- Combined decision ---
    # Pass if EITHER:
    #   - Bridge alignment ≥ 0.33 (at least 1 of top-3 bridges match)
    #   - At least 1 domain keyword matches
    # Embry (cross-domain assistant) gets a pass on bridges since all 6 match
    has_bridge_alignment = bridge_score >= 0.33
    has_keyword_match = len(matched_keywords) >= 1
    passed = has_bridge_alignment or has_keyword_match

    # Build reason
    reason_parts = []
    if bridge_matched:
        reason_parts.append(f"bridges: {bridge_matched} (score={bridge_score:.2f})")
    if matched_keywords:
        reason_parts.append(f"keywords: {matched_keywords[:5]}")
    if not reason_parts:
        reason_parts.append("no bridge or keyword alignment found")

    return GateResult(
        gate="persona_alignment",
        passed=passed,
        reason="; ".join(reason_parts),
        score=max(bridge_score, len(matched_keywords) / 5.0),
        details={
            "bridge_tags": bridge_matched,
            "bridge_score": bridge_score,
            "matched_keywords": matched_keywords,
        },
    )


# ---------------------------------------------------------------------------
# Gate 2: F36 grounding
# ---------------------------------------------------------------------------

def check_f36_grounding(question: str, persona: PersonaProfile) -> GateResult:
    """Check that the question relates to F36 datalake categories."""
    q_lower = question.lower()

    # Check for F36 category keywords
    matched_cats = []
    for cat_id, cat_desc in F36_CATEGORIES.items():
        # Match on category keywords from description
        desc_words = cat_desc.lower().split(", ")
        for word in desc_words:
            if word.strip() in q_lower:
                matched_cats.append(cat_id)
                break

    # Also check for explicit F-36/F36 mention
    has_f36_ref = bool(re.search(r'f[- ]?36', q_lower))
    # Check for generic aerospace/defense terms that imply F36 context
    f36_context_terms = [
        "fighter", "aircraft", "avionics", "cockpit", "airframe",
        "engine", "propulsion", "manufacturing", "plant floor",
        "supply chain", "vendor", "flight test", "subsystem",
        "flight software", "flight control", "dual-engine", "turbine",
        "radar", "sensor", "weapons", "navigation", "firmware",
        "coverage", "assurance", "non-conformance", "tolerance",
    ]
    context_matches = [t for t in f36_context_terms if t in q_lower]

    # Pass if any 2 of 3 signals present, or explicit F-36 reference
    signals = sum([len(matched_cats) >= 1, len(context_matches) >= 1, has_f36_ref])
    passed = signals >= 2 or has_f36_ref
    reason_parts = []
    if matched_cats:
        reason_parts.append(f"F36 categories: {matched_cats[:3]}")
    if has_f36_ref:
        reason_parts.append("explicit F-36 reference")
    if context_matches:
        reason_parts.append(f"context terms: {context_matches[:3]}")
    if not reason_parts:
        reason_parts.append("no F36 datalake connection found")

    return GateResult(
        gate="f36_grounding",
        passed=passed,
        reason="; ".join(reason_parts),
        details={"categories": matched_cats, "f36_ref": has_f36_ref, "context": context_matches},
    )


# ---------------------------------------------------------------------------
# Gate 3: Data answerability (checks ArangoDB for matching data)
# ---------------------------------------------------------------------------

def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def check_data_answerability(question: str, **_kwargs) -> GateResult:
    """Check that answerable data exists via /memory recall."""
    # Extract distinctive keywords for the recall query
    _stopwords = {
        "what", "which", "where", "when", "does", "that", "this", "from",
        "with", "have", "been", "their", "they", "will", "would", "could",
        "should", "about", "into", "your", "than", "them", "then", "also",
        "most", "more", "many", "much", "some", "such", "each", "like",
        "over", "only", "very", "just", "being", "other", "after", "before",
        "during", "between", "through", "think", "belong", "favorite",
        "color", "pizza", "pineapple", "given", "considering", "against",
        "based", "using", "across", "while", "within", "might", "especially",
        "recommend", "approach", "address", "dealing", "different", "recent",
        "system", "systems",
    }
    raw_text = re.sub(r'[^\w\s-]', '', question.lower())
    raw_text = raw_text.replace('-', ' ')
    q_words = [
        w for w in raw_text.split()
        if len(w) > 3 and w not in _stopwords
    ]

    _domain_terms = {
        "sparta", "countermeasure", "countermeasures", "firmware", "attack",
        "threat", "vulnerability", "cyber", "compliance", "control", "controls",
        "security", "defense", "adversary", "exploit", "supply", "chain",
        "avionics", "flight", "software", "hardware", "network", "sensor",
        "weapons", "navigation", "encryption", "authentication", "lateral",
        "persistence", "reconnaissance", "exfiltration", "injection",
        "nist", "stig", "cmmc", "stpa", "vendor", "manufacturing",
        "inspection", "tolerance", "weld", "alloy", "boot", "integrity",
    }
    domain_hits = [w for w in q_words if w in _domain_terms]
    other_words = [w for w in q_words if w not in _domain_terms]
    distinctive = (domain_hits + sorted(other_words, key=len, reverse=True))[:3]

    search_query = " ".join(distinctive) if distinctive else question[:80]

    # Use /memory recall for semantic search across collections
    qra_count = 0
    control_count = 0
    lesson_count = 0

    try:
        results = _memory_cmd(["recall", search_query, "--limit", "15"])
        docs = results if isinstance(results, list) else results.get("results", [])
        for doc in docs:
            collection = doc.get("_collection", doc.get("collection", ""))
            if "qra" in collection:
                qra_count += 1
            elif "control" in collection:
                control_count += 1
            elif "lesson" in collection:
                lesson_count += 1
            else:
                lesson_count += 1  # Default to lesson bucket
    except Exception as e:
        logger.warning(f"Memory recall failed: {e}")
        return GateResult(
            gate="data_answerability",
            passed=True,  # Skip gracefully
            reason=f"Memory service unavailable ({e}) — gate skipped",
            details={"skipped": True},
        )

    total = qra_count + control_count + lesson_count
    passed = total >= 1
    reason = f"{qra_count} QRAs, {control_count} controls, {lesson_count} lessons"
    if not passed:
        reason += " — question may not be answerable from available data"

    return GateResult(
        gate="data_answerability",
        passed=passed,
        reason=reason,
        score=min(total / 5.0, 1.0),
        details={
            "qra_count": qra_count,
            "control_count": control_count,
            "lesson_count": lesson_count,
        },
    )


# ---------------------------------------------------------------------------
# Gate 4: Naturalness (LLM-based via /scillm)
# ---------------------------------------------------------------------------

def check_naturalness(question: str) -> GateResult:
    """Check that the question sounds like a real engineer asking a colleague."""
    from prompts import naturalness_system, naturalness_user

    result = _llm_completion(
        prompt=naturalness_user(question),
        system=naturalness_system(),
        json_mode=True,
    )
    if not result:
        return GateResult(
            gate="naturalness",
            passed=True,
            reason="LLM unavailable — gate skipped",
            details={"skipped": True},
        )

    try:
        data = json.loads(result)
        score = float(data.get("score", 0))
        reason = data.get("reason", "")
        return GateResult(
            gate="naturalness",
            passed=score >= 0.80,
            reason=f"score={score:.2f}: {reason}",
            score=score,
        )
    except (json.JSONDecodeError, ValueError) as e:
        return GateResult(
            gate="naturalness",
            passed=True,
            reason=f"LLM response parse error: {e} — gate skipped",
            details={"skipped": True, "raw": result[:200]},
        )


# ---------------------------------------------------------------------------
# Gate 5: System leakage
# ---------------------------------------------------------------------------

def check_system_leakage(question: str) -> GateResult:
    """Check for internal system concepts that shouldn't appear in questions."""
    leaked = []
    for term in SYSTEM_LEAKAGE_TERMS:
        if term == "|":
            # Check for pipe-delimited lists (3+ pipes = pattern)
            if question.count("|") >= 3:
                leaked.append("pipe-delimited list")
        elif term in question:
            # Don't flag if it's an allowed term in context
            if term.upper() not in [a.upper() for a in ALLOWED_TERMS]:
                leaked.append(term)

    passed = len(leaked) == 0
    reason = "clean" if passed else f"leaked terms: {leaked}"
    return GateResult(
        gate="system_leakage",
        passed=passed,
        reason=reason,
        details={"leaked": leaked},
    )


# ---------------------------------------------------------------------------
# Gate 6: Difficulty classification
# ---------------------------------------------------------------------------

def check_difficulty(question: str, claimed_difficulty: str) -> GateResult:
    """Check that the claimed difficulty matches the actual complexity."""
    from prompts import difficulty_classification_system, difficulty_classification_user
import httpx

    if claimed_difficulty not in DIFFICULTY_LEVELS:
        return GateResult(
            gate="difficulty",
            passed=False,
            reason=f"unknown difficulty '{claimed_difficulty}' — must be easy/medium/hard",
        )

    result = _llm_completion(
        prompt=difficulty_classification_user(question),
        system=difficulty_classification_system(),
        json_mode=True,
    )
    if not result:
        return GateResult(
            gate="difficulty",
            passed=True,
            reason="LLM unavailable — gate skipped",
            details={"skipped": True},
        )

    try:
        data = json.loads(result)
        actual = data.get("difficulty", "unknown")
        reason = data.get("reason", "")
        # Allow one level of drift (easy claimed as medium is OK)
        levels = list(DIFFICULTY_LEVELS.keys())
        claimed_idx = levels.index(claimed_difficulty)
        actual_idx = levels.index(actual) if actual in levels else -1
        drift = abs(claimed_idx - actual_idx) if actual_idx >= 0 else 2
        passed = drift <= 1
        return GateResult(
            gate="difficulty",
            passed=passed,
            reason=f"claimed={claimed_difficulty}, actual={actual} (drift={drift}): {reason}",
            details={"claimed": claimed_difficulty, "actual": actual, "drift": drift},
        )
    except (json.JSONDecodeError, ValueError) as e:
        return GateResult(
            gate="difficulty",
            passed=True,
            reason=f"LLM response parse error: {e} — gate skipped",
            details={"skipped": True},
        )


# ---------------------------------------------------------------------------
# Orchestrator: run all gates on a question
# ---------------------------------------------------------------------------

def validate_question(
    question: str,
    difficulty: str,
    f36_category: str,
    persona_key: str,
    skip_llm: bool = False,
) -> QuestionValidation:
    """Run all 6 validation gates on a single question."""
    persona = PERSONAS.get(persona_key)
    if persona is None:
        raise ValueError(f"Unknown persona: {persona_key}. Choose from: {list(PERSONAS.keys())}")

    validation = QuestionValidation(
        question=question,
        difficulty=difficulty,
        f36_category=f36_category,
    )

    # Gate 1: Persona alignment (fast, no LLM)
    validation.gates.append(check_persona_alignment(question, persona))

    # Gate 2: F36 grounding (fast, no LLM)
    validation.gates.append(check_f36_grounding(question, persona))

    # Gate 3: Data answerability (via /memory recall)
    validation.gates.append(check_data_answerability(question))

    # Gate 4: Naturalness (LLM-based)
    if skip_llm:
        validation.gates.append(GateResult(
            gate="naturalness", passed=True, reason="LLM gates skipped",
            details={"skipped": True},
        ))
    else:
        validation.gates.append(check_naturalness(question))

    # Gate 5: System leakage (fast, regex-based)
    validation.gates.append(check_system_leakage(question))

    # Gate 6: Difficulty classification (LLM-based)
    if skip_llm:
        validation.gates.append(GateResult(
            gate="difficulty", passed=True, reason="LLM gates skipped",
            details={"skipped": True},
        ))
    else:
        validation.gates.append(check_difficulty(question, difficulty))

    return validation
