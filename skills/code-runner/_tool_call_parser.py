"""Fallback tool call parser for raw tool call tags.

When LLMs (especially Qwen, DeepSeek) return raw <tool_call> tags instead of
structured tool_calls in the response, this parser extracts them.

Supports multiple formats:
1. Hermes format: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
2. DeepSeek V3 format: <｜tool▁call▁begin｜>type<｜tool▁sep｜>name\n```json\n{}\n```<｜tool▁call▁end｜>
3. Generic XML: <function_call name="...">{"arg": "value"}</function_call>
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# Import json_utils from common/
_skills_dir = Path(__file__).resolve().parent.parent
_common = str(_skills_dir / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)

from json_utils import parse_json as _parse_json


@dataclass
class ParsedToolCall:
    """A parsed tool call extracted from raw text."""

    id: str
    name: str
    arguments: dict[str, Any]


def parse_tool_calls(content: str) -> tuple[str | None, list[ParsedToolCall]]:
    """Parse raw tool call tags from content.

    Args:
        content: The assistant message content that may contain raw tool call tags.

    Returns:
        (cleaned_content, tool_calls) where:
        - cleaned_content is the text with tool call tags removed (None if only tags)
        - tool_calls is a list of ParsedToolCall objects
    """
    if not content:
        return content, []

    tool_calls: list[ParsedToolCall] = []
    cleaned = content

    # Try each parser in order
    for parser_fn in [_parse_hermes, _parse_deepseek_v3, _parse_generic_xml]:
        result = parser_fn(cleaned)
        if result:
            cleaned, calls = result
            tool_calls.extend(calls)

    # Return None if content is now empty/whitespace
    if cleaned and not cleaned.strip():
        cleaned = None

    return cleaned, tool_calls


# ── Hermes Format Parser ────────────────────────────────────────────────
# <tool_call>{"name": "write_file", "arguments": {"path": "...", "content": "..."}}</tool_call>

_HERMES_PATTERN = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)


def _parse_hermes(content: str) -> tuple[str, list[ParsedToolCall]] | None:
    """Parse Hermes-style <tool_call> tags."""
    if "<tool_call>" not in content:
        return None

    calls: list[ParsedToolCall] = []
    cleaned = content

    for match in _HERMES_PATTERN.finditer(content):
        try:
            # Use json_utils.parse_json for robust parsing (handles malformed JSON)
            data = _parse_json(match.group(1))
            if not isinstance(data, dict):
                continue
            name = data.get("name", "")
            args = data.get("arguments", {})
            if isinstance(args, str):
                args = _parse_json(args)
                if not isinstance(args, dict):
                    args = {}
            if name:
                calls.append(ParsedToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                ))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Failed to parse Hermes tool call: {}", e)
            continue

    if calls:
        # Remove matched tags from content
        cleaned = _HERMES_PATTERN.sub("", content).strip()
        return cleaned, calls

    return None


# ── DeepSeek V3 Format Parser ───────────────────────────────────────────
# <｜tool▁calls▁begin｜>
# <｜tool▁call▁begin｜>function<｜tool▁sep｜>write_file
# ```json
# {"path": "...", "content": "..."}
# ```
# <｜tool▁call▁end｜>
# <｜tool▁calls▁end｜>

_DEEPSEEK_START = "<｜tool▁calls▁begin｜>"
_DEEPSEEK_PATTERN = re.compile(
    r"<｜tool▁call▁begin｜>(?P<type>.*?)<｜tool▁sep｜>(?P<name>.*?)\s*```json\s*(?P<args>.*?)\s*```\s*<｜tool▁call▁end｜>",
    re.DOTALL,
)


def _parse_deepseek_v3(content: str) -> tuple[str, list[ParsedToolCall]] | None:
    """Parse DeepSeek V3-style tool calls."""
    if _DEEPSEEK_START not in content:
        return None

    calls: list[ParsedToolCall] = []

    for match in _DEEPSEEK_PATTERN.finditer(content):
        try:
            name = match.group("name").strip()
            args_raw = match.group("args").strip()
            args = _parse_json(args_raw) if args_raw else {}
            if not isinstance(args, dict):
                args = {}
            if name:
                calls.append(ParsedToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=name,
                    arguments=args,
                ))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Failed to parse DeepSeek V3 tool call: {}", e)
            continue

    if calls:
        # Remove the entire tool_calls block
        idx = content.find(_DEEPSEEK_START)
        cleaned = content[:idx].strip() if idx > 0 else None
        return cleaned or "", calls

    return None


# ── Generic XML Format Parser ───────────────────────────────────────────
# <function_call name="write_file">{"path": "...", "content": "..."}</function_call>
# <tool name="run_command">{"command": "..."}</tool>

_GENERIC_XML_PATTERN = re.compile(
    r"<(?:function_call|tool|function)\s+name=[\"']([^\"']+)[\"']>([^<]*)</(?:function_call|tool|function)>",
    re.DOTALL,
)


def _parse_generic_xml(content: str) -> tuple[str, list[ParsedToolCall]] | None:
    """Parse generic XML-style tool/function calls."""
    if not re.search(r"<(?:function_call|tool|function)\s+name=", content):
        return None

    calls: list[ParsedToolCall] = []
    cleaned = content

    for match in _GENERIC_XML_PATTERN.finditer(content):
        try:
            name = match.group(1).strip()
            args_raw = match.group(2).strip()
            args = _parse_json(args_raw) if args_raw else {}
            if not isinstance(args, dict):
                args = {}
            if name:
                calls.append(ParsedToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=name,
                    arguments=args,
                ))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug("Failed to parse generic XML tool call: {}", e)
            continue

    if calls:
        cleaned = _GENERIC_XML_PATTERN.sub("", content).strip()
        return cleaned, calls

    return None


def to_openai_format(calls: list[ParsedToolCall]) -> list[dict[str, Any]]:
    """Convert ParsedToolCall list to OpenAI tool_calls format.

    Use this to inject parsed calls into the message structure.
    """
    return [
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments),
            },
        }
        for call in calls
    ]
