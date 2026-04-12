"""Message sanitization for LLM API calls.

Prevents protocol corruption from invalid Unicode in tool outputs or user input.
Surrogates (U+D800..U+DFFF) are invalid in UTF-8 and crash json.dumps() inside
the OpenAI SDK. They can appear via clipboard paste, file reads, or command output.

Usage:
    from common.message_utils import sanitize_messages

    # Before LLM API call
    sanitize_messages(messages)
"""
from __future__ import annotations

import re

# Surrogate code points: U+D800 to U+DFFF
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')


def sanitize_surrogates(text: str) -> str:
    """Replace lone surrogate code points with U+FFFD (replacement character).

    Surrogates are invalid in UTF-8 and will crash json.dumps(). This is a
    fast no-op when the text contains no surrogates.
    """
    if _SURROGATE_RE.search(text):
        return _SURROGATE_RE.sub('\ufffd', text)
    return text


def sanitize_messages(messages: list[dict]) -> bool:
    """Sanitize surrogate characters from all string content in a messages list.

    Walks message dicts in-place. Returns True if any surrogates were found
    and replaced, False otherwise.

    Handles:
    - String content in user/assistant/system messages
    - Tool result content
    - Multimodal content arrays with text blocks
    """
    found_surrogates = False

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        content = msg.get("content")

        # String content (most common)
        if isinstance(content, str) and _SURROGATE_RE.search(content):
            msg["content"] = _SURROGATE_RE.sub('\ufffd', content)
            found_surrogates = True

        # Multimodal content array
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and _SURROGATE_RE.search(text):
                        block["text"] = _SURROGATE_RE.sub('\ufffd', text)
                        found_surrogates = True

        # Tool call arguments (can contain surrogates from file content)
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    func = tc.get("function", {})
                    args = func.get("arguments")
                    if isinstance(args, str) and _SURROGATE_RE.search(args):
                        func["arguments"] = _SURROGATE_RE.sub('\ufffd', args)
                        found_surrogates = True

    return found_surrogates
