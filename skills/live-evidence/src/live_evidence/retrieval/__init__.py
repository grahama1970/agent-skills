"""Evidence retrieval clients and ranking helpers."""

from .external import ExternalSkillClient
from .ask import AskSolutionClient
from .memory import MemoryEvidenceClient
from .ranker import has_reviewed_oracle_answer, is_code_location_query, prefer_reviewed_oracle_answers, rank_sources
from .ripgrep import RipgrepEvidenceClient

__all__ = [
    "AskSolutionClient",
    "ExternalSkillClient",
    "has_reviewed_oracle_answer",
    "is_code_location_query",
    "MemoryEvidenceClient",
    "prefer_reviewed_oracle_answers",
    "RipgrepEvidenceClient",
    "rank_sources",
]
