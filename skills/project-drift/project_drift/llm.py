"""Optional OpenAI-compatible LLM execution for project-drift."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx


class LLMExecutionError(RuntimeError):
    pass


def call_openai_compatible(payload: dict[str, Any], *, base_url: str | None, api_key: str | None, timeout: float = 60.0) -> dict[str, Any]:
    """Call an OpenAI-compatible /v1/chat/completions endpoint and parse JSON content."""
    base_url = (
        base_url
        or os.environ.get("PROJECT_DRIFT_LLM_BASE_URL")
        or os.environ.get("SCILLM_BASE_URL")
        or os.environ.get("SCILLM_URL")
    )
    if not base_url:
        raise LLMExecutionError("No LLM base URL configured. Set PROJECT_DRIFT_LLM_BASE_URL or pass --llm-base-url.")
    api_key = api_key or os.environ.get("PROJECT_DRIFT_LLM_API_KEY") or os.environ.get("SCILLM_API_KEY") or ""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json", "x-caller-skill": "project-drift"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        raise LLMExecutionError(f"LLM request failed: {response.status_code} {response.text[:1000]}")
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMExecutionError(f"Could not find choices[0].message.content in LLM response: {data}") from exc
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise LLMExecutionError(f"LLM content is not string or dict: {type(content).__name__}")
    text = content.strip()
    if text.startswith("```json"):
        text = text.removeprefix("```json").removesuffix("```").strip()
    elif text.startswith("```"):
        text = text.removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMExecutionError(f"LLM returned non-JSON content: {text[:1000]}") from exc
