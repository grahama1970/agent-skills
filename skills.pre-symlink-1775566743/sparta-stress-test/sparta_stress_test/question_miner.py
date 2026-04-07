"""LLM-driven question bank generator for SPARTA stress tests.

Mines questions using Margaret Chen and Jennifer Cheung personas via /scillm.
No templates — personas generate natural questions from F-36 lesson context.

Sources:
  A. F-36 Lessons — personas read real requirements, ask natural questions
  B. SPARTA QRAs — personas create adversarial/cross-control variants
  C. F-36 Specific Claims — personas probe verifiable data points
  D. Taxonomy gaps — personas target underrepresented bridge combinations

Adversarial injection:
  Margaret/Jennifer are instructed to occasionally produce intentionally
  ambiguous, off-topic, or flawed questions so Brandon's grader can be
  stress-tested on detection of bad inputs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Ensure graph_memory is importable
_src_path = str(Path(__file__).resolve().parents[4] / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# scillm path for batch completions
_scillm_path = str(Path(__file__).resolve().parents[4].parent / "pi-mono" / ".pi" / "skills" / "scillm")
if _scillm_path not in sys.path:
    sys.path.insert(0, _scillm_path)

# ---------------------------------------------------------------------------
# Shadow method gateway: route through /assistant validate() when available
# ---------------------------------------------------------------------------
_use_gateway = os.environ.get("STRESS_TEST_USE_GATEWAY", "1") == "1"
_gateway_available = False
if _use_gateway:
    try:
        _assistant_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assistant")
        if _assistant_dir not in sys.path:
            sys.path.insert(0, _assistant_dir)
        from assistant import validate as _gw_validate
        _gateway_available = True
    except ImportError:
        _gateway_available = False

# --------------------------------------------------------------------------- #
# Persona system prompts
# --------------------------------------------------------------------------- #

MARGARET_SYSTEM = """You are Margaret Chen, Senior Requirements Engineer at Pratt & Whitney.
Your expertise: DO-178C, V&V, traceability, coverage gaps, requirement drift,
formal verification, attack chain analysis, multi-hop defense assessment.

You are reviewing F-36 LEO Fighter data and SPARTA (Space Attack Research &
Tactic Analysis) framework content. Your job is to generate NATURAL questions
that a V&V engineer would actually ask when evaluating space cyber security.

QUESTION STYLE:
- Ask about traceability gaps, verification evidence, residual risk
- Reference specific data points from the content (IDs, thresholds, names)
- Use your V&V vocabulary naturally (drift, coverage, trace, evidence, validate)
- Questions should be answerable from the SPARTA QRA corpus
- Vary complexity: some simple lookups, some multi-hop analysis

ADVERSARIAL INJECTION (important for stress testing):
When the instruction says "inject_flaw", generate ONE of these instead:
- An ambiguous question too vague to answer ("What about security?")
- A question about a non-existent SPARTA control (make up a fake ID like SV-ZZ-99)
- A question completely off-topic for SPARTA (about cooking, sports, etc.)
- A question mixing SPARTA terms incorrectly

Label each question with its type: QUERY, CLARIFY, NO_MATCH, or OFF_TOPIC."""

JENNIFER_SYSTEM = """You are Jennifer Cheung, Cybersecurity Research Scientist at NIWC Pacific.
Your expertise: NIST SP 800-53, RMF, DISA STIGs, CAT I/II/III findings,
authorization boundaries, FedRAMP, SSP documentation, continuous monitoring.

You are reviewing F-36 LEO Fighter data and SPARTA (Space Attack Research &
Tactic Analysis) framework content. Your job is to generate NATURAL questions
that an RMF/compliance assessor would actually ask.

QUESTION STYLE:
- Ask about NIST control mappings, CAT findings, compliance gaps
- Reference specific data points from the content (control IDs, requirements)
- Use your compliance vocabulary naturally (ATO, SSP, finding, boundary, monitor)
- Questions should be answerable from the SPARTA QRA corpus
- Vary complexity: some direct lookups, some cross-framework analysis

