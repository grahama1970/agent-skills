"""
Memory Integration for Prompt Lab

Queries /memory skill for similar past taxonomy extractions to provide
few-shot context, improving extraction accuracy.

Uses the common memory client pattern for standard integration.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Try to import common memory client (standard skill integration pattern)
SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.memory_client import MemoryClient, MemoryScope, recall
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False

# Also try direct import from graph_memory if available
try:
    from graph_memory.api import MemoryClient as DirectClient
    HAS_DIRECT_CLIENT = True
except ImportError:
    HAS_DIRECT_CLIENT = False


class TaxonomyMemory:
    """Memory integration for taxonomy extraction few-shot context."""

    def __init__(self, scope: str = "taxonomy"):
        """Initialize memory client with taxonomy scope."""
        self.scope = scope
        self.client = None
        self.enabled = False

        if HAS_MEMORY_CLIENT:
            try:
                self.client = MemoryClient(scope=MemoryScope.OPERATIONAL)
                self.enabled = True
            except Exception:
                pass
        elif HAS_DIRECT_CLIENT:
            try:
                self.client = DirectClient(scope=scope)
                self.enabled = True
            except Exception:
                pass

    def recall_similar(
        self,
        name: str,
        description: str,
        k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Recall similar past taxonomy extractions.

        Args:
            name: Control/technique name
            description: Control/technique description
            k: Number of similar examples to retrieve

        Returns:
            List of similar past extractions with their labels
        """
        if not self.enabled or not self.client:
            return []

        try:
            # Build query from name and description
            query = f"taxonomy extraction: {name} - {description[:200]}"

            # Recall from memory
            result = self.client.recall(query, k=k)

            if result.get("found", False):
                return result.get("items", [])
            return []

        except Exception:
            return []

    def learn_extraction(
        self,
        name: str,
        description: str,
        conceptual: List[str],
        tactical: List[str],
        confidence: float,
    ) -> bool:
        """
        Store a taxonomy extraction for future few-shot context.

        Args:
            name: Control/technique name
            description: Control/technique description
            conceptual: Extracted conceptual tags
            tactical: Extracted tactical tags
            confidence: Extraction confidence score

        Returns:
            True if successfully stored
        """
        if not self.enabled or not self.client:
            return False

        try:
            problem = f"taxonomy extraction: {name}"
            solution = (
                f"Conceptual: {', '.join(conceptual)}\n"
                f"Tactical: {', '.join(tactical)}\n"
                f"Context: {description[:300]}"
            )

            self.client.learn(
                problem=problem,
                solution=solution,
                tags=["taxonomy", "prompt-lab"] + conceptual + tactical,
            )
            return True

        except Exception:
            return False


def format_few_shot_examples(
    similar: List[Dict[str, Any]],
    max_examples: int = 3,
) -> str:
    """
    Format retrieved examples as few-shot context for the prompt.

    Args:
        similar: List of similar past extractions from memory
        max_examples: Maximum number of examples to include

    Returns:
        Formatted few-shot examples string
    """
    if not similar:
        return ""

    examples = []
    for i, item in enumerate(similar[:max_examples], 1):
        problem = item.get("problem", "")
        solution = item.get("solution", "")

        if problem and solution:
            examples.append(f"Example {i}:\n  Input: {problem}\n  Output: {solution}")

    if not examples:
        return ""

    return "\n\nFew-shot examples from memory:\n" + "\n\n".join(examples) + "\n"


def enhance_prompt_with_memory(
    system_prompt: str,
    name: str,
    description: str,
    memory: Optional[TaxonomyMemory] = None,
) -> str:
    """
    Enhance system prompt with few-shot examples from memory.

    Args:
        system_prompt: Original system prompt
        name: Control/technique name
        description: Control/technique description
        memory: TaxonomyMemory instance (optional)

    Returns:
        Enhanced system prompt with few-shot context
    """
    if memory is None:
        memory = TaxonomyMemory()

    if not memory.enabled:
        return system_prompt

    # Recall similar extractions
    similar = memory.recall_similar(name, description, k=3)

    # Format as few-shot examples
    examples = format_few_shot_examples(similar)

    if examples:
        # Insert examples before the [USER] section or at end
        if "[USER]" in system_prompt:
            parts = system_prompt.split("[USER]")
            return parts[0] + examples + "[USER]" + parts[1]
        else:
            return system_prompt + examples

    return system_prompt


# Global instance for convenience
_memory_instance: Optional[TaxonomyMemory] = None


def get_memory() -> TaxonomyMemory:
    """Get or create global TaxonomyMemory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = TaxonomyMemory()
    return _memory_instance
