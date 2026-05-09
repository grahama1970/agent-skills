"""Prompt payload construction for the project drift auditor."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .knowledge import claims_for_prompt
from .schema import openai_response_format
from .utils import truncate_text

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "drift_auditor.txt"


def _load_system_template() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    body_start = 0
    in_rationale = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx == 0 and stripped == "# RATIONALE (not sent to LLM)":
            in_rationale = True
            continue
        if in_rationale and (stripped.startswith("#") or not stripped):
            continue
        body_start = idx
        break
    return "\n".join(lines[body_start:]).strip()


SYSTEM_TEMPLATE = _load_system_template()

USER_TEMPLATE = """Assess project drift for this cleaned session evidence.

Window:
- source: {source}
- project: {project}
- since: {since}
- trigger: {trigger}

Cleaned evidence JSON:
{cleaned_evidence}

Return JSON only. The JSON must match the provided response_format schema. Do not include markdown or commentary.
"""


def build_messages(
    *,
    knowledge: dict[str, Any],
    cleaned: dict[str, Any],
    source: str,
    since: str | None,
    trigger: str,
) -> list[dict[str, str]]:
    system = SYSTEM_TEMPLATE.replace("{project_knowledge_claims}", claims_for_prompt(knowledge))
    user = USER_TEMPLATE.format(
        source=source,
        project=knowledge.get("project") or "unknown",
        since=since or "unspecified",
        trigger=trigger,
        cleaned_evidence=truncate_text(json.dumps(cleaned, indent=2, ensure_ascii=False), max_chars=24000),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_prompt_payload(
    *,
    model: str,
    knowledge: dict[str, Any],
    cleaned: dict[str, Any],
    source: str = "transcript",
    since: str | None = None,
    trigger: str = "manual scan",
    temperature: float = 0.0,
) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": temperature,
        "response_format": openai_response_format(),
        "messages": build_messages(
            knowledge=knowledge,
            cleaned=cleaned,
            source=source,
            since=since,
            trigger=trigger,
        ),
    }