ADVERSARIAL INJECTION (important for stress testing):
When the instruction says "inject_flaw", generate ONE of these instead:
- An ambiguous question too vague to answer ("Tell me about compliance")
- A question about a non-existent control (make up a fake NIST or SPARTA ID)
- A question completely off-topic for SPARTA (about weather, history, etc.)
- A question that confuses SPARTA with a different framework

Label each question with its type: QUERY, CLARIFY, NO_MATCH, or OFF_TOPIC."""

# JSON output schema instruction (appended to user prompts)
JSON_INSTRUCTION = """
Return ONLY a JSON array of question objects. Each object must have:
{
  "question": "the natural question text",
  "expected_action": "QUERY" or "CLARIFY" or "NO_MATCH" or "OFF_TOPIC",
  "difficulty": "simple" or "medium" or "complex" or "ambiguous" or "flawed",
  "reasoning": "brief note on why you asked this"
}"""

# SPARTA subsystems for variety in prompts
SUBSYSTEMS = [
    "avionics bus", "ground station", "uplink segment", "downlink segment",
    "spacecraft processor", "GPS receiver", "command and control link",
    "telemetry stream", "onboard storage", "attitude control system",
]

DOMAINS = [
    "Spacecraft", "Ground_Station", "Uplink", "Downlink",
    "Launch_Segment", "User_Segment",
]


def _get_db() -> Any:
    from graph_memory.arango_client import get_db
    return get_db()


# --------------------------------------------------------------------------- #
# Control ID validation — reject hallucinated controls
# --------------------------------------------------------------------------- #

_VALID_CONTROL_IDS: set[str] | None = None
_CONTROL_ID_PATTERN = None


def _load_valid_controls(db: Any = None) -> set[str]:
    """Load all valid control IDs from ArangoDB (cached module-level)."""
    global _VALID_CONTROL_IDS
    if _VALID_CONTROL_IDS is not None:
        return _VALID_CONTROL_IDS

    try:
        if db is None:
            db = _get_db()
        ids = set()
        for coll_name in ("sparta_controls", "controls"):
            try:
                coll = db.collection(coll_name)
                for doc in coll.all():
                    cid = doc.get("control_id", "")
                    if cid:
                        ids.add(cid)
            except Exception:
                pass
        _VALID_CONTROL_IDS = ids
        logger.info(f"Loaded {len(ids)} valid control IDs for question validation")
        return ids
    except Exception as e:
        logger.warning(f"Could not load valid control IDs: {e}")
        _VALID_CONTROL_IDS = set()
        return _VALID_CONTROL_IDS


def _get_control_id_pattern():
    """Regex pattern matching common control ID formats."""
    global _CONTROL_ID_PATTERN
    if _CONTROL_ID_PATTERN is None:
        import re
        # Matches patterns like: AC-2, SV-RS-45, SC-1.2, CWE-79, CVE-2026-1234, PE-3(1)
        _CONTROL_ID_PATTERN = re.compile(
            r'\b([A-Z]{2,6}-(?:[A-Z]{1,4}-)?[\d]+(?:\.\d+)*(?:\([^\)]+\))?)\b'
        )
    return _CONTROL_ID_PATTERN


def _validate_mined_questions(
    questions: list[dict],
    db: Any = None,
) -> list[dict]:
    """Validate mined questions — reject any with hallucinated control IDs.

    Checks:
      1. target_control field exists in ArangoDB
      2. Any control-ID-like patterns in question text exist in ArangoDB
    Questions with expected_action NO_MATCH are exempt (they test error detection).
    """
    valid_ids = _load_valid_controls(db)
    if not valid_ids:
        logger.warning("No valid control IDs loaded — skipping validation")
        return questions

    pattern = _get_control_id_pattern()
    accepted = []
    rejected_count = 0

    for q in questions:
        # Adversarial questions that deliberately use fake controls are OK
        if q.get("expected_action") in ("NO_MATCH", "OFF_TOPIC"):
            accepted.append(q)
            continue

        # Check target_control
        tc = q.get("target_control", "")
        if tc and tc not in valid_ids:
            logger.debug(
                f"Rejected question: hallucinated target_control='{tc}' "
                f"q='{q['question'][:60]}...'"
            )
            rejected_count += 1
            continue

        # Check control-ID-like patterns in question text
        matches = pattern.findall(q.get("question", ""))
        hallucinated = [m for m in matches if m not in valid_ids]
        if hallucinated:
            logger.debug(
                f"Rejected question: hallucinated IDs {hallucinated} in text "
                f"q='{q['question'][:60]}...'"
            )
            rejected_count += 1
            continue

        accepted.append(q)

    if rejected_count:
        logger.info(
            f"Question validation: {rejected_count} rejected "
            f"(hallucinated control IDs), {len(accepted)} accepted"
        )
    return accepted


# --------------------------------------------------------------------------- #
# LLM call helper
# --------------------------------------------------------------------------- #

def _call_scillm_sync(system: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Call /scillm synchronously via quick_completion, with gateway fallback."""
    # Gateway path: route through /assistant validate()
    if _gateway_available:
        try:
            gw_result = _gw_validate(
                input_data={
                    "source_type": "stress_test_prompt",
                    "content": user_prompt[:3000],
                },
                task="sparta-question-miner",
            )
            result = gw_result.result
            if isinstance(result, dict):
                return json.dumps(result)
            if isinstance(result, str):
                return result
            return json.dumps(result)
        except Exception as e:
            logger.debug(f"Gateway failed, falling back to direct scillm: {e}")

    # Fallback: direct scillm call
    # Try multiple import paths for scillm
    quick_completion = None
    for module_name in ("batch", "scillm_skill.batch", "scillm.batch"):
        try:
            mod = __import__(module_name, fromlist=["quick_completion"])
            if hasattr(mod, "quick_completion"):
                quick_completion = mod.quick_completion
                break
        except ImportError:
            continue

    if quick_completion is None:
        logger.warning("scillm not importable from any known path, falling back to mock")
        return "[]"

    return quick_completion(
        prompt=user_prompt,
        system=system,
        json_mode=True,
        max_tokens=max_tokens,
        temperature=0.7,  # some creativity for natural questions
        timeout=60,
    )


