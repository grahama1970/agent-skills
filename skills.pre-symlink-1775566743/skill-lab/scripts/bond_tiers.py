"""Tier functions for the bond prediction cascade.

Implements the 4-tier cascade for predicting skill composition bonds:
    Tier 0:   Heuristic -- AFFINITIES dict + PRECEDES + taxonomy overlap
    Tier 0.5: Classifier -- trained on execution traces (sklearn RF on features)
    Tier 1.5: Small GPT -- trained via teacher-student loop (Qwen2.5-0.5B)
    Tier 2:   scillm teacher -- DeepSeek/Chutes for novel compositions
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from bond_types import (
    BondFeatures,
    CLASSIFIER_MODEL,
    GPT_MODEL,
    SCRIPTS_DIR,
    SKILLS_DIR,
)

# Import TierResult (with same fallback as original)
sys.path.insert(0, str(SKILLS_DIR / "common"))
try:
    from cascade import TierResult
except ImportError:
    from dataclasses import dataclass, field

    @dataclass
    class TierResult:  # type: ignore
        result: Dict[str, Any] = field(default_factory=dict)
        confidence: float = 0.0
        tier: float = -1
        source: str = ""
        latency_ms: float = 0.0
        cached: bool = False
        scope: str = ""
        task: str = ""
        prediction: str = ""
        probabilities: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tier 0: Heuristic -- from AFFINITIES + PRECEDES + composes
# ---------------------------------------------------------------------------

def tier0_heuristic(
    input_data: dict,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> TierResult | None:
    """Heuristic bond prediction from static tables."""
    features: BondFeatures = input_data["features"]

    # Strong evidence: explicit composition declared
    if features.a_composes_b or features.b_composes_a:
        return TierResult(
            result={
                "bond_type": "covalent",
                "success_probability": 0.90,
                "reason": "explicit_composes_declaration",
            },
            confidence=0.85,
            source="heuristic",
            prediction="covalent",
        )

    # Affinity-based prediction
    max_affinity = max(features.affinity_weight, features.reverse_affinity_weight)
    if max_affinity >= 0.8:
        return TierResult(
            result={
                "bond_type": "covalent",
                "success_probability": max_affinity,
                "reason": f"high_affinity={max_affinity:.2f}",
            },
            confidence=max_affinity * 0.9,
            source="heuristic",
            prediction="covalent",
        )
    elif max_affinity >= 0.5:
        return TierResult(
            result={
                "bond_type": "ionic",
                "success_probability": max_affinity * 0.8,
                "reason": f"moderate_affinity={max_affinity:.2f}",
            },
            confidence=max_affinity * 0.7,
            source="heuristic",
            prediction="ionic",
        )

    # Taxonomy overlap suggests weak bond
    if features.shared_taxonomy_tags >= 2:
        return TierResult(
            result={
                "bond_type": "van_der_waals",
                "success_probability": 0.5,
                "reason": f"taxonomy_overlap={features.shared_taxonomy_tags}",
            },
            confidence=0.4,
            source="heuristic",
            prediction="van_der_waals",
        )

    # No signal -- very low confidence, escalate
    if max_affinity > 0 or features.shared_taxonomy_tags > 0:
        return TierResult(
            result={
                "bond_type": "van_der_waals",
                "success_probability": 0.3,
                "reason": "weak_signal",
            },
            confidence=0.25,
            source="heuristic",
            prediction="van_der_waals",
        )

    # Truly no bond evidence
    return TierResult(
        result={
            "bond_type": "none",
            "success_probability": 0.1,
            "reason": "no_affinity_no_taxonomy",
        },
        confidence=0.2,
        source="heuristic",
        prediction="none",
    )


# ---------------------------------------------------------------------------
# Tier 0.5: Classifier -- sklearn RF trained on execution traces
# ---------------------------------------------------------------------------

def tier05_classifier(
    input_data: dict,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> TierResult | None:
    """Classifier-based bond prediction.

    Trained by bond_harvest.py from execution traces.
    Uses sklearn RandomForest on feature vectors.
    """
    if not CLASSIFIER_MODEL.exists():
        return None  # No model yet, skip to next tier

    try:
        import pickle
        with open(CLASSIFIER_MODEL, "rb") as f:
            model = pickle.load(f)
    except Exception:
        return None

    features: BondFeatures = input_data["features"]
    vector = [features.to_vector()]

    try:
        prediction = model.predict(vector)[0]
        probabilities = dict(zip(model.classes_, model.predict_proba(vector)[0]))
        confidence = max(probabilities.values())

        success_prob = probabilities.get("covalent", 0) * 0.9 + probabilities.get("ionic", 0) * 0.6

        return TierResult(
            result={
                "bond_type": prediction,
                "success_probability": round(success_prob, 3),
                "probabilities": {k: round(v, 3) for k, v in probabilities.items()},
                "reason": "classifier_prediction",
            },
            confidence=confidence,
            source="classifier",
            prediction=prediction,
            probabilities={k: round(v, 3) for k, v in probabilities.items()},
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 1.5: Small GPT -- local GGUF for complex bond reasoning
# ---------------------------------------------------------------------------

def tier15_gpt(
    input_data: dict,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> TierResult | None:
    """Small GPT for bond prediction.

    Trained via teacher-student loop from /scillm labels.
    Runs as GGUF model via llama-cpp-python.
    """
    if not GPT_MODEL.exists():
        return None

    try:
        from llama_cpp import Llama
    except ImportError:
        return None

    features: BondFeatures = input_data["features"]
    prompt = _build_gpt_prompt(features, input_data.get("graph"))

    try:
        llm = Llama(model_path=str(GPT_MODEL), n_ctx=2048, verbose=False)
        response = llm(
            prompt,
            max_tokens=256,
            temperature=0.1,
            stop=["```", "\n\n\n"],
        )
        text = response["choices"][0]["text"].strip()

        # Parse structured output
        result = _parse_gpt_bond_response(text)
        if result:
            return TierResult(
                result=result,
                confidence=result.get("confidence", 0.7),
                source="gpt",
                prediction=result.get("bond_type", ""),
            )
    except Exception as e:
        logger.debug("result extraction failed: {}", e)

    return None


def _build_gpt_prompt(features: BondFeatures, graph: dict | None = None) -> str:
    """Build prompt for small GPT bond prediction."""
    desc_a = ""
    desc_b = ""
    if graph:
        info_a = graph.get("skills", {}).get(features.skill_a, {})
        info_b = graph.get("skills", {}).get(features.skill_b, {})
        desc_a = str(info_a.get("description", ""))[:100]
        desc_b = str(info_b.get("description", ""))[:100]

    return f"""Predict the bond type between two skills.

