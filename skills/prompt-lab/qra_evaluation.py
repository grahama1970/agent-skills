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
            
        # 2. Context Keyword Check
        # The question MUST reference specific entities from the context
        found_keywords = [k for k in context_keywords if k.lower() in question.lower()]
        if not found_keywords:
            return {"ok": False, "reason": f"Missing context keywords: {context_keywords[:3]}..."}
            
        return {"ok": True, "reason": "Pass"}

def check_entity_anchoring(question: str, entities: List[str]) -> Dict[str, Any]:
    """Check if question explicitly names at least one entity."""
    found = [e for e in entities if e.lower() in question.lower()]
    missing = [e for e in entities if e not in found]
    return {
        "anchored": len(found) > 0,
        "found_entities": found,
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
        cases.append(QRATestCase(
            id=c["id"],
            name=c["input"]["name"],
            description=c["input"]["description"],
            collection=c["input"].get("collection", ""),
            item_type=c["input"].get("type", ""),
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