async def _call_scillm_batch(
    system: str,
    prompts: List[str],
    max_tokens: int = 2048,
    concurrency: int = 4,
) -> List[str]:
    """Call /scillm in parallel for multiple prompts."""
    batch_acompletions_iter = None
    for module_name in ("scillm.batch", "scillm_skill.batch", "batch"):
        try:
            mod = __import__(module_name, fromlist=["batch_acompletions_iter"])
            batch_acompletions_iter = mod.batch_acompletions_iter
            break
        except (ImportError, AttributeError):
            continue

    if batch_acompletions_iter is None:
        logger.warning("scillm batch not available, falling back to sequential")
        return [_call_scillm_sync(system, p, max_tokens) for p in prompts]

    model = os.environ.get("CHUTES_MODEL_ID", os.environ.get("CHUTES_TEXT_MODEL", "moonshotai/Kimi-K2-Instruct-0905"))
    api_base = os.environ.get("SCILLM_API_BASE", "http://localhost:4001")
    api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

    if not api_base or not api_key:
        logger.warning("SCILLM env vars not set, falling back to sequential")
        return [_call_scillm_sync(system, p, max_tokens) for p in prompts]

    requests = []
    for prompt in prompts:
        requests.append({
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0.7,
        })

    results = [""] * len(prompts)
    async for event in batch_acompletions_iter(
        requests,
        api_base=api_base,
        api_key=api_key,
        custom_llm_provider="openai",
        concurrency=concurrency,
        timeout=60,
        wall_time_s=600,
        tenacious=True,
        response_format={"type": "json_object"},
        retry_invalid_json=1,
    ):
        idx = event.get("index", 0)
        if event.get("ok"):
            content = event.get("content", "")
            results[idx] = content if isinstance(content, str) else json.dumps(content)
        else:
            logger.warning(f"Batch item {idx} failed: {event.get('error', 'unknown')}")

    return results


