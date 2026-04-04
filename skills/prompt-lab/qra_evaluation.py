"""
Prompt Lab Skill - QRA Evaluation
QRA-specific test cases, results, and metrics.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import SKILL_DIR


@dataclass
class QRATestCase:
    """A QRA test case with input and expected keywords."""
    id: str
    name: str
    description: str
    collection: str
    item_type: str
    question_keywords: List[str]
    reasoning_keywords: List[str]
    min_reasoning_sentences: int
    notes: str = ""


@dataclass
class QRAResult:
    """Result of evaluating a QRA generation."""
    case_id: str
    question: str
    reasoning: str
    answer: str
    confidence: float
    question_keyword_hits: int
    question_keyword_total: int
    reasoning_keyword_hits: int
    reasoning_keyword_total: int
    reasoning_sentences: int
    latency_ms: float

    @property
    def question_score(self) -> float:
        if self.question_keyword_total == 0:
            return 1.0
        return self.question_keyword_hits / self.question_keyword_total

    @property
    def reasoning_score(self) -> float:
        if self.reasoning_keyword_total == 0:
            return 1.0
        return self.reasoning_keyword_hits / self.reasoning_keyword_total

    @property
    def overall_score(self) -> float:
        return (self.question_score + self.reasoning_score) / 2


@dataclass
class QRAGroundedTestCase:
    """QRA test case with citation grounding validation."""
    id: str
    name: str
    description: str
    source_text: str
    min_qras: int
    required_question_types: List[str]
    citations_must_be_verbatim: bool
    notes: str = ""

class AmbiguityGate:
    """Input Guard: Detects ambiguous questions that fail taxonomy mapping."""

    @staticmethod
    def check(question: str, context_keywords: List[str]) -> Dict[str, Any]:
        """Check content ambiguity using keyword density and length."""
        # 1. Length Check (Too short = likely Vague)
        if len(question.split()) < 5:
            return {"ok": False, "reason": "Too short (ambiguous)"}

        # 2. Context Keyword Check - use improved entity matching
        if _entity_mentioned(context_keywords, question.lower()):
            return {"ok": True, "reason": "Pass"}

        return {"ok": False, "reason": f"Missing context keywords: {context_keywords[:3]}..."}


def _entity_mentioned(keywords: List[str], question_lower: str) -> bool:
    """
    Check if any keyword (or significant part) is mentioned in the question.

    Handles:
    - Exact matches (case-insensitive)
    - ID patterns (CWE-xxx, T1xxx, CM-xxxx, D3-xxx, AC-x(x))
    - Parenthetical parts of long CWE names
    - Significant trailing phrases for very long names (30+ chars)
    - Namespace-stripped variants (d3f:Foo -> Foo)
    """
    import re
    for keyword in keywords:
        if not keyword:
            continue
        keyword_lower = keyword.lower()

        # Direct match
        if keyword_lower in question_lower:
            return True

        # Namespace-stripped match (d3f:Foo -> Foo)
        if ":" in keyword:
            stripped = keyword.split(":", 1)[1].lower()
            if stripped and stripped in question_lower:
                return True

        # ID pattern matching (CWE-xxx, T1xxx, CM-xxxx, D3-xxx, AC-x)
        if re.match(r"^(cwe-?\d+|t\d+\.?\d*|cm-?\d+|d3-\w+|rd-\d+\.?\d*|[a-z]{2,3}-\d+)", keyword_lower):
            if keyword_lower in question_lower:
                return True
            # Also try without parenthetical (AC-4(17) -> AC-4)
            base = re.sub(r"\(\d+\)$", "", keyword_lower)
            if base != keyword_lower and base in question_lower:
                return True

        # Parenthetical parts of long names like "Improper Input Validation ('Injection')"
        paren_match = re.search(r"\('([^']+)'\)|\(([^)]+)\)", keyword)
        if paren_match:
            paren_text = (paren_match.group(1) or paren_match.group(2)).lower()
            if len(paren_text) > 5 and paren_text in question_lower:
                return True

        # Significant trailing phrases for long names (25+ chars)
        # e.g., "Credential Access Through Kerberoasting" -> "kerberoasting"
        if len(keyword) >= 25:
            words = keyword.split()
            if len(words) >= 3:
                # Check last 2 words
                last_words = " ".join(words[-2:]).lower()
                if last_words in question_lower:
                    return True
                # Also check just the last word if it's substantial
                if len(words[-1]) > 6 and words[-1].lower() in question_lower:
                    return True

    return False


def check_entity_anchoring(question: str, entities: List[str]) -> Dict[str, Any]:
    """Check if question explicitly names at least one entity."""
    question_lower = question.lower()

    # Use improved entity matching
    if _entity_mentioned(entities, question_lower):
        # Find which entities were found for reporting
        found = []
        for e in entities:
            if e and e.lower() in question_lower:
                found.append(e)
            elif e and ":" in e and e.split(":", 1)[1].lower() in question_lower:
                found.append(e)
        missing = [e for e in entities if e not in found]
        return {
            "anchored": True,
            "found_entities": found if found else ["(matched via pattern)"],
            "missing_entities": missing
        }

    missing = entities
    return {
        "anchored": False,
        "found_entities": [],
        "missing_entities": missing
    }


@dataclass
class QRAGroundedResult:
    """Result of evaluating QRA generation with citation grounding."""
    case_id: str
    qra_items: List[Dict[str, Any]]
    source_text: str
    latency_ms: float
    total_qras: int
    citation_grounding_rate: float
    hallucination_count: int
    duplicate_count: int
    question_type_distribution: Dict[str, float]
    persona_distribution: Dict[str, float]
    confidence_distribution: Dict[str, float]
    question_type_coverage: int
    # SPARTA Metrics
    ambiguity_pass_rate: float = 1.0
    entity_anchoring_rate: float = 1.0
    missing_entities_common: List[str] = None

@dataclass
class QRAEvalSummary:
    """Summary of QRA evaluation with citation grounding metrics."""
    prompt_name: str
    model_name: str
    timestamp: str
    results: List[QRAGroundedResult]
    
    @property
    def total_qras_generated(self) -> int:
        return sum(r.total_qras for r in self.results)
    
    @property
    def avg_qras_per_input(self) -> float:
        if not self.results:
            return 0.0
        return self.total_qras_generated / len(self.results)
    
    @property
    def avg_citation_grounding_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.citation_grounding_rate for r in self.results) / len(self.results)
    
    @property
    def total_hallucinations(self) -> int:
        return sum(r.hallucination_count for r in self.results)
    
    @property
    def total_duplicates(self) -> int:
        return sum(r.duplicate_count for r in self.results)
    
    @property
    def avg_question_type_coverage(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.question_type_coverage for r in self.results) / len(self.results)
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.latency_ms for r in self.results) / len(self.results)

    @property
    def avg_ambiguity_pass_rate(self) -> float:
        if not self.results: return 0.0
        return sum(r.ambiguity_pass_rate for r in self.results) / len(self.results)

    @property
    def avg_entity_anchoring_rate(self) -> float:
        if not self.results: return 0.0
        return sum(r.entity_anchoring_rate for r in self.results) / len(self.results)



class QRAEvaluator:
    """Centralized evaluator for QRA items using grounding, ambiguity, and diversity metrics."""
    
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold

    def evaluate(
        self, 
        case_id: str, 
        qra_items: List[Dict[str, Any]], 
        source_text: str, 
        context_keywords: List[str], 
        latency_ms: float
    ) -> QRAGroundedResult:
        """Evaluate a set of QRA items for a single test case."""
        from citation_validator import validate_citations, check_duplicate_answers, analyze_question_diversity
        
        # 1. Citation Grounding
        citation_validation = validate_citations(qra_items, source_text, self.threshold)
        
        # 2. Ambiguity & Anchoring
        ambiguity_passes = 0
        anchoring_passes = 0
        common_missing = []
        
        for item in qra_items:
            q = item.get("question", "")
            # Ambiguity Check
            if AmbiguityGate.check(q, context_keywords)["ok"]:
                ambiguity_passes += 1
            
            # Entity Anchoring Check
            anchoring = check_entity_anchoring(q, context_keywords)
            if anchoring["anchored"]:
                anchoring_passes += 1
            else:
                common_missing.extend(anchoring["missing_entities"])

        ambiguity_rate = ambiguity_passes / len(qra_items) if qra_items else 1.0
        anchoring_rate = anchoring_passes / len(qra_items) if qra_items else 1.0
        
        # 3. Diversity & Duplicates
        duplicates = check_duplicate_answers(qra_items)
        diversity = analyze_question_diversity(qra_items)
        
        return QRAGroundedResult(
            case_id=case_id,
            qra_items=qra_items,
            source_text=source_text[:100], # Truncated
            latency_ms=latency_ms,
            total_qras=len(qra_items),
            citation_grounding_rate=citation_validation.grounding_rate,
            hallucination_count=citation_validation.ungrounded_citations,
            duplicate_count=len(duplicates),
            question_type_distribution=diversity["question_type_distribution"],
            persona_distribution=diversity["persona_distribution"],
            confidence_distribution=diversity["confidence_distribution"],
            question_type_coverage=diversity["question_type_coverage"],
            ambiguity_pass_rate=ambiguity_rate,
            entity_anchoring_rate=anchoring_rate,
            missing_entities_common=list(set(common_missing))
        )
def load_qra_ground_truth(skill_dir: Optional[Path] = None) -> List[QRATestCase]:
    """Load QRA ground truth test cases."""
    if skill_dir is None:
        skill_dir = SKILL_DIR

    gt_file = skill_dir / "ground_truth" / "qra.json"
    if not gt_file.exists():
        return []

    data = json.loads(gt_file.read_text())
    cases = []
    for c in data.get("cases", []):
        inp = c.get("input", {})
        name = inp.get("name")
        description = inp.get("description")
        collection = inp.get("collection", "")
        item_type = inp.get("type", "")
        
        # Handle SPARTA nested tactic/control schema
        if not name and "tactic_hierarchy" in inp:
            tech = inp["tactic_hierarchy"].get("technique", {})
            name = tech.get("name")
            description = tech.get("description")
            collection = tech.get("id", "")
            item_type = "tactic_control"
            
        cases.append(QRATestCase(
            id=c["id"],
            name=name or c["id"],
            description=description or "",
            collection=collection,
            item_type=item_type,
            question_keywords=c["expected"].get("question_contains", []),
            reasoning_keywords=c["expected"].get("reasoning_contains", []),
            min_reasoning_sentences=c["expected"].get("min_reasoning_sentences", 2),
            notes=c.get("notes", "")
        ))
    return cases


def load_qra_grounded_truth(skill_dir: Optional[Path] = None) -> List[QRAGroundedTestCase]:
    """Load QRA grounded truth test cases with citation validation."""
    if skill_dir is None:
        skill_dir = SKILL_DIR
    
    gt_file = skill_dir / "ground_truth" / "qra_grounded.json"
    if not gt_file.exists():
        return []
    
    data = json.loads(gt_file.read_text())
    cases = []
    for c in data.get("cases", []):
        cases.append(QRAGroundedTestCase(
            id=c["id"],
            name=c["input"]["name"],
            description=c["input"]["description"],
            source_text=c["source_text"],
            min_qras=c["expected"].get("min_qras", 3),
            required_question_types=c["expected"].get("required_types", []),
            citations_must_be_verbatim=c["expected"].get("citations_grounded", True),
            notes=c.get("notes", "")
        ))
    return cases
