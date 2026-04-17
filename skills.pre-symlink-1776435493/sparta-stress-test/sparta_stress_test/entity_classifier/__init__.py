"""Entity ID extraction and validation classifier for SPARTA stress tests.

Replaces brittle regex with a trie-based extractor + DistilBERT hallucination detector.

Two-stage architecture:
  1. Trie extractor: Fast, exact-match extraction of candidate entity IDs
     from text using an Aho-Corasick automaton built from all known IDs.
  2. Hallucination classifier: For candidate IDs NOT found in the trie,
     classify as REAL (new/unseen but plausible) vs HALLUCINATED (LLM invention).
"""

from .extractor import EntityExtractor
from .validator import EntityValidator
from .classifier import EntityClassifier

__all__ = ["EntityExtractor", "EntityValidator", "EntityClassifier"]