def _parse_questions_json(raw: str, persona: str, source: str, bridges: List[str] = None) -> List[dict]:
    """Parse LLM JSON response into standardized question dicts."""
    if not raw or raw.strip() == "[]":
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON array from markdown code block
        import re
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSON from LLM response: {raw[:200]}")
                return []
        else:
            logger.warning(f"No JSON array found in LLM response: {raw[:200]}")
            return []

    if isinstance(data, dict):
        # Sometimes LLM wraps in {"questions": [...]}
        data = data.get("questions", [data])

    questions = []
    for item in data:
        if not isinstance(item, dict) or "question" not in item:
            continue
        q_text = item["question"].strip()
        if len(q_text) < 10:
            continue

        qid = hashlib.sha256(q_text.encode()).hexdigest()[:12]
        expected = item.get("expected_action", "QUERY").upper()
        difficulty = item.get("difficulty", "medium").lower()

        # Map adversarial types to difficulty labels
        if expected in ("CLARIFY", "OFF_TOPIC"):
            difficulty = "ambiguous"
        elif expected == "NO_MATCH":
            difficulty = "flawed"

        questions.append({
            "id": f"{difficulty}-{qid}",
            "difficulty": difficulty,
            "persona": persona,
            "question": q_text,
            "expected_action": expected,
            "target_control": item.get("target_control"),
            "expected_techniques": item.get("expected_techniques", []),
            "expected_countermeasures": item.get("expected_countermeasures", []),
            "bridge_tags": bridges or [],
            "source": source,
            "grading_notes": item.get("reasoning", ""),
        })

    return questions


# --------------------------------------------------------------------------- #
# Source A: F-36 Lessons → Persona questions
# --------------------------------------------------------------------------- #

def mine_f36_lessons(db: Any, limit: int = 100) -> List[dict]:
    """Feed F-36 lesson content to Margaret/Jennifer, get natural questions."""
    aql = """
    FOR doc IN lessons
      FILTER doc.scope == "fort_worth_f36"
      FILTER doc.bridge_attributes != null AND LENGTH(doc.bridge_attributes) > 0
      SORT RAND()
      LIMIT @limit
      RETURN { problem: doc.problem, solution: SUBSTRING(doc.solution, 0, 500),
               bridge: doc.bridge_attributes, title: doc.title }
    """
    docs = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    logger.info(f"Source A: {len(docs)} F-36 lessons with taxonomy")

    if not docs:
        return []

    # Batch lessons into groups of 10 for LLM calls
    batch_size = 10
    all_questions = []

    for batch_start in range(0, len(docs), batch_size):
        batch = docs[batch_start:batch_start + batch_size]
        bridges = []
        for d in batch:
            bridges.extend(d.get("bridge", []))

        # Format batch content for LLM
        content_block = ""
        for i, doc in enumerate(batch):
            content_block += f"\n--- Lesson {i+1} ---\n"
            content_block += f"Topic: {doc.get('title', 'unknown')}\n"
            content_block += f"Question: {doc.get('problem', '')}\n"
            content_block += f"Answer: {doc.get('solution', '')}\n"
            content_block += f"Taxonomy: {', '.join(doc.get('bridge', []))}\n"

        # Decide if this batch should inject adversarial questions
        inject = random.random() < 0.15  # 15% of batches get adversarial injection

        user_prompt = f"""Based on these F-36 LEO Fighter lessons, generate {len(batch)} natural questions
that a {"V&V engineer" if batch_start % 2 == 0 else "compliance assessor"} would ask about SPARTA coverage.

{content_block}

{"IMPORTANT: inject_flaw — Make 1-2 of your questions intentionally ambiguous, off-topic, or referencing non-existent controls." if inject else "All questions should be legitimate QUERY type."}

{JSON_INSTRUCTION}"""

        persona = "Margaret Chen" if batch_start % 2 == 0 else "Jennifer Cheung"
        system = MARGARET_SYSTEM if persona == "Margaret Chen" else JENNIFER_SYSTEM

        raw = _call_scillm_sync(system, user_prompt)
        parsed = _parse_questions_json(raw, persona, "f36_lesson", bridges)
        all_questions.extend(parsed)

        if (batch_start + batch_size) % 50 == 0:
            logger.info(f"Source A progress: {batch_start + batch_size}/{len(docs)}, {len(all_questions)} questions so far")

    logger.info(f"Source A: generated {len(all_questions)} questions from {len(docs)} lessons")
    return all_questions


