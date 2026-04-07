"""LLM prompt templates for question generation and validation.

All prompts loaded from /prompt-lab/prompts/*.txt files.
"""
from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    """Load a validated prompt from /prompt-lab/prompts/{name}.txt."""
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


_QUESTION_GEN_TEMPLATE = _load_prompt("review_question_generation")
_NATURALNESS_TEMPLATE = _load_prompt("review_question_naturalness")
_BRANDON_TEMPLATE = _load_prompt("review_question_brandon")
_FOLLOW_UP_TEMPLATE = _load_prompt("review_question_follow_up")
_DIFFICULTY_TEMPLATE = _load_prompt("review_question_difficulty")
_EVALUATION_TEMPLATE = _load_prompt("review_question_evaluation")


def question_generation_system(persona_name: str, persona_role: str,
                                persona_org: str, domain_keywords: list[str],
                                f36_categories: list[str],
                                category_descriptions: dict[str, str]) -> str:
    """System prompt for generating F36-grounded questions."""
    cats = "\n".join(
        f"  - {cat}: {category_descriptions.get(cat, '')}"
        for cat in f36_categories
    )
    keywords = ", ".join(domain_keywords[:15])
    return _QUESTION_GEN_TEMPLATE.format(
        persona_name=persona_name,
        persona_role=persona_role,
        persona_org=persona_org,
        keywords=keywords,
        cats=cats,
    )


def question_generation_user(count: int, difficulty_dist: dict[str, int]) -> str:
    """User prompt for generating questions."""
    dist = ", ".join(f"{n} {d}" for d, n in difficulty_dist.items())
    return f"Generate {count} questions: {dist}. Return a JSON array."


def naturalness_system() -> str:
    """System prompt for naturalness scoring."""
    return _NATURALNESS_TEMPLATE


def naturalness_user(question: str) -> str:
    """User prompt for naturalness scoring."""
    return f'Rate this question for naturalness:\n\n"{question}"'


def conversation_brandon_system(questioner_name: str, questioner_role: str,
                                 questioner_org: str) -> str:
    """System prompt for Brandon responding to persona questions."""
    return _BRANDON_TEMPLATE.format(
        questioner_name=questioner_name,
        questioner_role=questioner_role,
        questioner_org=questioner_org,
    )


def conversation_brandon_user(question: str) -> str:
    """User prompt for Brandon responding."""
    return question


def follow_up_system(questioner_name: str) -> str:
    """System prompt for evaluating whether a follow-up is needed."""
    return _FOLLOW_UP_TEMPLATE.format(questioner_name=questioner_name)


def follow_up_user(original_question: str, brandon_response: str) -> str:
    """User prompt for follow-up evaluation."""
    return f"""Original question: {original_question}

Brandon's response: {brandon_response}

Evaluate this response."""


def difficulty_classification_system() -> str:
    """System prompt for classifying question difficulty."""
    return _DIFFICULTY_TEMPLATE


def difficulty_classification_user(question: str) -> str:
    """User prompt for difficulty classification."""
    return f'Classify this question:\n\n"{question}"'


def response_evaluation_system() -> str:
    """System prompt for evaluating Brandon's response quality."""
    return _EVALUATION_TEMPLATE


def response_evaluation_user(question: str, response: str) -> str:
    """User prompt for response evaluation."""
    return f"""Question: {question}

Response: {response}

Evaluate this response."""
