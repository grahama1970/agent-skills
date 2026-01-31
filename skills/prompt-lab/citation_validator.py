"""
Prompt Lab Skill - Citation Grounding Validation
Validates that citations in QRA items are verbatim excerpts from source text.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

try:
    from rapidfuzz import fuzz
except ImportError:
    # Fallback to basic string matching if rapidfuzz not available
    class fuzz:
        @staticmethod
        def partial_ratio(s1: str, s2: str) -> float:
            """Fallback: simple substring matching."""
            if not s1 or not s2:
                return 0.0
            s1_lower = s1.lower().strip()
            s2_lower = s2.lower().strip()
            if s1_lower in s2_lower or s2_lower in s1_lower:
                return 100.0
            return 0.0


@dataclass
class CitationValidation:
    """Result of validating a single citation."""
    citation: str
    score: float
    is_grounded: bool
    question_preview: str


@dataclass
class CitationValidationSummary:
    """Summary of citation validation for all QRA items."""
    total_citations: int
    grounded_citations: int
    ungrounded_citations: int
    hallucinations: List[CitationValidation]
    
    @property
    def grounding_rate(self) -> float:
        """Percentage of citations that are properly grounded."""
        if self.total_citations == 0:
            return 1.0
        return self.grounded_citations / self.total_citations


def validate_citation(
    citation: str,
    source_text: str,
    threshold: float = 0.85
) -> Tuple[bool, float]:
    """
    Validate a single citation against source text.
    
    Args:
        citation: Citation text to validate
        source_text: Source text to check against
        threshold: Minimum similarity score to consider grounded (0.0-1.0)
    
    Returns:
        Tuple of (is_grounded, similarity_score)
    """
    if not citation or not source_text:
        return False, 0.0
    
    # Use rapidfuzz for fuzzy matching
    score = fuzz.partial_ratio(citation.lower(), source_text.lower()) / 100.0
    is_grounded = score >= threshold
    
    return is_grounded, score


def validate_citations(
    qra_items: List[Dict[str, Any]],
    source_text: str,
    threshold: float = 0.85
) -> CitationValidationSummary:
    """
    Validate all citations in QRA items against source text.
    
    Args:
        qra_items: List of QRA items with citations
        source_text: Source text to validate against
        threshold: Minimum similarity score (0.0-1.0)
    
    Returns:
        CitationValidationSummary with detailed results
    """
    hallucinations = []
    grounded_count = 0
    ungrounded_count = 0
    total_citations = 0
    
    for item in qra_items:
        citations = item.get("citations", [])
        question = item.get("question", "")
        
        for citation in citations:
            total_citations += 1
            is_grounded, score = validate_citation(citation, source_text, threshold)
            
            if is_grounded:
                grounded_count += 1
            else:
                ungrounded_count += 1
                hallucinations.append(CitationValidation(
                    citation=citation[:200],  # Truncate for display
                    score=score,
                    is_grounded=False,
                    question_preview=question[:100]
                ))
    
    return CitationValidationSummary(
        total_citations=total_citations,
        grounded_citations=grounded_count,
        ungrounded_citations=ungrounded_count,
        hallucinations=hallucinations
    )


def check_duplicate_answers(qra_items: List[Dict[str, Any]], threshold: float = 0.90) -> List[Tuple[str, str]]:
    """
    Find duplicate or near-duplicate answers in QRA items.
    
    Args:
        qra_items: List of QRA items
        threshold: Similarity threshold for duplicates (0.0-1.0)
    
    Returns:
        List of (question1, question2) pairs with duplicate answers
    """
    duplicates = []
    answers = [(item.get("question", ""), item.get("answer", "")) for item in qra_items]
    
    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            q1, a1 = answers[i]
            q2, a2 = answers[j]
            
            if not a1 or not a2:
                continue
            
            similarity = fuzz.ratio(a1.lower(), a2.lower()) / 100.0
            if similarity >= threshold:
                duplicates.append((q1[:100], q2[:100]))
    
    return duplicates


def analyze_question_diversity(
    qra_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Analyze diversity of questions, personas, and confidence levels.
    
    Args:
        qra_items: List of QRA items
    
    Returns:
        Dict with distribution metrics
    """
    question_types = {}
    personas = {}
    confidence_levels = {}
    
    for item in qra_items:
        # Question type
        q_type = item.get("question_type", "unknown")
        question_types[q_type] = question_types.get(q_type, 0) + 1
        
        # Persona
        persona = item.get("questioner_persona", "unknown")
        personas[persona] = personas.get(persona, 0) + 1
        
        # Confidence
        confidence = item.get("confidence", "unknown")
        confidence_levels[confidence] = confidence_levels.get(confidence, 0) + 1
    
    total = len(qra_items)
    
    return {
        "question_type_distribution": {
            k: v / total if total > 0 else 0 for k, v in question_types.items()
        },
        "persona_distribution": {
            k: v / total if total > 0 else 0 for k, v in personas.items()
        },
        "confidence_distribution": {
            k: v / total if total > 0 else 0 for k, v in confidence_levels.items()
        },
        "question_type_coverage": len(question_types),
        "persona_coverage": len(personas),
        "total_qras": total
    }