# --------------------------------------------------------------------------- #
# Source B: SPARTA QRAs → Adversarial variants
# --------------------------------------------------------------------------- #

def mine_sparta_qras(db: Any, limit: int = 100) -> List[dict]:
    """Feed high-grounding QRAs to personas for adversarial question variants."""
    aql = """
    FOR doc IN sparta_qra
      FILTER doc.grounding_score >= 0.75
      FILTER doc.conceptual_tags != null AND LENGTH(doc.conceptual_tags) > 0
      SORT RAND()
      LIMIT @limit
      RETURN { question: doc.question, answer: SUBSTRING(doc.answer, 0, 500),
               control_id: doc.control_id,
               techniques: doc.sparta_techniques,
               cms: doc.sparta_countermeasures,
               bridges: doc.conceptual_tags }
    """
    try:
        docs = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    except Exception:
        logger.warning("sparta_qra collection not available, skipping Source B")
        return []

    logger.info(f"Source B: {len(docs)} high-grounding QRAs")

    if not docs:
        return []

    batch_size = 10
    all_questions = []

    for batch_start in range(0, len(docs), batch_size):
        batch = docs[batch_start:batch_start + batch_size]
        bridges = []
        for d in batch:
            bridges.extend(d.get("bridges", []))

        content_block = ""
        for i, doc in enumerate(batch):
            content_block += f"\n--- QRA {i+1} ---\n"
            content_block += f"Control: {doc.get('control_id', 'unknown')}\n"
            content_block += f"Original Q: {doc.get('question', '')}\n"
            content_block += f"Answer excerpt: {doc.get('answer', '')[:300]}\n"
            techs = [t.get("id", str(t)) if isinstance(t, dict) else str(t) for t in (doc.get('techniques') or [])[:3]]
            cms = [c.get("id", str(c)) if isinstance(c, dict) else str(c) for c in (doc.get('cms') or [])[:3]]
            content_block += f"Techniques: {', '.join(techs)}\n"
            content_block += f"Countermeasures: {', '.join(cms)}\n"

        inject = random.random() < 0.20  # 20% adversarial injection for QRA variants
        subsystem = random.choice(SUBSYSTEMS)

        user_prompt = f"""These are existing SPARTA QRAs (Question-Reasoning-Answers) with verified answers.
Generate {len(batch)} NEW questions that approach the same controls from a DIFFERENT angle.

Strategies:
- Ask from the opposite perspective (if QRA is about attack, ask about defense, or vice versa)
- Combine two controls into a cross-control synthesis question
- Ask "what-if" scenarios ("What if {subsystem} is compromised?")
- Probe for gaps the original QRA doesn't cover

{content_block}

{"IMPORTANT: inject_flaw — Make 2 questions intentionally problematic: one ambiguous, one referencing a made-up control like SV-ZZ-99." if inject else "All questions should be legitimate QUERY type."}

{JSON_INSTRUCTION}"""

        persona = "Margaret Chen" if batch_start % 2 == 0 else "Jennifer Cheung"
        system = MARGARET_SYSTEM if persona == "Margaret Chen" else JENNIFER_SYSTEM

        raw = _call_scillm_sync(system, user_prompt)
        parsed = _parse_questions_json(raw, persona, "qra_adversarial", bridges)

        # Attach target_control from source QRAs where possible
        for q in parsed:
            if not q.get("target_control"):
                q["target_control"] = batch[0].get("control_id")

        all_questions.extend(parsed)

    logger.info(f"Source B: generated {len(all_questions)} questions from {len(docs)} QRAs")
    return all_questions


