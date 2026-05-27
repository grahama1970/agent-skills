"""F36-grounded question generation using /scillm."""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from config import (
    DEFAULT_BATCH_SIZE,
    DIFFICULTY_DISTRIBUTION,
    F36_CATEGORIES,
    PERSONAS,
    PersonaProfile,
)

SKILLS_DIR = Path(__file__).resolve().parents[1]  # .claude/skills/ (or .pi/skills/)
# scillm lives in pi-mono, find it reliably
_SCILLM_DIR = Path.home() / ".pi" / "skills" / "scillm"
if not _SCILLM_DIR.exists():
    _SCILLM_DIR = SKILLS_DIR / "scillm"  # fallback to sibling


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GeneratedQuestion:
    question: str
    difficulty: str
    f36_category: str
    domain_context: str
    persona: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# LLM-based generation
# ---------------------------------------------------------------------------

def _load_project_env() -> dict[str, str]:
    """Load .env from project root into env dict for subprocess calls."""
    env = dict(os.environ)
    # Walk up from skill dir to find project .env
    for candidate in [
        Path(__file__).resolve().parents[3] / ".env",  # embry-os/.env
        Path.home() / "workspace" / "experiments" / "embry-os" / ".env",
    ]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    env[key] = val  # .env wins — canonical source of truth
            break
    return env


def _llm_generate(system: str, user: str) -> str:
    """Call /scillm via subprocess for question generation.

    Generates in batches of 5 to stay within token limits.
    Tries Chutes.ai first, falls back to DeepSeek direct API on 429/error.
    """
    import subprocess

    combined = f"[SYSTEM]\n{system}\n\n[USER]\n{user}"

    # Provider configs: try Chutes first, then DeepSeek direct
    providers = [
        {
            "name": "chutes",
            "env_overrides": {},
            "model_flag": None,
        },
        {
            "name": "deepseek-direct",
            "env_overrides": {
                "SCILLM_API_BASE": "https://api.deepseek.com/v1",
                "SCILLM_PROXY_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
                "CHUTES_TEXT_MODEL": "deepseek-chat",
            },
            "model_flag": "deepseek-chat",
        },
    ]

    for provider in providers:
        cmd = [
            "uv", "run", "--directory", str(_SCILLM_DIR),
            "python", "batch.py", "single",
            "--json",
            "--timeout", "90",
        ]
        # Use SCILLM_DEFAULT_MODEL or explicit override
        model = provider.get("model_flag")
        if not model:
            model = os.environ.get("SCILLM_MODEL") or os.environ.get("SCILLM_DEFAULT_MODEL")
        if model:
            cmd.extend(["--model", model])
        cmd.append(combined)

        try:
            env = _load_project_env()
            env.pop("VIRTUAL_ENV", None)
            # Apply provider-specific overrides
            env.update(provider.get("env_overrides", {}))

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=str(_SCILLM_DIR),
                env=env,
            )
            if result.returncode != 0:
                stderr = result.stderr[-500:]
                if "429" in stderr or "Too Many Requests" in stderr or "EmptyContent" in stderr:
                    logger.warning(f"{provider['name']} rate limited/empty, trying next provider")
                    continue
                logger.error(f"scillm failed via {provider['name']} (rc={result.returncode}): {stderr}")
                continue
            output = result.stdout.strip()
            if output and output != "[]":
                logger.info(f"Generation succeeded via {provider['name']}")
                return output
            logger.warning(f"{provider['name']} returned empty, trying next")
            continue
        except subprocess.TimeoutExpired:
            logger.warning(f"{provider['name']} timed out, trying next provider")
            continue
        except FileNotFoundError:
            logger.error("scillm not found — cannot generate questions")
            return "[]"

    logger.error("All providers failed")
    return "[]"


