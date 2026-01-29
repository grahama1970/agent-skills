"""
Prompt Lab Skill - Pydantic Models and Validation
Defines response models for LLM outputs and parsing utilities.
"""
import json
from typing import List, Dict, Any, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from config import TIER0_CONCEPTUAL, TIER1_TACTICAL


class TaxonomyResponse(BaseModel):
    """Pydantic model for validating LLM taxonomy extraction responses."""

    conceptual: List[str] = Field(
        default_factory=list,
        description="Tier 0 conceptual bridge tags"
    )
    tactical: List[str] = Field(
        default_factory=list,
        description="Tier 1 tactical bridge tags"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score"
    )

    @field_validator('conceptual', mode='before')
    @classmethod
    def validate_conceptual(cls, v):
        """Filter to only valid Tier 0 tags."""
        if not isinstance(v, list):
            v = [v] if v else []
        return [tag for tag in v if tag in TIER0_CONCEPTUAL]

    @field_validator('tactical', mode='before')
    @classmethod
    def validate_tactical(cls, v):
        """Filter to only valid Tier 1 tags."""
        if not isinstance(v, list):
            v = [v] if v else []
        return [tag for tag in v if tag in TIER1_TACTICAL]


def parse_llm_response(content: str) -> Tuple[TaxonomyResponse, List[str]]:
    """
    Parse and validate LLM response.

    Args:
        content: Raw LLM response (JSON string or dict)

    Returns:
        Tuple of (validated_response, rejected_tags)
    """
    rejected = []

    # Handle dict input
    if isinstance(content, dict):
        data = content
    else:
        # Extract JSON from response (handle markdown wrapping)
        json_str = str(content)
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            data = json.loads(json_str.strip())
        except json.JSONDecodeError:
            return TaxonomyResponse(), ["PARSE_ERROR"]

    # Track rejected tags for analysis
    raw_conceptual = data.get("conceptual", [])
    raw_tactical = data.get("tactical", [])

    if isinstance(raw_conceptual, list):
        rejected.extend([t for t in raw_conceptual if t not in TIER0_CONCEPTUAL])
    if isinstance(raw_tactical, list):
        rejected.extend([t for t in raw_tactical if t not in TIER1_TACTICAL])

    # Pydantic validation filters invalid tags
    validated = TaxonomyResponse(**data)

    return validated, rejected


def parse_qra_response(content: str) -> Dict[str, Any]:
    """
    Parse QRA (Question-Reasoning-Answer) JSON response.

    Args:
        content: Raw LLM response

    Returns:
        Parsed dict with question, reasoning, answer, confidence
    """
    if isinstance(content, dict):
        return content

    json_str = str(content)
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"question": "", "reasoning": "", "answer": "", "confidence": 0}