# --------------------------------------------------------------------------- #
# Source C: F-36 Specific Claims → probing questions
# --------------------------------------------------------------------------- #

def mine_f36_specific_claims(db: Any, limit: int = 100) -> List[dict]:
    """Feed F-36 lessons with specific data points to personas."""
    # Get lessons with rich content (longer solutions = more data points)
    aql = """
    FOR doc IN lessons
      FILTER doc.scope == "fort_worth_f36"
      FILTER LENGTH(doc.solution) > 100
      SORT RAND()
      LIMIT @limit
      RETURN { problem: doc.problem, solution: SUBSTRING(doc.solution, 0, 600),
               bridge: doc.bridge_attributes, title: doc.title }
    """
    docs = list(db.aql.execute(aql, bind_vars={"limit": limit}))
    logger.info(f"Source C: {len(docs)} F-36 docs with rich content")

    if not docs:
        return []

    batch_size = 10
    all_questions = []

    for batch_start in range(0, len(docs), batch_size):
        batch = docs[batch_start:batch_start + batch_size]
        bridges = []
        for d in batch:
            bridges.extend(d.get("bridge") or [])

        content_block = ""
        for i, doc in enumerate(batch):
            content_block += f"\n--- Document {i+1} ---\n"
            content_block += f"Topic: {doc.get('title', '')}\n"
            content_block += f"Content: {doc.get('problem', '')} {doc.get('solution', '')}\n"

        inject = random.random() < 0.10

        user_prompt = f"""These F-36 documents contain SPECIFIC verifiable claims (numeric thresholds,
requirement IDs, control references, timelines). Generate {len(batch)} questions that
PROBE these specific data points against the SPARTA framework.

Focus on:
- Exact numbers and thresholds mentioned (hours, seconds, MHz, etc.)
- Requirement IDs (F-36-SRS-*, NIST SP 800-*, etc.)
- Named systems, subsystems, or protocols
- Ask how SPARTA maps to or covers these specific claims

{content_block}

{"IMPORTANT: inject_flaw — Make 1 question about something NOT in SPARTA (like weather forecasting or submarine operations)." if inject else "All questions should probe real SPARTA-relevant claims."}

{JSON_INSTRUCTION}"""

        persona = "Margaret Chen" if batch_start % 2 == 0 else "Jennifer Cheung"
        system = MARGARET_SYSTEM if persona == "Margaret Chen" else JENNIFER_SYSTEM

        raw = _call_scillm_sync(system, user_prompt)
        parsed = _parse_questions_json(raw, persona, "f36_claim", bridges)
        all_questions.extend(parsed)

    logger.info(f"Source C: generated {len(all_questions)} questions from {len(docs)} docs")
    return all_questions


# --------------------------------------------------------------------------- #
# Source D: Taxonomy Gap Questions
# --------------------------------------------------------------------------- #

