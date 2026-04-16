"""
Shared validation functions for SPARTA QRA quality gates.
Used by: prompt-lab, batch-quality, quality-audit

Provides:
- AmbiguityGate.check() - Validate question clarity
- check_entity_anchoring() - Validate question grounds in context entities
-validate_citations() - Validate answers cite source text
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Set, Tuple

# Import from prompt-lab
import sys
from pathlib import Path

# Add prompt-lab to path if not already there
PROMPT_LAB_DIR = Path(__file__).parent.parent / "prompt-lab"
if str(PROMPT_LAB_DIR) not in sys.path:
    sys.path.insert(0, str(PROMPT_LAB_DIR))

try:
    from ambiguity_gate import AmbiguityGate
    from entity_anchoring import check_entity_anchoring
    from citation_validator import (
        validate_citation,
        validate_citations,
        CitationValidation,
        CitationValidationSummary,
        check_duplicate_answers,
        analyze_question_diversity
    )
except ImportError as e:
    raise ImportError(
        f"Failed to import from prompt-lab. Ensure prompt-lab is available: {e}"
    )


# Re-export all validation functions
__all__ = [
    "AmbiguityGate",
    "check_entity_anchoring",
    "validate_citation",
    "validate_citations",
    "CitationValidation",
    "CitationValidationSummary",
    "check_duplicate_answers",
    "analyze_question_diversity",
]
