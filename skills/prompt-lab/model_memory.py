"""
Model Prompting Memory - Learn what works best for each model.

Stores observations about model behavior, successful prompting patterns,
and failure modes in /memory for retrieval during prompt engineering.

Collection: model_prompting_notes
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

# Try to import memory client
SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.memory_client import MemoryClient, MemoryScope
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False

try:
    from graph_memory.api import MemoryClient as DirectClient
    HAS_DIRECT = True
except ImportError:
    HAS_DIRECT = False


@dataclass
class ModelNote:
    """A note about model behavior."""
    model_alias: str
    model_id: str
    note_type: str  # success, failure, observation, tip
    prompt_type: str  # taxonomy, qra, code, general
    observation: str
    details: Optional[str] = None
    f1_score: Optional[float] = None
    latency_ms: Optional[float] = None
    timestamp: Optional[str] = None


class ModelMemory:
    """Memory integration for model prompting notes."""

    COLLECTION = "model_prompting_notes"

    def __init__(self):
        """Initialize memory client."""
        self.client = None
        self.enabled = False

        if HAS_MEMORY:
            try:
                self.client = MemoryClient(scope=MemoryScope.OPERATIONAL)
                self.enabled = True
            except Exception:
                pass
        elif HAS_DIRECT:
            try:
                self.client = DirectClient(scope=self.COLLECTION)
                self.enabled = True
            except Exception:
                pass

    def learn_note(self, note: ModelNote) -> bool:
        """
        Store a model prompting note in memory.

        Args:
            note: ModelNote with observation details

        Returns:
            True if stored successfully
        """
        if not self.enabled or not self.client:
            return False

        try:
            # Build problem/solution format for memory
            problem = f"model:{note.model_alias} prompt_type:{note.prompt_type} {note.note_type}"

            solution_parts = [note.observation]
            if note.details:
                solution_parts.append(f"Details: {note.details}")
            if note.f1_score is not None:
                solution_parts.append(f"F1: {note.f1_score:.3f}")
            if note.latency_ms is not None:
                solution_parts.append(f"Latency: {note.latency_ms:.0f}ms")

            solution = "\n".join(solution_parts)

            tags = [
                "model_prompting",
                f"model:{note.model_alias}",
                f"type:{note.note_type}",
                f"prompt:{note.prompt_type}",
            ]

            self.client.learn(
                problem=problem,
                solution=solution,
                tags=tags,
            )
            return True

        except Exception:
            return False

    def recall_for_model(
        self,
        model_alias: str,
        prompt_type: Optional[str] = None,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recall notes about a specific model.

        Args:
            model_alias: Model alias (e.g., 'deepseek-v3')
            prompt_type: Optional filter by prompt type
            k: Number of notes to retrieve

        Returns:
            List of relevant notes
        """
        if not self.enabled or not self.client:
            return []

        try:
            query = f"model:{model_alias}"
            if prompt_type:
                query += f" prompt_type:{prompt_type}"

            result = self.client.recall(query, k=k)
            return result.get("items", []) if result.get("found") else []

        except Exception:
            return []

    def recall_successes(
        self,
        prompt_type: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recall successful prompting patterns for a prompt type.

        Args:
            prompt_type: Type of prompt (taxonomy, qra, etc.)
            k: Number of notes to retrieve

        Returns:
            List of successful patterns
        """
        if not self.enabled or not self.client:
            return []

        try:
            query = f"prompt_type:{prompt_type} type:success"
            result = self.client.recall(query, k=k)
            return result.get("items", []) if result.get("found") else []

        except Exception:
            return []

    def recall_failures(
        self,
        model_alias: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recall known failure modes for a model.

        Args:
            model_alias: Model alias
            k: Number of notes to retrieve

        Returns:
            List of known failures
        """
        if not self.enabled or not self.client:
            return []

        try:
            query = f"model:{model_alias} type:failure"
            result = self.client.recall(query, k=k)
            return result.get("items", []) if result.get("found") else []

        except Exception:
            return []


def record_eval_result(
    memory: ModelMemory,
    model_alias: str,
    model_id: str,
    prompt_type: str,
    f1_score: float,
    latency_ms: float,
    observation: str,
    details: Optional[str] = None,
) -> bool:
    """
    Record an evaluation result as a model note.

    Args:
        memory: ModelMemory instance
        model_alias: Model alias
        model_id: Full model ID
        prompt_type: Type of prompt evaluated
        f1_score: F1 score achieved
        latency_ms: Latency in milliseconds
        observation: What was learned
        details: Additional details

    Returns:
        True if stored
    """
    note_type = "success" if f1_score >= 0.8 else "observation" if f1_score >= 0.5 else "failure"

    note = ModelNote(
        model_alias=model_alias,
        model_id=model_id,
        note_type=note_type,
        prompt_type=prompt_type,
        observation=observation,
        details=details,
        f1_score=f1_score,
        latency_ms=latency_ms,
        timestamp=datetime.now().isoformat(),
    )

    return memory.learn_note(note)


def get_model_recommendations(
    memory: ModelMemory,
    prompt_type: str,
) -> str:
    """
    Get model recommendations based on stored notes.

    Args:
        memory: ModelMemory instance
        prompt_type: Type of prompt

    Returns:
        Formatted recommendations string
    """
    successes = memory.recall_successes(prompt_type, k=10)

    if not successes:
        return "No model recommendations available yet. Run evaluations to build knowledge."

    lines = [f"Model recommendations for {prompt_type} prompts:"]
    lines.append("-" * 50)

    seen_models = set()
    for item in successes:
        problem = item.get("problem", "")
        solution = item.get("solution", "")

        # Extract model from problem
        if "model:" in problem:
            model = problem.split("model:")[1].split()[0]
            if model not in seen_models:
                seen_models.add(model)
                lines.append(f"\n{model}:")
                lines.append(f"  {solution[:200]}...")

    return "\n".join(lines)


# Singleton instance
_memory_instance: Optional[ModelMemory] = None


def get_model_memory() -> ModelMemory:
    """Get or create global ModelMemory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ModelMemory()
    return _memory_instance


# Pre-seed with known observations
KNOWN_OBSERVATIONS = [
    ModelNote(
        model_alias="deepseek-v3",
        model_id="deepseek-ai/DeepSeek-V3-0324-TEE",
        note_type="success",
        prompt_type="taxonomy",
        observation="Achieves 0.95 F1 on taxonomy extraction with vocabulary in system prompt",
        details="Works best with explicit vocabulary list and JSON response_format",
        f1_score=0.95,
    ),
    ModelNote(
        model_alias="kimi",
        model_id="moonshotai/Kimi-K2.5-TEE",
        note_type="failure",
        prompt_type="taxonomy",
        observation="JSON mode fails - returns malformed JSON or ignores response_format",
        details="Use kimi-instruct instead for structured output tasks",
    ),
    ModelNote(
        model_alias="kimi-instruct",
        model_id="moonshotai/Kimi-K2-Instruct-0905",
        note_type="tip",
        prompt_type="taxonomy",
        observation="JSON mode works reliably, good alternative to DeepSeek",
        details="September 2025 release fixed JSON issues from K2.5",
    ),
    ModelNote(
        model_alias="deepseek-terminus",
        model_id="deepseek-ai/DeepSeek-V3.1-Terminus-TEE",
        note_type="tip",
        prompt_type="general",
        observation="Best for agentic workflows with tool use",
        details="Optimized for reasoning chains and multi-step tasks",
    ),
    ModelNote(
        model_alias="minimax",
        model_id="MiniMaxAI/MiniMax-M2.1-TEE",
        note_type="tip",
        prompt_type="general",
        observation="1M context window useful for long document processing",
        details="Lightning MoE architecture, only 2 experts active per token",
    ),
]


def seed_known_observations(memory: Optional[ModelMemory] = None) -> int:
    """
    Seed memory with known model observations.

    Returns:
        Number of observations stored
    """
    if memory is None:
        memory = get_model_memory()

    if not memory.enabled:
        return 0

    stored = 0
    for note in KNOWN_OBSERVATIONS:
        if memory.learn_note(note):
            stored += 1

    return stored


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Model prompting memory")
    parser.add_argument("command", choices=["seed", "recall", "recommend"],
                        help="Command to run")
    parser.add_argument("--model", "-m", help="Model alias")
    parser.add_argument("--type", "-t", default="taxonomy", help="Prompt type")
    args = parser.parse_args()

    memory = get_model_memory()

    if not memory.enabled:
        print("Memory not available (standalone mode)")
        sys.exit(1)

    if args.command == "seed":
        stored = seed_known_observations(memory)
        print(f"Seeded {stored} known observations")

    elif args.command == "recall":
        if not args.model:
            print("--model required for recall")
            sys.exit(1)
        notes = memory.recall_for_model(args.model, args.type)
        print(f"Notes for {args.model}:")
        for note in notes:
            print(f"  - {note.get('solution', '')[:100]}...")

    elif args.command == "recommend":
        print(get_model_recommendations(memory, args.type))