Skill A: {features.skill_a}
Description A: {desc_a}
Provides A: {graph.get('skills', {}).get(features.skill_a, {}).get('provides', []) if graph else []}

Skill B: {features.skill_b}
Description B: {desc_b}
Provides B: {graph.get('skills', {}).get(features.skill_b, {}).get('provides', []) if graph else []}

Features:
- Affinity A->B: {features.affinity_weight}
- Affinity B->A: {features.reverse_affinity_weight}
- A precedes B: {features.a_precedes_b}
- A composes B: {features.a_composes_b}
- Shared taxonomy: {features.shared_taxonomy_tags}
- Co-occurrences: {features.co_occurrence_count}
- Historical success rate: {features.success_rate}

Bond types: covalent (strong/shared state), ionic (message passing), van_der_waals (coexist), none

Output JSON:
```json
{{"bond_type": "...", "success_probability": 0.XX, "confidence": 0.XX, "reason": "..."}}
```"""


def _parse_gpt_bond_response(text: str) -> dict | None:
    """Parse GPT bond prediction response."""
    try:
        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Tier 2: scillm teacher -- full LLM for novel compositions
# ---------------------------------------------------------------------------

def tier2_scillm(
    input_data: dict,
    task: str = "",
    scope: str = "",
    **kwargs,
) -> TierResult | None:
    """Scillm/Chutes teacher for bond prediction.

    Used for:
    1. Novel skill pairs with no prior data
    2. Training data generation (bootstrap phase)
    3. Shadow mode validation of local models
    """
    features: BondFeatures = input_data["features"]
    graph = input_data.get("graph")

    # Build teacher prompt
    prompt = _build_teacher_prompt(features, graph)

    try:
        result = _call_scillm(prompt)
        if result:
            return TierResult(
                result=result,
                confidence=result.get("confidence", 0.9),
                source="scillm",
                prediction=result.get("bond_type", ""),
            )
    except Exception as e:
        logger.debug("result extraction failed: {}", e)

    return None


def _build_teacher_prompt(features: BondFeatures, graph: dict | None = None) -> str:
    """Build the teacher prompt for scillm."""
    skills_context = ""
    if graph:
        for skill_name in [features.skill_a, features.skill_b]:
            info = graph.get("skills", {}).get(skill_name, {})
            skills_context += f"\n### {skill_name}\n"
            skills_context += f"Description: {info.get('description', 'unknown')}\n"
            skills_context += f"Provides: {info.get('provides', [])}\n"
            skills_context += f"Composes: {info.get('composes', [])}\n"
            skills_context += f"Taxonomy: {info.get('taxonomy', [])}\n"

    return f"""You are an expert at predicting how well two agent skills compose together.

## Skills to Analyze
{skills_context}

## Feature Data
- Empirical affinity A->B: {features.affinity_weight}
- Empirical affinity B->A: {features.reverse_affinity_weight}
- A precedes B in pipelines: {features.a_precedes_b}
- B precedes A in pipelines: {features.b_precedes_a}
- A declares composes B: {features.a_composes_b}
- B declares composes A: {features.b_composes_a}
- Shared taxonomy tags: {features.shared_taxonomy_tags}
- Historical co-occurrences: {features.co_occurrence_count}
- Historical success rate: {features.success_rate}

## Bond Types
- **covalent**: Strong bond. Skills share state/data, produce joint output. Like extractor->memory.
- **ionic**: Moderate bond. Skills pass messages but run independently. Like dogpile->extractor.
- **van_der_waals**: Weak bond. Skills can coexist in pipeline but don't directly interact.
- **none**: No meaningful bond. Skills are unrelated domains.

## Task
Predict the bond type and success probability for composing {features.skill_a} with {features.skill_b}.

Return ONLY valid JSON:
{{"bond_type": "covalent|ionic|van_der_waals|none", "success_probability": 0.0-1.0, "confidence": 0.0-1.0, "reason": "brief explanation", "optimal_order": ["{features.skill_a}", "{features.skill_b}"] or ["{features.skill_b}", "{features.skill_a}"]}}"""


def _call_scillm(prompt: str) -> dict | None:
    """Call scillm/Chutes for teacher prediction."""
    scillm_skill = SKILLS_DIR / "scillm"
    if not (scillm_skill / "run.sh").exists():
        return None

    try:
        result = subprocess.run(
            [str(scillm_skill / "run.sh"), "complete",
             "--prompt", prompt,
             "--json", "--max-tokens", "300"],
            capture_output=True, text=True, timeout=30,
            cwd=str(scillm_skill),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            return None

        text = result.stdout.strip()
        # Parse JSON from response
        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
    except Exception as e:
        logger.debug("JSON parse failed: {}", e)

    return None