def generate_questions(
    persona_key: str,
    count: int = DEFAULT_BATCH_SIZE,
    difficulty_dist: Optional[dict[str, int]] = None,
) -> list[GeneratedQuestion]:
    """Generate F36-grounded questions for a persona via /scillm.

    Args:
        persona_key: "margaret" or "jennifer"
        count: Total questions to generate
        difficulty_dist: Override difficulty distribution (default: even split)

    Returns:
        List of GeneratedQuestion objects
    """
    from prompts import question_generation_system, question_generation_user

    persona = PERSONAS.get(persona_key)
    if persona is None:
        raise ValueError(f"Unknown persona: {persona_key}")

    if difficulty_dist is None:
        # Scale default distribution to match count
        total_default = sum(DIFFICULTY_DISTRIBUTION.values())
        difficulty_dist = {
            d: max(1, round(n * count / total_default))
            for d, n in DIFFICULTY_DISTRIBUTION.items()
        }
        # Adjust to match exact count
        diff = count - sum(difficulty_dist.values())
        if diff != 0:
            key = "medium"  # Adjust medium to balance
            difficulty_dist[key] = max(1, difficulty_dist[key] + diff)

    system = question_generation_system(
        persona_name=persona.name,
        persona_role=persona.role,
        persona_org=persona.organization,
        domain_keywords=persona.domain_keywords,
        f36_categories=persona.f36_categories,
        category_descriptions=F36_CATEGORIES,
    )

    # Generate in batches of 5 to stay within max_tokens=1024
    BATCH_SIZE = 5
    all_questions: list[GeneratedQuestion] = []
    remaining = dict(difficulty_dist)

    logger.info(f"Generating {count} questions for {persona.name} ({difficulty_dist})")

    while sum(remaining.values()) > 0:
        # Build batch distribution
        batch_dist = {}
        batch_count = 0
        for diff, n in remaining.items():
            take = min(n, BATCH_SIZE - batch_count)
            if take > 0:
                batch_dist[diff] = take
                batch_count += take
            if batch_count >= BATCH_SIZE:
                break

        user = question_generation_user(batch_count, batch_dist)
        raw = _llm_generate(system, user)

        try:
            data = json.loads(raw)
            # Unwrap dict wrappers — LLMs sometimes wrap the array
            if isinstance(data, dict):
                for key in ("questions", "data", "results", "items"):
                    if key in data:
                        data = data[key]
                        break
                else:
                    if len(data) == 1:
                        val = list(data.values())[0]
                        if isinstance(val, list):
                            data = val
                    if isinstance(data, dict) and "question" in data:
                        data = [data]
            if not isinstance(data, list):
                logger.error(f"Expected list, got {type(data)}: {str(data)[:200]}")
                break

            for item in data:
                if not isinstance(item, dict) or not item.get("question"):
                    continue
                diff = item.get("difficulty", "medium")
                all_questions.append(GeneratedQuestion(
                    question=item["question"],
                    difficulty=diff,
                    f36_category=item.get("f36_category", persona.f36_categories[0]),
                    domain_context=item.get("domain_context", ""),
                    persona=persona_key,
                ))
                # Decrement remaining
                if diff in remaining and remaining[diff] > 0:
                    remaining[diff] -= 1

            logger.info(f"  batch: {len(data)} questions, total so far: {len(all_questions)}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {raw[:500]}")
            break

    logger.info(f"Generated {len(all_questions)} questions for {persona.name}")
    return all_questions


def save_questions(questions: list[GeneratedQuestion], output: Path) -> None:
    """Save generated questions to JSON file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    data = [q.to_dict() for q in questions]
    output.write_text(json.dumps(data, indent=2))
    logger.info(f"Saved {len(questions)} questions to {output}")


def load_questions(path: Path) -> list[GeneratedQuestion]:
    """Load questions from JSON file."""
    data = json.loads(path.read_text())
    return [
        GeneratedQuestion(
            question=item["question"],
            difficulty=item["difficulty"],
            f36_category=item["f36_category"],
            domain_context=item.get("domain_context", ""),
            persona=item.get("persona", ""),
        )
        for item in data
    ]
