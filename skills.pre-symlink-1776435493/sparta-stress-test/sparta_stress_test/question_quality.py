"""Quality gate for mined SPARTA stress test questions.

7 rejection criteria + enrichment for passing questions.
Also includes taxonomy coverage balancer (Phase 4).
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

_src_path = str(Path(__file__).resolve().parents[4] / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

try:
    from graph_memory.lessons.store import extract_bridges_fast
except ImportError:
    # Fallback: inline minimal extraction if graph_memory not on path
    def extract_bridges_fast(text: str) -> list[str]:
        """Minimal fallback bridge extraction."""
        if not text:
            return []
        text_lower = text.lower()
        bridges = []
        patterns = {
            "Precision": ["optimiz", "precis", "algorithm", "reconnaissance", "targeting"],
            "Resilience": ["robust", "resili", "harden", "defense", "recover", "countermeasure"],
            "Fragility": ["vulnerability", "weakness", "exploit", "cwe", "fragile"],
            "Corruption": ["corrupt", "compromise", "breach", "backdoor", "malware"],
            "Loyalty": ["auth", "encrypt", "complian", "trust", "nist", "detect"],
            "Stealth": ["evas", "obfuscat", "infiltrat", "covert", "exfiltrat"],
        }
        for tag, pats in patterns.items():
            if any(p in text_lower for p in pats):
                bridges.append(tag)
        return bridges

# --------------------------------------------------------------------------- #
# Quality criteria
# --------------------------------------------------------------------------- #

# Criterion 1: Minimum word count
MIN_WORDS = 15

# Criterion 3: Template skeleton patterns (strip IDs/numbers, compare)
_ID_PATTERN = re.compile(r'SV-\w+-\d+|F-36-\w+-\w+-\d+|T\d{4}|CWE-\d+|NIST-\d+')
_NUMBER_PATTERN = re.compile(r'\b\d+[\.\d]*\b')

# Criterion 5: Jaccard similarity threshold
JACCARD_THRESHOLD = 0.7

# Criterion 6: Persona voice keywords
MARGARET_KEYWORDS = {
    "trace", "traceability", "verification", "coverage", "drift",
    "validate", "evidence", "residual risk", "attack chain", "multi-hop",
    "defense", "mitigate", "aggregate risk", "avionics", "subsystem",
}
JENNIFER_KEYWORDS = {
    "compliance", "rmf", "nist", "cat i", "cat ii", "ssp", "ato",
    "authorization", "fedramp", "finding", "auditor", "boundary",
    "monitoring", "incident response", "risk acceptance", "documentation",
}


def _word_set(text: str) -> Set[str]:
    """Tokenize text into a set of lowered words."""
    return set(text.lower().split())


def _jaccard(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _skeleton(text: str) -> str:
    """Strip IDs and numbers to reveal template skeleton."""
    s = _ID_PATTERN.sub("", text)
    s = _NUMBER_PATTERN.sub("", s)
    return " ".join(s.split()).lower()


# --------------------------------------------------------------------------- #
# Individual criterion scorers (0.0 = bad, 1.0 = good)
# --------------------------------------------------------------------------- #

def score_length(q: dict) -> float:
    """Criterion 1: reject if < MIN_WORDS."""
    words = len(q["question"].split())
    if words < MIN_WORDS:
        return 0.0
    return min(1.0, words / 25)  # Scale up to 25 words


def score_grounding(q: dict) -> float:
    """Criterion 2: must have target_control OR specific data point."""
    text = q["question"]
    if q.get("target_control"):
        return 1.0
    # Check for specific data points
    has_sv = bool(re.search(r'SV-\w+-\d+', text))
    has_nist = bool(re.search(r'(?:SI|IA|AU|AC|SC|CM)-\d+', text))
    has_cwe = bool(re.search(r'CWE-\d+', text))
    has_technique = bool(re.search(r'T\d{4}', text))
    has_threshold = bool(re.search(r'\d+[\.\d]*\s*(?:hour|second|MHz|dB|Mbps)', text))
    has_f36_req = bool(re.search(r'F-36-\w+', text))

    specifics = sum([has_sv, has_nist, has_cwe, has_technique, has_threshold, has_f36_req])
    if specifics >= 1:
        return 0.8
    # Check for domain-specific keywords
    domain_words = {"spacecraft", "ground station", "uplink", "downlink", "avionics",
                    "gps", "telemetry", "command", "control link", "bus"}
    text_lower = text.lower()
    if any(w in text_lower for w in domain_words):
        return 0.5
    return 0.2


def score_template_smell(q: dict, all_skeletons: List[str]) -> float:
    """Criterion 3: reject if skeleton matches > 80% of other skeletons."""
    skel = _skeleton(q["question"])
    if not all_skeletons:
        return 1.0
    matches = sum(1 for s in all_skeletons if _jaccard(_word_set(skel), _word_set(s)) > 0.8)
    # Allow some template reuse but not too much
    if matches > 5:
        return 0.2
    if matches > 2:
        return 0.5
    return 1.0


def score_qra_coverage(q: dict, qra_controls: Set[str], all_controls: Optional[Set[str]] = None) -> float:
    """Criterion 4: entity IDs in question must exist and have QRAs.

    Uses EntityClassifier (trie + gradient boosting) to detect hallucinated IDs
    like SV-ZZ-99, AC-99 that the LLM invented. Falls back to set lookup if
    classifier unavailable.
    """
    # Ambiguous/flawed questions don't need QRA coverage
    if q.get("difficulty") in ("ambiguous", "flawed"):
        return 1.0

    # Use classifier if available
    entities = _classify_entities(q["question"])
    if entities is not None:
        # Classifier-based validation
        fake_ids = [e['entity_id'] for e in entities if not e.get('valid', True)]
        if fake_ids:
            q["_fake_entities"] = fake_ids
            return 0.0

        real_ids = [e['entity_id'] for e in entities if e.get('valid', False)]
        if not real_ids and not q.get("target_control"):
            return 0.5  # No entities found, mild penalty

        # Check QRA coverage for real entities
        all_ids = real_ids
        if q.get("target_control"):
            all_ids = [q["target_control"]] + [e for e in all_ids if e != q["target_control"]]
        if not all_ids:
            return 0.5

        covered = sum(1 for e in all_ids if e in qra_controls)
        if covered == 0:
            return 0.1
        return min(1.0, covered / len(all_ids))

    # Fallback: regex + set lookup (if classifier not available)
    entity_ids = _extract_entity_ids(q["question"])
    target = q.get("target_control")
    if target:
        entity_ids = [target] + [e for e in entity_ids if e != target]

    if not entity_ids:
        return 0.5

    if all_controls:
        fake_ids = [e for e in entity_ids if e not in all_controls and e not in qra_controls]
        if fake_ids:
            q["_fake_entities"] = fake_ids
            return 0.0

    covered = sum(1 for e in entity_ids if e in qra_controls)
    if covered == 0:
        return 0.1
    return min(1.0, covered / len(entity_ids))


def score_duplicate(q: dict, accepted_words: List[Set[str]]) -> float:
    """Criterion 5: Jaccard similarity with existing accepted questions."""
    q_words = _word_set(q["question"])
    for existing in accepted_words:
        if _jaccard(q_words, existing) > JACCARD_THRESHOLD:
            return 0.0
    return 1.0


def score_persona_voice(q: dict) -> float:
    """Criterion 6: persona should use appropriate vocabulary."""
    text_lower = q["question"].lower()
    persona = q.get("persona", "")

    if persona == "Margaret Chen":
        # Margaret shouldn't sound like compliance
        compliance_only = JENNIFER_KEYWORDS - MARGARET_KEYWORDS
        if any(k in text_lower for k in compliance_only):
            return 0.3
        if any(k in text_lower for k in MARGARET_KEYWORDS):
            return 1.0
        return 0.6  # Neutral

    elif persona == "Jennifer Cheung":
        # Jennifer shouldn't sound like V&V
        vv_only = MARGARET_KEYWORDS - JENNIFER_KEYWORDS
        if any(k in text_lower for k in vv_only):
            return 0.3
        if any(k in text_lower for k in JENNIFER_KEYWORDS):
            return 1.0
        return 0.6  # Neutral

    return 0.5


def score_taxonomy(q: dict) -> float:
    """Criterion 7: must have extractable bridge tags."""
    bridges = q.get("bridge_tags") or []
    if bridges:
        return 1.0
    # Try fast extraction
    extracted = extract_bridges_fast(q["question"])
    if extracted:
        q["bridge_tags"] = extracted
        return 0.8
    # Questions with valid entity IDs get partial credit even without
    # bridge keywords — the entity anchoring provides some taxonomy signal
    if q.get("target_control") or q.get("difficulty") in ("ambiguous", "flawed"):
        return 0.4
    return 0.1


# --------------------------------------------------------------------------- #
# Quality Gate
# --------------------------------------------------------------------------- #

def quality_gate(
    questions: List[dict],
    qra_controls: Optional[Set[str]] = None,
    all_controls: Optional[Set[str]] = None,
) -> Tuple[List[dict], List[dict]]:
    """Run all 7 criteria on each question. Returns (accepted, rejected).

    Rejection rules:
      - Any criterion < 0.3 → reject
      - 3+ criteria < 0.5 → reject

    Also enriches passing questions with taxonomy and metadata.
    """
    if qra_controls is None:
        qra_controls = _load_qra_controls()
    if all_controls is None:
        all_controls = _load_all_control_ids()

    accepted = []
    rejected = []
    accepted_word_sets: List[Set[str]] = []
    all_skeletons = [_skeleton(q["question"]) for q in questions]

    for q in questions:
        scores = {
            "length": score_length(q),
            "grounding": score_grounding(q),
            "template_smell": score_template_smell(q, all_skeletons),
            "qra_coverage": score_qra_coverage(q, qra_controls, all_controls),
            "duplicate": score_duplicate(q, accepted_word_sets),
            "persona_voice": score_persona_voice(q),
            "taxonomy": score_taxonomy(q),
        }

        # Rejection logic
        any_below_03 = any(v < 0.3 for v in scores.values())
        count_below_05 = sum(1 for v in scores.values() if v < 0.5)

        if any_below_03 or count_below_05 >= 3:
            q["quality_scores"] = scores
            q["rejection_reason"] = _rejection_reason(scores)
            rejected.append(q)
            continue

        # Enrichment
        q["quality_scores"] = scores
        _enrich_question(q)
        accepted.append(q)
        accepted_word_sets.append(_word_set(q["question"]))

    logger.info(
        f"Quality gate: {len(accepted)} accepted, {len(rejected)} rejected "
        f"({len(rejected) / max(1, len(questions)) * 100:.0f}% rejection rate)"
    )

    return accepted, rejected


def _rejection_reason(scores: Dict[str, float]) -> str:
    """Build human-readable rejection reason."""
    reasons = []
    for name, score in scores.items():
        if score < 0.3:
            reasons.append(f"{name}={score:.2f}")
    if not reasons:
        low = [(n, s) for n, s in scores.items() if s < 0.5]
        reasons = [f"{n}={s:.2f}" for n, s in low]
    return "REJECTED: " + ", ".join(reasons)


def _enrich_question(q: dict) -> None:
    """Enrich a passing question with taxonomy and metadata."""
    # Ensure bridge_tags present
    if not q.get("bridge_tags"):
        q["bridge_tags"] = extract_bridges_fast(q["question"])

    # Assign difficulty complexity score
    word_count = len(q["question"].split())
    has_multi_control = len(re.findall(r'SV-\w+-\d+', q["question"])) > 1
    has_cross_ref = bool(re.search(r'(?:both|compare|overlap|aggregate)', q["question"].lower()))

    if q["difficulty"] in ("ambiguous", "flawed"):
        pass  # Keep assigned difficulty
    elif has_multi_control and has_cross_ref:
        q["difficulty"] = "complex"
    elif has_multi_control or word_count > 40:
        q["difficulty"] = "medium"


_entity_classifier = None

def _get_entity_classifier():
    """Lazy-load singleton EntityClassifier."""
    global _entity_classifier
    if _entity_classifier is None:
        try:
            from .entity_classifier import EntityClassifier
            _entity_classifier = EntityClassifier()
            if not _entity_classifier.load():
                logger.info("No trained model found, training entity classifier...")
                _entity_classifier.train()
        except Exception as e:
            logger.warning(f"Could not load entity classifier: {e}")
            _entity_classifier = False  # Sentinel: don't retry
    return _entity_classifier if _entity_classifier else None


def _classify_entities(text: str) -> Optional[List[Dict]]:
    """Extract and validate entities using the trained classifier.

    Returns list of {entity_id, category, valid, ...} or None if classifier unavailable.
    """
    clf = _get_entity_classifier()
    if clf is None:
        return None
    try:
        return clf.extract_and_validate(text)
    except Exception as e:
        logger.debug(f"Classifier failed, falling back to regex: {e}")
        return None


def _extract_entity_ids(text: str) -> List[str]:
    """Extract SPARTA/NIST/CWE/ATT&CK entity IDs from text using regex.

    Order matters: longer/more specific patterns first to avoid sub-matches.
    """
    ids = []
    # Specific multi-part IDs first (greedy — prevents sub-pattern extraction)
    ids.extend(re.findall(r'\b(SV-[A-Z]{2,3}-\d+)\b', text))
    ids.extend(re.findall(r'\b(ESA-T\d+)\b', text))
    ids.extend(re.findall(r'\b(CWE-\d+)\b', text))
    ids.extend(re.findall(r'\b(D3-[A-Z]+)\b', text))
    ids.extend(re.findall(r'\b(d3f:\w+)\b', text))
    ids.extend(re.findall(r'\b(CM\d{4})\b', text))
    # ATT&CK: T1548.004, T1134, etc.
    ids.extend(re.findall(r'\b(T\d{4}(?:\.\d{3})?)\b', text))
    # SPARTA native: REC-0008.03, DE-0010, etc.
    ids.extend(re.findall(r'\b([A-Z]{2,4}-\d{4}(?:\.\d{2})?)\b', text))
    # NIST: AU-6, IA-5, SI-4, AC-2(12) — but NOT sub-patterns like SP-1 inside SV-SP-1
    for m in re.finditer(r'\b([A-Z]{2}-\d+(?:\(\d+\))?)\b', text):
        candidate = m.group(1)
        start = m.start()
        # Skip if this is a sub-match inside a longer ID (e.g. SP-1 in SV-SP-1)
        if start > 0 and text[start - 1] == '-':
            continue
        ids.append(candidate)

    return list(dict.fromkeys(ids))


def _load_qra_controls() -> Set[str]:
    """Load set of control IDs that have QRAs in ArangoDB."""
    try:
        from graph_memory.arango_client import get_db
        db = get_db()
        result = list(db.aql.execute(
            "FOR doc IN sparta_qra COLLECT ctrl = doc.control_id RETURN ctrl"
        ))
        controls = set(r for r in result if r)
        logger.info(f"Loaded {len(controls)} control IDs with QRAs")
        return controls
    except Exception as e:
        logger.warning(f"Could not load QRA controls: {e}")
        return set()


def _load_all_control_ids() -> Set[str]:
    """Load ALL known control IDs from the controls collection.

    Used to detect hallucinated entity IDs that don't exist at all.
    """
    try:
        from graph_memory.arango_client import get_db
        db = get_db()
        result = list(db.aql.execute(
            "FOR doc IN controls RETURN doc.control_id"
        ))
        controls = set(r for r in result if r and len(str(r)) < 50)  # Skip full-sentence "IDs"
        logger.info(f"Loaded {len(controls)} valid control IDs from controls collection")
        return controls
    except Exception as e:
        logger.warning(f"Could not load control IDs: {e}")
        return set()


# --------------------------------------------------------------------------- #
# Phase 4: Taxonomy Coverage Balancer
# --------------------------------------------------------------------------- #

TARGET_BRIDGE_DISTRIBUTION = {
    "Resilience": 0.30,
    "Fragility": 0.20,
    "Precision": 0.18,
    "Loyalty": 0.15,
    "Stealth": 0.10,
    "Corruption": 0.07,
}

TOLERANCE = 0.05  # ±5%


def balance_taxonomy(
    questions: List[dict],
    gap_mine_fn=None,
    max_iterations: int = 3,
) -> List[dict]:
    """Rebalance question bank to match target bridge distribution.

    If a bridge is underrepresented, mines more questions from Source D.
    Iterates up to max_iterations times until within ±5%.
    """
    for iteration in range(max_iterations):
        dist = _bridge_distribution(questions)
        imbalanced = []
        for bridge, target in TARGET_BRIDGE_DISTRIBUTION.items():
            actual = dist.get(bridge, 0.0)
            if abs(actual - target) > TOLERANCE:
                imbalanced.append((bridge, target, actual))

        if not imbalanced:
            logger.info(f"Taxonomy balanced after {iteration} iterations")
            break

        logger.info(
            f"Iteration {iteration + 1}: {len(imbalanced)} bridges imbalanced: "
            + ", ".join(f"{b}={a:.1%} (target {t:.1%})" for b, t, a in imbalanced)
        )

        # Can't mine more without DB access, just report
        if gap_mine_fn is None:
            logger.warning("No gap mining function provided, cannot rebalance")
            break

        # Mine targeted questions for underrepresented bridges
        for bridge, target, actual in imbalanced:
            if actual < target:
                needed = int((target - actual) * len(questions))
                extras = gap_mine_fn(bridge=bridge, count=needed)
                questions.extend(extras)

    return questions


def _bridge_distribution(questions: List[dict]) -> Dict[str, float]:
    """Calculate current bridge tag distribution across questions."""
    counter: Counter = Counter()
    total = 0
    for q in questions:
        for bridge in (q.get("bridge_tags") or []):
            counter[bridge] += 1
            total += 1

    if total == 0:
        return {}
    return {bridge: count / total for bridge, count in counter.items()}


def report_distribution(questions: List[dict]) -> Dict[str, Any]:
    """Generate a distribution report for the question bank."""
    dist = _bridge_distribution(questions)
    by_difficulty = Counter(q["difficulty"] for q in questions)
    by_persona = Counter(q["persona"] for q in questions)
    by_source = Counter(q.get("source", "unknown") for q in questions)
    by_action = Counter(q["expected_action"] for q in questions)

    return {
        "total": len(questions),
        "bridge_distribution": {k: f"{v:.1%}" for k, v in sorted(dist.items())},
        "by_difficulty": dict(by_difficulty),
        "by_persona": dict(by_persona),
        "by_source": dict(by_source),
        "by_action": dict(by_action),
    }