def mine_taxonomy_gaps(
    db: Any = None,
    target_distribution: Optional[Dict[str, float]] = None,
    count: int = 50,
) -> List[dict]:
    """Generate questions targeting underrepresented bridge combinations."""
    if target_distribution is None:
        target_distribution = {
            "Resilience": 0.30,
            "Fragility": 0.20,
            "Precision": 0.18,
            "Loyalty": 0.15,
            "Stealth": 0.10,
            "Corruption": 0.07,
        }

    all_questions = []

    # Generate a batch prompt for each underrepresented bridge
    for bridge, weight in sorted(target_distribution.items(), key=lambda x: x[1]):
        bridge_count = max(2, int(count * weight))
        domain = random.choice(DOMAINS)
        inject = random.random() < 0.15

        user_prompt = f"""Generate {bridge_count} questions about SPARTA controls tagged with the
"{bridge}" bridge attribute in the {domain} domain.

Bridge definitions:
- Precision: targeting, reconnaissance, optimization, algorithm accuracy
- Resilience: defense, hardening, recovery, countermeasures, robustness
- Fragility: vulnerabilities, weaknesses, exploits, CWE entries
- Corruption: compromise, breach, integrity violation, backdoors, malware
- Loyalty: authentication, encryption, trust, compliance, NIST controls
- Stealth: evasion, obfuscation, infiltration, covert channels, exfiltration

Your questions should specifically probe {bridge}-related aspects of space cyber security.

{"IMPORTANT: inject_flaw — Make 1 question deliberately off-topic or about a non-existent framework." if inject else ""}

{JSON_INSTRUCTION}"""

        persona = "Margaret Chen" if bridge in ("Precision", "Fragility", "Resilience") else "Jennifer Cheung"
        system = MARGARET_SYSTEM if persona == "Margaret Chen" else JENNIFER_SYSTEM

        raw = _call_scillm_sync(system, user_prompt, max_tokens=1536)
        parsed = _parse_questions_json(raw, persona, "taxonomy_gap", [bridge])
        all_questions.extend(parsed)

    logger.info(f"Source D: generated {len(all_questions)} taxonomy gap questions")
    return all_questions


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #

def mine_all(
    total: int = 200,
    *,
    db: Any = None,
) -> List[dict]:
    """Mine questions from all 4 sources via /scillm personas.

    Distribution target:
        Source A (F-36 lessons):    ~30%
        Source B (QRA adversarial): ~30%
        Source C (F-36 claims):     ~15%
        Source D (taxonomy gaps):   ~10%
        (adversarial injection:     ~15% embedded in all sources)

    Note: total is approximate — LLM may produce slightly more or fewer per batch.
    """
    if db is None:
        db = _get_db()

    # Enforce minimums so small counts still query real datalake data.
    # With total=3, int(3*0.30)=0 which silently skips all real sources.
    a_target = max(3, int(total * 0.30))
    b_target = max(3, int(total * 0.30))
    c_target = max(2, int(total * 0.15))
    d_target = max(2, int(total * 0.10))

    logger.info(f"Mining ~{total} questions via /scillm personas...")
    all_questions = []

    a_questions = mine_f36_lessons(db, limit=a_target)
    all_questions.extend(a_questions)

    b_questions = mine_sparta_qras(db, limit=b_target)
    all_questions.extend(b_questions)

    c_questions = mine_f36_specific_claims(db, limit=c_target)
    all_questions.extend(c_questions)

    d_questions = mine_taxonomy_gaps(db, count=d_target)
    all_questions.extend(d_questions)

    # Validate all mined questions — reject hallucinated control IDs
    pre_validation_count = len(all_questions)
    all_questions = _validate_mined_questions(all_questions, db)
    rejected = pre_validation_count - len(all_questions)

    # Count adversarial after validation (some may have been rejected)
    adversarial_count = sum(
        1 for q in all_questions
        if q["expected_action"] in ("CLARIFY", "NO_MATCH", "OFF_TOPIC")
    )

    logger.info(
        f"Mined {len(all_questions)} total questions: "
        f"A={len(a_questions)}, B={len(b_questions)}, "
        f"C={len(c_questions)}, D={len(d_questions)}, "
        f"adversarial={adversarial_count} ({adversarial_count/max(1,len(all_questions))*100:.0f}%)"
        + (f", rejected={rejected} (hallucinated IDs)" if rejected else "")
    )

    random.shuffle(all_questions)
    return all_questions
