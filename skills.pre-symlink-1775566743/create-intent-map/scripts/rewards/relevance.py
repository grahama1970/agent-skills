"""Relevance reward function using LLM judge.

Uses scillm to evaluate whether retrieved QRAs actually answer the query.
This provides semantic relevance signal beyond just grounding scores.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .execution import QuerySpec, get_executor

# Ensure scillm is importable
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(_SKILLS_DIR / "scillm") not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR / "scillm"))


JUDGE_SYSTEM_PROMPT = """You are a relevance judge for a space cybersecurity knowledge base.

Given a user query and retrieved results, rate how well the results answer the query.

Score 0-10:
- 0-2: Results are irrelevant or completely miss the point
- 3-4: Results are tangentially related but don't answer the question
- 5-6: Results partially answer the question
- 7-8: Results mostly answer the question with good coverage
- 9-10: Results directly and comprehensively answer the question

Output ONLY a single integer 0-10, nothing else."""

JUDGE_USER_TEMPLATE = """Query: {query}

Retrieved Results:
{results}

Score (0-10):"""


class ScillmJudge:
    """LLM judge for relevance scoring via scillm."""

    def __init__(self, model: str = "deepseek-ai/DeepSeek-V3"):
        self.model = model
        self.api_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
        try:
            from batch import quick_completion
            self._quick_completion = quick_completion
        except ImportError:
            self._quick_completion = None

    def score(self, query: str, results: list[dict]) -> float:
        """Score relevance of results to query.

        Args:
            query: Original user query
            results: List of QRA result dicts

        Returns:
            Relevance score 0.0-1.0 (normalized from 0-10)
        """
        if not self.api_key or not self._quick_completion:
            logger.warning("No API key or scillm unavailable, returning neutral score")
            return 0.5

        if not results:
            return 0.0

        formatted_results = []
        for i, r in enumerate(results[:3]):
            formatted_results.append(
                f"{i+1}. Q: {r.get('question', 'N/A')}\n"
                f"   A: {r.get('answer', 'N/A')[:200]}..."
            )
        results_text = "\n\n".join(formatted_results)

        try:
            content = self._quick_completion(
                JUDGE_USER_TEMPLATE.format(query=query, results=results_text),
                system=JUDGE_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=10,
                timeout=30,
            ).strip()

            try:
                score = int(content)
                return min(1.0, max(0.0, score / 10.0))
            except ValueError:
                match = re.search(r'\d+', content)
                if match:
                    score = int(match.group())
                    return min(1.0, max(0.0, score / 10.0))
                return 0.5

        except Exception as e:
            logger.warning(f"LLM judge failed: {e}")
            return 0.5

    def close(self) -> None:
        """No-op (scillm manages its own connections)."""
        pass


class MockJudge:
    """Mock judge for testing without API calls."""

    def __init__(self):
        self.call_count = 0

    def score(self, query: str, results: list[dict]) -> float:
        """Return mock score based on result presence."""
        self.call_count += 1
        if not results:
            return 0.0
        # Mock: score based on number of results and their grounding
        avg_grounding = sum(r.get("grounding_score", 0.5) for r in results) / len(results)
        return min(1.0, avg_grounding + 0.1)

    def close(self) -> None:
        """No-op for mock judge."""
        pass


def get_judge(mock: bool = False) -> ScillmJudge | MockJudge:
    """Get appropriate judge based on environment."""
    if mock:
        return MockJudge()

    judge = ScillmJudge()
    if not judge.api_key:
        logger.warning("No API key found, using mock judge")
        return MockJudge()
    return judge


def relevance_reward(
    completions: list[list[dict]],
    prompts: list[str] = None,
    queries: list[str] = None,
    executor: Any = None,
    judge: Any = None,
    **kwargs,
) -> list[float]:
    """Compute reward based on LLM-judged relevance of results.

    Args:
        completions: List of completion groups containing QuerySpec JSON
        prompts: Original prompts (may contain query in system message format)
        queries: Direct query strings (preferred if available)
        executor: ArangoDB executor instance
        judge: LLM judge instance
        **kwargs: Additional args from TRL trainer

    Returns:
        List of reward scores, one per completion

    Reward scale:
        -1.0: Invalid QuerySpec or execution failure
         0.0: No results or completely irrelevant
         0.0-2.0: Scaled by LLM relevance score
    """
    if executor is None:
        executor = get_executor()
    if judge is None:
        judge = get_judge()

    # Extract queries from prompts if not provided directly
    if queries is None and prompts is not None:
        queries = []
        for prompt in prompts:
            # Extract user query from prompt
            if isinstance(prompt, str):
                import re
                # Try JSON chat template format first
                m = re.search(r'"role"\s*:\s*"user"\s*,\s*"content"\s*:\s*"(.*?)"', prompt, re.DOTALL)
                if not m:
                    # Fallback to plain text format
                    m = re.search(r'(?:^|\n)(?:user|human)\s*:\s*(.*?)(?:\n\s*(assistant|system)|$)', prompt, re.IGNORECASE | re.DOTALL)
                queries.append(m.group(1).strip() if m else "")
            elif isinstance(prompt, list):
                # Find user message
                for msg in prompt:
                    if msg.get("role") == "user":
                        queries.append(msg.get("content", ""))
                        break
                else:
                    queries.append("")
            else:
                queries.append("")

    scores = []

    for i, completion in enumerate(completions):
        # Get query for this completion
        query = queries[i] if queries and i < len(queries) else ""

        # Extract QuerySpec from completion
        if isinstance(completion, list) and len(completion) > 0:
            content = completion[0].get("content", "")
        elif isinstance(completion, dict):
            content = completion.get("content", "")
        elif isinstance(completion, str):
            content = completion
        else:
            scores.append(-1.0)
            continue

        # Parse QuerySpec
        spec = QuerySpec.from_json(content)
        if spec is None:
            scores.append(-1.0)
            continue

        # Handle non-QUERY actions
        if spec.action in ("NO_MATCH", "CLARIFY"):
            # These don't have results to judge
            scores.append(0.5)  # Neutral
            continue

        # Execute query
        try:
            results = executor.execute(spec)
        except Exception as e:
            logger.warning(f"Execution failed: {e}")
            scores.append(-1.0)
            continue

        if not results:
            scores.append(0.0)
            continue

        # Get LLM relevance score
        relevance = judge.score(query, results)

        # Scale to reward range (0.0 to 2.0)
        reward = relevance * 2.0
        scores.append(reward)

    return scores


def relevance_reward_weighted(
    completions: list[list[dict]],
    weight: float = 0.4,
    **kwargs,
) -> list[float]:
    """Relevance reward with configurable weight."""
    raw_scores = relevance_reward(completions, **kwargs)
    return [score * weight for score in raw_scores]
